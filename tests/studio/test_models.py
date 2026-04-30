from __future__ import annotations

import app.models as models
import pytest
from app.models import ErrorResponse, RunRequest
from app.services.placeholders import placeholder_skill_detail
from pydantic import ValidationError


def test_model_exports_cover_phase0_contracts() -> None:
    expected_exports = {
        "AuditResult",
        "CompareResult",
        "CopilotDispatchReq",
        "CopilotResponse",
        "CreateSkillReq",
        "ErrorResponse",
        "GoldenBaseline",
        "LintError",
        "LintResult",
        "ResumeReq",
        "RunDetail",
        "RunMetadata",
        "RunRequest",
        "SetGoldenReq",
        "SkillDetail",
        "SkillSummary",
        "TerminalSession",
        "TestInputMetadata",
        "TokensMetrics",
        "UpdateSkillReq",
    }
    assert set(models.__all__) == expected_exports


def test_models_validate_fields_and_reuse_graph_agent_contracts() -> None:
    detail = placeholder_skill_detail("demo-skill")

    assert detail.manifest.type == "agent"
    assert detail.manifest.name == "demo-skill"
    assert detail.file_paths["skill_md"].endswith("SKILL.md")

    with pytest.raises(ValidationError):
        ErrorResponse(
            error_code="X",
            http_status=400,
            message="bad retry",
            retry_strategy="retry_later",
        )

    with pytest.raises(ValidationError):
        RunRequest.model_validate({"unexpected": "field"})
