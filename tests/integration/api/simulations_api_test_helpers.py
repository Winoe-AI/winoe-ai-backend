import pytest
from sqlalchemy import select
from app.api.dependencies.github_native import get_github_client
from app.api.dependencies.notifications import get_email_service
from app.domains import CandidateSession
from app.integrations.github.client import GithubError
from app.integrations.github.workspaces.workspace import Workspace, WorkspaceGroup
from app.integrations.notifications.email_provider import MemoryEmailProvider
from app.services.email import EmailService
from tests.factories import create_recruiter, create_simulation

__all__ = [name for name in globals() if not name.startswith("__")]
