"""What a Test says about a fallback chain, when only some of it answers.

A chain exists so that a dead link is survivable: the caller reaches the model
through whichever route answers. So the verdict on the chain cannot be read off
the worst link — it has to be read off whether ANY link answered.

Found on 2026-08-21 by testing a real compare candidate on Auto fallback: 12 of
its 16 routes answered, 4 did not, and the dialog said "Test failed" while
listing only the 4 — a usable candidate reported as broken, with no sign that
anything had worked.
"""

from __future__ import annotations

from typing import Any

from app.routers import llm as llm_router


def _result(status: str, *, warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "warnings": warnings or []}


def test_a_chain_with_one_answering_route_is_not_a_failure() -> None:
    status = llm_router._chain_test_status(
        [_result("ok"), _result("failed"), _result("ok")]
    )

    assert status == "warning"


def test_a_chain_nothing_answers_on_is_a_failure() -> None:
    status = llm_router._chain_test_status([_result("failed"), _result("failed")])

    assert status == "failed"


def test_a_chain_that_could_not_be_reached_at_all_says_blocked() -> None:
    """Blocked outranks failed when nothing answered: it names the account-level
    reason, which is the one the reader can act on."""
    status = llm_router._chain_test_status([_result("failed"), _result("blocked")])

    assert status == "blocked"


def test_a_blocked_route_beside_a_working_one_still_leaves_the_chain_usable() -> None:
    status = llm_router._chain_test_status([_result("blocked"), _result("ok")])

    assert status == "warning"


def test_a_chain_where_everything_answers_is_ok() -> None:
    assert llm_router._chain_test_status([_result("ok"), _result("ok")]) == "ok"


def test_a_downgrade_on_an_otherwise_clean_chain_is_still_a_warning() -> None:
    """A warning is not only "some link failed" — it is also "it answered, but
    not the way you asked" (a downgrade), which F4's tooltip already reports."""
    status = llm_router._chain_test_status(
        [_result("ok"), _result("ok", warnings=[{"code": "thinking_not_enabled"}])]
    )

    assert status == "warning"


def test_an_empty_chain_is_not_silently_ok() -> None:
    """No route to test is not the same as every route passing."""
    assert llm_router._chain_test_status([]) == "failed"
