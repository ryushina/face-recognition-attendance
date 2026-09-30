"""Create a portable SQLite-and-samples backup or restore into a new directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import SCHEMA_VERSION
from recognition_service import MODEL_VERSION, PREPROCESSING_ID
from kiosk_settings import read_json


DATABASE_NAME = "attendance.sqlite3"
MANIFEST_NAME = "backup_manifest.json"
FORMAT_VERSION = 1


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot be completed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"Could not open SQLite database '{path}': {exc}") from exc


def _validate_database(path: Path) -> tuple[list[tuple[int, str]], list[str], list[str]]:
    connection = None
    try:
        connection = _connect_readonly(path)
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise BackupError(
                f"Database schema version {version} is unsupported; expected {SCHEMA_VERSION}."
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise BackupError(f"SQLite integrity check failed: {integrity}")
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise BackupError("SQLite foreign-key validation failed.")
        samples = [tuple(row) for row in connection.execute(
            "SELECT sample_id, image_path FROM face_samples ORDER BY sample_id"
        )]
        versions = [row[0] for row in connection.execute(
            "SELECT DISTINCT embedding_model_version FROM face_samples "
            "WHERE embedding_model_version IS NOT NULL ORDER BY 1"
        )]
        preprocessing = [row[0] for row in connection.execute(
            "SELECT DISTINCT embedding_preprocessing_id FROM face_samples "
            "WHERE embedding_preprocessing_id IS NOT NULL ORDER BY 1"
        )]
        return samples, versions, preprocessing
    except sqlite3.Error as exc:
        raise BackupError(f"Could not validate SQLite database '{path}': {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _copy_database_snapshot(source: Path, destination: Path) -> None:
    source_connection = None
    destination_connection = None
    try:
        source_connection = _connect_readonly(source)
        destination_connection = sqlite3.connect(destination)
        source_connection.backup(destination_connection)
        destination_connection.commit()
    except sqlite3.Error as exc:
        raise BackupError(f"Could not create a consistent SQLite snapshot: {exc}") from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()


def _new_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(
        prefix=f".{destination.name or 'attendance'}.staging-",
        dir=destination.parent,
    ))


def _publish_staging_directory(staging: Path, destination: Path) -> None:
    if destination.exists():
        raise BackupError(f"Destination already exists: {destination}")
    try:
        staging.rename(destination)
    except OSError as exc:
        raise BackupError(f"Could not publish completed data at '{destination}': {exc}") from exc


def _cleanup_staging(staging: Path | None) -> None:
    if staging is not None and staging.exists():
        shutil.rmtree(staging)


def create_backup(source_directory: str | Path, destination: str | Path) -> Path:
    """Snapshot the database and every referenced sample into a new folder."""
    source_root = Path(source_directory).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    source_database = source_root / DATABASE_NAME
    if not source_root.is_dir():
        raise BackupError(f"Data directory does not exist: {source_root}")
    if not source_database.is_file():
        raise BackupError(f"Attendance database does not exist: {source_database}")
    if target.exists():
        raise BackupError(f"Backup destination already exists: {target}")

    staging = _new_staging_directory(target)
    try:
        database_copy = staging / DATABASE_NAME
        _copy_database_snapshot(source_database, database_copy)
        sample_rows, model_versions, preprocessing_ids = _validate_database(database_copy)
        sample_manifest = []
        connection = sqlite3.connect(database_copy)
        try:
            for sample_id, stored_path in sample_rows:
                sample_source = Path(stored_path).expanduser()
                if not sample_source.is_absolute():
                    sample_source = source_root / sample_source
                try:
                    sample_source = sample_source.resolve(strict=True)
                except OSError as exc:
                    raise BackupError(
                        f"Referenced face sample is missing, empty, or unreadable: {stored_path}"
                    ) from exc
                if not sample_source.is_file() or sample_source.stat().st_size <= 0:
                    raise BackupError(f"Referenced face sample is missing, empty, or unreadable: {stored_path}")
                suffix = sample_source.suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                    suffix = ".jpg"
                relative_path = PurePosixPath("samples") / f"{sample_id:08d}{suffix}"
                copied_path = staging.joinpath(*relative_path.parts)
                copied_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sample_source, copied_path)
                sample_manifest.append({
                    "sample_id": sample_id,
                    "path": relative_path.as_posix(),
                    "sha256": _sha256(copied_path),
                    "size": copied_path.stat().st_size,
                })
                connection.execute(
                    "UPDATE face_samples SET image_path = ? WHERE sample_id = ?",
                    (relative_path.as_posix(), sample_id),
                )
            connection.commit()
        finally:
            connection.close()

        sample_rows, model_versions, preprocessing_ids = _validate_database(database_copy)
        if [path for _sample_id, path in sample_rows] != [
            item["path"] for item in sorted(sample_manifest, key=lambda item: item["sample_id"])
        ]:
            raise BackupError("Backup database sample paths do not match the copied samples.")
        manifest = {
            "format_version": FORMAT_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "schema_version": SCHEMA_VERSION,
            "database_sha256": _sha256(database_copy),
            "recognition_model_version": MODEL_VERSION,
            "recognition_preprocessing_id": PREPROCESSING_ID,
            "stored_embedding_model_versions": model_versions,
            "stored_preprocessing_ids": preprocessing_ids,
            "configuration": {
                "attendance_timezone": os.environ.get("ATTENDANCE_TIMEZONE") or read_json(source_root / "kiosk-settings.json").get("timezone"),
                "minimum_similarity": os.environ.get("ATTENDANCE_MINIMUM_SIMILARITY", "0.50"),
                "minimum_margin": os.environ.get("ATTENDANCE_MINIMUM_MARGIN", "0.08"),
            },
            "samples": sample_manifest,
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _publish_staging_directory(staging, target)
        return target
    except Exception:
        _cleanup_staging(staging)
        raise


def restore_backup(backup_directory: str | Path, destination: str | Path) -> Path:
    """Validate a backup and restore it into a destination that does not exist."""
    backup_root = Path(backup_directory).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if target.exists():
        raise BackupError(
            f"Restore destination already exists; choose a new, separate data directory: {target}"
        )
    if not backup_root.is_dir():
        raise BackupError(f"Backup directory does not exist: {backup_root}")
    manifest_path = backup_root / MANIFEST_NAME
    database_source = backup_root / DATABASE_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"Could not read backup manifest '{manifest_path}': {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
        raise BackupError("Backup manifest format is missing or unsupported.")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BackupError("Backup manifest schema version does not match this application.")
    if not database_source.is_file() or _sha256(database_source) != manifest.get("database_sha256"):
        raise BackupError("Backup database is missing or its checksum does not match the manifest.")

    sample_rows, model_versions, preprocessing_ids = _validate_database(database_source)
    manifest_samples = manifest.get("samples")
    if not isinstance(manifest_samples, list) or any(
        not isinstance(item, dict) or isinstance(item.get("sample_id"), bool)
        or not isinstance(item.get("sample_id"), int)
        for item in manifest_samples
    ):
        raise BackupError("Backup sample manifest is invalid.")
    samples_by_id = {item["sample_id"]: item for item in manifest_samples}
    if set(samples_by_id) != {sample_id for sample_id, _path in sample_rows}:
        raise BackupError("Backup manifest does not list every database sample.")
    if model_versions != manifest.get("stored_embedding_model_versions"):
        raise BackupError("Backup embedding model metadata does not match the database.")
    if preprocessing_ids != manifest.get("stored_preprocessing_ids"):
        raise BackupError("Backup preprocessing metadata does not match the database.")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = _new_staging_directory(target)
    try:
        shutil.copy2(database_source, staging / DATABASE_NAME)
        for sample_id, stored_path in sample_rows:
            entry = samples_by_id[sample_id]
            relative = PurePosixPath(stored_path)
            if relative.is_absolute() or ".." in relative.parts or "\\" in stored_path:
                raise BackupError(f"Unsafe sample path in backup database: {stored_path}")
            if entry.get("path") != stored_path:
                raise BackupError(f"Backup sample path metadata does not match: {stored_path}")
            try:
                backup_file = backup_root.joinpath(*relative.parts).resolve(strict=True)
            except OSError as exc:
                raise BackupError(f"Backup sample is missing or corrupt: {stored_path}") from exc
            try:
                backup_file.relative_to(backup_root)
            except ValueError as exc:
                raise BackupError(f"Backup sample escapes the backup directory: {stored_path}") from exc
            if (
                not backup_file.is_file()
                or backup_file.stat().st_size != entry.get("size")
                or _sha256(backup_file) != entry.get("sha256")
            ):
                raise BackupError(f"Backup sample is missing or corrupt: {stored_path}")
            restored_file = staging.joinpath(*relative.parts)
            restored_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, restored_file)

        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _validate_database(staging / DATABASE_NAME)
        _publish_staging_directory(staging, target)
        return target
    except Exception:
        _cleanup_staging(staging)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup_parser = commands.add_parser("backup", help="create a portable data backup")
    backup_parser.add_argument("--source-dir", required=True, type=Path)
    backup_parser.add_argument("--destination", required=True, type=Path)
    restore_parser = commands.add_parser("restore", help="restore into a new data directory")
    restore_parser.add_argument("--backup-dir", required=True, type=Path)
    restore_parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = create_backup(args.source_dir, args.destination)
        else:
            result = restore_backup(args.backup_dir, args.destination)
    except (BackupError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
