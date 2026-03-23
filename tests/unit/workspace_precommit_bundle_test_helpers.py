from __future__ import annotations
import json
from types import SimpleNamespace
import pytest
from app.core.errors import ApiError
from app.integrations.github.client import GithubError
from app.repositories.precommit_bundles import repository as precommit_repo
from app.repositories.precommit_bundles.models import PRECOMMIT_BUNDLE_STATUS_READY
from app.services.submissions import workspace_precommit_bundle as precommit_service
from app.services.submissions.workspace_precommit_bundle import (
    apply_precommit_bundle_if_available,
    build_precommit_commit_marker,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)
from tests.unit.workspace_precommit_bundle_branch_failure_github import (
    _BranchFailureGithub,
)
from tests.unit.workspace_precommit_bundle_stub_github_client import StubGithubClient

__all__ = [name for name in globals() if not name.startswith("__")]
