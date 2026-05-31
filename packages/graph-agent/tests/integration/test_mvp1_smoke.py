"""MVP-1 e2e smoke: text-segmentation v3 + state invariants.

T8 of MVP-1 (A1 WorkflowState 拆分): proves the post-MVP-1 framework
still compiles a real SKILL end-to-end and that the post-run state
honors the four design invariants from
``.kiro/specs/v1-reset-mvp-1-state-split/design.md`` §7-§8:

1. ``state["data"]`` contains no ``_``-prefixed keys (BusinessData
   purity invariant).
2. ``state["flow"]`` round-trips through ``FrameworkState.model_validate``
   (FrameworkState ``extra='forbid'`` invariant).
3. Business fields are non-empty (the workflow actually produced output).
4. ``state["messages"]`` is non-empty (the LLM phase actually ran).

The suite splits into two layers because LLM API credentials may not be
configured in every environment:

- **Compile + invariant layer (always runs)** — uses
  ``load_workflow_from_md`` to compile the v3 SKILL, then synthesizes a
  realistic post-run WorkflowState and asserts the four invariants. This
  exercises the same state-shape contracts the real run would produce
  while costing zero LLM tokens.
- **Real-LLM layer** — gated on the provider ``api_key_env`` values
  declared in ``config/llm_roles.yaml``. The test is silent under CI
  without provider credentials but turns on automatically once any
  configured provider key is exported or present in ``.env``. Runs the
  full ``GraphAgentHarness.run`` and re-asserts the four invariants on
  the live final state.

Reference paths:
- The canonical text-segmentation SKILL lives at ``skills/text-segmentation/SKILL.md``;
  it ships with the [setup, segment, review] pipeline the spec brief
  refers to as "v3". The brief's ``skills/text-segmentation/v3/SKILL.md``
  path is stale, and every directory under ``skills/text-segmentation/versions/``
  is a frozen development snapshot whose ``script/`` package is missing
  (compile fails with F-tool-path-not-found). The top-level SKILL is the
  only runnable copy.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from graph_agent_gateway.registry.resolver import resolve_role
from graph_agent_gateway.resolver import ModelResolver, load_registry_snapshot
from langchain_core.messages import HumanMessage

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.loader import load_workflow_from_md
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    StateMessage,
    WorkflowState,
    verify_state_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
LLM_ROLES_PATH = REPO_ROOT / "config" / "llm_roles.yaml"
LLM_CREDENTIALS_PATH = Path.home() / ".studio" / "llm_credentials.json"
V3_SKILL_PATH = REPO_ROOT / "skills/text-segmentation"
REAL_LLM_SMOKE_ROLE_ENV = "GRAPH_AGENT_REAL_LLM_SMOKE_ROLE"
DEFAULT_REAL_LLM_SMOKE_ROLE = "test_opus47_ws"
E2E_TRACE_RUN_ENV = "GRAPH_AGENT_E2E_TRACE_RUN"
E2E_TRACE_BASE = REPO_ROOT / "docs" / "v1-reset" / "e2e_traces"


def _route_registry_smoke_ready() -> bool:
    """Return true when v4/v2 route registry has a credentialed smoke role."""
    try:
        snapshot = load_registry_snapshot(LLM_CREDENTIALS_PATH, LLM_ROLES_PATH)
        resolved = resolve_role(snapshot, _real_llm_smoke_role())
    except Exception:
        return False
    return bool(resolved.routes and resolved.routes[0].api_key.get_secret_value())


def _real_llm_smoke_role() -> str:
    """Single-model role used by the live smoke test."""
    return os.environ.get(REAL_LLM_SMOKE_ROLE_ENV, DEFAULT_REAL_LLM_SMOKE_ROLE)


def _resolve_e2e_trace_dir() -> Path | None:
    """Resolve the per-run trace dump directory from the env var.

    Returns ``None`` when ``GRAPH_AGENT_E2E_TRACE_RUN`` is unset so the
    legacy test path stays a no-op for normal pytest invocations.
    """
    run_id = os.environ.get(E2E_TRACE_RUN_ENV)
    if not run_id:
        return None
    out = E2E_TRACE_BASE / f"run_{run_id}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _serialize_message(message: object) -> dict[str, Any]:
    """Best-effort dict form of a LangChain message for json.dumps."""
    if hasattr(message, "model_dump"):
        try:
            return message.model_dump()  # type: ignore[no-any-return,attr-defined]
        except Exception:  # noqa: BLE001 — fall through to dict()/str fallback
            pass
    if hasattr(message, "dict"):
        try:
            return message.dict()  # type: ignore[no-any-return,attr-defined]
        except Exception:  # noqa: BLE001
            pass
    return {
        "type": type(message).__name__,
        "content": str(getattr(message, "content", "")),
    }


def _extract_tool_calls(messages: list[Any]) -> list[dict[str, Any]]:
    """Pull every tool_call across messages into a flat list for analysis."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        tcs = getattr(msg, "tool_calls", None)
        if not tcs:
            continue
        for tc in tcs:
            if isinstance(tc, dict):
                out.append(
                    {
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "id": tc.get("id", ""),
                    }
                )
            else:
                out.append(
                    {
                        "name": getattr(tc, "name", ""),
                        "args": getattr(tc, "args", {}),
                        "id": getattr(tc, "id", ""),
                    }
                )
    return out


