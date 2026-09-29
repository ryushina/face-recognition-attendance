"""Submit an enrollment session through the student repository."""

from __future__ import annotations

from enrollment_session import EnrollmentSession
from repositories import (
    DuplicateStudentError,
    StudentRepository,
    StudentRepositoryError,
    StudentValidationError,
)


MIN_ENROLLMENT_SAMPLES = 3


def submit_enrollment(
    session: EnrollmentSession,
    repository: StudentRepository | None,
    details: dict[str, str],
    *,
    minimum_samples: int = MIN_ENROLLMENT_SAMPLES,
) -> tuple[bool, str]:
    """Persist all enrollment fields and samples, preserving pending files on error."""
    if session is None:
        return False, "No active enrollment session. Reopen student registration and try again."
    if session.submitted:
        return False, "This enrollment has already been submitted."
    session.update_details(details)
    if session.accepted_count < minimum_samples:
        return False, (
            f"Capture at least {minimum_samples} suitable face images before submitting; "
            f"{session.accepted_count} accepted."
        )
    if repository is None:
        return False, "Student storage is unavailable. Check the local database and try again."

    values = session.form_details
    try:
        repository.create_student(
            student_id=values.get("user_id", ""),
            first_name=values.get("first_name", ""),
            middle_name=values.get("middle_name") or None,
            last_name=values.get("last_name", ""),
            guardian_full_name=values.get("guardian_fullname") or None,
            guardian_phone=values.get("guardian_phone") or None,
            sample_paths=tuple(session.sample_paths),
            enrollment_status="pending",
        )
    except DuplicateStudentError as exc:
        return False, str(exc)
    except StudentValidationError as exc:
        return False, str(exc)
    except StudentRepositoryError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Could not save this student: {exc}"

    session.mark_submitted()
    return True, f"Student {values.get('user_id', '').strip()} registered; recognition indexing is pending."
