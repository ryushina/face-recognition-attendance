"""SQLite schema and connection setup for local attendance data."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 3
DEFAULT_DATABASE_NAME = "attendance.sqlite3"


class DatabaseError(RuntimeError):
    """Raised when the local database cannot be opened or initialized."""


class UnsupportedSchemaVersion(DatabaseError):
    """Raised when a database was created by a newer application version."""


class Database:
    """Open thread-owned SQLite connections and initialize the local schema."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def from_config(cls, config):
        """Use the configured writable data directory without creating it."""
        return cls(config.data_dir / DEFAULT_DATABASE_NAME)

    def connect(self) -> sqlite3.Connection:
        """Return a new connection with foreign-key checks enabled."""
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            if enabled != 1:
                raise DatabaseError("SQLite foreign-key enforcement could not be enabled.")
            return connection
        except (sqlite3.Error, OSError) as exc:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            raise DatabaseError(
                f"Could not open SQLite database '{self.path}': {exc}"
            ) from exc

    def initialize(self) -> int:
        """Create or migrate the local schema atomically."""
        connection = self.connect()
        try:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version > SCHEMA_VERSION:
                raise UnsupportedSchemaVersion(
                    f"Database schema version {current_version} is newer than "
                    f"this application supports (version {SCHEMA_VERSION})."
                )

            if current_version == SCHEMA_VERSION:
                return current_version

            connection.execute("BEGIN IMMEDIATE")
            try:
                if current_version == 0:
                    self._create_schema(connection)
                    connection.execute("PRAGMA user_version = 1")
                    current_version = 1
                if current_version < 2:
                    self._migrate_embeddings(connection)
                    connection.execute("PRAGMA user_version = 2")
                    current_version = 2
                if current_version < 3:
                    self._migrate_attendance(connection)
                    connection.execute("PRAGMA user_version = 3")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return SCHEMA_VERSION
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Could not initialize SQLite database '{self.path}': {exc}"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        """Create the initial student and face-sample tables and indexes."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY
                    CHECK (length(trim(student_id)) > 0),
                first_name TEXT NOT NULL,
                middle_name TEXT,
                last_name TEXT NOT NULL,
                guardian_full_name TEXT,
                guardian_phone TEXT,
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                enrollment_status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS face_samples (
                sample_id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                image_path TEXT NOT NULL UNIQUE
                    CHECK (length(trim(image_path)) > 0),
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                FOREIGN KEY (student_id)
                    REFERENCES students (student_id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_face_samples_student_id
                ON face_samples (student_id)
            """
        )

    @staticmethod
    def _migrate_embeddings(connection: sqlite3.Connection) -> None:
        """Add versioned feature storage without touching existing sample rows."""
        connection.execute("ALTER TABLE face_samples ADD COLUMN embedding BLOB")
        connection.execute("ALTER TABLE face_samples ADD COLUMN embedding_dimension INTEGER")
        connection.execute("ALTER TABLE face_samples ADD COLUMN embedding_model_version TEXT")
        connection.execute("ALTER TABLE face_samples ADD COLUMN embedding_preprocessing_id TEXT")
        connection.execute("ALTER TABLE students ADD COLUMN enrollment_error TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_students_enrollment_status "
            "ON students (enrollment_status)"
        )

    @staticmethod
    def _migrate_attendance(connection: sqlite3.Connection) -> None:
        """Add once-per-student-local-day attendance records."""
        connection.execute(
            """
            CREATE TABLE attendance (
                attendance_id INTEGER PRIMARY KEY,
                student_id TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                timezone_name TEXT NOT NULL,
                similarity REAL NOT NULL,
                model_version TEXT NOT NULL,
                evidence_frame_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE (student_id, attendance_date),
                FOREIGN KEY (student_id)
                    REFERENCES students (student_id)
                    ON UPDATE CASCADE
                    ON DELETE RESTRICT,
                CHECK (length(attendance_date) = 10),
                CHECK (evidence_frame_id >= 0)
            )
            """
        )
        connection.execute(
            "CREATE INDEX idx_attendance_date_student "
            "ON attendance (attendance_date, student_id)"
        )
