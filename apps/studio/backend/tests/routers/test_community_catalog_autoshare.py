"""Post-probe community auto-share (gate) wiring.

After a successful probe the desktop best-effort uploads newly probe-verified
evidence to the community catalog gate using an ingestion-scoped token (never a
repo token). Best-effort means a probe must NEVER fail because background sharing
failed, and the path stays dormant until upload is explicitly enabled AND a gate
URL + ingestion token are configured.
"""

from __future__ import annotations

import pytest
from app.core.backends import BackendConfig
from app.routers import llm as llm_router


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _enabled_config() -> BackendConfig:
    return BackendConfig(
        community_upload_enabled=True,
        community_gate_url="https://gate.example.workers.dev",
        community_ingestion_token="tkn-test",
    )


@pytest.mark.anyio
async def test_autoshare_dormant_when_upload_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dormant by default: never collects evidence when upload is not configured."""
    monkeypatch.setattr(llm_router, "get_backend_config", BackendConfig)
    collected = False

    def spy_collect(*args: object, **kwargs: object) -> list[object]:
        nonlocal collected
        collected = True
        return []

    monkeypatch.setattr(llm_router, "collect_uploadable_uploads", spy_collect)
    await llm_router._autoshare_after_probe_best_effort()
    assert collected is False  # disabled => no network, no collection


@pytest.mark.anyio
async def test_autoshare_uploads_batch_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When configured, the probe-verified batch is uploaded to the gate."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    monkeypatch.setattr(llm_router, "load_evidence_library", lambda: object())
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    sentinel = [object()]
    monkeypatch.setattr(llm_router, "collect_uploadable_uploads", lambda *a, **k: sentinel)
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def upload_batch(
            self, records: object, *, idempotency_key: str, queue: object = None
        ) -> object:
            captured["records"] = records
            captured["idempotency_key"] = idempotency_key
            return object()

    monkeypatch.setattr(llm_router, "CommunityUploadClient", FakeClient)
    await llm_router._autoshare_after_probe_best_effort()

    assert captured["records"] is sentinel
    assert captured["idempotency_key"] == "key-1"
    init = captured["init"]
    assert isinstance(init, dict)
    assert init["gate_url"] == "https://gate.example.workers.dev"
    assert init["ingestion_token"] == "tkn-test"


@pytest.mark.anyio
async def test_autoshare_skips_when_no_uploadable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing to upload => the client is never constructed."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    monkeypatch.setattr(llm_router, "load_evidence_library", lambda: object())
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable_uploads", lambda *a, **k: [])

    constructed = False

    class TripwireClient:
        def __init__(self, **kwargs: object) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setattr(llm_router, "CommunityUploadClient", TripwireClient)
    await llm_router._autoshare_after_probe_best_effort()
    assert constructed is False


@pytest.mark.anyio
async def test_autoshare_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Best-effort: an upload failure must not propagate out of the hook."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    monkeypatch.setattr(llm_router, "load_evidence_library", lambda: object())
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable_uploads", lambda *a, **k: [object()])
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    class BoomClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def upload_batch(
            self, records: object, *, idempotency_key: str, queue: object = None
        ) -> object:
            raise RuntimeError("gate down")

    monkeypatch.setattr(llm_router, "CommunityUploadClient", BoomClient)
    # Must not raise — a probe never fails because background sharing did.
    await llm_router._autoshare_after_probe_best_effort()
