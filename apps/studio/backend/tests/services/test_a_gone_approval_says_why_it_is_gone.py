"""A held approval that is no longer held has to say WHICH way it went.

Problem ledger CP6, second half. Every one of these answered
`approval_not_found`:

* the call was decided a moment ago (a double click, or a stale card),
* the call timed out and the task was stopped,
* the app or the session restarted, so nothing is holding anything.

One string for three situations tells the reader nothing, and the frontend
papered over it by prefixing "Approval expired:" — asserting the middle case as
fact whichever one had actually happened.

The backend already knows the difference; it just threw it away. It now keeps,
per skill session, why each settled approval stopped being held — the way a
supervisor keeps a child's exit reason rather than only noting its absence.
The memory is bounded by the session: `_cleanup_pending_tool_approvals` drops
it along with the holds themselves.
"""

from __future__ import annotations

import asyncio

import pytest
from app.services import copilot as copilot_service
from app.services.copilot import resolve_tool_approval

SKILL = "demo-skill"
CALL = "toolu_01"


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    copilot_service._cleanup_pending_tool_approvals()
    copilot_service._settled_tool_approvals.clear()


def test_a_call_this_session_never_held_says_the_session_is_gone() -> None:
    outcome = resolve_tool_approval(SKILL, CALL, approve=True)

    assert outcome.resolved is False
    assert "session" in (outcome.message or "").lower()
    assert "not_found" not in (outcome.message or "")


def test_a_call_already_decided_says_it_was_decided() -> None:
    async def hold_then_decide_twice() -> tuple[object, object]:
        loop = asyncio.get_running_loop()
        copilot_service._pending_tool_approvals[(SKILL, CALL)] = loop.create_future()
        first = resolve_tool_approval(SKILL, CALL, approve=True)
        copilot_service._pending_tool_approvals.pop((SKILL, CALL), None)
        second = resolve_tool_approval(SKILL, CALL, approve=True)
        return first, second

    first, second = asyncio.run(hold_then_decide_twice())

    assert first.resolved is True
    assert second.resolved is False
    assert "already" in (second.message or "").lower()


def test_a_call_that_timed_out_says_it_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """The distinction that matters most: nobody answered, versus nobody asked."""
    monkeypatch.setattr(copilot_service, "_TOOL_APPROVAL_TIMEOUT_S", 0.01)

    async def hold_until_it_lapses() -> object:
        sink = copilot_service._SafeWriteSink(queue=asyncio.Queue(), workspace_root=None)  # type: ignore[arg-type]
        await copilot_service._hold_for_tool_approval(
            SKILL, sink, tool_name="Bash", detail="ls", tool_use_id=CALL
        )
        return resolve_tool_approval(SKILL, CALL, approve=True)

    outcome = asyncio.run(hold_until_it_lapses())

    assert outcome.resolved is False
    assert "timed out" in (outcome.message or "").lower()


def test_cleaning_a_session_forgets_its_settled_calls() -> None:
    """The memory is the session's, so it goes when the session does.

    Without this it would grow for as long as the process lives — and a call id
    from a session that has been torn down is exactly the "session is gone" case
    again, which is what the empty answer already says.
    """
    copilot_service._settled_tool_approvals[(SKILL, CALL)] = "decided"

    copilot_service._cleanup_pending_tool_approvals(SKILL)

    assert (SKILL, CALL) not in copilot_service._settled_tool_approvals
