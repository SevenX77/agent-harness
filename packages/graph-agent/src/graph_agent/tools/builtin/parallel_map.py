"""builtin.parallel_map — fan out a child skill over a list of items.

Lets a SKILL.md declare declarative concurrency without hand-rolling a
ThreadPoolExecutor dispatcher. Each item is handed to a fresh child-skill
run; the function returns the list of child contexts in input order.

Spec reference: tasks.md Task 4.3, research.md decision "parallel_map
default max_concurrent=3".

Behaviour:

* A fresh harness is loaded via :func:`load_workflow_from_md` for each
  sub-run, so we never race on the cached-harness instance that
  ``run_skill`` uses for serial callers.
* Every sub-run receives a unique ``sub_run_id`` plus a shared
  ``group_key`` via ``runtime_inputs``. ``TracingClientProxy`` reads
  these two keys off the context and stamps every ``prompt_captured``
  event with them so Studio can collapse the fan-out into one folded
  timeline group (Gemini audit Major #1).
* Parent callbacks propagate to child runs through an event subscriber;
  each child writes its own run-scoped ``trace.jsonl`` under the workspace
  root passed as ``trace_dir``.
* Errors inside a sub-run are captured and surfaced in the returned
  list as ``{"error": "..."}`` entries — a single bad item does not
  halt the whole fan-out. Callers that want fail-fast semantics can
  set ``stop_on_error=True``.
"""

from __future__ import annotations

import logging
import time as _time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol

logger = logging.getLogger(__name__)


def parallel_map(
    skill_path: str | Path,
    item_list: list[Any],
    item_as: str,
    *,
    skill_resolver: SkillResolverProtocol,
    max_concurrent: int = 3,
    base_runtime_inputs: dict[str, Any] | None = None,
    callbacks: list[Any] | None = None,
    trace_dir: str | Path | None = None,
    stop_on_error: bool = False,
) -> list[dict[str, Any]]:
    """Run ``skill_path`` once per item in ``item_list`` under a thread pool.

    Args:
        skill_path: Path to the child SKILL.md. Must already have IO
            declarations matching ``item_as``.
        item_list: The items to fan out over. An empty list returns ``[]``.
        item_as: Name of the runtime input the child skill expects — the
            current item's value is forwarded as ``{item_as: item}``.
        max_concurrent: Upper bound on concurrent child runs. Default 3
            matches DeerFlow's SubagentExecutor limit so the two pools don't
            compound unexpectedly (research.md decision).
        base_runtime_inputs: Dict merged into every child's runtime_inputs
            *before* the per-item ``{item_as: item}`` and the framework's
            ``_sub_run_id`` / ``_group_key`` grouping keys.
        callbacks: Callback list propagated to each child's ``run_skill``.
            Defaults to the child's own fresh trace callbacks when ``None``.
        trace_dir: Workspace root under which each child run writes
            ``runs/<sub_run_id>/`` artifacts. When ``None`` the child
            falls back to ``Path.cwd() / ".workspace"``.
        stop_on_error: Re-raise the first child exception instead of
            collecting it into the results list.

    Returns:
        A list of child-skill result dicts in the same order as
        ``item_list``. Successful child runs return their ``run_skill``
        result; failed ones are represented as
        ``{"error": "<exc>", "sub_run_id": "..."}``.
    """
    if not item_list:
        logger.info("parallel_map: empty item_list, nothing to do (skill=%s)", skill_path)
        return []

    if max_concurrent < 1:
        raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
    if not item_as or not isinstance(item_as, str):
        raise ValueError("item_as must be a non-empty string")

    group_key = uuid.uuid4().hex[:12]
    base_inputs = dict(base_runtime_inputs or {})

    results: list[dict[str, Any] | None] = [None] * len(item_list)

    logger.info(
        "parallel_map start: skill=%s items=%d max_concurrent=%d group_key=%s",
        skill_path,
        len(item_list),
        max_concurrent,
        group_key,
    )

    # Tier 1 Commit C (T-B9): emit a visible group boundary so Studio
    # can fold all the sibling sub-runs' events under one timeline block.
    # Per Gemini Q7 sub-run events still merge into the parent trace.jsonl
    # via shared callbacks; the boundary events give the folding anchor.
    group_start_monotonic = _time.monotonic()
    _emit_group_started(
        callbacks,
        group_key=group_key,
        skill_path=skill_path,
        item_count=len(item_list),
        max_concurrent=max_concurrent,
        item_as=item_as,
    )

    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        future_to_index = _submit_parallel_map_items(
            pool,
            skill_path=skill_path,
            item_list=item_list,
            item_as=item_as,
            base_inputs=base_inputs,
            group_key=group_key,
            callbacks=callbacks,
            trace_dir=trace_dir,
            skill_resolver=skill_resolver,
        )
        _collect_parallel_map_results(
            future_to_index,
            results=results,
            group_key=group_key,
            skill_path=skill_path,
            stop_on_error=stop_on_error,
        )

    succeeded = sum(1 for r in results if r and "error" not in r)
    failed = sum(1 for r in results if r and "error" in r)
    logger.info(
        "parallel_map end: skill=%s group_key=%s succeeded=%d failed=%d",
        skill_path,
        group_key,
        succeeded,
        failed,
    )

    # Tier 1 Commit C (T-B9): close the visible group boundary.
    _emit_group_ended(
        callbacks,
        group_key=group_key,
        succeeded=succeeded,
        failed=failed,
        wall_time_seconds=round(_time.monotonic() - group_start_monotonic, 3),
    )

    # Every slot was populated either by a result or an error placeholder.
    return [r for r in results if r is not None]


