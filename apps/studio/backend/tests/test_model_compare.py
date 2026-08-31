"""PR2 node-level Compare LLMs — isolated single-node side-run mechanics.

Covers the three things a candidate side-run is assembled from: the input slice
extracted from a base run's events, the single-node skill variant (which really
compiles + runs with that slice), and the candidate roles data — including that
it resolves for every role the node's execution can ask for, not just the node's
own. The orchestration/spawn path is covered in the API test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.models.model_compare import CompareCandidate
from app.services.model_compare import (
    CompareNodeInputMissingError,
    extract_node_input,
    materialize_single_node_skill,
    node_effective_role,
)
from graph_agent.core.compiler import compile_skill
from graph_agent.core.event_contracts import make_event_envelope
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _two_phase_skill(root: Path) -> Path:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: two-phase
io:
  inputs: {type: object, properties: {}}
  outputs:
    type: object
    required: [report]
    properties: {report: {type: string}}
phases: [prepare, score]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>score</phase>
""",
    )
    _write(
        root / "phases" / "prepare" / "LOGIC.md",
        """---
io:
  inputs: {type: object, properties: {}}
  outputs:
    type: object
    required: [seed]
    properties: {seed: {type: integer}}
actions: [prepare]
validator: false
---
<action>prepare</action>
""",
    )
    _write(root / "phases" / "prepare" / "actions" / "prepare.py", "def prepare(inputs):\n    return {'seed': 3}\n")
    _write(
        root / "phases" / "score" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    required: [seed]
    properties: {seed: {type: integer}}
  outputs:
    type: object
    required: [report]
    properties: {report: {type: string}}
actions: [score]
validator: false
---
<action>score</action>
""",
    )
    _write(
        root / "phases" / "score" / "actions" / "score.py",
        "def score(inputs):\n    return {'report': f\"scored {inputs['seed']}\"}\n",
    )
    return root


# ---------------------------------------------------------------------------
# extract_node_input
# ---------------------------------------------------------------------------


def _dispatch_event(run_id: str, seq: int, to_phase: str, snapshot: dict) -> object:
    return make_event_envelope(
        stream_id=f"run:{run_id}",
        seq=seq,
        run_id=run_id,
        event_type="input_dispatch",
        payload={
            "event_type": "input_dispatch",
            "from_phase": None,
            "to_phase": to_phase,
            "changed_keys": list(snapshot),
            "blackboard_snapshot": snapshot,
            "dispatched_keys": list(snapshot),
            "branch_index": None,
        },
        cursor=f"run:{run_id}:{seq}",
        timestamp=datetime.now(tz=UTC),
    )


def test_extract_node_input_returns_dispatched_slice() -> None:
    events = [
        _dispatch_event("r1", 1, "prepare", {}),
        _dispatch_event("r1", 2, "score", {"seed": 3}),
    ]
    assert extract_node_input(events, "score") == {"seed": 3}


def test_extract_node_input_missing_raises() -> None:
    events = [_dispatch_event("r1", 1, "prepare", {})]
    with pytest.raises(CompareNodeInputMissingError):
        extract_node_input(events, "score")


def test_extract_node_input_uses_last_dispatch() -> None:
    # a re-dispatched node (retry/loop) -> take the latest slice
    events = [
        _dispatch_event("r1", 1, "score", {"seed": 1}),
        _dispatch_event("r1", 2, "score", {"seed": 9}),
    ]
    assert extract_node_input(events, "score") == {"seed": 9}


# ---------------------------------------------------------------------------
# materialize_single_node_skill  (compiles + runs)
# ---------------------------------------------------------------------------


def test_materialize_single_node_compiles_and_runs(tmp_path: Path) -> None:
    skill = _two_phase_skill(tmp_path / "skill")
    variant = materialize_single_node_skill(skill, "score", tmp_path / "variant")

    compiled = compile_skill(variant, cache=False)
    assert [n.phase_name for n in compiled.nodes] == ["score"]
    # only the target phase dir survives
    assert (variant / "phases" / "score").is_dir()
    assert not (variant / "phases" / "prepare").exists()

    assembled = assemble_graph(compiled)
    init = WorkflowState(
        data=BusinessData.model_validate({"seed": 3}),
        flow=FrameworkState(),
        messages=[],
    )
    result = assembled.graph.invoke(init)
    assert result["data"].model_dump()["report"] == "scored 3"


def test_materialize_unknown_node_raises(tmp_path: Path) -> None:
    skill = _two_phase_skill(tmp_path / "skill")
    with pytest.raises(ValueError, match="not found"):
        materialize_single_node_skill(skill, "nope", tmp_path / "variant")


def test_node_effective_role_agent_without_role_is_refused(tmp_path: Path) -> None:
    # J-X.10 (用户裁决 2026-08-31): no invented fallback. An AGENT node that
    # resolves no role is refused with the fix spelled out, instead of quietly
    # binding the deleted conventional name.
    skill = tmp_path / "skill"
    _write(skill / "GRAPH.md", _AGENT_ONLY_GRAPH)
    _write(
        skill / "phases" / "write" / "SKILL.md",
        _CHILD_AGENT.replace("llm_role: analyst\n", ""),
    )
    with pytest.raises(ValueError, match="resolves no LLM role"):
        node_effective_role(skill, "write")


def test_node_effective_role_logic_node_without_graph_default_is_none(tmp_path: Path) -> None:
    # A LOGIC node consumes no role itself; with no graph default there is
    # nothing to bind — None, not an invented name and not an error.
    skill = _two_phase_skill(tmp_path / "skill")
    assert node_effective_role(skill, "score") is None


# ---------------------------------------------------------------------------
# build_candidate_roles
# ---------------------------------------------------------------------------


_SUBGRAPH_HOST_GRAPH = """---
schema_version: "v0.3.0"
name: subgraph-host
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [headline]
    properties:
      headline: {type: string}
phases: [delegate]
---
<phase depends_on="input" output>delegate</phase>
"""

_SUBGRAPH_MARKER = """---
name: delegate
path: ./child
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [headline]
    properties:
      headline: {type: string}
---
"""

_CHILD_GRAPH = """---
schema_version: "v0.3.0"
name: subgraph-child
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [headline]
    properties:
      headline: {type: string}
phases: [write]
---
<phase depends_on="input" output>write</phase>
"""

_CHILD_AGENT = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [headline]
    properties:
      headline: {type: string}
---
<role>Headline writer.</role>
<goal>Write one headline for the topic, then finish the task.</goal>
"""


def _subgraph_skill(root: Path) -> Path:
    """A root graph whose only node is a SUBGRAPH; the inner phase wants `analyst`.

    This is the shape the lab skill has: nothing at root level declares a role,
    so the SUBGRAPH node resolves no role of its own (J-X.10: no conventional
    fallback), while the role the run actually asks for lives one level down.
    """
    _write(root / "GRAPH.md", _SUBGRAPH_HOST_GRAPH)
    _write(root / "phases" / "delegate" / "SUBGRAPH.md", _SUBGRAPH_MARKER)
    _write(root / "child" / "GRAPH.md", _CHILD_GRAPH)
    _write(root / "child" / "phases" / "write" / "SKILL.md", _CHILD_AGENT)
    return root


_CANDIDATE_ROUTE = "ark-lab:seed-lite"
_ANALYST_ROUTE = "openai-direct:gpt-5"


def _settings_with_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point Studio settings at a tmp dir holding both the analyst and candidate routes."""
    from app.core import config
    from app.core.backends import clear_backend_caches
    from app.models.llm_config import (
        LLMCredentialsFile,
        ProviderEndpoint,
        ProviderRoute,
    )
    from app.services.llm_credentials import save_credentials

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_GATEWAY_TRANSPORT", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    clear_backend_caches()
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": ProviderEndpoint(
                    endpoint_id="openai-direct",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                ),
                "ark-lab": ProviderEndpoint(
                    endpoint_id="ark-lab",
                    display_name="Ark",
                    protocol="openai_compatible",
                    base_url="https://ark.example/v3",
                    api_key="secret",
                ),
            },
            provider_routes={
                _ANALYST_ROUTE: ProviderRoute(
                    route_id=_ANALYST_ROUTE,
                    endpoint_id="openai-direct",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                ),
                _CANDIDATE_ROUTE: ProviderRoute(
                    route_id=_CANDIDATE_ROUTE,
                    endpoint_id="ark-lab",
                    route_slug="seed-lite",
                    provider_model_id="seed-lite",
                    canonical_id="seed-lite",
                    display_name="Seed Lite",
                    status="verified",
                ),
            },
        ),
        settings_dir / "llm" / "llm_credentials.json",
    )
    return settings_dir


def _save_active_roles(settings_dir: Path) -> Path:
    """Write an active roles truth whose `analyst` is NOT the conventional role."""
    from app.models.llm_config import (
        RoleEntry,
        RoleIntent,
        RoleModelGroup,
        RoleProviderModel,
        RoleRouteEntry,
        RolesData,
    )
    from app.services.llm_roles import save_roles_file

    path = settings_dir / "llm" / "llm_roles.yaml"
    save_roles_file(
        path,
        RolesData(
            schema_version=3,
            roles={
                "analyst": RoleEntry(
                    system_prompt_prefix="You are the analyst.",
                    intent=RoleIntent(temperature=1.9),
                    model_groups=[
                        RoleModelGroup(
                            canonical_id="gpt-5",
                            display_name="GPT-5",
                            provider_models=[RoleProviderModel(route_id=_ANALYST_ROUTE)],
                        )
                    ],
                    fallback_chain=[RoleRouteEntry(route_id=_ANALYST_ROUTE)],
                )
            },
        ),
    )
    return path


def _candidate() -> CompareCandidate:
    return CompareCandidate(candidate_id="c1", model_group_id="seed-lite", route="auto")


def test_build_candidate_roles_materializes_an_executable_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compare candidate's role must arrive at the engine ready to run.

    The engine resolves a role through its ``fallback_chain``; ``model_groups``
    is authoring intent that Settings materializes on save. A candidate role
    written with groups only resolves to nothing, and the side-run dies with
    ``resource.no_available_route`` before it makes a single call.
    """
    from app.services.model_compare import build_candidate_roles

    _settings_with_both_routes(tmp_path, monkeypatch)

    skill = tmp_path / "skill"
    _write(skill / "GRAPH.md", _AGENT_ONLY_GRAPH)
    _write(skill / "phases" / "write" / "SKILL.md", _CHILD_AGENT)
    roles = build_candidate_roles(skill, "write", _candidate())

    entry = roles.roles["analyst"]
    assert [route.route_id for route in entry.fallback_chain] == [_CANDIDATE_ROUTE]


def test_build_candidate_roles_swaps_the_model_for_every_role_in_the_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every role the run can ask for must land on the candidate model.

    A SUBGRAPH node resolves no role of its own (J-X.10: no conventional
    fallback), but the phases INSIDE the subgraph declare their own roles.
    Binding only the node's effective role leaves those undefined in the
    candidate roles file, and the side-run dies at ``analyst`` with
    ``resource.no_available_route``.
    """
    from app.services.model_compare import build_candidate_roles

    settings_dir = _settings_with_both_routes(tmp_path, monkeypatch)
    _save_active_roles(settings_dir)

    skill = _subgraph_skill(tmp_path / "skill")
    roles = build_candidate_roles(skill, "delegate", _candidate())

    assert "analyst" in roles.roles, (
        "the role the subgraph's inner phase asks for is missing from the "
        f"candidate roles file: {sorted(roles.roles)}"
    )
    assert [route.route_id for route in roles.roles["analyst"].fallback_chain] == [
        _CANDIDATE_ROUTE
    ]
    # The role-less SUBGRAPH node itself adds no entry (J-X.10: nothing to bind).
    assert "graph_agent" not in roles.roles


_AGENT_ONLY_GRAPH = """---
schema_version: "v0.3.0"
name: agent-only
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [headline]
    properties:
      headline: {type: string}
phases: [write]
---
<phase depends_on="input" output>write</phase>
"""


def test_build_candidate_roles_still_binds_an_agent_nodes_own_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An AGENT node's declared role is bound even when the truth has no such role.

    ``reviewer`` exists nowhere in the roles truth; the node's effective role is
    still what the run will ask for, so it must be present in the candidate file.
    """
    from app.services.model_compare import build_candidate_roles

    settings_dir = _settings_with_both_routes(tmp_path, monkeypatch)
    _save_active_roles(settings_dir)

    skill = tmp_path / "skill"
    _write(skill / "GRAPH.md", _AGENT_ONLY_GRAPH)
    _write(skill / "phases" / "write" / "SKILL.md", _CHILD_AGENT.replace("analyst", "reviewer"))

    assert node_effective_role(skill, "write") == "reviewer"
    roles = build_candidate_roles(skill, "write", _candidate())

    assert [route.route_id for route in roles.roles["reviewer"].fallback_chain] == [
        _CANDIDATE_ROUTE
    ]
    assert "analyst" in roles.roles


def test_build_candidate_roles_keeps_each_role_params_and_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Comparison means only the MODEL differs — a role keeps its own params."""
    from app.services.model_compare import build_candidate_roles

    settings_dir = _settings_with_both_routes(tmp_path, monkeypatch)
    _save_active_roles(settings_dir)

    skill = _subgraph_skill(tmp_path / "skill")
    roles = build_candidate_roles(skill, "delegate", _candidate())

    analyst = roles.roles["analyst"]
    assert analyst.intent.temperature == 1.9
    assert analyst.system_prompt_prefix == "You are the analyst."


def test_candidate_roles_file_resolves_the_inner_role_to_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end on the real seam: the worker resolves roles from this file.

    ``_run_worker_main`` points ``STUDIO_LLM_ROLES_PATH`` at the written file and
    the engine resolver reads it as the WHOLE roles truth, so whatever role the
    run asks for must resolve there — to the candidate's route.
    """
    from app.services.gateway_resolver import build_gateway_model_resolver
    from app.services.model_compare import write_candidate_roles_file

    settings_dir = _settings_with_both_routes(tmp_path, monkeypatch)
    _save_active_roles(settings_dir)

    skill = _subgraph_skill(tmp_path / "skill")
    roles_file = write_candidate_roles_file(
        skill, "delegate", _candidate(), tmp_path / "group"
    )

    resolver = build_gateway_model_resolver(roles_file)
    resolved = resolver.resolve_routes("analyst")
    assert [route.route_id for route in resolved.routes] == [_CANDIDATE_ROUTE]
