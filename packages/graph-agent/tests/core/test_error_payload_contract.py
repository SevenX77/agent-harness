from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from graph_agent.core.exceptions import (
    GraphAgentError,
    GraphAgentFatalError,
    SkillCompilationError,
    SkillLoadError,
)
from graph_agent.core.loader import SkillLoader
from graph_agent.runtime.state_mapper import StateMapper
from graph_agent.tools.builtin.read_reference import read_declared_reference

REPO_ROOT = Path(__file__).resolve().parents[4]
ERROR_SPEC = (
    REPO_ROOT
    / "docs"
    / "engine"
    / "mvp1"
    / "01-contract"
    / "03-compile-rules"
    / "mvp1-alignment.md"
)


def _error_payload_model() -> Any:
    exceptions = importlib.import_module("graph_agent.core.exceptions")
    return exceptions.ErrorPayload


def _error_registry() -> dict[str, Any]:
    registry = importlib.import_module("graph_agent.core.error_registry")
    return registry.ERROR_REGISTRY


def _spec_codes() -> set[str]:
    text = ERROR_SPEC.read_text(encoding="utf-8")
    match = re.search(r"## 4\. 错误码全表\(98\)(.*?)(?:\n## 5\.|\Z)", text, re.S)
    assert match is not None, "mvp1 compile-rules must keep a bounded 98-code table section"
    return set(re.findall(r"\[F-v3-[a-z0-9-]+\]", match.group(1)))


def test_error_payload_autofills_registry_metadata() -> None:
    ErrorPayload = _error_payload_model()

    payload = ErrorPayload(code="[F-v3-graph-phase-cycle]", message="cycle")
    metadata = _error_registry()[payload.code]

    assert payload.code == "[F-v3-graph-phase-cycle]"
    assert payload.level == "FATAL"
    assert payload.stage == ("编译期",)
    assert payload.message == "cycle"
    assert payload.doc_link == metadata.doc_link
    assert payload.details == {}


def test_error_payload_details_default_to_empty_json_object() -> None:
    ErrorPayload = _error_payload_model()

    payload = ErrorPayload(code="[F-v3-graph-phase-cycle]", message="cycle")

    assert payload.details == {}
    assert payload.model_dump(mode="json")["details"] == {}


def test_error_payload_details_are_json_safe_and_stable(tmp_path: Path) -> None:
    import json

    class DiagnosticModel(BaseModel):
        label: str

    ErrorPayload = _error_payload_model()
    payload = ErrorPayload(
        code="[F-v3-graph-phase-cycle]",
        message="cycle",
        details={
            "path": tmp_path / "GRAPH.md",
            "choices": {"beta", "alpha"},
            "error": RuntimeError("boom"),
            "nested": {"model": DiagnosticModel(label="ok")},
        },
    )

    dumped = payload.model_dump(mode="json")
    assert dumped["details"]["path"] == str(tmp_path / "GRAPH.md")
    assert dumped["details"]["choices"] == ["alpha", "beta"]
    assert dumped["details"]["error"] == "RuntimeError: boom"
    assert dumped["details"]["nested"]["model"] == {"label": "ok"}
    assert json.loads(payload.model_dump_json())["details"] == dumped["details"]


def test_error_payload_rejects_unknown_code() -> None:
    ErrorPayload = _error_payload_model()

    with pytest.raises(ValueError):
        ErrorPayload(code="[F-v3-not-in-spec]", message="unknown")


def test_graph_agent_error_rejects_unknown_embedded_code() -> None:
    with pytest.raises(ValueError, match="unknown graph_agent error code"):
        GraphAgentFatalError("[F-v3-typo-not-registered] typo")


def test_error_registry_matches_error_code_spec_key_set() -> None:
    registry = _error_registry()

    assert set(registry) == _spec_codes()
    assert len(registry) == len(_spec_codes()) == 98


def test_error_registry_preserves_multi_stage_codes() -> None:
    registry = _error_registry()

    assert registry["[F-v3-resource-reference-path-invalid]"].stage == (
        "编译期",
        "运行期",
    )
    assert registry["[F-v3-resource-example-path-invalid]"].stage == (
        "编译期",
        "运行期",
    )
    assert registry["[F-v3-skill-not-registered]"].stage == ("编译期", "装配期")
    assert registry["[F-v3-skill-id-ambiguous]"].stage == ("编译期", "装配期")


def test_graph_agent_error_exposes_serializable_payload() -> None:
    ErrorPayload = _error_payload_model()
    payload = ErrorPayload(code="[F-v3-runtime-state-mapping-failed]", message="bad state")
    metadata = _error_registry()[payload.code]

    exc = GraphAgentError("bad state", payload=payload)

    dumped = exc.payload.model_dump()
    assert dumped["code"] == "[F-v3-runtime-state-mapping-failed]"
    assert dumped["level"] == "FATAL"
    assert dumped["stage"] == ("运行期",)
    assert dumped["message"] == "bad state"
    assert dumped["doc_link"] == metadata.doc_link


def test_concrete_graph_agent_error_subclass_exposes_payload() -> None:
    ErrorPayload = _error_payload_model()
    payload = ErrorPayload(code="[F-v3-tool-argument-invalid]", message="bad argument")
    metadata = _error_registry()[payload.code]

    exc = GraphAgentFatalError("bad argument", payload=payload)

    assert exc.payload.model_dump()["code"] == "[F-v3-tool-argument-invalid]"
    assert exc.payload.model_dump()["doc_link"] == metadata.doc_link


