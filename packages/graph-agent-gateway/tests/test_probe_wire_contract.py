"""What each probe method puts on the wire, pinned byte for byte.

The gateway is about to grow one set of dialects shared by the probe and the
real call, so that what a probe proves is what production will send. That
refactor is only trustworthy if it changes no request at all — and "the tests
still pass" does not show that, because no test ever looked at a request body.

So the current bodies are recorded in ``data/probe_wire_baseline.json`` and
replayed here: url, auth headers, and every field of the payload, for each
official method across a plain call, an effort, reasoning with no effort named,
a thinking budget, and with and without an image.

When a request SHOULD change, re-record the baseline in the same commit that
changes it — the diff on this fixture is then the review of the wire change.
Regenerate with: uv run python <scratchpad>/dump_wire.py

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md (D2)
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

BASELINE = json.loads(
    (Path(__file__).parent / "data" / "probe_wire_baseline.json").read_text(encoding="utf-8")
)

_RECORDED_HEADERS = ("authorization", "x-api-key", "anthropic-version")
_CASES = {
    "plain": None,
    "effort_high": {"max_output_tokens": 16, "reasoning": {"enabled": True, "effort": "high"}},
    "reasoning_on_no_effort": {"max_output_tokens": 16, "reasoning": {"enabled": True}},
    "budget": {"max_output_tokens": 1025, "reasoning": {"enabled": True, "budget_tokens": 1024}},
}


def _case_keys() -> list[str]:
    return sorted(BASELINE)


async def _wire_for(method_id: str, case: str, multimodal: bool) -> dict[str, object]:
    from graph_agent_gateway.probing import probe_official_call_method

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = {
            key: value for key, value in request.headers.items() if key in _RECORDED_HEADERS
        }
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json={"ok": True}, request=request)

    try:
        await probe_official_call_method(
            method_id,
            "SECRET",
            "https://host.example/v1",
            "m-1",
            runtime_settings=_CASES[case],
            transport=httpx.MockTransport(handler),
            multimodal=multimodal,
        )
    except ValueError:
        return {"refused": True}
    return captured


@pytest.mark.anyio
@pytest.mark.parametrize("case_key", _case_keys())
async def test_probe_request_matches_the_recorded_wire(case_key: str) -> None:
    method_id, case, multimodal_flag = case_key.split("|")
    multimodal = multimodal_flag == "multimodal=True"

    assert await _wire_for(method_id, case, multimodal) == BASELINE[case_key]


def test_the_baseline_covers_every_official_method() -> None:
    from graph_agent_gateway.registry import official_call_method_ids

    covered = {key.split("|")[0] for key in BASELINE}

    assert official_call_method_ids() <= covered
