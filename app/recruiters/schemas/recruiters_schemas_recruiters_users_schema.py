"""Application module for recruiters schemas recruiters users schema workflows."""

from pydantic import ConfigDict

from app.shared.types.shared_types_base_model import APIModel


class UserRead(APIModel):
    """Serialized user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    companyId: int | None = None
    companyName: str | None = None
    onboardingComplete: bool = True


class RecruiterOnboardingWrite(APIModel):
    """Payload for completing recruiter onboarding."""

    name: str
    companyName: str
