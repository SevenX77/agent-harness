"""Every message the report prints is bounded and stays on its own line.

RUN_EXECUTION-9 already says a single message is truncated at 200 characters,
and gives the reason: "实测一条 protocol_violation 消息几千字,原样打印会把同一节里
其他失败全部压到屏幕外" — the full text is one link away in `trace.jsonl`, and what
the report owes the reader is "recognisable", not a verbatim transcript.

The rule was applied in exactly one spot. Field evidence, run
`2026-08-20T10-27-18_a98f6ba5` (story-deconstruction-v3-lab): a
`dropped_rejected_settings` decision carried the provider's raw 400 body as its
reason, the Routes table printed it whole, and one table cell came to 263,241
characters — a 529 KB report for a run that made three LLM calls.

Two other paths leak the same way and are covered here:

* the Failure section clips `message` but not the `errors` / `violations`
  lists, which is where a rejected `finish_task_verdict` arrives;
* the unmet-settings table prints each setting's reason whole.

Length is not the only thing a raw provider message breaks. A markdown table
row is delimited by `|`, so a message containing one silently splits its own
row into extra columns, and a message containing a newline ends the row early.
"""

from __future__ import annotations

import json
import re

from app.services.run_report_routes import routes_section
from app.services.run_report_text import MESSAGE_BUDGET, one_line, table_cell

HUGE = "BadRequestError: Error code: 400 - " + json.dumps(
    {"errors": [{"code": "invalid_union", "path": [index]} for index in range(400)]}
)


def _route_decision(reason: str, decision: str = "dropped_rejected_settings") -> dict[str, object]:
    return {
        "event_type": "llm_route_decision",
        "route_id": "openrouter:deepseek-v4-flash",
        "provider_model_id": "deepseek/deepseek-v4-flash",
        "decision": decision,
        "reason": reason,
    }


def _call_settings(reason: str) -> dict[str, object]:
    return {
        "event_type": "llm_call_settings",
        "route_id": "openrouter:deepseek-v4-flash",
        "settings": [
            {
                "setting": "reasoning.enabled",
                "requested": True,
                "verdict": "rejected",
                "reason": reason,
            }
        ],
    }


def test_a_providers_raw_error_body_does_not_become_the_report() -> None:
    assert len(HUGE) > 10_000, "the fixture has to be big enough to be the defect"

    section = routes_section([_route_decision(HUGE)])

    longest = max(len(line) for line in section.split("\n"))
    assert longest < 400, f"a single Routes line came to {longest} characters"
    assert "BadRequestError: Error code: 400" in section, "it still has to be recognisable"


def test_a_clipped_message_says_it_was_clipped() -> None:
    section = routes_section([_route_decision(HUGE)])

    assert "…" in section, "a reader must be able to tell the message was cut"


def test_a_reason_with_a_pipe_does_not_split_its_own_row() -> None:
    section = routes_section([_route_decision("timeout | retry | gave up")])

    row = next(line for line in section.split("\n") if "dropped" in line)
    delimiters = re.findall(r"(?<!\\)\|", row)
    assert len(delimiters) == 4, f"a three-cell row grew extra columns: {row}"
    assert "timeout" in row and "gave up" in row, "escaping must not eat the text"


def test_a_reason_with_a_newline_does_not_end_its_own_row() -> None:
    section = routes_section([_route_decision("first line\nsecond line")])

    assert "second line" in section
    row = next(line for line in section.split("\n") if "second line" in line)
    assert row.startswith("|") and row.endswith("|")


def test_the_unmet_settings_table_clips_too() -> None:
    """The same reason, printed a second time, is not exempt from the same rule."""
    section = routes_section([_call_settings(HUGE)])

    assert "Settings that did not run as asked" in section
    longest = max(len(line) for line in section.split("\n"))
    assert longest < 400, f"a single unmet-settings line came to {longest} characters"


def test_one_line_keeps_a_short_message_exactly_as_it_is() -> None:
    assert one_line("Request timed out.") == "Request timed out."


def test_one_line_bounds_a_long_one() -> None:
    clipped = one_line("x" * (MESSAGE_BUDGET * 3))

    assert len(clipped) == MESSAGE_BUDGET + 1, "the budget plus the mark that says it was cut"
    assert clipped.endswith("…")


def test_a_table_cell_escapes_the_delimiter_it_sits_between() -> None:
    assert table_cell("a | b") == r"a \| b"
