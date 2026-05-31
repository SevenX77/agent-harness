from __future__ import annotations

from pathlib import Path

import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.services.llm_credentials import load_credentials, save_credentials
from app.services.llm_import_drafts import (
    DraftApplyConflict,
    DraftExpired,
    create_draft,
    load_draft,
    save_draft,
)
from graph_agent_gateway.registry.schema import (
    EndpointCandidate,
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
