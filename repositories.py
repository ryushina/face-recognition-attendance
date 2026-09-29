"""Parameterized persistence operations for students and face samples."""

from __future__ import annotations

import sqlite3
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from database import Database, DatabaseError


class StudentValidationError(ValueError):
    """Raised when student details or sample files fail validation."""


class DuplicateStudentError(ValueError):
    """Raised when a student ID is already registered."""


class StudentRepositoryError(RuntimeError):
    """Raised when a student or sample cannot be persisted."""


@dataclass(frozen=True)
class FaceSampleRecord:
    sample_id: int
    student_id: str
    image_path: str
    created_at: str
    embedding: bytes | None = None
    embedding_dimension: int | None = None
    embedding_model_version: str | None = None
    embedding_preprocessing_id: str | None = None


@dataclass(frozen=True)
class StudentRecord:
    student_id: str
    first_name: str
    middle_name: str | None
    last_name: str
    guardian_full_name: str | None
    guardian_phone: str | None
    created_at: str
    enrollment_status: str
    enrollment_error: str | None
    samples: tuple[FaceSampleRecord, ...]


class StudentRepository:
    """Store and query student registration data using one DB connection per call."""

    def __init__(self, database: Database, data_dir: str | Path | None = None):
        self.database = database
        self.data_dir = Path(data_dir or database.path.parent).expanduser().resolve()

    def create_student(
        self,
        student_id: str,
        first_name: str,
        last_name: str,
        sample_paths: Iterable[str | Path],
        *,
        middle_name: str | None = None,
        guardian_full_name: str | None = None,
        guardian_phone: str | None = None,
        enrollment_status: str = "pending",
        allow_empty_samples: bool = False,
    ) -> StudentRecord:
        """Validate details/files and atomically insert a student and its samples."""
        values = self._validate_student_fields(
            student_id,
            first_name,
            last_name,
            middle_name,
            guardian_full_name,
            guardian_phone,
            enrollment_status,
        )
        normalized_samples = self._validate_sample_paths(
            sample_paths, allow_empty=allow_empty_samples
        )

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO students (
                    student_id, first_name, middle_name, last_name,
                    guardian_full_name, guardian_phone, enrollment_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            for stored_path in normalized_samples:
                connection.execute(
                    """
                    INSERT INTO face_samples (student_id, image_path)
                    VALUES (?, ?)
                    """,
                    (values[0], stored_path),
                )
            row = connection.execute(
                "SELECT * FROM students WHERE student_id = ?", (values[0],)
            ).fetchone()
            student = self._to_student(connection, row)
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            if "students.student_id" in str(exc):
                raise DuplicateStudentError(
                    f"Student ID {values[0]!r} is already registered."
                ) from exc
            if "face_samples.image_path" in str(exc):
                raise StudentRepositoryError(
                    "A captured image is already linked to another student."
                ) from exc
            raise StudentRepositoryError(
                f"The student record violates a database constraint: {exc}"
            ) from exc
        except (sqlite3.Error, DatabaseError) as exc:
            connection.rollback()
            raise StudentRepositoryError(
                f"Could not save student {values[0]!r}: {exc}"
            ) from exc
        finally:
            connection.close()

        return student

    def get_student(self, student_id: str) -> StudentRecord | None:
        """Return a student and associated sample rows, or None when not found."""
        normalized_id = self._validate_student_id(student_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM students WHERE student_id = ?", (normalized_id,)
            ).fetchone()
            return None if row is None else self._to_student(connection, row)
        except (sqlite3.Error, DatabaseError) as exc:
            raise StudentRepositoryError(
                f"Could not load student {normalized_id!r}: {exc}"
            ) from exc
        finally:
            connection.close()

    def list_students(self) -> list[StudentRecord]:
        """Return students in stable ID order, including their samples."""
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM students ORDER BY student_id"
            ).fetchall()
            return [self._to_student(connection, row) for row in rows]
        except (sqlite3.Error, DatabaseError) as exc:
            raise StudentRepositoryError(f"Could not list students: {exc}") from exc
        finally:
            connection.close()

    def get_samples(self, student_id: str) -> list[FaceSampleRecord]:
        """Return samples associated with the requested student ID."""
        normalized_id = self._validate_student_id(student_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM face_samples
                WHERE student_id = ?
                ORDER BY sample_id
                """,
                (normalized_id,),
            ).fetchall()
            return [self._to_sample(row) for row in rows]
        except (sqlite3.Error, DatabaseError) as exc:
            raise StudentRepositoryError(
                f"Could not load samples for student {normalized_id!r}: {exc}"
            ) from exc
        finally:
            connection.close()

    def begin_indexing(self, student_id: str) -> tuple[FaceSampleRecord, ...]:
        """Hide the student from the gallery while a complete index is built."""
        normalized_id = self._validate_student_id(student_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE students SET enrollment_status = 'indexing', enrollment_error = NULL "
                "WHERE student_id = ?",
                (normalized_id,),
            )
            if cursor.rowcount != 1:
                raise StudentValidationError(f"Student {normalized_id!r} was not found.")
            rows = connection.execute(
                "SELECT * FROM face_samples WHERE student_id = ? ORDER BY sample_id",
                (normalized_id,),
            ).fetchall()
            connection.commit()
            return tuple(self._to_sample(row) for row in rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete_indexing(self, student_id: str, embeddings: dict[int, object]) -> int:
        """Atomically save every compatible feature then publish the student."""
        normalized_id = self._validate_student_id(student_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT sample_id FROM face_samples WHERE student_id = ? ORDER BY sample_id",
                (normalized_id,),
            ).fetchall()
            sample_ids = {row["sample_id"] for row in rows}
            if not sample_ids or sample_ids != set(embeddings):
                raise StudentRepositoryError(
                    "Embedding set does not cover every saved sample; student remains pending."
                )
            prepared = []
            metadata = None
            for sample_id in sorted(sample_ids):
                item = embeddings[sample_id]
                vector = tuple(float(value) for value in item.vector)
                current_metadata = (
                    item.model_version,
                    item.preprocessing_id,
                    len(vector),
                )
                if (
                    len(vector) != 128
                    or not all(math.isfinite(value) for value in vector)
                    or not math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, abs_tol=0.02)
                ):
                    raise StudentRepositoryError("An embedding is invalid or not normalized.")
                if metadata is None:
                    metadata = current_metadata
                elif current_metadata != metadata:
                    raise StudentRepositoryError("Embedding model versions do not match.")
                prepared.append((struct.pack("<128f", *vector), *current_metadata, sample_id))

            connection.executemany(
                "UPDATE face_samples SET embedding = ?, embedding_model_version = ?, "
                "embedding_preprocessing_id = ?, embedding_dimension = ? "
                "WHERE sample_id = ? AND student_id = ?",
                [(blob, version, preprocessing, dimension, sample_id, normalized_id)
                 for blob, version, preprocessing, dimension, sample_id in prepared],
            )
            connection.execute(
                "UPDATE students SET enrollment_status = 'ready', enrollment_error = NULL "
                "WHERE student_id = ?",
                (normalized_id,),
            )
            connection.commit()
            return len(prepared)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fail_indexing(self, student_id: str, message: str) -> None:
        """Keep samples retryable and report a bounded indexing failure."""
        normalized_id = self._validate_student_id(student_id)
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE students SET enrollment_status = 'failed', enrollment_error = ? "
                "WHERE student_id = ?",
                (str(message)[:500], normalized_id),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StudentRepositoryError(f"Could not record indexing failure: {exc}") from exc
        finally:
            connection.close()

    def load_compatible_gallery(self, model_version: str, preprocessing_id: str) -> list[dict]:
        """Return only ready students whose every sample has compatible valid bytes."""
        connection = self._connect()
        try:
            students = connection.execute(
                "SELECT * FROM students WHERE enrollment_status = 'ready' ORDER BY student_id"
            ).fetchall()
            gallery = []
            for student in students:
                rows = connection.execute(
                    "SELECT * FROM face_samples WHERE student_id = ? ORDER BY sample_id",
                    (student["student_id"],),
                ).fetchall()
                if not rows:
                    continue
                if any(
                    row["embedding"] is None
                    or row["embedding_dimension"] != 128
                    or row["embedding_model_version"] != model_version
                    or row["embedding_preprocessing_id"] != preprocessing_id
                    or len(row["embedding"]) != 128 * 4
                    for row in rows
                ):
                    continue
                gallery.append({
                    "student_id": student["student_id"],
                    "name": " ".join(filter(None, (
                        student["first_name"], student["middle_name"], student["last_name"]
                    ))),
                    "embeddings": tuple(struct.unpack("<128f", row["embedding"]) for row in rows),
                })
            return gallery
        except sqlite3.Error as exc:
            raise StudentRepositoryError(f"Could not load recognition gallery: {exc}") from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            return self.database.connect()
        except DatabaseError as exc:
            raise StudentRepositoryError(str(exc)) from exc

    @staticmethod
    def _validate_student_id(student_id: str) -> str:
        if not isinstance(student_id, str) or not student_id.strip():
            raise StudentValidationError("Student ID is required.")
        return student_id.strip()

    @classmethod
    def _validate_student_fields(
        cls,
        student_id,
        first_name,
        last_name,
        middle_name,
        guardian_full_name,
        guardian_phone,
        enrollment_status,
    ) -> tuple[str, str, str | None, str, str | None, str | None, str]:
        normalized_id = cls._validate_student_id(student_id)
        if not isinstance(first_name, str) or not first_name.strip():
            raise StudentValidationError("First name is required.")
        if not isinstance(last_name, str) or not last_name.strip():
            raise StudentValidationError("Last name is required.")
        if not isinstance(enrollment_status, str) or not enrollment_status.strip():
            raise StudentValidationError("Enrollment status is required.")

        for field_name, value in (
            ("middle name", middle_name),
            ("guardian full name", guardian_full_name),
            ("guardian phone", guardian_phone),
        ):
            if value is not None and not isinstance(value, str):
                raise StudentValidationError(f"{field_name.title()} must be text or empty.")

        return (
            normalized_id,
            first_name.strip(),
            middle_name,
            last_name.strip(),
            guardian_full_name,
            guardian_phone,
            enrollment_status.strip(),
        )

    def _validate_sample_paths(
        self, sample_paths: Iterable[str | Path], *, allow_empty: bool
    ) -> tuple[str, ...]:
        if sample_paths is None:
            raise StudentValidationError("At least one existing face sample is required.")
        if isinstance(sample_paths, (str, bytes, Path)):
            sample_paths = (sample_paths,)

        try:
            paths = tuple(sample_paths)
        except TypeError as exc:
            raise StudentValidationError("Face samples must be a list of image paths.") from exc

        if not paths and not allow_empty:
            raise StudentValidationError("At least one existing face sample is required.")

        stored_paths = []
        for raw_path in paths:
            try:
                path = Path(raw_path).expanduser()
                if not path.is_absolute():
                    path = self.data_dir / path
                resolved = path.resolve(strict=True)
            except (TypeError, OSError, RuntimeError) as exc:
                raise StudentValidationError(
                    f"Face sample path {raw_path!r} does not exist or cannot be read."
                ) from exc

            if not resolved.is_file():
                raise StudentValidationError(
                    f"Face sample path {raw_path!r} is not a file."
                )
            try:
                if resolved.stat().st_size <= 0:
                    raise StudentValidationError(
                        f"Face sample file {raw_path!r} is empty."
                    )
            except OSError as exc:
                raise StudentValidationError(
                    f"Face sample file {raw_path!r} cannot be read."
                ) from exc

            try:
                stored_path = resolved.relative_to(self.data_dir).as_posix()
            except ValueError:
                stored_path = resolved.as_posix()
            stored_paths.append(stored_path)

        if len(set(stored_paths)) != len(stored_paths):
            raise StudentValidationError("The same face sample was supplied more than once.")
        return tuple(stored_paths)

    @classmethod
    def _to_student(cls, connection, row) -> StudentRecord:
        samples = connection.execute(
            """
            SELECT *
            FROM face_samples
            WHERE student_id = ?
            ORDER BY sample_id
            """,
            (row["student_id"],),
        ).fetchall()
        return StudentRecord(
            student_id=row["student_id"],
            first_name=row["first_name"],
            middle_name=row["middle_name"],
            last_name=row["last_name"],
            guardian_full_name=row["guardian_full_name"],
            guardian_phone=row["guardian_phone"],
            created_at=row["created_at"],
            enrollment_status=row["enrollment_status"],
            enrollment_error=row["enrollment_error"],
            samples=tuple(cls._to_sample(sample) for sample in samples),
        )

    @staticmethod
    def _to_sample(row) -> FaceSampleRecord:
        return FaceSampleRecord(
            sample_id=row["sample_id"],
            student_id=row["student_id"],
            image_path=row["image_path"],
            created_at=row["created_at"],
            embedding=row["embedding"],
            embedding_dimension=row["embedding_dimension"],
            embedding_model_version=row["embedding_model_version"],
            embedding_preprocessing_id=row["embedding_preprocessing_id"],
        )
