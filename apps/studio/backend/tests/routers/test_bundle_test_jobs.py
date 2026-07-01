"""#50b 束级 test 端点 — bundle test runs via a TRANSIENT materialized role
(materialize_model_bundle) without touching the persisted roles store, and keys
its result under __bundle__{id} so role results stay clean.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ModelBundle,
    ProviderEndpoint,
    ProviderRoute,
    RoleModelGroup,
    RoleProviderModel,
    RolesData,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import load_roles_file, roles_path, save_roles_file


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.backends import clear_backend_caches

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    # Pin the gateway adapter to in_process (get_backend_config is lru_cached and
    # another test may have left STUDIO_GATEWAY_TRANSPORT=http_loopback cached).
    monkeypatch.delenv("STUDIO_GATEWAY_TRANSPORT", raising=False)
    clear_backend_caches()
    credentials_path = settings_dir / "llm" / "llm_credentials.json"
    bundle_roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": ProviderEndpoint(
                    endpoint_id="openai-direct",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "openai-direct:gpt-5": ProviderRoute(
                    route_id="openai-direct:gpt-5",
                    endpoint_id="openai-direct",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                )
            },
        ),
        credentials_path,
    )
    save_roles_file(
        bundle_roles_path,
        RolesData(
            model_bundles={
                "primary": ModelBundle(
                    model_profile_id="primary",
                    display_name="Primary",
                    canonical_id="bundle:primary",
                    model_groups=[
                        RoleModelGroup(
                            canonical_id="gpt-5",
                            display_name="GPT-5",
                            provider_models=[
                                RoleProviderModel(route_id="openai-direct:gpt-5")
                            ],
                        )
                    ],
                )
            },
        ),
        known_route_ids={"openai-direct:gpt-5"},
    )


def test_unknown_bundle_test_job_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, monkeypatch)
    from app.routers.llm import start_bundle_test_job
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(start_bundle_test_job("ghost"))
    assert excinfo.value.status_code == 404


def test_bundle_test_job_targets_bundle_routes_without_touching_role_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, monkeypatch)
    from app.routers import llm as llm_router
    from app.routers.llm import start_bundle_test_job

    before = roles_path().read_text(encoding="utf-8")

    job = asyncio.run(start_bundle_test_job("primary"))

    # The job targets the bundle's materialized route and is keyed under the
    # __bundle__ namespace so it never pollutes the role-test results store.
    assert job.role_name == "__bundle__primary"
    assert job.status in {"queued", "running"}
    assert [progress.route_id for progress in job.provider_statuses] == [
        "openai-direct:gpt-5"
    ]
    # The persisted roles file is unchanged: the bundle was materialized as a
    # transient role, never written back as a real role.
    after = roles_path().read_text(encoding="utf-8")
    assert before == after
    reloaded = load_roles_file(roles_path())
    assert "__bundle__primary" not in reloaded.roles
    assert reloaded.roles == {}
    # The job is registered in the same in-memory job store role tests use.
    assert job.job_id in llm_router._role_test_jobs


def test_compare_candidate_test_job_targets_temporary_model_group_without_touching_role_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, monkeypatch)
    from app.routers import llm as llm_router
    from app.routers.llm import (
        CompareCandidateTestRequest,
        start_compare_candidate_test_job,
    )

    before = roles_path().read_text(encoding="utf-8")

    job = asyncio.run(
        start_compare_candidate_test_job(
            CompareCandidateTestRequest(
                canonical_id="gpt-5",
                route_id="openai-direct:gpt-5",
            )
        )
    )

    assert job.role_name.startswith("__compare__")
    assert job.status in {"queued", "running"}
    assert [progress.route_id for progress in job.provider_statuses] == [
        "openai-direct:gpt-5"
    ]
    after = roles_path().read_text(encoding="utf-8")
    assert before == after
    assert "__compare__" not in load_roles_file(roles_path()).roles
    assert job.job_id in llm_router._role_test_jobs
