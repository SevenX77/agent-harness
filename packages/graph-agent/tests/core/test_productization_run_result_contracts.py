from __future__ import annotations

import dataclasses
import importlib
import inspect
from typing import Any


def _fields(cls: type[Any]) -> set[str]:
    if hasattr(cls, "model_fields"):
        return set(cls.model_fields)
    if dataclasses.is_dataclass(cls):
        return {field.name for field in dataclasses.fields(cls)}
    try:
        return {
            name
            for name in inspect.signature(cls).parameters
            if name != "self"
        }
    except (TypeError, ValueError):
        return set(getattr(cls, "__annotations__", {}))


def test_run_result_snapshot_contract_is_readable_by_golden_headless() -> None:
    contracts = importlib.import_module("graph_agent.core.result_contracts")

    RunResultsRef = contracts.RunResultsRef
    NodeRunResult = contracts.NodeRunResult
    RunResultSnapshot = contracts.RunResultSnapshot
    GoldenInputRef = contracts.GoldenInputRef

    assert {
        "run_id",
        "uri",
        "content_hash",
    } <= _fields(RunResultsRef)
    assert {
        "agent_node_id",
        "status",
        "outputs_ref",
        "trace_refs",
    } <= _fields(NodeRunResult)
    assert {
        "run_results_ref",
        "node_results",
        "status",
        "outputs_ref",
        "trace_refs",
    } <= _fields(RunResultSnapshot)
    assert {
        "run_results_ref",
        "baseline_ref",
    } <= _fields(GoldenInputRef)

    run_results_ref = RunResultsRef(
        run_id="run-1",
        uri="artifact://runs/run-1/results.json",
        content_hash="sha256:run-results",
    )
    node_result = NodeRunResult(
        agent_node_id="draft",
        status="succeeded",
        outputs_ref="artifact://runs/run-1/nodes/draft/outputs.json",
        trace_refs=["artifact://runs/run-1/trace.jsonl"],
    )
    snapshot = RunResultSnapshot(
        run_results_ref=run_results_ref,
        node_results=[node_result],
        status="succeeded",
        outputs_ref="artifact://runs/run-1/outputs.json",
        trace_refs=["artifact://runs/run-1/trace.jsonl"],
    )
    golden_input = GoldenInputRef(
        run_results_ref=run_results_ref,
        baseline_ref="artifact://baselines/baseline-1.json",
    )

    assert snapshot.run_results_ref is run_results_ref
    assert snapshot.node_results[0].agent_node_id == "draft"
    assert snapshot.node_results[0].outputs_ref.endswith("/outputs.json")
    assert golden_input.run_results_ref is run_results_ref


def test_run_result_snapshot_contract_does_not_start_or_evaluate_runs() -> None:
    contracts = importlib.import_module("graph_agent.core.result_contracts")

    forbidden_callables = {
        "run",
        "run_skill",
        "run_artifact",
        "predict",
        "predict_artifact",
        "resume",
        "start_run",
        "execute",
        "invoke",
        "evaluate_golden_baseline",
    }

    for class_name in ("RunResultsRef", "NodeRunResult", "RunResultSnapshot", "GoldenInputRef"):
        contract_cls = getattr(contracts, class_name)
        leaked = [
            name
            for name in forbidden_callables
            if callable(getattr(contract_cls, name, None))
        ]
        assert leaked == [], f"{class_name} must stay a read-only result contract"


def test_missing_run_result_ref_has_explicit_golden_error_code() -> None:
    contracts = importlib.import_module("graph_agent.core.result_contracts")

    error = contracts.RunResultsNotFoundError("missing run result")

    assert getattr(error, "error_code", None) == "golden.run_results_not_found"