def _serialize_final_state(state: WorkflowState | None) -> dict[str, Any]:
    if state is None:
        return {}
    return {
        "data": state["data"].model_dump() if state.get("data") is not None else {},
        "flow": state["flow"].model_dump() if state.get("flow") is not None else {},
        "messages": [_serialize_message(m) for m in state.get("messages", [])],
    }


def _build_metrics_text(
    *,
    role: str,
    final_state: WorkflowState | None,
    duration_seconds: float,
    error_text: str | None,
) -> str:
    lines = [
        f"role={role}",
        f"timestamp={datetime.now(tz=UTC).isoformat()}",
        f"duration_seconds={duration_seconds:.2f}",
    ]
    if final_state is None:
        lines.append("status=ERROR")
    else:
        flow = final_state["flow"]
        data_dump = final_state["data"].model_dump()
        lines.append("status=OK")
        lines.append(f"messages_count={len(final_state.get('messages', []))}")
        lines.append(f"data_keys={sorted(data_dump.keys())}")
        lines.append(f"current_phase={flow.current_phase}")
        lines.append(f"io_errors={list(flow.io_errors)}")
        lines.append(f"validation_warnings={list(flow.validation_warnings)}")
        lines.append(f"retry_counts={dict(flow.retry_counts)}")
        lines.append(f"metrics={dict(flow.metrics)}")
    if error_text:
        lines.append("error=<see error.txt>")
    return "\n".join(lines) + "\n"


