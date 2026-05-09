from __future__ import annotations

import hashlib

import pytest
from app.services.copilot import make_session_key, resolve_base_url


def test_session_key_differs_by_skill_and_backend() -> None:
    assert make_session_key("skill-a", "claude", "same-key") != make_session_key("skill-b", "claude", "same-key")
    assert make_session_key("skill-a", "claude", "same-key") != make_session_key(
        "skill-a",
        "deepseek",
        "same-key",
    )


def test_session_key_is_stable_for_same_skill_backend_and_api_key() -> None:
    assert make_session_key("skill-a", "claude", "same-key") == make_session_key("skill-a", "claude", "same-key")


def test_session_key_changes_when_api_key_changes() -> None:
    assert make_session_key("skill-a", "claude", "old-key") != make_session_key("skill-a", "claude", "new-key")


def test_session_key_hashes_api_key_one_way() -> None:
    api_key = "sk-ant-secret"
    _, _, api_key_hash = make_session_key("skill-a", "claude", api_key)

    assert api_key_hash == hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    assert len(api_key_hash) == 16
    assert api_key not in api_key_hash


def test_resolve_base_url_v1_backends() -> None:
    assert resolve_base_url("claude") is None
    assert resolve_base_url("deepseek") == "https://api.deepseek.com/anthropic"


def test_resolve_base_url_rejects_v1_5_backends() -> None:
    with pytest.raises(NotImplementedError):
        resolve_base_url("gemini")
    with pytest.raises(NotImplementedError):
        resolve_base_url("openai")
