"""Pending files and form state for one student enrollment attempt."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Mapping


class EnrollmentSession:
    """Own pending capture files until this enrollment is saved or cancelled."""

    def __init__(self, data_dir: str | Path, *, session_id: str | None = None):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.session_id = session_id or str(uuid.uuid4())
        # Reject path-like caller supplied IDs; session paths are always one level deep.
        if (
            not self.session_id
            or Path(self.session_id).name != self.session_id
            or self.session_id in {".", ".."}
        ):
            raise ValueError("Enrollment session ID must be a single path segment.")
        self.session_dir = (
            self.data_dir / "assets" / "enrollment_sessions" / self.session_id
        ).resolve()
        self.student_id = ""
        self.form_details: dict[str, str] = {}
        self.sample_paths: list[Path] = []
        self.capture_errors: list[str] = []
        self.submitted = False

    @property
    def accepted_count(self) -> int:
        return len(self.sample_paths)

    def update_details(self, details: Mapping[str, str]) -> bool:
        """Keep current form values; clear captures when the student ID changes."""
        if self.submitted:
            return False
        normalized = {key: (value or "").strip() for key, value in details.items()}
        new_student_id = normalized.get("user_id", "")
        identity_changed = bool(self.student_id and new_student_id != self.student_id)
        if identity_changed:
            self.clear_samples()
        self.student_id = new_student_id
        self.form_details = normalized
        return identity_changed

    def capture(
        self,
        capture_fn: Callable[[str], tuple[bool, str]],
        details: Mapping[str, str],
        *,
        filename_prefix: str = "face",
    ) -> tuple[bool, str]:
        """Run a capture into this session and retain only successful file paths."""
        if self.submitted:
            return False, "This enrollment has already been submitted."
        self.update_details(details)
        if not self.student_id:
            message = "LRN is required before capturing an image."
            self.capture_errors.append(message)
            return False, message
        try:
            success, result = capture_fn(str(self.session_dir))
        except Exception as exc:
            success, result = False, f"Image capture failed: {exc}"
        if not success:
            self.capture_errors.append(str(result))
            return False, str(result)

        path = Path(result).expanduser().resolve()
        if not self._is_owned_path(path):
            message = "Captured image path is outside this enrollment session."
            self.capture_errors.append(message)
            return False, message
        if not path.is_file() or path.stat().st_size <= 0:
            message = "The captured image was not saved as a non-empty file."
            self.capture_errors.append(message)
            return False, message
        self.sample_paths.append(path)
        self.capture_errors.clear()
        return True, str(path)

    def clear_samples(self) -> None:
        """Delete only tracked sample files within this session's own directory."""
        if self.submitted:
            return
        for path in self.sample_paths:
            resolved = path.resolve()
            if self._is_owned_path(resolved) and resolved.is_file():
                resolved.unlink()
        self.sample_paths.clear()

    def cancel(self) -> bool:
        """Remove pending session-owned files; never remove a submitted enrollment."""
        if self.submitted:
            return False
        self.clear_samples()
        try:
            if self.session_dir.is_dir():
                try:
                    self.session_dir.rmdir()
                except OSError:
                    # Leave any untracked file or directory untouched.
                    return True
                for parent in (self.session_dir.parent, self.session_dir.parent.parent):
                    try:
                        parent.rmdir()
                    except OSError:
                        break
        except OSError:
            return False
        return True

    def mark_submitted(self) -> None:
        """Protect accepted sample files from subsequent cancel/cleanup actions."""
        self.submitted = True

    def _is_owned_path(self, path: Path) -> bool:
        try:
            path.relative_to(self.session_dir)
            return True
        except ValueError:
            return False