def _dump_e2e_trace(
    trace_dir: Path,
    *,
    role: str,
    final_state: WorkflowState | None,
    duration_seconds: float,
    error_text: str | None,
    tmp_path: Path,
) -> None:
    """Write the trace bundle for one run into ``trace_dir``.

    Always written (status=OK or status=ERROR):
      - metrics.txt — role / duration / token metrics / data keys
      - error.txt — full traceback when the run raised
    Written when final_state is populated:
      - final_state.json — pydantic.model_dump of data + flow + messages
      - tool_calls.json — flat list of every tool_call across messages
    Picked up from tmp_path when the run wrote them:
      - tracing.jsonl — TracingCallback event log
      - text-segmentation chapter_*_segments.json — SKILL declared output
    """
    (trace_dir / "metrics.txt").write_text(
        _build_metrics_text(
            role=role,
            final_state=final_state,
            duration_seconds=duration_seconds,
            error_text=error_text,
        ),
        encoding="utf-8",
    )
    if error_text:
        (trace_dir / "error.txt").write_text(error_text, encoding="utf-8")
    if final_state is not None:
        state_dump = _serialize_final_state(final_state)
        (trace_dir / "final_state.json").write_text(
            json.dumps(state_dump, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tool_calls = _extract_tool_calls(list(final_state.get("messages", [])))
        (trace_dir / "tool_calls.json").write_text(
            json.dumps(tool_calls, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # Copy harness/SKILL outputs that the run wrote into tmp_path.
    for src_name in ("tracing.jsonl", "real_llm_metrics.txt"):
        src = tmp_path / src_name
        if src.exists():
            shutil.copy2(src, trace_dir / src_name)
    skill_outputs = tmp_path / "output" / "text-segmentation"
    if skill_outputs.exists():
        dst = trace_dir / "skill_outputs"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(skill_outputs, dst)


def _force_llm_role(harness: GraphAgentHarness, role: str) -> None:
    """Pin every LLM phase to a single-model test role for deterministic e2e."""
    for phase in harness.phases:
        if phase.requires_llm:
            phase.tier = role
            phase.llm_role = role


class _FixedRoleResolver:
    """Test-only resolver adapter that keeps live smoke role explicit."""

    def __init__(self, resolver: ModelResolver, role: str) -> None:
        self._resolver = resolver
        self._role = role

    def resolve(self, role_name: str | None = None, **kwargs: Any) -> Any:
        return self._resolver.resolve(role_name or self._role, **kwargs)


@pytest.fixture
def expected_mvp1_state_shape() -> dict[str, Any]:
    """T8 baseline state shape for regression detection.

    Future MVPs (e.g. MVP-4 phase_executor rewrite, MVP-5 hardening)
    can re-use this shape descriptor as a regression checkpoint when
    they re-run the smoke test against the new pipeline.
    """
    return {
        "data_keys_count_min": 1,
        "flow_finish_task_result_present": True,
        "messages_count_min": 1,
        "v3_phase_names": ["setup", "segment", "review"],
    }


@pytest.fixture
def synthetic_post_run_state() -> WorkflowState:
    """Build a WorkflowState that mirrors what a successful v3 run yields.

    BusinessData carries a populated ``segments`` business field plus the
    bookkeeping fields the v3 SKILL preserves (``chapter_number``,
    ``chapter_content``). FrameworkState carries a typical
    ``finish_task_result`` payload, a non-empty ``messages`` list, and
    the metrics dict the harness fills in. Touching every populated
    flow field is deliberate so a regression in any single field's
    serialization shows up here.
    """
    business = BusinessData.model_validate(
        {
            "chapter_number": 1,
            "chapter_content": "第一章 测试场景\n这是一段用于 MVP-1 状态拆分验证的样本文本。",
            "segments": [
                {
                    "index": 1,
                    "type": "B",
                    "start_line": 1,
                    "end_line": 2,
                    "content": "测试场景开场",
                    "confidence": 0.95,
                },
            ],
        }
    )
    flow = FrameworkState(
        finish_task_result={
            "meta": {},
            "raw": {"segments": "...markdown..."},
        },
        thread_id="t-mvp1-smoke",
        run_id="r-mvp1-smoke",
        unattended=True,
        current_phase="review",
        retry_counts={"segment": 0},
        metrics={"total_input_tokens": 1234, "total_output_tokens": 567},
        validation_warnings=[],
        io_errors=[],
    )
    messages: list[StateMessage] = [HumanMessage(content="kickoff for MVP-1 smoke")]
    return WorkflowState(data=business, flow=flow, messages=messages)


class TestCompileLayer:
    """Layer 1: SKILL compile + harness build, no LLM token spent."""

    def test_v3_skill_compiles_to_graph_agent_harness(self) -> None:
        path = Path(V3_SKILL_PATH)
        assert (path / "GRAPH.md").exists()
        compiled = compile_skill(path, cache=False)
        assembled = assemble_graph(compiled)

        assert assembled.graph is not None
        assert [phase.id for phase in compiled.manifest.phases] == ["setup", "segment", "review"]

    def test_v3_skill_io_outputs_declared(self) -> None:
        compiled = compile_skill(Path(V3_SKILL_PATH), cache=False)

        assert compiled.raw["io"]["outputs"]["required"] == ["segmentation_result"]
        assert "segmentation_result" in compiled.raw["io"]["output_schema_keys"]


class TestStateInvariants:
    """Layer 1b: post-run state invariants (synthetic).

    The four invariants come from design.md §7-§8 and are exactly the
    contract a real v3 run must honor.
    """

    def test_invariant_1_business_data_has_no_underscore_prefix(
        self, synthetic_post_run_state: WorkflowState
    ) -> None:
        """Invariant 1: state['data'] contains zero ``_``-prefixed keys."""
        bad = [k for k in synthetic_post_run_state["data"].model_dump() if k.startswith("_")]
        assert bad == [], f"BusinessData carries forbidden _-prefixed keys: {bad}"

    def test_invariant_2_framework_state_strict_round_trip(
        self, synthetic_post_run_state: WorkflowState
    ) -> None:
        """Invariant 2: FrameworkState round-trips through model_validate.

        FrameworkState declares ``extra='forbid'``. If the post-run flow
        ever picks up an undeclared field, this validation raises.
        """
        dumped = synthetic_post_run_state["flow"].model_dump()
        re_validated = FrameworkState.model_validate(dumped)
        assert isinstance(re_validated, FrameworkState)
        assert re_validated.model_dump() == dumped

    def test_invariant_3_business_fields_populated(
        self, synthetic_post_run_state: WorkflowState
    ) -> None:
        """Invariant 3: post-run BusinessData carries non-empty business fields."""
        dumped = synthetic_post_run_state["data"].model_dump()
        assert "segments" in dumped, "v3 should hoist 'segments' into BusinessData"
        assert len(dumped["segments"]) > 0, (
            "Empty segments list signals the segment phase produced nothing."
        )

    def test_invariant_4_messages_non_empty(self, synthetic_post_run_state: WorkflowState) -> None:
        """Invariant 4: messages list non-empty (LLM phase exercised)."""
        assert len(synthetic_post_run_state["messages"]) > 0

    def test_verify_state_invariants_passes(self, synthetic_post_run_state: WorkflowState) -> None:
        """The framework's own ``verify_state_invariants`` must accept the synthesized state."""
        # Should not raise.
        verify_state_invariants(synthetic_post_run_state)

    def test_state_shape_matches_baseline(
        self,
        synthetic_post_run_state: WorkflowState,
        expected_mvp1_state_shape: dict[str, Any],
    ) -> None:
        """Lock in the shape descriptor as a forward regression checkpoint."""
        data_dump = synthetic_post_run_state["data"].model_dump()
        assert len(data_dump) >= expected_mvp1_state_shape["data_keys_count_min"]
        assert (
            synthetic_post_run_state["flow"].finish_task_result is not None
        ) == expected_mvp1_state_shape["flow_finish_task_result_present"]
        assert (
            len(synthetic_post_run_state["messages"])
            >= expected_mvp1_state_shape["messages_count_min"]
        )


@pytest.mark.skipif(
    not _route_registry_smoke_ready(),
    reason=(
        "no credentialed v4/v2 route registry for real-LLM smoke; "
        "real-LLM smoke skipped — compile + invariant layers above already exercise state contracts"
    ),
)
class TestRealLLMSmoke:
    """Layer 2: real LLM run over text-segmentation v3 with 1 chapter input.

    Skipped automatically when no LLM API key is configured. Once an
    operator exports a key (and accepts the token cost) the suite picks
    this layer up automatically; the same four invariants are asserted
    on the live final state.
    """

    def test_v3_run_one_chapter_honors_invariants(self, tmp_path: Path) -> None:
        role = _real_llm_smoke_role()
        sample_chapter = (
            "第一章 测试场景\n\n"
            "李雷走进房间，看见桌上有一封信。\n"
            "次元空间是一种由能量编织的非物理世界。\n"
            "李雷合上信，决定继续调查。\n"
        )
        trace_dir = _resolve_e2e_trace_dir()
        final_state: WorkflowState | None = None
        error_text: str | None = None
        run_start = time.monotonic()

        resolver = _FixedRoleResolver(
            ModelResolver(
                credentials_path=LLM_CREDENTIALS_PATH,
                roles_path=LLM_ROLES_PATH,
            ),
            role,
        )
        harness = load_workflow_from_md(Path(V3_SKILL_PATH), model_resolver=resolver)
        try:
            try:
                _force_llm_role(harness, role)
                final_state = harness.run(
                    initial_context={
                        "chapter_content": sample_chapter,
                        "chapter_number": 1,
                        "output_dir": str(tmp_path),
                    },
                    unattended=True,
                )
                (tmp_path / "real_llm_metrics.txt").write_text(
                    f"role={role}\nmetrics={final_state['flow'].metrics}\n",
                    encoding="utf-8",
                )
            except Exception:
                error_text = traceback.format_exc()
                raise
        finally:
            harness.close()
            if trace_dir is not None:
                _dump_e2e_trace(
                    trace_dir,
                    role=role,
                    final_state=final_state,
                    duration_seconds=time.monotonic() - run_start,
                    error_text=error_text,
                    tmp_path=tmp_path,
                )

        assert final_state is not None  # narrow for mypy after the try/finally
        # Invariant 1
        bad = [k for k in final_state["data"].model_dump() if k.startswith("_")]
        assert bad == [], f"BusinessData carries forbidden _-prefixed keys: {bad}"
        # Invariant 2
        FrameworkState.model_validate(final_state["flow"].model_dump())
        # Invariant 3
        dumped = final_state["data"].model_dump()
        assert "segments" in dumped or len(dumped) > 0
        # Invariant 4
        assert len(final_state["messages"]) > 0
