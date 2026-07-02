"""R20: completed role/copilot test jobs persist their result; the read
endpoint re-projects the persisted results so badges survive a restart."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.routers import llm
from app.services import llm_role_test_results
from app.services.runtime_activity import load_runtime_activity


def _completed_graph_agent_job(job_id: str, role_name: str) -> None:
    llm._role_test_jobs[job_id] = llm.RoleTestJobResponse(
        job_id=job_id,
        role_name=role_name,
        status="queued",
        message="queued",
        provider_statuses=[],
    )


def test_completed_graph_agent_role_test_persists_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "llm_role_test_results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(store))

    job_id = "job-graph-agent-1"
    _completed_graph_agent_job(job_id, "analyst")
    try:
        asyncio.run(llm._run_role_test_job_impl(job_id, "analyst", []))
    finally:
        llm._role_test_jobs.pop(job_id, None)

    persisted = llm_role_test_results.load_result("analyst", path=store)
    assert persisted is not None
    assert persisted["role_name"] == "analyst"
    assert persisted["result"]["role_name"] == "analyst"
    # An empty target list aggregates to the default "ok" status.
    assert persisted["status"] == "ok"


def test_persist_completed_role_test_result_writes_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "llm_role_test_results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(store))

    result = {
        "role_name": "copilot_chat",
        "status": "ok",
        "warnings": [],
        "model_groups": [],
        "sdk_evidence": {"tested": True, "passed": 1, "total": 1, "routes": {}},
    }
    llm._persist_completed_role_test_result("copilot_chat", result)

    persisted = llm_role_test_results.load_result("copilot_chat", path=store)
    assert persisted is not None
    assert persisted["status"] == "ok"
    assert persisted["result"]["sdk_evidence"]["passed"] == 1


def test_persist_completed_role_test_result_logs_per_route_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime-activity entry must carry the SAME per-route facts as the
    persisted truth file — the General-settings Runtime log is the diagnostic
    trail, so "analyst failed" without the failing routes/messages is useless."""
    store = tmp_path / "llm_role_test_results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(store))
    log_path = tmp_path / "runtime_activity.jsonl"
    monkeypatch.setenv("STUDIO_RUNTIME_ACTIVITY_LOG_PATH", str(log_path))

    result = {
        "role_name": "analyst",
        "status": "failed",
        "warnings": [],
        "model_groups": [
            {
                "canonical_id": "claude-fable-5",
                "provider_results": [
                    {
                        "route_id": "qiniu:anthropic.claude-fable-5",
                        "provider_label": "Qiniu",
                        "status": "failed",
                        "message": "Provider returned HTTP 502 (processing_error).",
                    },
                    {
                        "route_id": "anthropic-official:claude-fable-5",
                        "provider_label": "Anthropic Official",
                        "status": "ok",
                        "message": None,
                    },
                ],
            }
        ],
    }
    llm._persist_completed_role_test_result("analyst", result)

    entries = load_runtime_activity(source_id="llm_role_test_results")
    assert entries, "expected a runtime-activity entry for the saved role test"
    changes = entries[0]["changes"]
    assert changes["role_name"] == "analyst"
    assert changes["status"] == "failed"
    assert changes["route_results"] == [
        {
            "canonical_id": "claude-fable-5",
            "route_id": "qiniu:anthropic.claude-fable-5",
            "provider": "Qiniu",
            "status": "failed",
            "message": "Provider returned HTTP 502 (processing_error).",
        },
        {
            "canonical_id": "claude-fable-5",
            "route_id": "anthropic-official:claude-fable-5",
            "provider": "Anthropic Official",
            "status": "ok",
            "message": None,
        },
    ]


def test_persist_is_best_effort_and_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(llm, "save_role_test_result", _boom)

    # Must not raise — persistence failure cannot break a finished test job.
    llm._persist_completed_role_test_result("analyst", {"status": "ok"})


def test_read_endpoint_reprojects_persisted_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "llm_role_test_results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(store))
    llm_role_test_results.save_result(
        "analyst",
        {"role_name": "analyst", "status": "ok", "model_groups": []},
        status="ok",
        message="Role test completed.",
        path=store,
    )

    response = asyncio.run(llm.get_role_test_results())

    assert "analyst" in response.results
    entry = response.results["analyst"]
    assert entry.role_name == "analyst"
    assert entry.status == "ok"
    assert entry.message == "Role test completed."
    assert entry.result["role_name"] == "analyst"


def test_read_endpoint_is_empty_when_nothing_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(tmp_path / "missing.json")
    )

    response = asyncio.run(llm.get_role_test_results())

    assert response.results == {}
