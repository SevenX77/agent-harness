"""WS-5 regression-lock: ``copilot_`` role-key routing contract.

settings-ux-spec §3.5 documents a frontend bug where ``CopilotTab.selectModelGroup``
rewrites a ``copilot_*`` role key into a bare model-group id (e.g.
``claude-opus-4.7``). The backend ``_is_copilot_role`` only recognises the
``copilot_`` prefix, so a bare-keyed role is misclassified as a Graph Agent role
and stored on the wrong side of the put_llm_roles split.

This test pins the backend contract: copilot roles MUST keep the ``copilot_``
prefix to survive routing. The bug itself is caught by the frontend RED
(``CopilotTab``); this is the backend-side regression lock (GREEN today).
"""

from __future__ import annotations

from app.routers.llm import _is_copilot_role


def test_copilot_prefix_is_recognized_as_copilot_role() -> None:
    assert _is_copilot_role("copilot_chat") is True
    assert _is_copilot_role("copilot_opus_4_7") is True
    assert _is_copilot_role("copilot_custom_1") is True


def test_bare_model_group_id_is_not_a_copilot_role() -> None:
    # This is exactly what the buggy CopilotTab.selectModelGroup produced:
    # a bare canonical id that the backend would misroute to Graph Agent.
    assert _is_copilot_role("claude-opus-4.7") is False
    assert _is_copilot_role("deepseek-v4-pro") is False
