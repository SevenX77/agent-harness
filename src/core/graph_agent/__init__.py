"""graph_agent — self-contained multi-phase Agent orchestration engine.

Public API:
run_skill — generic Skill runner (document-driven, no per-skill Python needed)
GraphAgentHarness — main orchestrator (LangGraph StateGraph + DeerFlow Agent)
Phase — phase definition dataclass
WorkflowState — typed state flowing through the graph
load_workflow_from_md — compile SKILL.md into a harness
ModelResolver — role-based model selection with provider failover
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_deerflow_parent = str(_Path(__file__).resolve().parent)
if _deerflow_parent not in _sys.path:
    _sys.path.insert(0, _deerflow_parent)

from .callbacks import Callback, LoggingCallback, MetricsCallback, TracingCallback  # noqa: E402
from .io.context_resolver import ContextResolver  # noqa: E402
from .core.exceptions import (  # noqa: E402
    AllProvidersFailedError,
    GraphAgentError,
    MaxRetriesExceededError,
    SkillCompilationError,
    SkillLoadError,
    TemplateRenderError,
)
from .core.harness import GraphAgentHarness  # noqa: E402
from .core.types import ContextBridge, Phase  # noqa: E402
from .io.manager import IOManager  # noqa: E402
from .core.loader import load_workflow_from_md  # noqa: E402
from .core.compiler import compile_skill  # noqa: E402
from .models.resolver import ModelResolver, get_model_resolver  # noqa: E402
from .core.runner import run_skill, clear_cache  # noqa: E402
from .io.skill_analyzer import get_skill_type  # noqa: E402
from .core.state import WorkflowState  # noqa: E402
from .core.manifest import (  # noqa: E402
    GraphSkillManifest,
    PhaseConfig,
    SimpleSkillManifest,
    SkillManifest,
)

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
    "GraphSkillManifest",
    "SimpleSkillManifest",
    "PhaseConfig",
]
