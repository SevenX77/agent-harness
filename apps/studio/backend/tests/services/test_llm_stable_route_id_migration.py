from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models.llm_config import (
    EndpointCandidate,
    EvidenceRecord,
    LLMCredentialsFile,
    ModelBundle,
    ModelProfile,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RoleRouteEntry,
    RolesData,
    RouteCandidate,
)
from app.services.llm_credentials import load_credentials, save_credentials
from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore
from app.services.llm_import_drafts import load_evidence_library, save_draft
from app.services.llm_role_test_results import load_all as load_role_test_results
from app.services.llm_role_test_results import save_result
from app.services.llm_roles import load_roles_file, save_roles_file
from graph_agent_gateway.registry.route_identity import stable_endpoint_id, stable_route_id


def test_migration_rewrites_random_custom_route_ids_across_all_llm_stores(tmp_path: Path) -> None:
    old_endpoint_id = "custom-00000000-0000-4000-8000-000000000001"
    old_route_id = f"{old_endpoint_id}:openai.gpt-5"
    base_url = "https://llm.wavespeed.ai/v1"
    protocol = "openai_compatible"
    provider_model_id = "openai/gpt-5"
    new_route_id = stable_route_id(
        protocol=protocol,
        base_url=base_url,
        provider_model_id=provider_model_id,
    )
    new_endpoint_id = new_route_id.split(":", 1)[0]
    legacy_openrouter_route_id = "openrouter-prod:anthropic.claude-sonnet-4.6"
    legacy_openrouter_new_route_id = (
        f"{stable_endpoint_id(protocol='anthropic_compatible', base_url='https://openrouter.ai/api')}"
        ":anthropic.claude-sonnet-4.6"
    )
    orphan_endpoint_id = "custom-11111111-1111-4111-8111-111111111111"
    orphan_route_id = f"{orphan_endpoint_id}:anthropic.claude-sonnet-4.6"
    orphan_new_endpoint_id = legacy_openrouter_new_route_id.split(":", 1)[0]
    orphan_new_route_id = f"{orphan_new_endpoint_id}:anthropic.claude-sonnet-4.6"

    credentials_path = tmp_path / "llm_credentials.json"
    roles_path = tmp_path / "llm_roles.yaml"
    drafts_path = tmp_path / "llm_import_drafts.json"
    results_path = tmp_path / "llm_role_test_results.json"
    health_path = tmp_path / "llm_health.sqlite"

    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                old_endpoint_id: ProviderEndpoint(
                    endpoint_id=old_endpoint_id,
                    display_name="WaveSpeed Custom",
                    protocol=protocol,
                    base_url=base_url,
                    api_key="secret",
                    status="verified",
                    provider_kind="custom",
                )
            },
            provider_routes={
                old_route_id: ProviderRoute(
                    route_id=old_route_id,
                    endpoint_id=old_endpoint_id,
                    route_slug="openai.gpt-5",
                    provider_model_id=provider_model_id,
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                    metadata={"probe_attempts": [{"route_id": old_route_id}]},
                )
            },
        ),
        credentials_path,
    )
    roles = RolesData(
        model_profiles={
            "profile": ModelProfile(
                model_profile_id="profile",
                display_name="Profile",
                canonical_id="gpt-5",
                fallback_chain=[RoleRouteEntry(route_id=old_route_id)],
            )
        },
        model_bundles={
            "bundle": ModelBundle(
                model_profile_id="bundle",
                display_name="Bundle",
                canonical_id="gpt-5",
                model_groups=[
                    RoleModelGroup(
                        canonical_id="gpt-5",
                        display_name="GPT-5",
                        provider_models=[RoleProviderModel(route_id=old_route_id)],
                    )
                ],
                fallback_chain=[RoleRouteEntry(route_id=old_route_id)],
            )
        },
        roles={
            "assistant": RoleEntry(
                model_groups=[
                    RoleModelGroup(
                        canonical_id="gpt-5",
                        display_name="GPT-5",
                        provider_models=[RoleProviderModel(route_id=old_route_id)],
                    )
                ],
                fallback_chain=[RoleRouteEntry(route_id=old_route_id)],
            ),
            "legacy_openrouter": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id=legacy_openrouter_route_id)],
                source_profile_snapshot={"route_ids": [legacy_openrouter_route_id]},
            ),
            "legacy_official_slug": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="anthropic-official:claude-opus-4-7")],
            ),
        },
    )
    save_roles_file(
        roles_path,
        roles,
        known_route_ids={
            old_route_id,
            legacy_openrouter_route_id,
            "anthropic-official:claude-opus-4-7",
        },
        known_bundle_ids={"bundle"},
    )
    save_draft(
        ProviderImportDraft(
            draft_id="studio-evidence-library",
            source={"kind": "studio_evidence_library"},
            status="pending",
            endpoint_candidates={
                old_endpoint_id: EndpointCandidate(
                    endpoint_id=old_endpoint_id,
                    display_name="WaveSpeed Custom",
                    protocol=protocol,
                    base_url=base_url,
                    api_key="secret",
                )
            },
                route_candidates={
                    old_route_id: RouteCandidate(
                        endpoint_id=old_endpoint_id,
                        route_slug="openai.gpt-5",
                        provider_model_id=provider_model_id,
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                        metadata={"route_id": old_route_id},
                    ),
                    orphan_route_id: RouteCandidate(
                        endpoint_id=orphan_endpoint_id,
                        route_slug="anthropic.claude-sonnet-4.6",
                        provider_model_id="anthropic/claude-sonnet-4.6",
                        canonical_id="claude-sonnet-4.6",
                        display_name="Claude Sonnet 4.6",
                        metadata={"route_id": orphan_route_id},
                    )
                },
            probe_results={
                old_route_id: {"target_type": "route", "status": "success"},
            },
            evidence_records=[
                    EvidenceRecord(
                        evidence_id="probe-old",
                        evidence_type="probe",
                        trust_state="probe-verified",
                    endpoint_id=old_endpoint_id,
                    route_id=old_route_id,
                    model_id=provider_model_id,
                    provider_model_id=provider_model_id,
                    probe_status="ok",
                        scope={"endpoint_id": old_endpoint_id, "route_id": old_route_id},
                        successful_probe={"route_id": old_route_id},
                    ),
                    EvidenceRecord(
                        evidence_id="model-list-orphan",
                        evidence_type="model_list_observation",
                        trust_state="provider-list-observed",
                        endpoint_id=orphan_endpoint_id,
                        scope={"endpoint_id": orphan_endpoint_id},
                        model_list_observation={
                            "base_url_fingerprint": hashlib.sha256(
                                b"https://openrouter.ai/api"
                            ).hexdigest()[:16],
                            "observed_model_ids": ["anthropic/claude-sonnet-4.6"],
                        },
                    )
                ],
            ),
        path=drafts_path,
    )
    save_result(
        "assistant",
        {
            "routes": {
                old_route_id: {
                    "route_id": old_route_id,
                    "endpoint_id": old_endpoint_id,
                }
            },
            "selected_route_id": old_route_id,
        },
        status="ok",
        path=results_path,
    )
    health = SqliteLlmHealthStore(health_path)
    now = datetime.now(UTC)
    health.open_circuit(
        RuntimeCircuit(
            scope="route",
            scope_id=old_route_id,
            opened_at=now,
            retry_at=now + timedelta(minutes=5),
            ttl_seconds=300,
            reason_code="rate_limited",
        )
    )
    health.open_circuit(
        RuntimeCircuit(
            scope="endpoint",
            scope_id=old_endpoint_id,
            opened_at=now,
            retry_at=now + timedelta(minutes=5),
            ttl_seconds=300,
            reason_code="rate_limited",
        )
    )

    from app.services.llm_stable_id_migration import migrate_llm_stable_route_ids

    report = migrate_llm_stable_route_ids(
        credentials_path=credentials_path,
        roles_path=roles_path,
        import_drafts_path=drafts_path,
        role_test_results_path=results_path,
        health_db_path=health_path,
    )

    assert report.endpoint_id_map[old_endpoint_id] == new_endpoint_id
    assert report.endpoint_id_map["openrouter-prod"] == legacy_openrouter_new_route_id.split(":", 1)[0]
    assert report.route_id_map == {old_route_id: new_route_id}

    migrated_credentials = load_credentials(credentials_path)
    assert old_endpoint_id not in migrated_credentials.provider_endpoints
    assert old_route_id not in migrated_credentials.provider_routes
    assert migrated_credentials.provider_endpoints[new_endpoint_id].endpoint_id == new_endpoint_id
    assert migrated_credentials.provider_routes[new_route_id].endpoint_id == new_endpoint_id

    migrated_roles = load_roles_file(roles_path)
    assert migrated_roles.roles["assistant"].fallback_chain[0].route_id == new_route_id
    assert migrated_roles.roles["legacy_openrouter"].fallback_chain[0].route_id == legacy_openrouter_new_route_id
    assert migrated_roles.roles["legacy_openrouter"].source_profile_snapshot == {
        "route_ids": [legacy_openrouter_new_route_id],
    }
    assert (
        migrated_roles.roles["legacy_official_slug"].fallback_chain[0].route_id
        == "anthropic-official:claude-opus-4.7"
    )
    assert migrated_roles.roles["assistant"].model_groups[0].provider_models[0].route_id == new_route_id
    assert migrated_roles.model_profiles["profile"].fallback_chain[0].route_id == new_route_id
    assert migrated_roles.model_bundles["bundle"].fallback_chain[0].route_id == new_route_id
    assert migrated_roles.model_bundles["bundle"].model_groups[0].provider_models[0].route_id == new_route_id

    migrated_draft = load_evidence_library(path=drafts_path)
    assert old_route_id not in migrated_draft.route_candidates
    assert new_route_id in migrated_draft.route_candidates
    assert orphan_route_id not in migrated_draft.route_candidates
    assert orphan_new_route_id in migrated_draft.route_candidates
    assert migrated_draft.route_candidates[orphan_new_route_id].endpoint_id == orphan_new_endpoint_id
    assert migrated_draft.route_candidates[new_route_id].endpoint_id == new_endpoint_id
    assert migrated_draft.evidence_records[0].route_id == new_route_id
    assert migrated_draft.evidence_records[0].endpoint_id == new_endpoint_id
    assert migrated_draft.evidence_records[0].scope == {
        "endpoint_id": new_endpoint_id,
        "route_id": new_route_id,
    }

    migrated_results = load_role_test_results(path=results_path)
    assert old_route_id not in json.dumps(migrated_results)
    assert migrated_results["assistant"]["result"]["selected_route_id"] == new_route_id
    assert migrated_results["assistant"]["result"]["routes"][new_route_id]["endpoint_id"] == new_endpoint_id

    migrated_health = SqliteLlmHealthStore(health_path)
    assert migrated_health.get_active_circuits(
        route_id=old_route_id,
        endpoint_id=old_endpoint_id,
        rate_limit_bucket=old_endpoint_id,
        now=now,
    ) == []
    assert {
        (circuit.scope, circuit.scope_id)
        for circuit in migrated_health.get_active_circuits(
            route_id=new_route_id,
            endpoint_id=new_endpoint_id,
            rate_limit_bucket=new_endpoint_id,
            now=now,
        )
    } == {("route", new_route_id), ("endpoint", new_endpoint_id)}

    second_report = migrate_llm_stable_route_ids(
        credentials_path=credentials_path,
        roles_path=roles_path,
        import_drafts_path=drafts_path,
        role_test_results_path=results_path,
        health_db_path=health_path,
    )

    assert second_report.changed is False
