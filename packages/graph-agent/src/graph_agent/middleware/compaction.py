"""Compaction slot: summarization with sidecar observability.

Migrated from the legacy dead family by the 2026-08-15 cognitive-features
migration decision (§3.6). The slot wraps langchain's official
``SummarizationMiddleware`` — user ruling P0-1 fixed the parameters at
``trigger=("fraction", 0.8)`` / ``keep=("messages", 20)`` — and adds the
observability the legacy WM-checkpoint compression provided:

* every message removed from the context is preserved in full in a
  **sidecar** JSON file under the run directory, and
* a ``CompactionEvent`` whose ``content_ref`` points at that file is
  emitted, so a compaction is always traceable after the fact.

Trigger detection deliberately avoids langchain internals: the wrapper
calls the inner ``before_model`` hook and diffs the returned messages
update against the incoming state. ``None`` means no summarization
happened (zero behavior change); a non-``None`` update identifies the
removed messages by id. Both facts are the hook's public contract, so a
langchain minor-version bump either keeps this working or fails the
behavior tests loudly — it cannot silently drop the sidecar.

The storage face is the run directory carried in
``FrameworkState.persistent_storage_config["run_dir"]`` (written by the
runner, which is the one caller that knows whether an execution files
under ``runs/`` or ``predicts/`` — see ``io/run_layout.py``). A state
without that face (e.g. a bare graph invocation in tests) degrades to
``content_ref=None`` with a warning instead of aborting the run:
compaction itself is a context-window necessity, the sidecar is
observability on top of it.
"""

from __future__ import annotations

import itertools
import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain_core.messages import AnyMessage, BaseMessage, RemoveMessage, message_to_dict
from langgraph.runtime import Runtime

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import CompactionEvent

logger = logging.getLogger(__name__)

#: User ruling P0-1 (nine-round finalization): summarize when the history
#: reaches 80% of the model's input window, keep the 20 most recent messages.
COMPACTION_TRIGGER_FRACTION = 0.8
COMPACTION_KEEP_MESSAGES = 20

#: Conservative window assumed for models that expose no profile metadata
#: (migrated verbatim from the legacy ``_ensure_summarization_profile``).
SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS = 32_000

_SIDECAR_DIRNAME = "compaction"


class CompactionSidecarWriter(Protocol):
    """Persists the full text of removed messages; returns the file path."""

    def __call__(
        self,
        *,
        run_dir: Path,
        phase_name: str,
        sequence: int,
        removed_messages: Sequence[AnyMessage],
    ) -> Path: ...


def write_compaction_sidecar(
    *,
    run_dir: Path,
    phase_name: str,
    sequence: int,
    removed_messages: Sequence[AnyMessage],
) -> Path:
    """Default sidecar writer: one JSON file per compaction under the run dir.

    ``message_to_dict`` keeps the full message payload (content, tool
    calls, ids), so the sidecar is a lossless record of what left the
    context window.
    """
    target = run_dir / _SIDECAR_DIRNAME / f"{phase_name}-{sequence:03d}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase_name": phase_name,
        "sequence": sequence,
        "removed_message_count": len(removed_messages),
        "messages": [message_to_dict(message) for message in removed_messages],
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


class _SummarizationReadyModel:
    """Delegate model calls while supplying construction-time metadata.

    ``SummarizationMiddleware`` needs ``profile["max_input_tokens"]`` for a
    fractional trigger and ``_llm_type`` for its token-counter tuning — both
    at construction time. Models that lack either (gateway-backed chat
    models, test doubles) would make the phase unassemblable, so this shim
    fills the gaps and forwards everything else untouched.
    """

    def __init__(self, wrapped: Any, *, max_input_tokens: int) -> None:
        self._wrapped = wrapped
        self.profile: Mapping[str, Any] = {"max_input_tokens": max_input_tokens}

    @property
    def _llm_type(self) -> str:
        llm_type = getattr(self._wrapped, "_llm_type", None)
        return llm_type if isinstance(llm_type, str) else "unknown"

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._wrapped.invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        return await self._wrapped.ainvoke(*args, **kwargs)


def _max_input_tokens_from_profile(model: Any) -> int | None:
    try:
        profile = model.profile
    except AttributeError:
        return None
    if not isinstance(profile, Mapping):
        return None
    max_input_tokens = profile.get("max_input_tokens")
    return max_input_tokens if isinstance(max_input_tokens, int) else None


def _summarization_ready_model(model: Any) -> Any:
    """Return ``model`` unchanged when constructible, else the compat shim."""
    max_input_tokens = _max_input_tokens_from_profile(model)
    if max_input_tokens is not None and isinstance(getattr(model, "_llm_type", None), str):
        return model
    if max_input_tokens is None:
        logger.warning(
            "compaction: summarization model lacks profile.max_input_tokens; "
            "using fallback max_input_tokens=%d",
            SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS,
        )
        max_input_tokens = SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS
    return _SummarizationReadyModel(model, max_input_tokens=max_input_tokens)


