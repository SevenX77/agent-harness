from __future__ import annotations

from pathlib import Path

import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.services.llm_credentials import load_credentials, save_credentials
from app.services.llm_import_drafts import (
    DraftApplyConflict,
    DraftExpired,
    append_evidence_record,
    create_draft,
    load_draft,
    load_evidence_library,
    save_draft,
)
from graph_agent_gateway.registry.schema import (
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


def test_apply_draft_persists_protocol_canonical_base_urls(tmp_path: Path) -> None:
    from app.services.llm_import_drafts import apply_draft

    store_path = tmp_path / "import_drafts.json"
    credentials_path = tmp_path / "llm_credentials.json"
    draft = ProviderImportDraft(
        draft_id="canonical-draft",
        source={"url": "https://provider.example/docs"},
        status="pending",
        endpoint_candidates={
            "wavespeed-anthropic": EndpointCandidate(
                endpoint_id="wavespeed-anthropic",
                display_name="WaveSpeed Anthropic",
                protocol="anthropic_compatible",
                base_url="https://llm.wavespeed.ai/v1/",
                api_key="secret",
            ),
            "deepseek-anthropic": EndpointCandidate(
                endpoint_id="deepseek-anthropic",
                display_name="DeepSeek Anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.deepseek.com/v1/",
                api_key="secret",
            ),
            "ark-runtime": EndpointCandidate(
                endpoint_id="ark-runtime",
                display_name="Ark Runtime",
                protocol="ark_runtime",
                base_url="https://ark.cn-beijing.volces.com/",
                api_key="secret",
            ),
            "openai-compatible": EndpointCandidate(
                endpoint_id="openai-compatible",
                display_name="OpenAI Compatible",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            ),
        },
    )
    save_draft(draft, path=store_path)

    apply_draft("canonical-draft", path=store_path, credentials_path=credentials_path)

    saved = load_credentials(credentials_path)
    assert saved.provider_endpoints["wavespeed-anthropic"].base_url == "https://llm.wavespeed.ai"
    assert (
        saved.provider_endpoints["deepseek-anthropic"].base_url
        == "https://api.deepseek.com/anthropic"
    )
    assert (
        saved.provider_endpoints["ark-runtime"].base_url
        == "https://ark.cn-beijing.volces.com/api/v3"
    )
    assert saved.provider_endpoints["openai-compatible"].base_url == "https://api.openai.example/v1"


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