def test_graph_agent_error_generated_payload_carries_context_details(tmp_path: Path) -> None:
    exc = GraphAgentFatalError(
        "[F-v3-runtime-state-mapping-failed] bad state",
        context={"phase": "draft", "path": tmp_path / "state.json"},
    )

    assert exc.payload is not None
    assert exc.payload.details["context"] == {
        "phase": "draft",
        "path": str(tmp_path / "state.json"),
    }


def test_graph_agent_error_merges_explicit_payload_details_and_context(tmp_path: Path) -> None:
    ErrorPayload = _error_payload_model()
    payload = ErrorPayload(
        code="[F-v3-runtime-state-mapping-failed]",
        message="bad state",
        details={"hint": "keep", "context": {"priority": "payload"}},
    )

    exc = GraphAgentError(
        "bad state",
        payload=payload,
        context={"phase": "draft", "priority": "exception", "path": tmp_path / "state.json"},
    )

    assert exc.payload is payload
    assert exc.payload.details["hint"] == "keep"
    assert exc.payload.details["context"] == {
        "phase": "draft",
        "priority": "payload",
        "path": str(tmp_path / "state.json"),
    }


def test_gateway_external_error_code_compatibility_keeps_payload_absent() -> None:
    exc = GraphAgentError(
        "[F-v3-gateway-provider-timeout] upstream failed",
        context={"provider": "test"},
    )

    assert exc.payload is None
    assert exc.context == {"provider": "test"}


def test_skill_compilation_error_maps_location_fields_into_payload(tmp_path: Path, mock_skill_resolver: object) -> None:
    ErrorPayload = _error_payload_model()
    skill_path = tmp_path / "GRAPH.md"
    payload = ErrorPayload(code="[F-v3-graph-schema-unknown-field]", message="bad field")

    exc = SkillCompilationError(
        "bad field",
        payload=payload,
        skill_path=skill_path,
        field_path="io.inputs",
    )

    assert exc.payload.source_path == str(skill_path)
    assert exc.payload.field_path == "io.inputs"


def test_loader_failure_asserts_payload_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-graph-root-missing]"


def test_runtime_failure_asserts_payload_code() -> None:
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
    with pytest.raises(GraphAgentFatalError) as exc_info:
        state = WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])
        mapper = StateMapper(output_schema={"type": "object", "properties": {"text": {}}})
        mapper.wrap_phase_output(state, {"data": {"extra": "undeclared"}})

    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_builtin_tool_failure_asserts_payload_code(tmp_path: Path, mock_skill_resolver: object) -> None:
    with pytest.raises(GraphAgentFatalError) as exc_info:
        read_declared_reference(root=tmp_path, references={}, reference_id="missing")

    assert exc_info.value.payload.code == "[F-v3-resource-reference-not-found]"


def test_error_registry_entries_have_complete_nonempty_metadata() -> None:
    registry = _error_registry()

    assert len(registry) == len(_spec_codes()) == 98
    for code, metadata in registry.items():
        assert metadata.code == code
        assert metadata.code
        assert metadata.level
        assert metadata.stage
        assert all(stage for stage in metadata.stage)
        assert metadata.doc_link


def test_pr4_compile_recursion_error_codes_are_registered() -> None:
    registry = _error_registry()

    for code in (
        "[F-v3-compile-recursion-cycle]",
        "[F-v3-compile-depth-exceeded]",
    ):
        metadata = registry[code]
        assert metadata.code == code
        assert metadata.level == "FATAL"
        assert "编译期" in metadata.stage
        assert metadata.doc_link


def test_golden_stale_fields_error_code_is_registered_for_eval_phase() -> None:
    registry = _error_registry()

    metadata = registry["[F-v3-golden-stale-fields]"]

    assert metadata.code == "[F-v3-golden-stale-fields]"
    assert metadata.level == "FATAL"
    assert metadata.stage == ("eval 期",)
    assert "golden-eval" in metadata.doc_link


def test_error_registry_preserves_warn_level_for_reference_reader_fallback() -> None:
    registry = _error_registry()

    assert registry["[F-v3-reference-reader-failed]"].level == "WARN"


def test_error_payload_requires_nonempty_message() -> None:
    ErrorPayload = _error_payload_model()

    with pytest.raises(ValueError):
        ErrorPayload(code="[F-v3-graph-phase-cycle]")
    with pytest.raises(ValueError):
        ErrorPayload(code="[F-v3-graph-phase-cycle]", message="")


def test_engine_source_has_no_coarse_error_code_literals() -> None:
    coarse_codes = {f"[F-v3-{suffix}]" for suffix in ("route", "io", "graph", "actions", "purity")}
    source_root = REPO_ROOT / "packages" / "graph-agent" / "src" / "graph_agent"
    occurrences: list[str] = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for code in coarse_codes:
            if code in text:
                occurrences.append(f"{path.relative_to(REPO_ROOT)}:{code}")

    assert occurrences == []


def test_error_payload_json_boundary_shape_uses_required_keys_and_stage_array() -> None:
    import json

    ErrorPayload = _error_payload_model()
    payload = ErrorPayload(code="[F-v3-graph-phase-cycle]", message="cycle")

    data = json.loads(payload.model_dump_json())

    assert {"code", "level", "stage", "message", "doc_link"} <= set(data)
    assert data["code"] == "[F-v3-graph-phase-cycle]"
    assert data["level"] == "FATAL"
    assert data["stage"] == ["编译期"]
    assert data["message"] == "cycle"
    assert data["doc_link"]
