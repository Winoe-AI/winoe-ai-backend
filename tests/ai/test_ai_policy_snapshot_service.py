from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai import ai_policy_snapshot_service as policy_snapshot_service
from app.ai import build_ai_policy_snapshot
from app.trials.constants.trials_constants_trials_ai_config_constants import (
    default_ai_eval_enabled_by_day,
)


def _trial() -> SimpleNamespace:
    return SimpleNamespace(
        ai_notice_version="mvp1",
        ai_notice_text="AI assistance may be used for evaluation support.",
        ai_eval_enabled_by_day={
            "1": True,
            "2": True,
            "3": True,
            "4": True,
            "5": True,
        },
    )


def test_build_ai_policy_snapshot_uses_prompt_layer_fallback_when_trial_has_no_snapshots(
    monkeypatch,
) -> None:
    def _fake_resolve_prompt_layers(**_kwargs):
        return ("resolved-instructions", "resolved-rubric")

    monkeypatch.setattr(
        policy_snapshot_service,
        "resolve_prompt_layers",
        _fake_resolve_prompt_layers,
    )

    snapshot = policy_snapshot_service.build_ai_policy_snapshot(trial=_trial())

    assert snapshot["agents"]["prestart"]["resolvedInstructionsMd"] == (
        "resolved-instructions"
    )
    assert snapshot["agents"]["prestart"]["resolvedRubricMd"] == "resolved-rubric"
    assert snapshot["agents"]["prestart"]["instructionsSha256"]
    assert snapshot["agents"]["prestart"]["rubricSha256"]


def test_get_and_require_agent_policy_snapshot_support_day23_alias() -> None:
    snapshot = {
        "agents": {
            "day23": {
                "key": "day23",
                "promptVersion": "legacy",
                "rubricVersion": "legacy",
                "runtime": {
                    "runtimeMode": "test",
                    "provider": "openai",
                    "model": "gpt",
                },
            }
        }
    }

    assert (
        policy_snapshot_service.get_agent_policy_snapshot(
            snapshot, "codeImplementationReviewer"
        )
        == snapshot["agents"]["day23"]
    )
    assert (
        policy_snapshot_service.require_agent_policy_snapshot(
            snapshot,
            "codeImplementationReviewer",
        )
        == snapshot["agents"]["day23"]
    )


def test_require_agent_runtime_rejects_missing_or_blank_runtime_fields() -> None:
    missing_runtime = {
        "agents": {
            "prestart": {
                "key": "prestart",
                "promptVersion": "1",
                "rubricVersion": "1",
            }
        }
    }
    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_missing",
    ):
        policy_snapshot_service.require_agent_runtime(missing_runtime, "prestart")

    blank_runtime = {
        "agents": {
            "prestart": {
                "key": "prestart",
                "promptVersion": "1",
                "rubricVersion": "1",
                "runtime": {
                    "runtimeMode": "test",
                    "provider": " ",
                    "model": "gpt",
                    "timeoutSeconds": 1,
                    "maxRetries": 0,
                },
            }
        }
    }
    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_provider_missing",
    ):
        policy_snapshot_service.require_agent_runtime(blank_runtime, "prestart")


def test_get_candidate_settings_from_snapshot_normalizes_partial_payloads() -> None:
    assert policy_snapshot_service.get_candidate_settings_from_snapshot(None) == (
        None,
        None,
        None,
    )
    assert policy_snapshot_service.get_candidate_settings_from_snapshot(
        {"candidateSettings": "not-a-mapping"}
    ) == (None, None, None)

    (
        notice_version,
        notice_text,
        enabled,
    ) = policy_snapshot_service.get_candidate_settings_from_snapshot(
        {
            "candidateSettings": {
                "noticeVersion": "mvp1",
                "noticeText": "hello",
                "evalEnabledByDay": {"1": True, "2": "nope", "3": False},
            }
        }
    )
    assert notice_version == "mvp1"
    assert notice_text == "hello"
    default_enabled = default_ai_eval_enabled_by_day()
    assert enabled["1"] is True
    assert enabled["2"] is default_enabled["2"]
    assert enabled["3"] is False
    assert enabled["4"] is default_enabled["4"]
    assert enabled["5"] is default_enabled["5"]


