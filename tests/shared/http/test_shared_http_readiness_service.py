from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.shared.http import shared_http_readiness_service as readiness_service


class _FakeSchemaInspector:
    def __init__(self, tables: list[str], foreign_keys: dict[str, list[dict]]):
        self._tables = tables
        self._foreign_keys = foreign_keys

    def get_table_names(self):
        return self._tables

    def get_foreign_keys(self, table_name: str):
        return self._foreign_keys.get(table_name, [])


class _FakeHeartbeatSessionContext:
    def __init__(self, db: object):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeHeartbeatSessionMaker:
    def __init__(self, db: object | None = None):
        self._db = db or SimpleNamespace()

    def __call__(self):
        return _FakeHeartbeatSessionContext(self._db)


def test_inspect_schema_reports_ready_when_tables_and_fks_exist(monkeypatch):
    inspector = _FakeSchemaInspector(
        [
            "candidate_sessions",
            "jobs",
            "scenario_versions",
            "tasks",
            "trials",
            "worker_heartbeats",
        ],
        {
            "candidate_sessions": [
                {
                    "constrained_columns": ["trial_id"],
                    "referred_table": "trials",
                    "referred_columns": ["id"],
                },
                {
                    "constrained_columns": ["scenario_version_id"],
                    "referred_table": "scenario_versions",
                    "referred_columns": ["id"],
                },
            ],
            "scenario_versions": [
                {
                    "constrained_columns": ["trial_id"],
                    "referred_table": "trials",
                    "referred_columns": ["id"],
                }
            ],
            "tasks": [
                {
                    "constrained_columns": ["trial_id"],
                    "referred_table": "trials",
                    "referred_columns": ["id"],
                }
            ],
        },
    )
    monkeypatch.setattr(readiness_service, "inspect", lambda _conn: inspector)

    result = readiness_service._inspect_schema(object())

    assert result.status == "ready"
    assert result.code == "schema_ok"
    assert result.detail == "Required database tables and foreign keys are present."


def test_inspect_schema_reports_missing_table_and_fk(monkeypatch):
    inspector = _FakeSchemaInspector(
        ["trials", "tasks"],
        {
            "tasks": [
                {
                    "constrained_columns": ["trial_id"],
                    "referred_table": "trials",
                    "referred_columns": ["id"],
                }
            ]
        },
    )
    monkeypatch.setattr(readiness_service, "inspect", lambda _conn: inspector)

    result = readiness_service._inspect_schema(object())

    assert result.status == "not_ready"
    assert result.code == "schema_mismatch"
    assert "scenario_versions" in result.data["missingTables"]
    assert "candidate_sessions" in result.data["missingTables"]


def test_inspect_schema_reports_missing_foreign_keys_when_tables_exist(monkeypatch):
    inspector = _FakeSchemaInspector(
        [
            "candidate_sessions",
            "jobs",
            "scenario_versions",
            "tasks",
            "trials",
            "worker_heartbeats",
        ],
        {
            "candidate_sessions": [
                {
                    "constrained_columns": ["trial_id"],
                    "referred_table": "trials",
                    "referred_columns": ["id"],
                }
            ],
            "scenario_versions": [],
            "tasks": [],
        },
    )
    monkeypatch.setattr(readiness_service, "inspect", lambda _conn: inspector)

    result = readiness_service._inspect_schema(object())

    assert result.status == "not_ready"
    assert result.code == "schema_mismatch"
    assert "missingForeignKeys" in result.data
    assert "candidate_sessions" in result.data["missingForeignKeys"]
    assert "scenario_versions" in result.data["missingForeignKeys"]
    assert "tasks" in result.data["missingForeignKeys"]


