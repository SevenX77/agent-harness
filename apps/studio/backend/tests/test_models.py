from __future__ import annotations

import app.models as models
import pytest
from app.models import CreateSkillReq, ErrorResponse, RunRequest, SkillDetail, UpdateSkillReq
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef
from pydantic import ValidationError


def test_model_exports_cover_phase0_contracts() -> None:
    expected_exports = {
        "AuditResult",
        "BatchRunItem",
        "BatchRunRequest",
        "BatchRunResponse",
        "BatchRunStatus",
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
        "RunListResponse",
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
    manifest = GraphManifest(
        name="demo-skill",
        description="demo",
        io_inputs_ref="io/inputs.json",
        io_outputs_ref="io/outputs.json",
        phases=[GraphPhaseRef(id="setup", src="phases/setup", depends_on=[])],
    )
    detail = SkillDetail(
        manifest=manifest,
        graph_topology=[{"id": "setup", "src": "phases/setup", "depends_on": [], "mode": "logic"}],
        node_schema_v21={"graph_phase_ref": {}, "logic": {}, "skill": {}, "subgraph": {}},
        io_schema={"inputs": {}, "outputs": {}},
        file_paths={"graph_md": "/tmp/GRAPH.md"},
        has_golden=False,
    )

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


def test_skill_create_update_reject_content_payload() -> None:
    create = CreateSkillReq.model_validate(
        {
            "skill_id": "demo-skill",
            "files": {"GRAPH.md": "# Demo"},
        }
    )
    update = UpdateSkillReq.model_validate({"files": {"GRAPH.md": "# Demo"}})

    assert create.files == {"GRAPH.md": "# Demo"}
    assert update.files == {"GRAPH.md": "# Demo"}

    with pytest.raises(ValidationError):
        CreateSkillReq.model_validate({"skill_id": "demo-skill", "content": "# Demo"})

    with pytest.raises(ValidationError):
        UpdateSkillReq.model_validate({"content": "# Demo"})