def _emit_group_started(
    callbacks: list[Any] | None,
    *,
    group_key: str,
    skill_path: str | Path,
    item_count: int,
    max_concurrent: int,
    item_as: str,
) -> None:
    if not callbacks:
        return
    from graph_agent.callbacks.events import ParallelMapGroupStartedEvent

    event = ParallelMapGroupStartedEvent(
        group_key=group_key,
        skill_path=str(skill_path),
        item_count=item_count,
        max_concurrent=max_concurrent,
        item_as=item_as,
    )
    _emit_callback_event(callbacks, event, "GroupStarted")


def _emit_group_ended(
    callbacks: list[Any] | None,
    *,
    group_key: str,
    succeeded: int,
    failed: int,
    wall_time_seconds: float,
) -> None:
    if not callbacks:
        return
    from graph_agent.callbacks.events import ParallelMapGroupEndedEvent

    event = ParallelMapGroupEndedEvent(
        group_key=group_key,
        succeeded=succeeded,
        failed=failed,
        wall_time_seconds=wall_time_seconds,
    )
    _emit_callback_event(callbacks, event, "GroupEnded")


def _emit_callback_event(callbacks: list[Any], event: Any, label: str) -> None:
    for cb in callbacks:
        try:
            cb.on_event(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "parallel_map: callback %r failed on %s",
                type(cb).__name__,
                label,
            )


def _submit_parallel_map_items(
    pool: ThreadPoolExecutor,
    *,
    skill_path: str | Path,
    item_list: list[Any],
    item_as: str,
    base_inputs: dict[str, Any],
    group_key: str,
    callbacks: list[Any] | None,
    trace_dir: str | Path | None,
    skill_resolver: SkillResolverProtocol,
) -> dict[Future[dict[str, Any]], int]:
    future_to_index: dict[Future[dict[str, Any]], int] = {}
    for idx, item in enumerate(item_list):
        sub_run_id = f"{group_key}-{idx:04d}"
        future = pool.submit(
            _run_one_item,
            skill_path=skill_path,
            item=item,
            item_as=item_as,
            base_inputs=base_inputs,
            sub_run_id=sub_run_id,
            group_key=group_key,
            callbacks=callbacks,
            trace_dir=trace_dir,
            skill_resolver=skill_resolver,
        )
        future_to_index[future] = idx
    return future_to_index


def _collect_parallel_map_results(
    future_to_index: dict[Future[dict[str, Any]], int],
    *,
    results: list[dict[str, Any] | None],
    group_key: str,
    skill_path: str | Path,
    stop_on_error: bool,
) -> None:
    for future in as_completed(future_to_index):
        idx = future_to_index[future]
        sub_run_id = f"{group_key}-{idx:04d}"
        try:
            results[idx] = future.result()
        except Exception as exc:
            logger.exception(
                "parallel_map: sub-run %s failed (skill=%s)",
                sub_run_id,
                skill_path,
            )
            if stop_on_error:
                for pending in future_to_index:
                    pending.cancel()
                raise
            results[idx] = {"error": str(exc), "sub_run_id": sub_run_id}


def _run_one_item(
    *,
    skill_path: str | Path,
    item: Any,
    item_as: str,
    base_inputs: dict[str, Any],
    sub_run_id: str,
    group_key: str,
    callbacks: list[Any] | None,
    trace_dir: str | Path | None,
    skill_resolver: SkillResolverProtocol,
) -> dict[str, Any]:
    """Execute one child-skill run under the shared group_key."""
    # Lazy import keeps tools/builtin/__init__.py import-light for callers
    # that just want the symbol.
    from graph_agent.core.runner import run_skill

    inputs = dict(base_inputs)
    inputs[item_as] = item
    # The harness reads these two off the context to stamp grouping fields
    # on TracingClientProxy events (see harness.py Step 4 integration).
    inputs["_sub_run_id"] = sub_run_id
    inputs["_group_key"] = group_key

    logger.info(
        "parallel_map sub-run start: sub_run_id=%s group_key=%s skill=%s",
        sub_run_id,
        group_key,
        skill_path,
    )
    workspace_dir = Path(trace_dir).resolve() if trace_dir is not None else Path.cwd() / ".workspace"
    result = run_skill(
        skill_path,
        workspace_dir=workspace_dir,
        event_subscriber=_legacy_callback_subscriber(callbacks),
        skill_resolver=skill_resolver,
        thread_id=sub_run_id,
        **inputs,
    )
    logger.info(
        "parallel_map sub-run end: sub_run_id=%s group_key=%s",
        sub_run_id,
        group_key,
    )
    return result.model_dump()


def _legacy_callback_subscriber(callbacks: list[Any] | None) -> Any:
    if not callbacks:
        return None

    def _emit(event: Any) -> None:
        _emit_callback_event(callbacks, event, type(event).__name__)

    return _emit
