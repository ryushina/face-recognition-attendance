"""CSV export for attendance history records."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile


FIELDS = (
    "attendance_date", "occurred_at_local", "timezone_name", "student_id",
    "student_name", "similarity", "model_version", "evidence_frame_id",
)


def export_attendance_csv(records, destination: str | Path) -> Path:
    """Write UTF-8 CSV atomically, preserving names and quoted delimiters."""
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(f"CSV destination is a directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", delete=False,
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                values = record if isinstance(record, dict) else vars(record)
                writer.writerow({field: values.get(field, "") for field in FIELDS})
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        return destination
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise
