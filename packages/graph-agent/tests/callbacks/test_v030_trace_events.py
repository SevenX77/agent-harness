from __future__ import annotations

import json
from pathlib import Path

from graph_agent.callbacks.events import (
    AmbiguityLoggedEvent,
    BuiltinSubagentEnterEvent,
    BuiltinSubagentExitEvent,
    BuiltinSubagentFallbackEvent,
    CallbackEvent,
)
from graph_agent.callbacks.tracing import TracingCallback
from graph_agent.cognitive.ambiguity import log_ambiguity
from graph_agent.core.graph_assembler import _reference_reader_markdown
from graph_agent.core.loader import CompiledSkill, PhaseDocument
from graph_agent.core.manifest import AgentNodeAST, GraphManifest, PhaseIOSchema, ReferenceSpec
from pydantic import TypeAdapter


class Collector:
    def __init__(self) -> None:
        self.events: list[object] = []

    def on_event(self, event: object) -> None:
        self.events.append(event)


def test_log_ambiguity_emits_v030_ambiguity_logged_event() -> None:
    collector = Collector()
    ctx = {"_current_phase": "main", "_callbacks": [collector]}

    result = json.loads(
        log_ambiguity(
            question="How should @reference:R1 be interpreted?",
            ambiguity_type="ambiguous_requirement",
            decision="Use conservative reading.",
            reason="Protocol @protocol:P1 is closest.",
            ctx=ctx,
        )
    )

    assert result["status"] == "recorded"
    event = collector.events[0]
    assert isinstance(event, AmbiguityLoggedEvent)
    assert event.phase_name == "main"
    assert event.related_reference_ids == ["R1"]
    assert event.related_protocol_ids == ["P1"]


def test_builtin_subagent_trace_events_round_trip_through_callback_union() -> None:
    adapter = TypeAdapter(CallbackEvent)

    for event in [
        BuiltinSubagentEnterEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentExitEvent(phase_name="main", builtin_name="reference_reader"),
        BuiltinSubagentFallbackEvent(
            phase_name="main",
            builtin_name="reference_reader",
            fallback_reason="config_missing",
            fallback_strategy="raw_excerpt",
            excerpt_token_limit=3000,
            warning_message="[F-v3-reference-reader-failed] missing config",
        ),
    ]:
        parsed = adapter.validate_python(event.model_dump())
        assert parsed.event_type == event.event_type


def test_tracing_callback_writes_v030_typed_events(tmp_path: Path) -> None:
    tracer = TracingCallback(trace_dir=tmp_path)
    tracer.on_event(
        BuiltinSubagentFallbackEvent(
            phase_name="main",
            builtin_name="reference_reader",
            fallback_reason="remote_timeout",
            fallback_strategy="raw_excerpt",
            excerpt_token_limit=3000,
        )
    )

    lines = (tmp_path / "tracing.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    assert payload["event_type"] == "builtin_subagent_fallback"
    assert payload["fallback_reason"] == "remote_timeout"
    assert payload["payload"]["fallback_reason"] is None


def test_reference_reader_emits_enter_and_exit_events(tmp_path: Path) -> None:
    phase_doc, phase_ast, compiled = _reference_reader_fixture(tmp_path)
    collector = Collector()

    markdown = _reference_reader_markdown(phase_doc, phase_ast, compiled, [collector])

    assert "reference content" in markdown
    assert [event.event_type for event in collector.events] == [
        "builtin_subagent_enter",
        "builtin_subagent_exit",
    ]
    enter, exit_event = collector.events
    assert isinstance(enter, BuiltinSubagentEnterEvent)
    assert enter.payload.trigger_stage == "assembly"
    assert enter.payload.reference_ids == ["R1"]
    assert isinstance(exit_event, BuiltinSubagentExitEvent)
    assert exit_event.payload.used_reference_ids == ["R1"]


def test_reference_reader_emits_fallback_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    phase_doc, phase_ast, compiled = _reference_reader_fixture(tmp_path)
    collector = Collector()

    def _fail(_payload):
        raise ValueError("[F-v3-reference-reader-output-invalid] bad markdown")

    monkeypatch.setattr("graph_agent.core.graph_assembler._run_reference_reader_wrapped", _fail)

    markdown = _reference_reader_markdown(phase_doc, phase_ast, compiled, [collector])

    assert "raw excerpt fallback" in markdown
    assert [event.event_type for event in collector.events] == [
        "builtin_subagent_enter",
        "builtin_subagent_fallback",
    ]
    fallback = collector.events[1]
    assert isinstance(fallback, BuiltinSubagentFallbackEvent)
    assert fallback.fallback_reason == "invalid_output"
    assert fallback.excerpt_token_limit == 3000
    assert fallback.payload.fallback_reason == "invalid_output"
    assert fallback.payload.fallback_strategy == "raw_excerpt"
    assert fallback.payload.warning_message is not None


def _reference_reader_fixture(
    tmp_path: Path,
) -> tuple[PhaseDocument, AgentNodeAST, CompiledSkill]:
    skill_root = tmp_path / "skill"
    phase_dir = skill_root / "phases" / "main"
    phase_dir.mkdir(parents=True)
    phase_path = phase_dir / "SKILL.md"
    phase_path.write_text("", encoding="utf-8")
    (skill_root / "ref.md").write_text("reference content", encoding="utf-8")
    io = PhaseIOSchema(inputs={"topic": {"type": "string"}}, outputs={"answer": {"type": "string"}})
    phase_ast = AgentNodeAST(
        mode="agent",
        role="reader",
        goal="read references",
        exit_contract="return answer",
        io=io,
        references=[ReferenceSpec(id="R1", path="ref.md", summary="Reference one")],
    )
    phase_doc = PhaseDocument(
        phase_name="main",
        path=phase_path,
        mode="agent",
        frontmatter={},
        raw_blocks={},
        ast=phase_ast,
    )
    manifest = GraphManifest(name="test-skill", io=io, phases=[])
    return phase_doc, phase_ast, CompiledSkill(raw={"io": {}}, manifest=manifest, nodes=[phase_doc])