def test_validate_current_ai_policy_snapshot_contract_rejects_version_mismatches() -> (
    None
):
    snapshot = build_ai_policy_snapshot(trial=_trial())

    prompt_pack_snapshot = dict(snapshot)
    prompt_pack_snapshot["promptPackVersion"] = "legacy-pack"
    prompt_pack_digest_snapshot = dict(prompt_pack_snapshot)
    prompt_pack_digest_snapshot.pop("snapshotDigest", None)
    prompt_pack_snapshot[
        "snapshotDigest"
    ] = policy_snapshot_service.compute_ai_policy_snapshot_digest(
        prompt_pack_digest_snapshot
    )
    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_prompt_pack_version_mismatch",
    ):
        policy_snapshot_service.validate_current_ai_policy_snapshot_contract(
            prompt_pack_snapshot
        )

    prompt_version_snapshot = build_ai_policy_snapshot(trial=_trial())
    prompt_version_snapshot["agents"]["prestart"]["promptVersion"] = "legacy"
    prompt_version_digest_snapshot = dict(prompt_version_snapshot)
    prompt_version_digest_snapshot.pop("snapshotDigest", None)
    prompt_version_snapshot[
        "snapshotDigest"
    ] = policy_snapshot_service.compute_ai_policy_snapshot_digest(
        prompt_version_digest_snapshot
    )
    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_prompt_version_mismatch",
    ):
        policy_snapshot_service.validate_current_ai_policy_snapshot_contract(
            prompt_version_snapshot
        )

    rubric_version_snapshot = build_ai_policy_snapshot(trial=_trial())
    rubric_version_snapshot["agents"]["prestart"]["rubricVersion"] = "legacy"
    rubric_version_digest_snapshot = dict(rubric_version_snapshot)
    rubric_version_digest_snapshot.pop("snapshotDigest", None)
    rubric_version_snapshot[
        "snapshotDigest"
    ] = policy_snapshot_service.compute_ai_policy_snapshot_digest(
        rubric_version_digest_snapshot
    )
    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_rubric_version_mismatch",
    ):
        policy_snapshot_service.validate_current_ai_policy_snapshot_contract(
            rubric_version_snapshot
        )


def test_build_snapshot_prompt_returns_none_for_missing_or_invalid_agent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        policy_snapshot_service,
        "validate_ai_policy_snapshot_contract",
        lambda snapshot_json, scenario_version_id=None: dict(snapshot_json or {}),
    )

    assert (
        policy_snapshot_service.build_snapshot_prompt(
            snapshot_json={"agents": {}},
            agent_key="prestart",
        )
        is None
    )

    snapshot = {
        "agents": {
            "prestart": {
                "resolvedInstructionsMd": 1,
                "resolvedRubricMd": 2,
            }
        }
    }
    assert (
        policy_snapshot_service.build_snapshot_prompt(
            snapshot_json=snapshot,
            agent_key="prestart",
        )
        is None
    )


def test_build_required_snapshot_prompt_raises_when_prompt_layers_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        policy_snapshot_service,
        "validate_ai_policy_snapshot_contract",
        lambda snapshot_json, scenario_version_id=None: dict(snapshot_json or {}),
    )
    monkeypatch.setattr(
        policy_snapshot_service,
        "require_agent_policy_snapshot",
        lambda snapshot_json, agent_key, scenario_version_id=None: {
            "resolvedInstructionsMd": 1,
            "resolvedRubricMd": 2,
        },
    )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_prompt_missing",
    ):
        policy_snapshot_service.build_required_snapshot_prompt(
            snapshot_json={"agents": {"prestart": {}}},
            agent_key="prestart",
            scenario_version_id=7,
        )


def test_require_candidate_settings_from_snapshot_returns_frozen_values() -> None:
    snapshot = build_ai_policy_snapshot(trial=_trial())
    (
        notice_version,
        notice_text,
        enabled,
    ) = policy_snapshot_service.require_candidate_settings_from_snapshot(snapshot)
    assert notice_version == "mvp1"
    assert notice_text == "AI assistance may be used for evaluation support."
    assert enabled["1"] is True


def test_ai_policy_snapshot_helpers_cover_remaining_validation_branches() -> None:
    assert policy_snapshot_service.compute_ai_policy_snapshot_digest(None) is None
    fingerprint_none = (
        policy_snapshot_service.compute_ai_policy_snapshot_basis_fingerprint(None)
    )
    fingerprint_empty = (
        policy_snapshot_service.compute_ai_policy_snapshot_basis_fingerprint({})
    )
    assert isinstance(fingerprint_none, str)
    assert isinstance(fingerprint_empty, str)
    assert len(fingerprint_none) == 64
    assert len(fingerprint_empty) == 64
    assert policy_snapshot_service.get_agent_policy_snapshot(None, "prestart") is None
    assert (
        policy_snapshot_service.get_agent_policy_snapshot({"agents": []}, "prestart")
        is None
    )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_missing",
    ):
        policy_snapshot_service.require_ai_policy_snapshot(None, scenario_version_id=1)

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_agents_missing",
    ):
        policy_snapshot_service.require_agent_policy_snapshot(
            {"agents": None},
            "prestart",
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_agent_missing",
    ):
        policy_snapshot_service.require_agent_policy_snapshot(
            {"agents": {}},
            "prestart",
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_missing",
    ):
        policy_snapshot_service.require_agent_runtime(
            {"agents": {"prestart": {"key": "prestart"}}},
            "prestart",
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_prompt_pack_version_missing",
    ):
        policy_snapshot_service.validate_ai_policy_snapshot_contract(
            {
                "candidateSettings": {"noticeVersion": "m", "noticeText": "t"},
                "agents": {},
            },
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_missing",
    ):
        policy_snapshot_service.build_ai_policy_snapshot(trial=SimpleNamespace(id=1))


