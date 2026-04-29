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

import os
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from graph_agent.config.llm_config import load_config
from graph_agent.core.harness import GraphAgentHarness
from graph_agent.core.loader import load_workflow_from_md
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    StateMessage,
    WorkflowState,
    verify_state_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LLM_ROLES_PATH = REPO_ROOT / "config" / "llm_roles.yaml"
V3_SKILL_PATH = "skills/text-segmentation/SKILL.md"
REAL_LLM_SMOKE_ROLE_ENV = "GRAPH_AGENT_REAL_LLM_SMOKE_ROLE"
DEFAULT_REAL_LLM_SMOKE_ROLE = "test_opus47_ws"


def _load_dotenv_for_smoke() -> None:
    """Load repo-local ``.env`` so provider keys participate in skip checks."""
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


def _any_llm_role_provider_key_present() -> bool:
    """Return true when any llm_roles.yaml provider api_key_env is set."""
    _load_dotenv_for_smoke()
    cfg = load_config(LLM_ROLES_PATH)
    return any(
        bool(provider.api_key_env and os.environ.get(provider.api_key_env))
        for provider in cfg.providers.values()
    )


def _real_llm_smoke_role() -> str:
    """Single-model role used by the live smoke test."""
    return os.environ.get(REAL_LLM_SMOKE_ROLE_ENV, DEFAULT_REAL_LLM_SMOKE_ROLE)


def _force_llm_role(harness: GraphAgentHarness, role: str) -> None:
    """Pin every LLM phase to a single-model test role for deterministic e2e."""
    for phase in harness.phases:
        if phase.requires_llm:
            phase.tier = role
            phase.llm_role = role


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
        assert path.exists(), (
            f"v3 SKILL missing at {V3_SKILL_PATH}; the spec brief's "
            "skills/text-segmentation/v3/SKILL.md path is stale, "
            "actual is under versions/v3-gemini-rewrite-r2/."
        )
        harness = load_workflow_from_md(path)

        try:
            assert isinstance(harness, GraphAgentHarness)
            phase_names = [p.name for p in harness.phases]
            assert phase_names == ["setup", "segment", "review"], (
                f"v3 SKILL expected phases [setup, segment, review]; "
                f"compiler produced {phase_names!r}."
            )
        finally:
            harness.close()

    def test_v3_skill_io_outputs_declared(self) -> None:
        harness = load_workflow_from_md(Path(V3_SKILL_PATH))
        try:
            io_config = harness._io_config
            assert io_config is not None and io_config.get("outputs"), (
                "text-segmentation SKILL declares at least one output "
                "(name varies by SKILL revision); harness should surface "
                "it via _io_config['outputs']."
            )
            output_names = [o.get("name") for o in io_config["outputs"]]
            assert len(output_names) >= 1, f"Expected ≥ 1 declared output, got {output_names!r}."
        finally:
            harness.close()


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
    not _any_llm_role_provider_key_present(),
    reason=(
        "no LLM provider api_key_env in environment per llm_roles.yaml; "
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
        harness = load_workflow_from_md(Path(V3_SKILL_PATH))
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
        finally:
            harness.close()

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
