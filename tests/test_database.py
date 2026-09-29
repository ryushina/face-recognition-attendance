"""Schema initialization and integrity checks using temporary SQLite files."""

import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from config import AppConfig
from database import (
    Database,
    SCHEMA_VERSION,
    UnsupportedSchemaVersion,
)


@contextmanager
def closing_transaction(connection_factory):
    connection = connection_factory()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class FailingDatabase(Database):
    @staticmethod
    def _create_schema(connection):
        connection.execute("CREATE TABLE partial_table (value TEXT)")
        raise RuntimeError("simulated schema creation failure")


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "attendance.sqlite3"
        self.database = Database(self.database_path)

    def insert_student(self, connection, student_id="00123456"):
        connection.execute(
            """
            INSERT INTO students (
                student_id, first_name, middle_name, last_name,
                guardian_full_name, guardian_phone
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (student_id, "Ana", "María", "Santos", "José Santos", "123-4567"),
        )

    def test_initialization_is_versioned_and_repeatable(self):
        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)

        with closing_transaction(self.database.connect) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertIn("students", tables)
            self.assertIn("face_samples", tables)
            self.assertNotIn("recognition_embeddings", tables)
            self.assertIn("attendance", tables)

    def test_text_ids_and_all_student_fields_are_stored(self):
        self.database.initialize()

        with closing_transaction(self.database.connect) as connection:
            self.insert_student(connection)
            student = connection.execute(
                "SELECT * FROM students WHERE student_id = ?", ("00123456",)
            ).fetchone()

        self.assertEqual(student["student_id"], "00123456")
        self.assertEqual(student["first_name"], "Ana")
        self.assertEqual(student["middle_name"], "María")
        self.assertEqual(student["last_name"], "Santos")
        self.assertEqual(student["guardian_full_name"], "José Santos")
        self.assertEqual(student["guardian_phone"], "123-4567")
        self.assertTrue(student["created_at"].endswith("Z"))
        self.assertEqual(student["enrollment_status"], "pending")

    def test_duplicate_student_ids_are_rejected(self):
        self.database.initialize()

        with closing_transaction(self.database.connect) as connection:
            self.insert_student(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                self.insert_student(connection)

    def test_each_connection_enforces_foreign_keys_and_sample_ownership(self):
        self.database.initialize()
        first_connection = self.database.connect()
        second_connection = self.database.connect()
        try:
            self.assertEqual(
                first_connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )
            self.assertEqual(
                second_connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )

            with self.assertRaises(sqlite3.IntegrityError):
                first_connection.execute(
                    "INSERT INTO face_samples (student_id, image_path) VALUES (?, ?)",
                    ("missing-student", "assets/missing.jpg"),
                )

            self.insert_student(first_connection)
            first_connection.execute(
                "INSERT INTO face_samples (student_id, image_path) VALUES (?, ?)",
                ("00123456", "assets/00123456/face.jpg"),
            )
            first_connection.commit()

            with self.assertRaises(sqlite3.IntegrityError):
                second_connection.execute(
                    "INSERT INTO face_samples (student_id, image_path) VALUES (?, ?)",
                    ("missing-student", "assets/other.jpg"),
                )
        finally:
            first_connection.close()
            second_connection.close()

        with closing_transaction(self.database.connect) as connection:
            sample = connection.execute("SELECT * FROM face_samples").fetchone()
            self.assertEqual(sample["student_id"], "00123456")
            self.assertEqual(sample["image_path"], "assets/00123456/face.jpg")

    def test_deleting_student_removes_owned_sample_rows(self):
        self.database.initialize()

        with closing_transaction(self.database.connect) as connection:
            self.insert_student(connection)
            connection.execute(
                "INSERT INTO face_samples (student_id, image_path) VALUES (?, ?)",
                ("00123456", "assets/00123456/face.jpg"),
            )
            connection.execute(
                "DELETE FROM students WHERE student_id = ?", ("00123456",)
            )
            sample_count = connection.execute(
                "SELECT COUNT(*) FROM face_samples"
            ).fetchone()[0]

        self.assertEqual(sample_count, 0)

    def test_schema_changes_roll_back_completely_on_failure(self):
        failing_database = FailingDatabase(self.database_path)

        with self.assertRaisesRegex(RuntimeError, "simulated schema"):
            failing_database.initialize()

        with closing_transaction(lambda: sqlite3.connect(self.database_path)) as connection:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertEqual(table_names, set())
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)

        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)

    def test_v1_database_migrates_without_losing_student_or_sample_rows(self):
        with closing_transaction(lambda: sqlite3.connect(self.database_path)) as connection:
            connection.execute("CREATE TABLE students (student_id TEXT PRIMARY KEY, first_name TEXT NOT NULL, middle_name TEXT, last_name TEXT NOT NULL, guardian_full_name TEXT, guardian_phone TEXT, created_at TEXT NOT NULL, enrollment_status TEXT NOT NULL DEFAULT 'pending')")
            connection.execute("CREATE TABLE face_samples (sample_id INTEGER PRIMARY KEY, student_id TEXT NOT NULL, image_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)")
            connection.execute("INSERT INTO students VALUES ('0007', 'Lin', NULL, 'Tan', NULL, NULL, '2026-01-01T00:00:00Z', 'pending')")
            connection.execute("INSERT INTO face_samples VALUES (1, '0007', 'assets/lin.jpg', '2026-01-01T00:00:00Z')")
            connection.execute("PRAGMA user_version = 1")

        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        with closing_transaction(self.database.connect) as connection:
            self.assertEqual(connection.execute("SELECT student_id FROM students").fetchone()[0], "0007")
            sample = connection.execute("SELECT * FROM face_samples").fetchone()
            self.assertEqual(sample["image_path"], "assets/lin.jpg")
            self.assertIsNone(sample["embedding"])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_newer_schema_version_is_preserved_and_rejected(self):
        with closing_transaction(lambda: sqlite3.connect(self.database_path)) as connection:
            connection.execute("CREATE TABLE retained_data (value TEXT)")
            connection.execute("INSERT INTO retained_data VALUES ('keep')")
            connection.execute("PRAGMA user_version = 99")

        with self.assertRaises(UnsupportedSchemaVersion):
            self.database.initialize()

        with closing_transaction(lambda: sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)
            self.assertEqual(
                connection.execute("SELECT value FROM retained_data").fetchone()[0],
                "keep",
            )

    def test_from_config_uses_data_directory_without_creating_it(self):
        data_dir = self.root / "custom-data"
        config = AppConfig.from_environment({"ATTENDANCE_DATA_DIR": str(data_dir)})

        database = Database.from_config(config)

        self.assertEqual(database.path, data_dir / "attendance.sqlite3")
        self.assertFalse(data_dir.exists())


if __name__ == "__main__":
    unittest.main()
