"""Read attendance history with names and configured local event times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from database import Database, DatabaseError


class AttendanceHistoryError(RuntimeError):
    """Raised when local attendance history cannot be read safely."""


@dataclass(frozen=True)
class AttendanceRecord:
    attendance_id: int
    student_id: str
    student_name: str
    attendance_date: str
    occurred_at_utc: str
    occurred_at_local: str
    timezone_name: str
    similarity: float
    model_version: str
    evidence_frame_id: int


class AttendanceRepository:
    """Query stored attendance without sharing SQLite connections across calls."""

    def __init__(self, database: Database):
        self.database = database

    def list_records(
        self, *, attendance_date: str | None = None, student_id: str | None = None,
        limit: int = 1000,
    ) -> list[AttendanceRecord]:
        if attendance_date:
            try:
                parsed = date.fromisoformat(attendance_date)
            except (TypeError, ValueError) as exc:
                raise ValueError("Attendance date must use YYYY-MM-DD format.") from exc
            if parsed.isoformat() != attendance_date:
                raise ValueError("Attendance date must use YYYY-MM-DD format.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise ValueError("Attendance history limit must be between 1 and 10000.")
        normalized_id = student_id.strip() if isinstance(student_id, str) else None
        if not normalized_id:
            normalized_id = None

        clauses = []
        parameters = []
        if attendance_date:
            clauses.append("a.attendance_date = ?")
            parameters.append(attendance_date)
        if normalized_id:
            clauses.append("a.student_id = ?")
            parameters.append(normalized_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            "SELECT a.attendance_id, a.student_id, a.attendance_date, "
            "a.occurred_at_utc, a.timezone_name, a.similarity, a.model_version, "
            "a.evidence_frame_id, s.first_name, s.middle_name, s.last_name "
            "FROM attendance a JOIN students s ON s.student_id = a.student_id"
            + where
            + " ORDER BY a.attendance_date DESC, a.occurred_at_utc DESC, a.attendance_id DESC LIMIT ?"
        )
        parameters.append(limit)
        connection = None
        try:
            connection = self.database.connect()
            rows = connection.execute(sql, parameters).fetchall()
            records = []
            for row in rows:
                utc_value = datetime.fromisoformat(
                    row["occurred_at_utc"].replace("Z", "+00:00")
                )
                local_value = utc_value.astimezone(ZoneInfo(row["timezone_name"]))
                name = " ".join(filter(None, (
                    row["first_name"], row["middle_name"], row["last_name"]
                )))
                records.append(AttendanceRecord(
                    attendance_id=row["attendance_id"],
                    student_id=row["student_id"],
                    student_name=name,
                    attendance_date=row["attendance_date"],
                    occurred_at_utc=row["occurred_at_utc"],
                    occurred_at_local=local_value.isoformat(timespec="seconds"),
                    timezone_name=row["timezone_name"],
                    similarity=row["similarity"],
                    model_version=row["model_version"],
                    evidence_frame_id=row["evidence_frame_id"],
                ))
            return records
        except (DatabaseError, OSError, ValueError, KeyError) as exc:
            raise AttendanceHistoryError(f"Could not read attendance history: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
