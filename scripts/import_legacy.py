"""Preview or explicitly import legacy users.txt rows into SQLite."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import AppConfig
from database import Database
from repositories import (
    DuplicateStudentError,
    StudentRepository,
    StudentRepositoryError,
    StudentValidationError,
)


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}


class LegacyImportError(RuntimeError):
    """Raised when the source CSV cannot be parsed safely."""


@dataclass(frozen=True)
class ImportCandidate:
    line_number: int
    student_id: str
    first_name: str
    middle_name: str | None
    last_name: str
    guardian_full_name: str | None
    guardian_phone: str | None
    photo_dir: str
    sample_paths: tuple[Path, ...]
    message: str


@dataclass(frozen=True)
class ImportResult:
    line_number: int
    student_id: str | None
    status: str
    message: str
    sample_count: int = 0


@dataclass(frozen=True)
class ImportReport:
    source: Path
    dry_run: bool
    results: tuple[ImportResult, ...]


def _read_candidates(source: Path, photo_root: Path):
    try:
        source_file = source.open("r", newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise LegacyImportError(f"Cannot read legacy users file '{source}': {exc}") from exc

    candidates: list[ImportCandidate | ImportResult] = []
    seen_ids: set[str] = set()
    try:
        with source_file:
            reader = csv.DictReader(source_file)
            fieldnames = {
                name.strip().casefold()
                for name in (reader.fieldnames or [])
                if name and name.strip()
            }
            id_field = "user_id" if "user_id" in fieldnames else "student_id"
            if id_field not in fieldnames or "first_name" not in fieldnames or "last_name" not in fieldnames:
                raise LegacyImportError(
                    "Legacy CSV must have user_id (or student_id), first_name, "
                    "and last_name columns."
                )

            for line_number, row in enumerate(reader, start=2):
                if row is None:
                    candidates.append(
                        ImportResult(line_number, None, "malformed", "Empty CSV row.")
                    )
                    continue

                if None in row:
                    candidates.append(
                        ImportResult(
                            line_number,
                            (row.get(id_field) or "").strip() or None,
                            "malformed",
                            "Row has more values than the header columns.",
                        )
                    )
                    continue

                normalized = {
                    (key.strip().casefold() if key else ""): value
                    for key, value in row.items()
                }
                student_id = (normalized.get(id_field) or "").strip()
                first_name = (normalized.get("first_name") or "").strip()
                middle_name = normalized.get("middle_name") or None
                last_name = (normalized.get("last_name") or "").strip()
                guardian_full_name = (
                    normalized.get("guardian_full_name")
                    or normalized.get("guardian_fullname")
                    or None
                )
                guardian_phone = normalized.get("guardian_phone") or None
                photo_dir = (normalized.get("photo_dir") or "").strip()

                missing = []
                if not student_id:
                    missing.append("user_id")
                if not first_name:
                    missing.append("first_name")
                if not last_name:
                    missing.append("last_name")
                if missing:
                    candidates.append(
                        ImportResult(
                            line_number,
                            student_id or None,
                            "malformed",
                            "Missing required field(s): " + ", ".join(missing) + ".",
                        )
                    )
                    continue

                if student_id in seen_ids:
                    candidates.append(
                        ImportResult(
                            line_number,
                            student_id,
                            "duplicate-source",
                            "This ID already appeared earlier in the source file.",
                        )
                    )
                    continue
                seen_ids.add(student_id)

                image_directory = None
                sample_paths: tuple[Path, ...] = ()
                if photo_dir:
                    image_directory = Path(photo_dir).expanduser()
                    if not image_directory.is_absolute():
                        image_directory = photo_root / image_directory
                    image_directory = image_directory.resolve()

                if image_directory is None:
                    message = "No photo directory is listed; student remains pending enrollment."
                elif not image_directory.is_dir():
                    message = (
                        f"Photo directory is missing: {image_directory}; "
                        "student remains pending enrollment."
                    )
                else:
                    try:
                        sample_paths = tuple(
                            path.resolve()
                            for path in sorted(image_directory.iterdir())
                            if path.is_file()
                            and path.suffix.casefold() in IMAGE_EXTENSIONS
                            and path.stat().st_size > 0
                        )
                    except OSError as exc:
                        message = (
                            f"Cannot inspect photo directory {image_directory}: {exc}; "
                            "student remains pending enrollment."
                        )
                    else:
                        if sample_paths:
                            message = (
                                f"Found {len(sample_paths)} image file(s); "
                                "student remains pending recognition indexing."
                            )
                        else:
                            message = (
                                f"No usable image files found in {image_directory}; "
                                "student remains pending enrollment."
                            )

                candidates.append(
                    ImportCandidate(
                        line_number=line_number,
                        student_id=student_id,
                        first_name=first_name,
                        middle_name=middle_name,
                        last_name=last_name,
                        guardian_full_name=guardian_full_name,
                        guardian_phone=guardian_phone,
                        photo_dir=photo_dir,
                        sample_paths=sample_paths,
                        message=message,
                    )
                )
    except (csv.Error, UnicodeError, OSError) as exc:
        raise LegacyImportError(f"Could not parse legacy users file '{source}': {exc}") from exc

    return candidates


def _existing_ids_read_only(database: Database) -> set[str]:
    """Read IDs from an existing database without creating or migrating it."""
    if not database.path.is_file():
        return set()

    uri = database.path.as_uri() + "?mode=ro"
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'students'"
        ).fetchone()
        if table is None:
            return set()
        return {
            row[0]
            for row in connection.execute("SELECT student_id FROM students")
        }
    except sqlite3.Error as exc:
        raise LegacyImportError(
            f"Cannot inspect existing database '{database.path}': {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def run_import(
    source: str | Path,
    database: Database,
    *,
    photo_root: str | Path | None = None,
    data_dir: str | Path | None = None,
    apply: bool = False,
) -> ImportReport:
    """Preview by default; write only when explicitly called with apply=True."""
    source_path = Path(source).expanduser().resolve()
    photo_root_path = Path(photo_root or source_path.parent).expanduser().resolve()
    candidates = _read_candidates(source_path, photo_root_path)

    if apply:
        target_data_dir = Path(data_dir or database.path.parent).expanduser().resolve()
        target_data_dir.mkdir(parents=True, exist_ok=True)
        database.initialize()
        repository = StudentRepository(database, target_data_dir)
        existing_ids = {student.student_id for student in repository.list_students()}
    else:
        repository = None
        existing_ids = _existing_ids_read_only(database)

    results: list[ImportResult] = []
    for candidate in candidates:
        if isinstance(candidate, ImportResult):
            results.append(candidate)
            continue
        if candidate.student_id in existing_ids:
            results.append(
                ImportResult(
                    candidate.line_number,
                    candidate.student_id,
                    "already-exists",
                    "Student ID is already present in SQLite; source row was skipped. "
                    + candidate.message,
                    len(candidate.sample_paths),
                )
            )
            continue

        if not apply:
            results.append(
                ImportResult(
                    candidate.line_number,
                    candidate.student_id,
                    "would-import",
                    candidate.message,
                    len(candidate.sample_paths),
                )
            )
            continue

        try:
            repository.create_student(
                student_id=candidate.student_id,
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                middle_name=candidate.middle_name,
                guardian_full_name=candidate.guardian_full_name,
                guardian_phone=candidate.guardian_phone,
                sample_paths=candidate.sample_paths,
                enrollment_status="pending",
                allow_empty_samples=True,
            )
        except DuplicateStudentError:
            status = "already-exists"
            message = "Student ID was registered while the import was running."
        except (StudentValidationError, StudentRepositoryError) as exc:
            status = "error"
            message = f"Could not import this row: {exc}"
        else:
            status = "imported"
            existing_ids.add(candidate.student_id)
            message = candidate.message

        results.append(
            ImportResult(
                candidate.line_number,
                candidate.student_id,
                status,
                message,
                len(candidate.sample_paths),
            )
        )

    return ImportReport(source_path, dry_run=not apply, results=tuple(results))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview legacy users.txt rows. The importer never reads log.txt "
            "and writes only when --apply is supplied."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT / "users.txt",
        help="legacy CSV file (default: repository-root users.txt)",
    )
    parser.add_argument(
        "--photo-root",
        type=Path,
        help="base directory for relative photo_dir values (default: source directory)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="SQLite database path (default: configured data directory)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="write eligible rows to SQLite; importing is never automatic",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview only (default)",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = AppConfig.from_environment()
    database = Database(args.database or config.data_dir / "attendance.sqlite3")
    try:
        report = run_import(
            args.source,
            database,
            photo_root=args.photo_root,
            data_dir=config.data_dir,
            apply=args.apply,
        )
    except (LegacyImportError, OSError, StudentRepositoryError) as exc:
        print(f"Import stopped: {exc}", file=sys.stderr)
        return 2

    mode = "DRY RUN: no database rows were changed" if report.dry_run else "APPLIED"
    print(f"{mode} — source: {report.source}")
    for result in report.results:
        student = f" student_id={result.student_id!r}" if result.student_id else ""
        print(
            f"line {result.line_number}:{student} {result.status} "
            f"samples={result.sample_count} — {result.message}"
        )
    print(f"Rows reviewed: {len(report.results)}")
    return 1 if any(result.status == "error" for result in report.results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
