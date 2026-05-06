"""graph_agent — self-contained multi-phase Agent orchestration engine.

Public API:
run_skill — generic Skill runner (document-driven, no per-skill Python needed)
GraphAgentHarness — main orchestrator (LangGraph StateGraph + LangChain Agent)
Phase — phase definition dataclass
WorkflowState — typed state flowing through the graph
load_workflow_from_md — compile SKILL.md into a harness
ModelResolver — role-based model selection with provider failover
"""

from __future__ import annotations

from graph_agent.callbacks import Callback, LoggingCallback, MetricsCallback, TracingCallback
from graph_agent.core.compiler import compile_skill  # noqa: E402
from graph_agent.core.exceptions import (  # noqa: E402
    AllProvidersFailedError,
    GraphAgentError,
    MaxRetriesExceededError,
    SkillCompilationError,
    SkillLoadError,
    TemplateRenderError,
)
from graph_agent.core.harness import GraphAgentHarness  # noqa: E402
from graph_agent.core.loader import load_workflow_from_md  # noqa: E402
from graph_agent.core.manifest import (  # noqa: E402
    AgentProfile,
    AgentSkillDef,
    ContextBridge,  # noqa: E402
    GraphSkillDef,
    LLMPhase,
    LogicPhase,
    PersonaSkillDef,
    PhaseDef,
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file  # noqa: E402
from graph_agent.core.runner import clear_cache, run_skill  # noqa: E402
from graph_agent.core.serialize import serialize_skill  # noqa: E402
from graph_agent.core.state import WorkflowState  # noqa: E402
from graph_agent.core.types import Phase  # noqa: E402
from graph_agent.io.context_resolver import ContextResolver  # noqa: E402
from graph_agent.io.manager import IOManager  # noqa: E402
from graph_agent.io.skill_analyzer import get_skill_type  # noqa: E402
from graph_agent.models.resolver import ModelResolver, get_model_resolver  # noqa: E402

__all__ = [
    "run_skill",
    "clear_cache",
    "GraphAgentHarness",
    "Phase",
    "ContextBridge",
    "WorkflowState",
    "load_workflow_from_md",
    "compile_skill",
    "ModelResolver",
    "get_model_resolver",
    "get_skill_type",
    "ContextResolver",
    "IOManager",
    "Callback",
    "LoggingCallback",
    "MetricsCallback",
    "TracingCallback",
    "GraphAgentError",
    "SkillLoadError",
    "SkillCompilationError",
    "TemplateRenderError",
    "AllProvidersFailedError",
    "MaxRetriesExceededError",
    "SkillManifest",
    "AgentProfile",
    "AgentSkillDef",
    "GraphSkillDef",
    "PersonaSkillDef",
    "PhaseDef",
    "LLMPhase",
    "LogicPhase",
    "serialize_skill",
    "parse_skill_file",
]
