"""Post-probe community auto-share (gate) wiring.

After a successful probe the desktop best-effort uploads newly probe-verified
evidence to the community catalog gate through a clean open API (no token, no
credentials — the gate rate-limits server-side). Best-effort means a probe must
NEVER fail because background sharing failed.

A SINGLE community model-catalog toggle (``remote_model_catalog_enabled``, on by
default) gates BOTH reading the catalog and contributing to it — so the upload
stays dormant whenever the user turns that one switch off, even though the gate
URL ships built in and contribution is on by default.
"""

from __future__ import annotations

import pytest
from app.core.backends import BackendConfig
from app.models.settings import AppSettings
from app.routers import llm as llm_router


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _enabled_config() -> BackendConfig:
    return BackendConfig(
        community_upload_enabled=True,
        community_gate_url="https://gate.example.workers.dev",
    )


class _FakeMetadata:
    """Stand-in MetadataStore returning a fixed catalog-toggle value."""

    def __init__(self, *, catalog_enabled: bool) -> None:
        self._catalog_enabled = catalog_enabled

    async def read_app_settings(self) -> AppSettings:
        return AppSettings(remote_model_catalog_enabled=self._catalog_enabled)


def _patch_metadata(monkeypatch: pytest.MonkeyPatch, *, catalog_enabled: bool) -> None:
    monkeypatch.setattr(
        llm_router, "get_metadata", lambda: _FakeMetadata(catalog_enabled=catalog_enabled)
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

    monkeypatch.setattr(llm_router, "collect_uploadable",spy_collect)
    await llm_router._autoshare_after_probe_best_effort()
    assert collected is False  # disabled => no network, no collection


@pytest.mark.anyio
async def test_autoshare_uploads_batch_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When configured AND the catalog toggle is on, the batch is uploaded."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    sentinel = [object()]
    monkeypatch.setattr(llm_router, "collect_uploadable",lambda *a, **k: sentinel)
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def upload_batch(self, records: object, *, idempotency_key: str) -> object:
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
    # Clean open API: the client is constructed without any token.
    assert "ingestion_token" not in init


@pytest.mark.anyio
async def test_autoshare_respects_user_optout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The single catalog toggle gates upload too: off => no collection, no client."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=False)

    collected = False

    def spy_collect(*args: object, **kwargs: object) -> list[object]:
        nonlocal collected
        collected = True
        return [object()]

    monkeypatch.setattr(llm_router, "collect_uploadable",spy_collect)

    constructed = False

    class TripwireClient:
        def __init__(self, **kwargs: object) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setattr(llm_router, "CommunityUploadClient", TripwireClient)
    await llm_router._autoshare_after_probe_best_effort()
    assert collected is False  # user opted out => never even collects
    assert constructed is False


@pytest.mark.anyio
async def test_autoshare_skips_when_no_uploadable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing to upload => the client is never constructed."""
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable",lambda *a, **k: [])

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
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable",lambda *a, **k: [object()])
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    class BoomClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def upload_batch(self, records: object, *, idempotency_key: str) -> object:
            raise RuntimeError("gate down")

    monkeypatch.setattr(llm_router, "CommunityUploadClient", BoomClient)
    # Must not raise — a probe never fails because background sharing did.
    await llm_router._autoshare_after_probe_best_effort()


@pytest.mark.anyio
async def test_autoshare_logs_uploaded_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    # W2-E.1c: a successful auto-share records an `autoshare_uploaded` activity with
    # the contributed count, so General settings can show the upload happened.
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable", lambda *a, **k: [object(), object()])
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def upload_batch(self, records: object, *, idempotency_key: str) -> object:
            return object()

    monkeypatch.setattr(llm_router, "CommunityUploadClient", FakeClient)
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(llm_router, "record_runtime_activity", lambda **k: logged.append(k))

    await llm_router._autoshare_after_probe_best_effort()

    uploaded = [event for event in logged if event["action"] == "autoshare_uploaded"]
    assert len(uploaded) == 1
    assert uploaded[0]["source_id"] == "llm_credentials"
    assert uploaded[0]["changes"] == {"uploaded_count": 2}


@pytest.mark.anyio
async def test_autoshare_logs_failed_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    # W2-E.1c: a failed upload records an `autoshare_failed` activity (and still never
    # propagates out of the best-effort hook).
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    monkeypatch.setattr(llm_router, "collect_uploadable", lambda *a, **k: [object()])
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    class BoomClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def upload_batch(self, records: object, *, idempotency_key: str) -> object:
            raise RuntimeError("gate down")

    monkeypatch.setattr(llm_router, "CommunityUploadClient", BoomClient)
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(llm_router, "record_runtime_activity", lambda **k: logged.append(k))

    await llm_router._autoshare_after_probe_best_effort()  # must not raise

    failed = [event for event in logged if event["action"] == "autoshare_failed"]
    assert len(failed) == 1
    assert failed[0]["changes"]["attempted_count"] == 1
