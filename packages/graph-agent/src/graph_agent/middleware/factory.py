"""Factory for the PR β MVP0 middleware chain."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from pydantic import BaseModel

from graph_agent.callbacks.base import Callback
from graph_agent.middleware import MVP0_MIDDLEWARE_ORDER_CONTRACT
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware, InterruptFn
from graph_agent.middleware.compaction import (
    CompactionMiddleware,
    CompactionSidecarWriter,
    write_compaction_sidecar,
)
from graph_agent.middleware.execution_control import ExecutionControlMiddleware
from graph_agent.middleware.exit_control import ExitControlMiddleware
from graph_agent.middleware.loop_detection import LoopDetectionMiddleware
from graph_agent.middleware.protocol_validation import ProtocolValidationMiddleware
from graph_agent.middleware.tool_error import ToolErrorHandlingMiddleware
from graph_agent.middleware.tracing import TracingMiddleware

if TYPE_CHECKING:
    from graph_agent.core.io_manager import IOManager
    from graph_agent.core.schema_engine import SchemaEngine, SchemaObject


MIDDLEWARE_ORDER_CONTRACT = MVP0_MIDDLEWARE_ORDER_CONTRACT


def build_middleware_chain(
    *,
    io_manager: IOManager,
    schema_engine: SchemaEngine | None = None,
    current_phase_schema: type[BaseModel] | SchemaObject | None = None,
    business_validator: Callable[[list[dict[str, Any]]], tuple[bool, list[str]]] | None = None,
    phase_name: str = "unknown",
    unattended: bool = False,
    interrupt_fn: InterruptFn | None = None,
    callbacks: Sequence[Callback] | None = None,
    compaction_model: Any = None,
    compaction_sidecar_writer: CompactionSidecarWriter | None = None,
) -> tuple[AgentMiddleware[AgentState[Any]], ...]:
    """Instantiate the eight middleware slots in the contract order.

    ``compaction_model`` powers the Compaction slot's summarizer (the
    assembler passes the phase's resolved chat model); ``None`` leaves the
    slot inert so bare chains keep the contract shape. The sidecar writer
    is injected explicitly — the assembler passes the default
    ``write_compaction_sidecar`` — so tests can substitute a fake storage
    face without patching module globals.
    """
    by_contract_name: dict[str, AgentMiddleware[AgentState[Any]]] = {
        "ProtocolValidation": ProtocolValidationMiddleware(
            schema_engine=schema_engine,
            current_phase_schema=current_phase_schema,
            phase_name=phase_name,
            callbacks=callbacks,
        ),
        "CognitiveFlow": CognitiveFlowMiddleware(
            io_manager=io_manager,
            unattended=unattended,
            schema_engine=schema_engine,
            current_phase_schema=current_phase_schema,
            business_validator=business_validator,
            phase_name=phase_name,
            interrupt_fn=interrupt_fn,
            callbacks=callbacks,
        ),
        "ExecutionControl": ExecutionControlMiddleware(
            callbacks=callbacks,
            phase_name=phase_name,
        ),
        "Compaction": CompactionMiddleware(
            model=compaction_model,
            phase_name=phase_name,
            callbacks=callbacks,
            sidecar_writer=compaction_sidecar_writer or write_compaction_sidecar,
        ),
        "Tracing": TracingMiddleware(
            callbacks=callbacks,
            phase_name=phase_name,
        ),
        "ToolError": ToolErrorHandlingMiddleware(phase_name=phase_name, callbacks=callbacks),
        "LoopDetection": LoopDetectionMiddleware(phase_name=phase_name, callbacks=callbacks),
        "ExitControl": ExitControlMiddleware(
            phase_name=phase_name,
            callbacks=callbacks,
        ),
    }
    return tuple(by_contract_name[name] for name in MIDDLEWARE_ORDER_CONTRACT)


def build_middleware_chain_cognitive_flow(
    *,
    io_manager: IOManager | None = None,
    schema_engine: SchemaEngine | None = None,
    current_phase_schema: type[BaseModel] | SchemaObject | None = None,
    business_validator: Callable[[list[dict[str, Any]]], tuple[bool, list[str]]] | None = None,
    phase_name: str = "unknown",
    unattended: bool = False,
    interrupt_fn: InterruptFn | None = None,
) -> CognitiveFlowMiddleware:
    """Build only the CognitiveFlow slot for callers that do not need all six layers."""

    if io_manager is None:
        from graph_agent.core.io_manager import IOManager

        io_manager = IOManager([])
    return CognitiveFlowMiddleware(
        io_manager=io_manager,
        unattended=unattended,
        schema_engine=schema_engine,
        current_phase_schema=current_phase_schema,
        business_validator=business_validator,
        phase_name=phase_name,
        interrupt_fn=interrupt_fn,
    )
