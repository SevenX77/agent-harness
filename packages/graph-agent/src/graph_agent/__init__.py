"""graph_agent - Document-driven LLM agent harness SDK.

Public API (12 stable, recommended for new code):
    run_skill, WorkflowResult, GraphAgentHarness, compile_skill,
    SkillManifest, Callback, LoggingCallback, MetricsCallback,
    TracingCallback, GraphAgentError, SkillLoadError,
    SkillCompilationError.

Deprecated API (14 names, lazy-loaded via __getattr__ with
DeprecationWarning, kept for backward compat with legacy host projects
like video-analysis). Will be removed in v1.0:
    parse_skill_file, serialize_skill, load_workflow_from_md,
    clear_cache, Phase, WorkflowState, ContextBridge, IOManager,
    ContextResolver, ModelResolver, get_model_resolver, get_skill_type,
    AllProvidersFailedError, MaxRetriesExceededError.
"""

from __future__ import annotations

import warnings as _warnings

from .callbacks import Callback, LoggingCallback, MetricsCallback, TracingCallback
from .core.compiler import compile_skill
from .core.exceptions import GraphAgentError, SkillCompilationError, SkillLoadError
from .core.harness import GraphAgentHarness
from .core.manifest import SkillManifest
from .core.runner import WorkflowResult, run_skill

# Deprecated lazy imports - only loaded on access
_DEPRECATED_LOADERS = {
    "parse_skill_file": ("graph_agent.core.parser", "parse_skill_file"),
    "serialize_skill": ("graph_agent.core.serialize", "serialize_skill"),
    "load_workflow_from_md": ("graph_agent.core.loader", "load_workflow_from_md"),
    "clear_cache": ("graph_agent.core.runner", "clear_cache"),
    "Phase": ("graph_agent.core.types", "Phase"),
    "WorkflowState": ("graph_agent.core.state", "WorkflowState"),
    "ContextBridge": ("graph_agent.core.manifest", "ContextBridge"),
    "IOManager": ("graph_agent.io.manager", "IOManager"),
    "ContextResolver": ("graph_agent.io.context_resolver", "ContextResolver"),
    "ModelResolver": ("graph_agent.models.resolver", "ModelResolver"),
    "get_model_resolver": ("graph_agent.models.resolver", "get_model_resolver"),
    "get_skill_type": ("graph_agent.io.skill_analyzer", "get_skill_type"),
    "AllProvidersFailedError": ("graph_agent.core.exceptions", "AllProvidersFailedError"),
    "MaxRetriesExceededError": ("graph_agent.core.exceptions", "MaxRetriesExceededError"),
}


def __getattr__(name: str):
    if name in _DEPRECATED_LOADERS:
        module_path, attr = _DEPRECATED_LOADERS[name]
        _warnings.warn(
            f"`graph_agent.{name}` is a deprecated re-export of an internal "
            f"helper. Migrate to the 12-export public SDK; this lazy alias "
            f"will be removed in v1.0. Internal usage: `from {module_path} import {attr}`.",
            DeprecationWarning,
            stacklevel=2,
        )
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module 'graph_agent' has no attribute {name!r}")


__all__ = [
    # 12 stable
    "run_skill",
    "WorkflowResult",
    "GraphAgentHarness",
    "compile_skill",
    "SkillManifest",
    "Callback",
    "LoggingCallback",
    "MetricsCallback",
    "TracingCallback",
    "GraphAgentError",
    "SkillLoadError",
    "SkillCompilationError",
    # 14 deprecated (lazy)
    "parse_skill_file",
    "serialize_skill",
    "load_workflow_from_md",
    "clear_cache",
    "Phase",
    "WorkflowState",
    "ContextBridge",
    "IOManager",
    "ContextResolver",
    "ModelResolver",
    "get_model_resolver",
    "get_skill_type",
    "AllProvidersFailedError",
    "MaxRetriesExceededError",
]
