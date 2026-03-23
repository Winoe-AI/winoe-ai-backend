from __future__ import annotations

from app.services.simulations.scenario_versions_approval import approve_scenario_version
from app.services.simulations.scenario_versions_create import (
    create_initial_scenario_version,
    get_active_scenario_version,
)
from app.services.simulations.scenario_versions_defaults import (
    ensure_scenario_version_mutable,
)
from app.services.simulations.scenario_versions_lock import lock_active_scenario_for_invites
from app.services.simulations.scenario_versions_patch_service import (
    patch_scenario_version,
)
from app.services.simulations.scenario_versions_patching import (
    build_edit_audit_payload as _build_edit_audit_payload,
)
from app.services.simulations.scenario_versions_patching import (
    is_editable_scenario_status as _is_editable_scenario_status,
)
from app.services.simulations.scenario_versions_patching import (
    is_editable_simulation_status as _is_editable_simulation_status,
)
from app.services.simulations.scenario_versions_patching import (
    validate_and_normalize_merged_scenario_state as _validate_and_normalize_merged_scenario_state,
)
from app.services.simulations.scenario_versions_regeneration import (
    regenerate_active_scenario_version,
    request_scenario_regeneration,
)
from app.services.simulations.scenario_versions_update_active import (
    update_active_scenario_version,
)
from app.services.simulations.scenario_versions_validation_base import (
    parse_positive_int as _parse_positive_int,
)
from app.services.simulations.scenario_versions_validation_base import (
    raise_patch_validation_error as _raise_patch_validation_error,
)

__all__ = [
    "approve_scenario_version",
    "create_initial_scenario_version",
    "ensure_scenario_version_mutable",
    "get_active_scenario_version",
    "lock_active_scenario_for_invites",
    "patch_scenario_version",
    "regenerate_active_scenario_version",
    "request_scenario_regeneration",
    "update_active_scenario_version",
]

