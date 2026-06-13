from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunResultsRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    uri: str
    content_hash: str


class NodeRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    agent_node_id: str
    status: str
    outputs_ref: str
    trace_refs: list[str] = Field(default_factory=list)


class RunResultSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_results_ref: RunResultsRef
    node_results: list[NodeRunResult] = Field(default_factory=list)
    status: str
    outputs_ref: str
    trace_refs: list[str] = Field(default_factory=list)


class GoldenInputRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_results_ref: RunResultsRef
    baseline_ref: str


class RunResultsNotFoundError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "golden.run_results_not_found"


class GoldenBaselineNotFoundError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "golden.baseline_not_found"


class GoldenJudgeUnavailableError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "golden.judge_unavailable"


class GoldenBaselineStaleError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "golden.baseline_stale"


def snapshot_from_run_result(
    *,
    run_result: Any,
    run_results_ref: RunResultsRef,
    node_results: list[NodeRunResult] | None = None,
    outputs_ref: str | None = None,
    trace_refs: list[str] | None = None,
) -> RunResultSnapshot:
    if node_results is None:
        node_results = []

    # Derive status
    status = None
    if hasattr(run_result, "status") and run_result.status is not None:
        status = str(run_result.status)
    elif hasattr(run_result, "success") and run_result.success is not None:
        status = "success" if run_result.success else "failed"
    else:
        status = "success"

    # Default outputs_ref
    if outputs_ref is None:
        outputs_ref = run_results_ref.uri

    # Default trace_refs
    if trace_refs is None:
        trace_refs = []
        if hasattr(run_result, "trace_path") and run_result.trace_path is not None:
            trace_refs = [str(run_result.trace_path)]

    return RunResultSnapshot(
        run_results_ref=run_results_ref,
        node_results=node_results,
        status=status,
        outputs_ref=outputs_ref,
        trace_refs=trace_refs,
    )