def test_utc_now_and_aggregate_status_normalize_inputs():
    naive_now = datetime(2026, 4, 27, 12, 0)
    aware_now = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

    normalized_naive = readiness_service._utc_now(naive_now)
    normalized_aware = readiness_service._utc_now(aware_now)
    all_skipped = readiness_service._aggregate_status(
        [
            readiness_service.ReadinessCheck(status="skipped", code="a", detail="a"),
            readiness_service.ReadinessCheck(status="skipped", code="b", detail="b"),
        ]
    )
    mixed_status = readiness_service._aggregate_status(
        [
            readiness_service.ReadinessCheck(status="ready", code="a", detail="a"),
            readiness_service.ReadinessCheck(status="skipped", code="b", detail="b"),
        ]
    )

    assert normalized_naive.tzinfo is UTC
    assert normalized_aware.tzinfo is UTC
    assert all_skipped == "skipped"
    assert mixed_status == "ready"


@pytest.mark.asyncio
async def test_check_ai_readiness_aggregates_resolvers_and_status(monkeypatch):
    monkeypatch.setattr(readiness_service.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(
        readiness_service.settings, "ANTHROPIC_API_KEY", "test-anthropic"
    )
    monkeypatch.setattr(
        readiness_service,
        "_AI_FEATURE_RESOLVERS",
        {
            "scenarioGeneration": lambda: SimpleNamespace(
                runtime_mode="demo", provider="openai"
            ),
            "transcription": lambda: SimpleNamespace(
                runtime_mode="real", provider="anthropic"
            ),
        },
    )

    result = await readiness_service.check_ai_readiness()

    assert result.status == "ready"
    assert result.code == "ai_providers_ready"
    assert set(result.data["checks"]) == {"scenarioGeneration", "transcription"}
    assert result.data["checks"]["scenarioGeneration"]["status"] == "skipped"
    assert result.data["checks"]["transcription"]["status"] == "ready"


@pytest.mark.asyncio
async def test_check_database_readiness_returns_specific_schema_failure(monkeypatch):
    class _BrokenConnection:
        async def run_sync(self, _func):
            raise RuntimeError("schema boom")

    class _BrokenContext:
        async def __aenter__(self):
            return _BrokenConnection()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        readiness_service,
        "engine",
        SimpleNamespace(connect=lambda: _BrokenContext()),
    )

    result = await readiness_service.check_database_readiness()

    assert result.status == "not_ready"
    assert result.code == "database_unavailable"


