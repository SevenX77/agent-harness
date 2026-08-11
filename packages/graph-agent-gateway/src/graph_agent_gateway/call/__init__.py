"""Making one call: which model answers it, what it asks for, and what came back.

This package is the call domain's whole public contract — the resolver that
turns a role into a model, the chat model that drives one answer, the provider
clients and dispatch beneath it, the settings that call carries, the cheap
question asked before the expensive one, and the report of what became of each
setting. Reaching past it into one of its files couples the caller to where a
definition happens to live today.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
"""

from __future__ import annotations

from graph_agent_gateway.call.chat_model import (
    ANSWER_RESTARTED,
    GatewayChatModel,
    answer_restarts_here,
)
from graph_agent_gateway.call.clients import LLMClientManager
from graph_agent_gateway.call.dispatch import dispatch_ordinary_chat
from graph_agent_gateway.call.factory import RouteChatModelFactory, provider_request_keys
from graph_agent_gateway.call.models import GenericRouteChatModel
from graph_agent_gateway.call.outcome import (
    AUTHORED_SOURCES,
    CALL_OVERRIDE,
    SettingOutcome,
    judge_settings,
)
from graph_agent_gateway.call.pre_call_probe import build_probe_model, probe_call_settings
from graph_agent_gateway.call.predict import PredictGatewayChatModel
from graph_agent_gateway.call.profiles import (
    ProviderProfile,
    apply_provider_profile,
    apply_provider_profile_layers,
    register_provider_profile,
    route_provider_profile_keys,
)
from graph_agent_gateway.call.protocol import ModelResolverProtocol, PredictContext
from graph_agent_gateway.call.resolver import ModelResolver, ResourceTerminalError
from graph_agent_gateway.call.settings import (
    KWARG_OF_SETTING,
    ActualRuntimeSettings,
    CallSettings,
    ModelDefaults,
    budget_cap,
    compose_call_settings,
    effective_runtime_settings,
    initial_budget,
    token_budget,
)
from graph_agent_gateway.call.tracing import (
    build_route_decision_event,
    emit_call_settings_event,
    emit_route_decision_event,
)

__all__ = [
    "ANSWER_RESTARTED",
    "AUTHORED_SOURCES",
    "CALL_OVERRIDE",
    "KWARG_OF_SETTING",
    "ActualRuntimeSettings",
    "CallSettings",
    "GatewayChatModel",
    "GenericRouteChatModel",
    "LLMClientManager",
    "ModelDefaults",
    "ModelResolver",
    "ModelResolverProtocol",
    "PredictContext",
    "PredictGatewayChatModel",
    "ProviderProfile",
    "ResourceTerminalError",
    "RouteChatModelFactory",
    "SettingOutcome",
    "answer_restarts_here",
    "apply_provider_profile",
    "apply_provider_profile_layers",
    "budget_cap",
    "build_probe_model",
    "build_route_decision_event",
    "compose_call_settings",
    "dispatch_ordinary_chat",
    "effective_runtime_settings",
    "emit_call_settings_event",
    "emit_route_decision_event",
    "initial_budget",
    "judge_settings",
    "probe_call_settings",
    "provider_request_keys",
    "register_provider_profile",
    "route_provider_profile_keys",
    "token_budget",
]
