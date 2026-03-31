"""Application module for auth roles utils workflows."""

from fastapi import HTTPException, status

from app.shared.database.shared_database_models_model import User

RECRUITER_ONBOARDING_REQUIRED_DETAIL = "Recruiter onboarding required"
_MISSING = object()


def _ensure_recruiter_onboarded(user: User) -> None:
    company_id = getattr(user, "company_id", _MISSING)
    if getattr(user, "role", None) == "recruiter" and company_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=RECRUITER_ONBOARDING_REQUIRED_DETAIL,
        )


def ensure_recruiter(user: User) -> None:
    """Enforce recruiter role."""
    if getattr(user, "role", None) != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )
    _ensure_recruiter_onboarded(user)


def ensure_recruiter_or_none(user: User) -> None:
    """Allow recruiter or unset role (legacy)."""
    if getattr(user, "role", None) not in {None, "recruiter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )
    _ensure_recruiter_onboarded(user)