def test_ai_policy_snapshot_internal_validation_branches() -> None:
    assert policy_snapshot_service._normalize_eval_enabled_by_day([]) == (
        default_ai_eval_enabled_by_day()
    )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_missing",
    ):
        policy_snapshot_service._validate_runtime_payload(
            runtime=None,
            scenario_version_id=1,
            agent_key="prestart",
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_provider_missing",
    ):
        policy_snapshot_service._validate_runtime_payload(
            runtime={
                "runtimeMode": "test",
                "provider": " ",
                "model": "gpt",
                "timeoutSeconds": 1,
                "maxRetries": 0,
            },
            scenario_version_id=1,
            agent_key="prestart",
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_timeoutSeconds_missing",
    ):
        policy_snapshot_service._validate_runtime_payload(
            runtime={
                "runtimeMode": "test",
                "provider": "openai",
                "model": "gpt",
                "timeoutSeconds": 0,
                "maxRetries": 0,
            },
            scenario_version_id=1,
            agent_key="prestart",
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_runtime_maxRetries_missing",
    ):
        policy_snapshot_service._validate_runtime_payload(
            runtime={
                "runtimeMode": "test",
                "provider": "openai",
                "model": "gpt",
                "timeoutSeconds": 1,
                "maxRetries": -1,
            },
            scenario_version_id=1,
            agent_key="prestart",
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_candidate_settings_missing",
    ):
        policy_snapshot_service._validate_candidate_settings(
            candidate_settings=None,
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_candidate_settings_noticeVersion_missing",
    ):
        policy_snapshot_service._validate_candidate_settings(
            candidate_settings={
                "noticeText": "hello",
                "evalEnabledByDay": {},
            },
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_candidate_settings_evalEnabledByDay_missing",
    ):
        policy_snapshot_service._validate_candidate_settings(
            candidate_settings={
                "noticeVersion": "mvp1",
                "noticeText": "hello",
                "evalEnabledByDay": None,
            },
            scenario_version_id=1,
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_agent_missing",
    ):
        policy_snapshot_service._validate_agent_snapshot_structure(
            agent_snapshot=None,
            scenario_version_id=1,
            agent_key="prestart",
        )

    with pytest.raises(
        policy_snapshot_service.AIPolicySnapshotError,
        match="scenario_version_ai_policy_snapshot_agent_key_mismatch",
    ):
        policy_snapshot_service._validate_agent_snapshot_structure(
            agent_snapshot={
                "key": "other",
                "promptVersion": "1",
                "rubricVersion": "1",
                "runtime": {
                    "runtimeMode": "test",
                    "provider": "openai",
                    "model": "gpt",
                    "timeoutSeconds": 1,
                    "maxRetries": 0,
                },
            },
            scenario_version_id=1,
            agent_key="prestart",
        )

    snapshot_map = policy_snapshot_service._trial_agent_snapshot_map(
        SimpleNamespace(
            agent_snapshots=[
                SimpleNamespace(agent_name=" "),
                SimpleNamespace(agent_name="prestart"),
            ]
        )
    )
    assert list(snapshot_map.keys()) == ["prestart"]

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            policy_snapshot_service,
            "validate_ai_policy_snapshot_contract",
            lambda snapshot_json, scenario_version_id=None: dict(snapshot_json or {}),
        )
        with pytest.raises(
            policy_snapshot_service.AIPolicySnapshotError,
            match="scenario_version_ai_policy_snapshot_candidate_settings_missing",
        ):
            policy_snapshot_service.require_candidate_settings_from_snapshot(
                {"candidateSettings": None}
            )
        prompt = policy_snapshot_service.build_snapshot_prompt(
            snapshot_json={
                "agents": {
                    "prestart": {
                        "resolvedInstructionsMd": "instructions",
                        "resolvedRubricMd": "rubric",
                    }
                }
            },
            agent_key="prestart",
        )
        assert prompt == ("instructions", "rubric")
    finally:
        monkeypatch.undo()
