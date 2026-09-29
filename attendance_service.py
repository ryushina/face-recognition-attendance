"""Timezone-explicit once-per-local-day attendance storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import Database, DatabaseError
from recognition_service import MODEL_VERSION


class TimezoneConfigError(ValueError):
    """Raised when attendance timezone is absent or invalid."""


class AttendanceError(RuntimeError):
    """Raised when an attendance decision cannot be safely recorded."""


@dataclass(frozen=True)
class AttendanceResult:
    status: str
    attendance_id: int | None
    student_id: str
    attendance_date: str
    occurred_at_utc: str | None
    timezone_name: str
    message: str


class AttendanceService:
    """Record one stable recognized student per explicitly configured local day."""

    def __init__(self, database: Database, timezone_name: str | None, *, clock=None):
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            raise TimezoneConfigError(
                "Set ATTENDANCE_TIMEZONE to the school's IANA timezone before recording attendance."
            )
        try:
            self.zone = ZoneInfo(timezone_name.strip())
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise TimezoneConfigError(
                f"Invalid IANA attendance timezone {timezone_name!r}."
            ) from exc
        self.timezone_name = timezone_name.strip()
        self.database = database
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def record(self, evidence) -> AttendanceResult:
        """Validate stable evidence and insert or return today's existing record."""
        student_id = getattr(evidence, "student_id", None)
        model_version = getattr(evidence, "model_version", None)
        score = getattr(evidence, "score", None)
        frame_id = getattr(evidence, "frame_id", None)
        if not isinstance(student_id, str) or not student_id.strip():
            raise AttendanceError("Attendance requires a recognized student identity.")
        student_id = student_id.strip()
        if model_version != MODEL_VERSION:
            raise AttendanceError("Recognition model version is incompatible with attendance evidence.")
        try:
            similarity = float(score)
            frame_id = int(frame_id)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AttendanceError("Attendance evidence is incomplete.") from exc
        if not math.isfinite(similarity) or similarity < -1.0 or similarity > 1.0 or frame_id < 0:
            raise AttendanceError("Attendance evidence contains invalid similarity or frame data.")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise AttendanceError("Attendance clock must return a timezone-aware datetime.")
        utc_now = now.astimezone(timezone.utc)
        local_date = utc_now.astimezone(self.zone).date().isoformat()
        utc_text = utc_now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        connection = None
        try:
            connection = self.database.connect()
            connection.execute("BEGIN IMMEDIATE")
            student = connection.execute(
                "SELECT enrollment_status FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            if student is None or student["enrollment_status"] != "ready":
                raise AttendanceError("Student is missing or not recognition-ready.")
            existing = connection.execute(
                "SELECT attendance_id, occurred_at_utc FROM attendance "
                "WHERE student_id = ? AND attendance_date = ?",
                (student_id, local_date),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return AttendanceResult(
                    "already_recorded", existing["attendance_id"], student_id,
                    local_date, existing["occurred_at_utc"], self.timezone_name,
                    "Attendance was already recorded for this local date.",
                )
            cursor = connection.execute(
                """
                INSERT INTO attendance (
                    student_id, attendance_date, occurred_at_utc, timezone_name,
                    similarity, model_version, evidence_frame_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (student_id, local_date, utc_text, self.timezone_name,
                 similarity, model_version, frame_id),
            )
            connection.commit()
            return AttendanceResult(
                "recorded", cursor.lastrowid, student_id, local_date,
                utc_text, self.timezone_name, "Attendance recorded.",
            )
        except AttendanceError:
            if connection is not None:
                connection.rollback()
            raise
        except (DatabaseError, OSError, Exception) as exc:
            if connection is not None:
                connection.rollback()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise AttendanceError(f"Could not record attendance: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
