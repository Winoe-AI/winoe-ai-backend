from __future__ import annotations

from pathlib import Path

import pytest

from app.ai import ai_prompt_pack_service as prompt_pack_service


def test_prompt_pack_helpers_cover_validation_branches(tmp_path, monkeypatch) -> None:
    with pytest.raises(ValueError, match="missing '## Instructions' section"):
        prompt_pack_service._extract_markdown_section(
            "## Rubric\nvalue", "Instructions"
        )

    with pytest.raises(ValueError, match="cannot be blank"):
        prompt_pack_service._extract_markdown_section(
            "## Instructions\n\n## Rubric\nvalue",
            "Instructions",
        )

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        prompt_pack_service._read_json_file(bad_json)

    with pytest.raises(FileNotFoundError):
        prompt_pack_service._read_text_file(tmp_path / "missing.md")

    monkeypatch.setattr(
        prompt_pack_service,
        "_prompt_asset_path",
        lambda file_name: tmp_path / file_name,
    )
    with pytest.raises(
        FileNotFoundError, match="Persona governance prompt asset not found"
    ):
        prompt_pack_service._load_persona_governance_md()


def test_prompt_pack_bundle_loader_covers_manifest_validation_branches(
    tmp_path, monkeypatch
) -> None:
    prompt_pack_service._load_prompt_pack_bundle.cache_clear()

    def _manifest_version_missing(path: Path) -> dict:
        if path.name == "manifest.json":
            return {"version": "", "agents": {"prestart": {}}}
        return {}

    monkeypatch.setattr(
        prompt_pack_service, "_read_json_file", _manifest_version_missing
    )
    with pytest.raises(ValueError, match="must declare a version"):
        prompt_pack_service._load_prompt_pack_bundle()

    prompt_pack_service._load_prompt_pack_bundle.cache_clear()

    def _empty_agents(path: Path) -> dict:
        if path.name == "manifest.json":
            return {"version": "pack-v4", "agents": {}}
        return {}

    monkeypatch.setattr(prompt_pack_service, "_read_json_file", _empty_agents)
    with pytest.raises(ValueError, match="must declare at least one agent"):
        prompt_pack_service._load_prompt_pack_bundle()

    prompt_pack_service._load_prompt_pack_bundle.cache_clear()

    def _non_dict_agent(path: Path) -> dict:
        if path.name == "manifest.json":
            return {"version": "pack-v4", "agents": {"prestart": []}}
        return {}

    monkeypatch.setattr(prompt_pack_service, "_read_json_file", _non_dict_agent)
    with pytest.raises(ValueError, match="must be an object"):
        prompt_pack_service._load_prompt_pack_bundle()

    prompt_pack_service._load_prompt_pack_bundle.cache_clear()

    def _incomplete_agent(path: Path) -> dict:
        if path.name == "manifest.json":
            return {
                "version": "pack-v4",
                "agents": {
                    "prestart": {
                        "policyFile": "",
                        "schemaFile": "",
                        "outputModel": "",
                    }
                },
            }
        return {}

    monkeypatch.setattr(prompt_pack_service, "_read_json_file", _incomplete_agent)
    with pytest.raises(ValueError, match="is incomplete"):
        prompt_pack_service._load_prompt_pack_bundle()

    prompt_pack_service._load_prompt_pack_bundle.cache_clear()

    def _unsupported_model(path: Path) -> dict:
        if path.name == "manifest.json":
            return {
                "version": "pack-v4",
                "agents": {
                    "prestart": {
                        "policyFile": "prestart.md",
                        "schemaFile": "prestart.schema.json",
                        "outputModel": "UnknownModel",
                    }
                },
            }
        return {}

    monkeypatch.setattr(prompt_pack_service, "_read_json_file", _unsupported_model)
    with pytest.raises(ValueError, match="Unsupported prompt pack output model"):
        prompt_pack_service._load_prompt_pack_bundle()

    prompt_pack_service._load_prompt_pack_bundle.cache_clear()
    policy_file = tmp_path / "prestart.md"
    policy_file.write_text(
        "## Instructions\nhello\n\n## Rubric\nworld", encoding="utf-8"
    )
    schema_file = tmp_path / "prestart.schema.json"
    schema_file.write_text("{}", encoding="utf-8")

    def _schema_mismatch(path: Path) -> dict:
        if path.name == "manifest.json":
            return {
                "version": "pack-v4",
                "agents": {
                    "prestart": {
                        "policyFile": "prestart.md",
                        "schemaFile": "prestart.schema.json",
                        "outputModel": "ScenarioGenerationOutput",
                    }
                },
            }
        if path.name == "prestart.schema.json":
            return {}
        return {}

    monkeypatch.setattr(prompt_pack_service, "_read_json_file", _schema_mismatch)
    monkeypatch.setattr(prompt_pack_service, "_prompt_assets_root", lambda: tmp_path)
    with pytest.raises(ValueError, match="does not match output model"):
        prompt_pack_service._load_prompt_pack_bundle()