def test_check_ai_feature_skips_demo_mode_and_handles_provider_modes(monkeypatch):
    demo_config = SimpleNamespace(runtime_mode="demo", provider="openai")
    test_config = SimpleNamespace(runtime_mode="test", provider="anthropic")
    real_openai = SimpleNamespace(runtime_mode="real", provider="openai")
    real_anthropic = SimpleNamespace(runtime_mode="real", provider="anthropic")
    unsupported = SimpleNamespace(runtime_mode="real", provider="local")
    monkeypatch.setattr(readiness_service.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(
        readiness_service.settings, "ANTHROPIC_API_KEY", "test-anthropic"
    )

    skipped = readiness_service._check_ai_feature("scenarioGeneration", demo_config)
    skipped_test = readiness_service._check_ai_feature("transcription", test_config)
    openai_ready = readiness_service._check_ai_feature(
        "codespaceSpecializer", real_openai
    )
    anthropic_ready = readiness_service._check_ai_feature(
        "winoeReportAggregator", real_anthropic
    )
    unsupported_result = readiness_service._check_ai_feature(
        "scenarioGeneration", unsupported
    )

    assert skipped.status == "skipped"
    assert skipped.code == "demo_mode"
    assert skipped_test.status == "skipped"
    assert openai_ready.status == "ready"
    assert anthropic_ready.status == "ready"
    assert unsupported_result.status == "not_ready"
    assert unsupported_result.code == "unsupported_provider"


def test_check_ai_feature_reports_missing_provider_keys(monkeypatch):
    monkeypatch.setattr(readiness_service.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(readiness_service.settings, "ANTHROPIC_API_KEY", "")

    openai_missing = readiness_service._check_ai_feature(
        "scenarioGeneration", SimpleNamespace(runtime_mode="real", provider="openai")
    )
    anthropic_missing = readiness_service._check_ai_feature(
        "transcription", SimpleNamespace(runtime_mode="real", provider="anthropic")
    )

    assert openai_missing.status == "not_ready"
    assert openai_missing.code == "no_provider_configured"
    assert anthropic_missing.status == "not_ready"
    assert anthropic_missing.code == "no_provider_configured"


def test_check_github_readiness_covers_demo_and_configured_modes(monkeypatch):
    github_cfg = SimpleNamespace(
        GITHUB_TOKEN="",
        GITHUB_ORG="",
        GITHUB_TEMPLATE_OWNER="legacy-template-owner",
        GITHUB_API_BASE="https://api.github.com",
    )
    monkeypatch.setattr(readiness_service.settings, "DEMO_MODE", True)
    monkeypatch.setattr(readiness_service.settings, "github", github_cfg)

    skipped = readiness_service._check_github_readiness()
    assert skipped.status == "skipped"
    assert skipped.code == "demo_mode"

    monkeypatch.setattr(readiness_service.settings, "DEMO_MODE", False)
    missing_token = readiness_service._check_github_readiness()
    assert missing_token.status == "not_ready"
    assert missing_token.code == "no_provider_configured"

    monkeypatch.setattr(github_cfg, "GITHUB_TOKEN", "token")
    missing_org = readiness_service._check_github_readiness()
    assert missing_org.status == "not_ready"
    assert missing_org.code == "missing_github_org"

    monkeypatch.setattr(github_cfg, "GITHUB_ORG", "winoe-ai")
    ready = readiness_service._check_github_readiness()
    assert ready.status == "ready"
    assert ready.code == "provider_ready"


def test_check_github_readiness_skips_demo_mode_even_with_legacy_template_owner(
    monkeypatch,
):
    github_cfg = SimpleNamespace(
        GITHUB_TOKEN="token",
        GITHUB_ORG="winoe-ai",
        GITHUB_TEMPLATE_OWNER="legacy-template-owner",
        GITHUB_API_BASE="https://api.github.com",
    )
    monkeypatch.setattr(readiness_service.settings, "DEMO_MODE", True)
    monkeypatch.setattr(readiness_service.settings, "github", github_cfg)

    skipped = readiness_service._check_github_readiness()

    assert skipped.status == "skipped"
    assert skipped.code == "demo_mode"


def test_check_email_readiness_covers_all_provider_modes(monkeypatch):
    email_cfg = SimpleNamespace(
        WINOE_EMAIL_PROVIDER="console",
        WINOE_EMAIL_FROM="Winoe <notifications@winoe.com>",
        WINOE_RESEND_API_KEY="",
        SENDGRID_API_KEY="",
        SMTP_HOST="",
    )
    monkeypatch.setattr(readiness_service.settings, "email", email_cfg)

    console_ready = readiness_service._check_email_readiness()
    assert console_ready.status == "ready"
    assert console_ready.code == "provider_ready"

    monkeypatch.setattr(email_cfg, "WINOE_EMAIL_PROVIDER", "resend")
    resend_missing = readiness_service._check_email_readiness()
    assert resend_missing.status == "not_ready"
    assert resend_missing.code == "no_provider_configured"

    monkeypatch.setattr(email_cfg, "WINOE_RESEND_API_KEY", "resend-key")
    resend_ready = readiness_service._check_email_readiness()
    assert resend_ready.status == "ready"

    monkeypatch.setattr(email_cfg, "WINOE_EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setattr(email_cfg, "SENDGRID_API_KEY", "")
    sendgrid_missing = readiness_service._check_email_readiness()
    assert sendgrid_missing.status == "not_ready"
    assert sendgrid_missing.code == "no_provider_configured"

    monkeypatch.setattr(email_cfg, "SENDGRID_API_KEY", "sendgrid-key")
    sendgrid_ready = readiness_service._check_email_readiness()
    assert sendgrid_ready.status == "ready"

    monkeypatch.setattr(email_cfg, "WINOE_EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(email_cfg, "SMTP_HOST", "")
    smtp_missing = readiness_service._check_email_readiness()
    assert smtp_missing.status == "not_ready"
    assert smtp_missing.code == "no_provider_configured"

    monkeypatch.setattr(email_cfg, "SMTP_HOST", "smtp.local")
    smtp_ready = readiness_service._check_email_readiness()
    assert smtp_ready.status == "ready"

    monkeypatch.setattr(email_cfg, "WINOE_EMAIL_PROVIDER", "other")
    unsupported = readiness_service._check_email_readiness()
    assert unsupported.status == "not_ready"
    assert unsupported.code == "unsupported_provider"


def test_check_media_readiness_covers_all_provider_modes(monkeypatch):
    media_cfg = SimpleNamespace(
        MEDIA_STORAGE_PROVIDER="fake",
        MEDIA_S3_ENDPOINT="",
        MEDIA_S3_BUCKET="",
        MEDIA_S3_ACCESS_KEY_ID="",
        MEDIA_S3_SECRET_ACCESS_KEY="",
    )
    monkeypatch.setattr(readiness_service.settings, "storage_media", media_cfg)

    fake_ready = readiness_service._check_media_readiness()
    assert fake_ready.status == "ready"
    assert fake_ready.code == "provider_ready"

    monkeypatch.setattr(media_cfg, "MEDIA_STORAGE_PROVIDER", "s3")
    missing = readiness_service._check_media_readiness()
    assert missing.status == "not_ready"
    assert missing.code == "no_provider_configured"
    assert "MEDIA_S3_ENDPOINT" in missing.data["missingFields"]

    monkeypatch.setattr(media_cfg, "MEDIA_S3_ENDPOINT", "http://minio.local")
    monkeypatch.setattr(media_cfg, "MEDIA_S3_BUCKET", "winoe-media")
    monkeypatch.setattr(media_cfg, "MEDIA_S3_ACCESS_KEY_ID", "access")
    monkeypatch.setattr(media_cfg, "MEDIA_S3_SECRET_ACCESS_KEY", "secret")
    s3_ready = readiness_service._check_media_readiness()
    assert s3_ready.status == "ready"
    assert s3_ready.code == "provider_ready"

    monkeypatch.setattr(media_cfg, "MEDIA_STORAGE_PROVIDER", "other")
    unsupported = readiness_service._check_media_readiness()
    assert unsupported.status == "not_ready"
    assert unsupported.code == "unsupported_provider"


@pytest.mark.asyncio
async def test_worker_readiness_reports_missing_stopped_stale_and_fresh_heartbeat(
    monkeypatch,
):
    class _SessionMaker(_FakeHeartbeatSessionMaker):
        pass

    async def fake_missing(db, *, service_name):
        assert (
            service_name
            == readiness_service.heartbeat_service.DEFAULT_WORKER_SERVICE_NAME
        )
        return None

    monkeypatch.setattr(
        readiness_service.jobs_repo,
        "get_latest_worker_heartbeat",
        fake_missing,
    )

    missing = await readiness_service.check_worker_readiness(
        session_maker=_SessionMaker()
    )
    assert missing.status == "not_ready"
    assert missing.code == "heartbeat_missing"

    stopped_heartbeat = SimpleNamespace(
        service_name="winoe-worker",
        instance_id="worker-1",
        status=readiness_service.heartbeat_service.WORKER_HEARTBEAT_STATUS_STOPPED,
        last_heartbeat_at=datetime.now(UTC),
    )

    async def fake_stopped(db, *, service_name):
        return stopped_heartbeat

    monkeypatch.setattr(
        readiness_service.jobs_repo,
        "get_latest_worker_heartbeat",
        fake_stopped,
    )

    stopped = await readiness_service.check_worker_readiness(
        session_maker=_SessionMaker()
    )
    assert stopped.status == "not_ready"
    assert stopped.code == "heartbeat_stopped"

    stale_heartbeat = SimpleNamespace(
        service_name="winoe-worker",
        instance_id="worker-2",
        status="running",
        last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=300),
    )

    async def fake_stale(db, *, service_name):
        return stale_heartbeat

    monkeypatch.setattr(
        readiness_service.jobs_repo,
        "get_latest_worker_heartbeat",
        fake_stale,
    )
    monkeypatch.setattr(
        readiness_service.settings, "WORKER_HEARTBEAT_STALE_SECONDS", 60
    )

    stale = await readiness_service.check_worker_readiness(
        session_maker=_SessionMaker(),
        now=datetime.now(UTC),
    )
    assert stale.status == "not_ready"
    assert stale.code == "heartbeat_stale"
    assert stale.data["ageSeconds"] >= 300
    assert stale.data["staleAfterSeconds"] == 60

    fresh_heartbeat = SimpleNamespace(
        service_name="winoe-worker",
        instance_id="worker-3",
        status="running",
        last_heartbeat_at=datetime.now(UTC),
    )

    async def fake_fresh(db, *, service_name):
        return fresh_heartbeat

    monkeypatch.setattr(
        readiness_service.jobs_repo,
        "get_latest_worker_heartbeat",
        fake_fresh,
    )

    fresh = await readiness_service.check_worker_readiness(
        session_maker=_SessionMaker(),
        now=datetime.now(UTC),
    )
    assert fresh.status == "ready"
    assert fresh.code == "heartbeat_fresh"
    assert fresh.data["ageSeconds"] in {0, 1}


@pytest.mark.asyncio
async def test_build_readiness_payload_aggregates_status_and_checked_at(monkeypatch):
    async def ready_db():
        return readiness_service._readiness_check(
            status="ready", code="schema_ok", detail="ok"
        )

    async def not_ready_worker(**_kwargs):
        return readiness_service._readiness_check(
            status="not_ready",
            code="heartbeat_stale",
            detail="stale",
            data={"ageSeconds": 200},
        )

    async def ready_ai():
        return readiness_service._readiness_check(
            status="ready", code="ai_providers_ready", detail="ok"
        )

    monkeypatch.setattr(readiness_service, "check_database_readiness", ready_db)
    monkeypatch.setattr(readiness_service, "check_worker_readiness", not_ready_worker)
    monkeypatch.setattr(readiness_service, "check_ai_readiness", ready_ai)
    monkeypatch.setattr(
        readiness_service,
        "_check_github_readiness",
        lambda: readiness_service._readiness_check(
            status="skipped", code="demo_mode", detail="ok"
        ),
    )
    monkeypatch.setattr(
        readiness_service,
        "_check_email_readiness",
        lambda: readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        ),
    )
    monkeypatch.setattr(
        readiness_service,
        "_check_media_readiness",
        lambda: readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        ),
    )

    payload = await readiness_service.build_readiness_payload(
        now=datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert payload["status"] == "not_ready"
    assert payload["demoMode"] is False
    assert payload["checkedAt"] == "2026-01-01T00:00:00Z"
    assert payload["checks"]["worker"]["status"] == "not_ready"
    assert payload["checks"]["worker"]["data"] == {"ageSeconds": 200}
    assert payload["checks"]["github"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_build_readiness_payload_returns_ready_when_all_checks_ready(monkeypatch):
    async def ready_check(**_kwargs):
        return readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        )

    monkeypatch.setattr(readiness_service, "check_database_readiness", ready_check)
    monkeypatch.setattr(readiness_service, "check_worker_readiness", ready_check)
    monkeypatch.setattr(readiness_service, "check_ai_readiness", ready_check)
    monkeypatch.setattr(
        readiness_service,
        "_check_github_readiness",
        lambda: readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        ),
    )
    monkeypatch.setattr(
        readiness_service,
        "_check_email_readiness",
        lambda: readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        ),
    )
    monkeypatch.setattr(
        readiness_service,
        "_check_media_readiness",
        lambda: readiness_service._readiness_check(
            status="ready", code="provider_ready", detail="ok"
        ),
    )

    payload = await readiness_service.build_readiness_payload(
        now=datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert payload["status"] == "ready"
    assert payload["demoMode"] is False
    assert set(payload["checks"]) == {
        "database",
        "worker",
        "ai",
        "github",
        "email",
        "media",
    }
