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
from app.core.adapters.gateway import EvidenceUpload
from app.core.backends import BackendConfig
from app.models.settings import AppSettings
from app.routers import llm as llm_router
from app.services.community_catalog_upload import UploadAck


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _enabled_config() -> BackendConfig:
    return BackendConfig(
        community_upload_enabled=True,
        community_gate_url="https://gate.example.workers.dev",
    )


def _evidence_upload(**overrides: object) -> EvidenceUpload:
    """A representative sanitized upload record for log-content assertions.

    ``EvidenceUpload`` is the wire-safe, ``extra="forbid"`` allowlisted shape
    (packages/graph-agent-gateway/.../evidence_wire.py) — it carries no secret
    or credential, so dumping it whole into the runtime activity log is safe.
    """
    fields: dict[str, object] = {
        "evidence_type": "probe_result",
        "trust_state": "probe-verified",
        "provider_id": "openai",
        "normalized_public_base_url": "https://api.openai.com/v1",
        "endpoint_fingerprint": "fingerprint-abc123",
        "route_key": "openai:gpt-4o",
        "provider_model_id": "gpt-4o",
        "model_id": "gpt-4o",
        "method_id": "chat.completions",
        "request_mapper_id": "openai-chat",
        "capability_family": "language",
        "model_type": "chat",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "probe_status": "verified",
        "observed_at": "2026-08-24T00:00:00+00:00",
    }
    fields.update(overrides)
    return EvidenceUpload(**fields)  # type: ignore[arg-type]


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
    sentinel = [_evidence_upload()]
    monkeypatch.setattr(llm_router, "collect_uploadable",lambda *a, **k: sentinel)
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda uploads: "key-1")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def upload_batch(self, records: object, *, idempotency_key: str) -> UploadAck:
            captured["records"] = records
            captured["idempotency_key"] = idempotency_key
            return UploadAck(accepted=1, rejected=0, receipt_token="receipt-1")

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
        return [_evidence_upload()]

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
    monkeypatch.setattr(llm_router, "collect_uploadable",lambda *a, **k: [_evidence_upload()])
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
    #
    # 2026-08-24 (log-content gap): a count alone violates the runtime-log
    # principle (docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:808 —
    # "changes 必须承载与真相 json 文件一致的事实明细") that Runtime log details
    # must reflect the same facts as the underlying truth file, not a one-line
    # summary. So this now also asserts the full per-record payload, the gate
    # URL, the idempotency key, and the gate's ack (including the receipt_token
    # needed to ever retract a contribution).
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    uploads = [
        _evidence_upload(provider_id="openai", model_id="gpt-4o"),
        _evidence_upload(provider_id="anthropic", model_id="claude-sonnet", route_key="anthropic:claude-sonnet"),
    ]
    monkeypatch.setattr(llm_router, "collect_uploadable", lambda *a, **k: uploads)
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda passed: "key-1")

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def upload_batch(self, records: object, *, idempotency_key: str) -> UploadAck:
            return UploadAck(accepted=2, rejected=0, receipt_token="receipt-xyz")

    monkeypatch.setattr(llm_router, "CommunityUploadClient", FakeClient)
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(llm_router, "record_runtime_activity", lambda **k: logged.append(k))

    await llm_router._autoshare_after_probe_best_effort()

    uploaded = [event for event in logged if event["action"] == "autoshare_uploaded"]
    assert len(uploaded) == 1
    assert uploaded[0]["source_id"] == "llm_credentials"
    changes = uploaded[0]["changes"]
    assert isinstance(changes, dict)
    assert changes["uploaded_count"] == 2
    # Full per-record content — not just a count — so Runtime log detail
    # matches what actually went out, record for record.
    assert changes["records"] == [upload.model_dump(exclude_none=True) for upload in uploads]
    assert changes["gate_url"] == "https://gate.example.workers.dev"
    assert changes["idempotency_key"] == "key-1"
    # The gate ack, including the receipt_token — the only handle to ever
    # retract this contribution later; losing it here loses it forever.
    assert changes["accepted"] == 2
    assert changes["rejected"] == 0
    assert changes["receipt_token"] == "receipt-xyz"


@pytest.mark.anyio
async def test_autoshare_logs_failed_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    # W2-E.1c: a failed upload records an `autoshare_failed` activity (and still never
    # propagates out of the best-effort hook). 2026-08-24: the attempted records and
    # the gate URL must also be visible, symmetric with the success log, so a failed
    # contribution attempt is auditable too.
    monkeypatch.setattr(llm_router, "get_backend_config", _enabled_config)
    _patch_metadata(monkeypatch, catalog_enabled=True)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: object())
    uploads = [_evidence_upload()]
    monkeypatch.setattr(llm_router, "collect_uploadable", lambda *a, **k: uploads)
    monkeypatch.setattr(llm_router, "batch_idempotency_key", lambda passed: "key-1")

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
    changes = failed[0]["changes"]
    assert isinstance(changes, dict)
    assert changes["attempted_count"] == 1
    assert changes["records"] == [upload.model_dump(exclude_none=True) for upload in uploads]
    assert changes["gate_url"] == "https://gate.example.workers.dev"
