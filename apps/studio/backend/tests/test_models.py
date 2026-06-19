from __future__ import annotations

import app.models as models
import pytest
from app.models import AppSettings, ErrorResponse, RunRequest, SkillDetail
from graph_agent.core.manifest import GraphManifest
from pydantic import ValidationError


def test_model_exports_cover_phase0_contracts() -> None:
    expected_exports = {
        "AuditResult",
        "AppSettings",
        "BatchRunItem",
        "BatchRunRequest",
        "BatchRunResponse",
        "BatchRunStatus",
        "CompareResult",
        "ContextUpdateRequest",
        "ContextUpdateResponse",
        "CreateSkillReq",
        "ErrorResponse",
        "GoldenBaseline",
        "GitHistoryItem",
        "LintError",
        "LintResult",
        "ResumeReq",
        "RevertSkillReq",
        "RunDetail",
        "RunListResponse",
        "RunMetadata",
        "RunRequest",
        "SerializeGraphReq",
        "SerializeGraphRes",
        "SetGoldenReq",
        "SkillDetail",
        "SkillSummary",
        "TerminalSession",
        "TestInputMetadata",
        "TokensMetrics",
        "UpdateSkillFileReq",
        "UpdateSkillFileRes",
        "UpdateSkillReq",
    }
    assert set(models.__all__) == expected_exports


def test_models_validate_fields_and_reuse_graph_agent_contracts() -> None:
    manifest = GraphManifest(
        schema_version="v0.3.0",
        name="demo-skill",
        description="demo",
        io={
            "inputs": {"type": "object", "properties": {}},
            "outputs": {"type": "object", "properties": {}},
        },
        phases=["setup"],
    )
    detail = SkillDetail(
        manifest=manifest,
        file_paths={"graph_md": "/tmp/GRAPH.md"},
        has_golden=False,
    )

    assert detail.manifest.schema_version == "v0.3.0"
    assert detail.manifest.name == "demo-skill"
    assert detail.file_paths["graph_md"].endswith("GRAPH.md")

    with pytest.raises(ValidationError):
        ErrorResponse(
            error_code="X",
            http_status=400,
            message="bad retry",
            retry_strategy="retry_later",
        )

    with pytest.raises(ValidationError):
        RunRequest.model_validate({"unexpected": "field"})


def test_app_settings_language_defaults_to_en() -> None:
    """N0 i18n: the UI language persists in AppSettings, defaulting to English."""
    settings = AppSettings()

    assert settings.language == "en"


def test_app_settings_accepts_supported_language() -> None:
    settings = AppSettings.model_validate(
        {
            "user_id": "alice",
            "gitea_host": "",
            "default_skills_directory": "",
            "language": "zh-CN",
        }
    )

    assert settings.language == "zh-CN"


def test_app_settings_rejects_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"language": "fr-FR"})


def test_app_settings_still_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"unknown_field": "x"})
