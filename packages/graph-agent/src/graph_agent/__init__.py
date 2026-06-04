"""graph_agent - Document-driven LLM agent harness SDK.

Public API (20 stable exports):

* Execution & Interception: ``run_skill``, ``predict_skill``, ``RunResult``,
  ``PathDiff``, ``PhaseRecord``
* Static analysis: ``compile_skill``, ``CompileResult``, ``SkillManifest``,
  ``serialize_skill``
* Graph assembly: ``assemble_graph``, ``CompiledSkill``, ``CompiledStateGraph``
* State: ``BlackboardState``
* Skill resolution: ``LocalWorkspaceResolver``
* Exceptions: ``GraphAgentError``, ``GraphCompileError``,
  ``GraphExecutionError``, ``ModelProviderError``, ``ResourceNotFoundError``

Internal helpers (``Phase``, ``WorkflowState``, ``IOManager``,
``ModelResolver``, ``load_workflow_from_md``,
etc.) live under
``graph_agent.core.*`` / ``graph_agent.io.*`` / ``graph_agent.models.*``
and are not part of the public ABI. Downstream code that depended on
the previous lazy-deprecated re-exports must migrate to the 20-export
surface.

Each ``from X import Y as Y`` re-export is intentional — the explicit
alias form satisfies ``mypy --strict``'s ``no_implicit_reexport`` rule.
"""

from __future__ import annotations

from graph_agent.core.compiler import CompileResult as CompileResult
from graph_agent.core.compiler import compile_skill as compile_skill
from graph_agent.core.exceptions import GraphAgentError as GraphAgentError
from graph_agent.core.exceptions import GraphCompileError as GraphCompileError
from graph_agent.core.exceptions import GraphExecutionError as GraphExecutionError
from graph_agent.core.exceptions import ModelProviderError as ModelProviderError
from graph_agent.core.exceptions import ResourceNotFoundError as ResourceNotFoundError
from graph_agent.core.graph_assembler import CompiledStateGraph as CompiledStateGraph
from graph_agent.core.graph_assembler import assemble_graph as assemble_graph
from graph_agent.core.loader import CompiledSkill as CompiledSkill
from graph_agent.core.local_workspace_resolver import (
    LocalWorkspaceResolver as LocalWorkspaceResolver,
)
from graph_agent.core.manifest import SkillManifest as SkillManifest
from graph_agent.core.result import PathDiff as PathDiff
from graph_agent.core.result import PhaseRecord as PhaseRecord
from graph_agent.core.result import RunResult as RunResult
from graph_agent.core.runner import predict_skill as predict_skill
from graph_agent.core.runner import run_skill as run_skill
from graph_agent.core.serialize import serialize_skill as serialize_skill
from graph_agent.runtime.state import BlackboardState as BlackboardState

__all__ = [
    "run_skill",
    "predict_skill",
    "RunResult",
    "PathDiff",
    "PhaseRecord",
    "compile_skill",
    "CompileResult",
    "assemble_graph",
    "CompiledSkill",
    "CompiledStateGraph",
    "BlackboardState",
    "LocalWorkspaceResolver",
    "SkillManifest",
    "serialize_skill",
    "GraphAgentError",
    "GraphCompileError",
    "GraphExecutionError",
    "ModelProviderError",
    "ResourceNotFoundError",
]
