from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.llm_credentials import load_credentials, save_credentials
from app.services.llm_import_drafts import (
    DraftApplyConflict,
    DraftExpired,
    RemoteCatalogSyncError,
    append_evidence_record,
    create_draft,
    load_draft,
    load_evidence_library,
    save_draft,
    sync_remote_evidence_library,
)
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EndpointCandidate,
    EvidenceRecord,
    FieldSource,
    ProviderImportDraft,
    RouteCandidate,
)


def _draft() -> ProviderImportDraft:
    return ProviderImportDraft(
        draft_id="draft-1",
        source={"url": "https://provider.example/docs"},
        status="pending",
        endpoint_candidates={
            "openai-direct": EndpointCandidate(
                endpoint_id="openai-direct",
                display_name="OpenAI Direct",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
                field_sources={
                    "base_url": FieldSource(source="agent_draft", message="docs"),
                },
            ),
            "openrouter-prod": EndpointCandidate(
                endpoint_id="openrouter-prod",
                display_name="OpenRouter",
                protocol="openai_compatible",
                base_url="https://openrouter.example/v1",
            ),
        },
        route_candidates={
            "openai-direct:gpt-5": RouteCandidate(
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
            )
        },
    )


def test_import_draft_store_round_trips_multi_endpoint_draft(tmp_path: Path) -> None:
    store_path = tmp_path / "import_drafts.json"

    draft = create_draft(_draft(), path=store_path)

    loaded = load_draft(draft.draft_id, path=store_path)
    assert loaded.draft_id == "draft-1"
    assert set(loaded.endpoint_candidates) == {"openai-direct", "openrouter-prod"}
    assert loaded.route_candidates["openai-direct:gpt-5"].endpoint_id == "openai-direct"
    assert loaded.evidence_records == []


