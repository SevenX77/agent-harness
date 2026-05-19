from __future__ import annotations

import hashlib

from app.services.copilot import make_session_key


def test_session_key_differs_by_skill_and_model() -> None:
    assert make_session_key("skill-a", "CL46T", "OC_CL_ANT", "same-key") != make_session_key(
        "skill-b",
        "CL46T",
        "OC_CL_ANT",
        "same-key",
    )
    assert make_session_key("skill-a", "CL46T", "OC_CL_ANT", "same-key") != make_session_key(
        "skill-a",
        "DS32R",
        "OC_DS",
        "same-key",
    )


def test_session_key_is_stable_for_same_skill_model_provider_and_api_key() -> None:
    assert make_session_key("skill-a", "CL46T", "OC_CL_ANT", "same-key") == make_session_key(
        "skill-a",
        "CL46T",
        "OC_CL_ANT",
        "same-key",
    )


def test_session_key_changes_when_api_key_changes() -> None:
    assert make_session_key("skill-a", "CL46T", "OC_CL_ANT", "old-key") != make_session_key(
        "skill-a",
        "CL46T",
        "OC_CL_ANT",
        "new-key",
    )


def test_session_key_hashes_api_key_one_way() -> None:
    api_key = "sk-ant-secret"
    _, model_provider, api_key_hash = make_session_key("skill-a", "CL46T", "OC_CL_ANT", api_key)

    assert model_provider == "CL46T:OC_CL_ANT"
    assert api_key_hash == hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    assert len(api_key_hash) == 16
    assert api_key not in api_key_hash