class CompactionMiddleware(AgentMiddleware[AgentState[Any]]):
    """Summarize an over-window history and preserve the removed text.

    Composition over inheritance: the langchain summarizer is held as a
    collaborator and only its documented hook surface is used, so the
    observability layer survives upstream refactors of the summarization
    internals.

    Without a model (bare test assembly, phase whose model resolution is
    deferred to invoke time and failed) the slot is inert: ``before_model``
    always returns ``None``, keeping the chain shape stable.
    """

    def __init__(
        self,
        *,
        model: Any = None,
        phase_name: str = "unknown",
        callbacks: Sequence[Callback] | None = None,
        sidecar_writer: CompactionSidecarWriter = write_compaction_sidecar,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._callbacks = list(callbacks or [])
        self._sidecar_writer = sidecar_writer
        self._sequence = itertools.count(1)
        self._summarizer: SummarizationMiddleware[Any, Any] | None = (
            None
            if model is None
            else SummarizationMiddleware(
                model=_summarization_ready_model(model),
                trigger=[("fraction", COMPACTION_TRIGGER_FRACTION)],
                keep=("messages", COMPACTION_KEEP_MESSAGES),
            )
        )

    def before_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        if self._summarizer is None:
            return None
        result = self._summarizer.before_model(state, runtime)
        return self._record_compaction(state, result)

    async def abefore_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        # Async graph executions dispatch to the async hook only (same
        # requirement as the sibling ExitControl middleware).
        if self._summarizer is None:
            return None
        result = await self._summarizer.abefore_model(state, runtime)
        return self._record_compaction(state, result)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _record_compaction(
        self,
        state: AgentState[Any],
        result: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if result is None:
            return None
        removed = _removed_messages(list(state.get("messages", [])), result)
        if not removed:
            return result
        content_ref = self._write_sidecar(state, removed)
        _safe_emit_event(
            self._callbacks,
            CompactionEvent(
                phase_name=self._phase_name,
                removed_message_count=len(removed),
                removed_summary=(
                    f"Compacted {len(removed)} message(s) in phase "
                    f"{self._phase_name!r}: the history reached "
                    f"{COMPACTION_TRIGGER_FRACTION:.0%} of the model input window, so "
                    f"everything but the {COMPACTION_KEEP_MESSAGES} most recent "
                    "message(s) was replaced by a summary. The removed messages' "
                    "full text is preserved in the sidecar file."
                ),
                content_ref=content_ref,
            ),
        )
        return result

    def _write_sidecar(self, state: AgentState[Any], removed: list[AnyMessage]) -> str | None:
        run_dir = _run_dir_from_state(state)
        if run_dir is None:
            logger.warning(
                "compaction: state carries no persistent_storage_config['run_dir']; "
                "sidecar skipped for phase %r (CompactionEvent.content_ref=None)",
                self._phase_name,
            )
            return None
        try:
            path = self._sidecar_writer(
                run_dir=run_dir,
                phase_name=self._phase_name,
                sequence=next(self._sequence),
                removed_messages=removed,
            )
        except OSError:
            # The compaction already happened inside langchain's hook; a disk
            # failure on the observability plane must not abort the run.
            logger.exception(
                "compaction: sidecar write failed for phase %r; "
                "CompactionEvent.content_ref degrades to None",
                self._phase_name,
            )
            return None
        return str(path)


def _removed_messages(
    original: list[AnyMessage],
    result: dict[str, Any],
) -> list[AnyMessage]:
    """Messages present in the incoming state but absent from the update.

    The summarizer's update is ``[RemoveMessage(REMOVE_ALL), summary,
    *preserved]`` where preserved messages keep their ids (it assigns ids to
    every incoming message first), so an id-diff identifies exactly what
    left the context.
    """
    returned = result.get("messages") or []
    preserved_ids = {
        message.id
        for message in returned
        if isinstance(message, BaseMessage)
        and not isinstance(message, RemoveMessage)
        and message.id is not None
    }
    return [message for message in original if message.id not in preserved_ids]


def _run_dir_from_state(state: AgentState[Any]) -> Path | None:
    flow = state.get("flow") if isinstance(state, dict) else None
    storage_config = (
        flow.get("persistent_storage_config")
        if isinstance(flow, dict)
        else getattr(flow, "persistent_storage_config", None)
    )
    if not isinstance(storage_config, Mapping):
        return None
    run_dir = storage_config.get("run_dir")
    if isinstance(run_dir, str) and run_dir:
        return Path(run_dir)
    return None