def test_legacy_import_draft_without_evidence_records_loads_and_saves(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "import_drafts.json"
    store_path.write_text(
        """
{
  "drafts": {
    "legacy-draft": {
      "draft_id": "legacy-draft",
      "source": {"url": "https://provider.example/docs"},
      "status": "pending"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    draft = load_draft("legacy-draft", path=store_path)
    save_draft(draft, path=store_path)

    saved = load_draft("legacy-draft", path=store_path)
    assert saved.evidence_records == []


def test_evidence_library_appends_probe_failure_without_overwriting_success(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "import_drafts.json"
    success = EvidenceRecord(
        evidence_id="evidence-success",
        evidence_type="probe",
        trust_state="probe-verified",
        observed_at="2026-05-31T10:00:00+00:00",
        endpoint_id="openai-official",
        route_id="openai-official:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        method_id="openai_responses",
        request_mapper_id="openai_responses_text",
        probe_status="ok",
        scope={"endpoint_id": "openai-official", "route_id": "openai-official:gpt-5"},
        probe_attempts=[{"status": "ok"}],
        successful_probe={"profile_count": 1},
    )
    failure = EvidenceRecord(
        evidence_id="evidence-failure",
        evidence_type="probe",
        trust_state="probe-failed",
        observed_at="2026-05-31T10:05:00+00:00",
        endpoint_id="openai-official",
        route_id="openai-official:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        method_id="openai_responses",
        request_mapper_id="openai_responses_text",
        probe_status="error",
        reason="provider rejected the request",
        scope={"endpoint_id": "openai-official", "route_id": "openai-official:gpt-5"},
        probe_attempts=[{"status": "error", "message": "provider rejected the request"}],
        failed_probe={"status": "error", "reason": "provider rejected the request"},
    )

    append_evidence_record(success, path=store_path)
    append_evidence_record(failure, path=store_path)

    library = load_evidence_library(path=store_path)
    assert [record.trust_state for record in library.evidence_records] == [
        "probe-verified",
        "probe-failed",
    ]
    assert library.evidence_records[0].successful_probe == {"profile_count": 1}
    assert library.evidence_records[1].reason == "provider rejected the request"


def test_sync_remote_evidence_library_raises_on_remote_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "import_drafts.json"
    cached = ProviderImportDraft(
        draft_id="studio-evidence-library",
        source={"kind": "studio_evidence_library"},
        status="pending",
        route_candidates={
            "openai-official:gpt-5": RouteCandidate(
                endpoint_id="openai-official",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
            )
        },
    )
    save_draft(cached, path=store_path)

    request = httpx.Request("GET", "https://example.invalid/llm_import_drafts.json")
    response = httpx.Response(404, request=request)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def get(self, _url: str) -> httpx.Response:
            return response

    import app.services.llm_import_drafts as import_drafts

    monkeypatch.setattr(import_drafts.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(RemoteCatalogSyncError, match="404"):
        asyncio.run(
            sync_remote_evidence_library(
                url=str(request.url),
                path=store_path,
            )
        )

    assert load_evidence_library(path=store_path).route_candidates == cached.route_candidates


def test_apply_draft_marks_applied_without_losing_interleaved_evidence_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.llm_import_drafts as import_drafts

    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    save_draft(_draft(), path=store_path)
    interleaved = EvidenceRecord(
        evidence_id="evidence-interleaved",
        evidence_type="probe",
        trust_state="probe-verified",
        endpoint_id="openai-direct",
        route_id="openai-direct:gpt-5",
        model_id="gpt-5",
        provider_model_id="gpt-5",
        probe_status="ok",
    )
    original_save_all = import_drafts.ImportDraftStore.save_all
    injected = False
    append_threads: list[threading.Thread] = []

    def _save_all_with_interleaved_append(self, drafts: dict[str, ProviderImportDraft]) -> None:
        nonlocal injected
        lock_owned = getattr(self._write_lock, "_is_owned", lambda: False)()
        draft = drafts.get("draft-1")
        if not injected and draft is not None and draft.status == "applied":
            injected = True
            if lock_owned:
                append_started = threading.Event()

                def _append_after_apply_lock_releases() -> None:
                    append_started.set()
                    append_evidence_record(interleaved, path=store_path)

                thread = threading.Thread(target=_append_after_apply_lock_releases)
                append_threads.append(thread)
                thread.start()
                assert append_started.wait(timeout=2)
            else:
                append_evidence_record(interleaved, path=store_path)
        original_save_all(self, drafts)

    monkeypatch.setattr(import_drafts.ImportDraftStore, "save_all", _save_all_with_interleaved_append)

    applied = apply_draft("draft-1", path=store_path, credentials_path=credentials_path)
    for thread in append_threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    evidence_ids = [record.evidence_id for record in load_evidence_library(path=store_path).evidence_records]
    assert applied.status == "applied"
    assert injected is True
    assert evidence_ids == ["evidence-interleaved"]


def test_expired_draft_apply_is_rejected(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    draft = _draft().model_copy(update={"status": "expired"})
    save_draft(draft, path=store_path)

    with pytest.raises(DraftExpired):
        apply_draft("draft-1", path=store_path, credentials_path=credentials_path)


def test_active_endpoint_collision_requires_explicit_choice(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": ProviderEndpoint(
                    endpoint_id="openai-direct",
                    display_name="Existing",
                    protocol="openai_compatible",
                    base_url="https://existing.example/v1",
                    api_key="existing-secret",
                )
            }
        ),
        credentials_path,
    )
    save_draft(_draft(), path=store_path)

    with pytest.raises(DraftApplyConflict, match="openai-direct"):
        apply_draft("draft-1", path=store_path, credentials_path=credentials_path)

    apply_draft(
        "draft-1",
        path=store_path,
        credentials_path=credentials_path,
        conflict_mode="merge",
    )

    saved = load_credentials(credentials_path)
    assert saved.provider_endpoints["openai-direct"].api_key.get_secret_value() == "secret"
    assert "openai-direct:gpt-5" in saved.provider_routes


def test_apply_draft_rejects_route_candidates_missing_materialized_endpoint(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {},
            "route_candidates": {
                "missing-endpoint:gpt-5": RouteCandidate(
                    endpoint_id="missing-endpoint",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                )
            },
        }
    )
    save_draft(draft, path=store_path)

    with pytest.raises(DraftApplyConflict, match="missing endpoint"):
        apply_draft("draft-1", path=store_path, credentials_path=credentials_path)

    saved = load_credentials(credentials_path)
    assert saved.provider_routes == {}


def test_active_route_collision_requires_explicit_choice_before_apply(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_routes={
                "openai-direct:gpt-5": ProviderRoute(
                    route_id="openai-direct:gpt-5",
                    endpoint_id="openai-direct",
                    route_slug="gpt-5",
                    provider_model_id="legacy-gpt-5",
                    canonical_id="legacy/gpt-5",
                    display_name="Legacy GPT-5",
                    status="verified",
                )
            }
        ),
        credentials_path,
    )
    save_draft(_draft(), path=store_path)

    with pytest.raises(DraftApplyConflict, match="active routes already exist: openai-direct:gpt-5"):
        apply_draft("draft-1", path=store_path, credentials_path=credentials_path)

    saved = load_credentials(credentials_path)
    assert saved.provider_routes["openai-direct:gpt-5"].provider_model_id == "legacy-gpt-5"


def test_apply_draft_uses_gateway_candidate_materialization_for_canonical_base_url(
    tmp_path: Path,
) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {
                "openai-direct": _draft()
                .endpoint_candidates["openai-direct"]
                .model_copy(
                    update={
                        "protocol": "anthropic_compatible",
                        "base_url": "https://llm.wavespeed.ai/v1/",
                    }
                )
            }
        }
    )
    save_draft(draft, path=store_path)

    apply_draft("draft-1", path=store_path, credentials_path=credentials_path)

    saved = load_credentials(credentials_path)
    assert saved.provider_endpoints["openai-direct"].base_url == "https://llm.wavespeed.ai"
    assert saved.provider_routes["openai-direct:gpt-5"].status == "unverified_manual"


def test_apply_draft_preserves_secret_display_name_capabilities_and_metadata(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    draft = _draft().model_copy(
        update={
            "endpoint_candidates": {
                "openai-direct": _draft()
                .endpoint_candidates["openai-direct"]
                .model_copy(update={"metadata": {"region": "us-west"}})
            },
            "route_candidates": {
                "openai-direct:gpt-5": _draft()
                .route_candidates["openai-direct:gpt-5"]
                .model_copy(
                    update={
                        "capabilities": {
                            "max_output_tokens": CapabilityValue(value={"max": 128000}, source="agent_draft")
                        },
                        "metadata": {"family": "gpt"},
                    }
                )
            },
        }
    )
    save_draft(draft, path=store_path)

    apply_draft("draft-1", path=store_path, credentials_path=credentials_path)

    saved = load_credentials(credentials_path)
    endpoint = saved.provider_endpoints["openai-direct"]
    route = saved.provider_routes["openai-direct:gpt-5"]
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "secret"
    assert endpoint.display_name == "OpenAI Direct"
    assert endpoint.metadata == {"region": "us-west"}
    assert route.display_name == "GPT-5"
    assert route.capabilities["max_output_tokens"].value == {"max": 128000}
    assert route.metadata == {"family": "gpt"}
