"""多模态能力真探测端点(#11 slice B):真塞图 → provider 接受则把 input_modalities/
vision 记为 probed_verified 证据;不支持则 probe-failed。catalog(provider_doc)只是
"可能带多模态"的提示,这里给实测判据。

Harness: 复用 test_llm_endpoint_test_evidence 的套路 —— seed 凭证 + monkeypatch
router 上的探测 seam + TestClient 打真端点 + 断言证据落到 route。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.routers import llm as llm_router
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from app.services.model_probe import ModelProbeResult
from fastapi.testclient import TestClient


def _seed_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "tp": ProviderEndpoint(
                    endpoint_id="tp",
                    display_name="tp",
                    protocol="openai_compatible",
                    base_url="https://tp.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "tp:vmodel": ProviderRoute(
                    route_id="tp:vmodel",
                    endpoint_id="tp",
                    route_slug="vmodel",
                    provider_model_id="vmodel",
                    canonical_id="vmodel",
                )
            },
        ),
        credentials_path(),
    )


def _probe_evidence(creds: LLMCredentialsFile, route_id: str) -> list[object]:
    return [e for e in creds.provider_routes[route_id].evidence if e.evidence_type == "probe"]


def test_multimodal_probe_candidate_skips_text_only_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="tp", display_name="tp", protocol="openai_compatible", base_url="https://x/v1", api_key="k"
    )
    completions = llm_router._candidate(
        method_id="openai_completions",
        profile_id="c",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=1,
        fallback_rank=1,
    )
    monkeypatch.setattr(
        llm_router, "_official_language_probe_candidates", lambda ep, model: [completions, chat]
    )

    picked = llm_router._multimodal_probe_candidate(endpoint, "vmodel")

    assert picked is not None
    assert picked.method_id == "openai_chat_completions"


def test_multimodal_probe_candidate_none_when_only_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="tp", display_name="tp", protocol="openai_compatible", base_url="https://x/v1", api_key="k"
    )
    completions = llm_router._candidate(
        method_id="openai_completions",
        profile_id="c",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    monkeypatch.setattr(
        llm_router, "_official_language_probe_candidates", lambda ep, model: [completions]
    )

    assert llm_router._multimodal_probe_candidate(endpoint, "vmodel") is None


def test_probe_multimodal_endpoint_records_image_as_probed_verified(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_route(monkeypatch, tmp_path)
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: chat)

    captured: dict[str, object] = {}

    async def fake_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
        candidate: object,
        *,
        multimodal: bool = False,
    ) -> ModelProbeResult:
        captured["multimodal"] = multimodal
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=12, message=None)

    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")
    assert resp.status_code == 200
    # 端点确实发了多模态探测(带图),不是普通文本探测。
    assert captured["multimodal"] is True

    creds = load_credentials(credentials_path())
    records = _probe_evidence(creds, "tp:vmodel")
    assert records
    verified = [r for r in records if r.trust_state == "probe-verified"]
    assert verified
    assert "image" in verified[0].input_modalities


def test_probe_multimodal_endpoint_publishes_active_model_atom(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_route(monkeypatch, tmp_path)
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    active_events: list[tuple[str, tuple[str, ...]]] = []

    async def fake_publish(endpoint_id: str, active_model_ids: tuple[str, ...]) -> None:
        active_events.append((endpoint_id, active_model_ids))

    async def fake_call_method(
        method_id: str,
        api_key: str,
        base_url: str,
        model_id: str,
        *,
        runtime_settings: dict[str, object] | None = None,
        multimodal: bool = False,
    ) -> ModelProbeResult:
        assert method_id == "openai_chat_completions"
        assert api_key == "secret"
        assert base_url == "https://tp.example/v1"
        assert model_id == "vmodel"
        assert runtime_settings == {"max_output_tokens": 16}
        assert multimodal is True
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=12, message=None)

    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: chat)
    monkeypatch.setattr(llm_router, "_publish_llm_probe_active", fake_publish)
    monkeypatch.setattr(llm_router, "_gateway_probe_official_call_method", fake_call_method)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")

    assert resp.status_code == 200
    assert active_events == [("tp", ("vmodel",)), ("tp", ())]


def test_probe_multimodal_endpoint_records_failure_when_the_model_id_is_wrong(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_route(monkeypatch, tmp_path)
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: chat)

    async def fake_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
        candidate: object,
        *,
        multimodal: bool = False,
    ) -> ModelProbeResult:
        # 模型 id 根本不存在 → invalid_model:那是一次没问出答案的探测。
        return ModelProbeResult(model_id=model_id, status="invalid_model", message="no image input")

    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    records = _probe_evidence(creds, "tp:vmodel")
    assert records
    assert any(r.trust_state == "probe-failed" for r in records)


def test_probe_multimodal_endpoint_422_when_no_multimodal_capable_method(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_route(monkeypatch, tmp_path)
    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: None)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")
    assert resp.status_code == 422


def test_probe_multimodal_endpoint_404_unknown_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_route(monkeypatch, tmp_path)
    resp = client.post("/api/llm/routes/tp:ghost/probe-multimodal")
    assert resp.status_code == 404


def test_a_model_that_answers_text_only_lands_on_the_capability_not_on_a_failure(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live 2026-08-11: Ark answered "Model only support text input" and Studio
    filed it as a failed probe of an invalid model. It is neither — the model is
    there, and it just told us what it takes."""
    _seed_route(monkeypatch, tmp_path)
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: chat)

    async def fake_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
        candidate: object,
        *,
        multimodal: bool = False,
    ) -> ModelProbeResult:
        return ModelProbeResult(
            model_id=model_id,
            status="capability_unsupported",
            message="Model only support text input",
        )

    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")
    assert resp.status_code == 200

    creds = load_credentials(credentials_path())
    route = creds.provider_routes["tp:vmodel"]
    vision = route.capabilities["vision"]
    assert vision.value is False
    assert vision.source == "probed_verified"
    # One refused image bounds images from above and settles nothing about the
    # rest of the list, so the list it could not settle is left alone.
    assert "input_modalities" not in route.capabilities

    records = _probe_evidence(creds, "tp:vmodel")
    assert records
    assert [r.trust_state for r in records] == ["probe-verified"]
    assert records[0].probe_status == "capability_unsupported"
    # And the sentence must agree with the field next to it: a record that
    # says probe-verified and "probe failed" in one breath is unreadable.
    reason = records[0].reason or ""
    assert "failed" not in reason.lower(), reason
    assert "capability_unsupported" in reason


def test_an_accepted_image_reaches_the_capability_the_button_reads(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`routeAcceptsImageVerified` wants capabilities.input_modalities at
    probed_verified with image in it; evidence alone never reaches it."""
    _seed_route(monkeypatch, tmp_path)
    chat = llm_router._candidate(
        method_id="openai_chat_completions",
        profile_id="chat",
        capability="language_reasoning",
        request_mapper_id="m",
        default_rank=0,
        fallback_rank=0,
    )
    monkeypatch.setattr(llm_router, "_multimodal_probe_candidate", lambda ep, model: chat)

    async def fake_probe(
        endpoint: ProviderEndpoint,
        model_id: str,
        candidate: object,
        *,
        multimodal: bool = False,
    ) -> ModelProbeResult:
        return ModelProbeResult(model_id=model_id, status="ok", latency_ms=9, message=None)

    monkeypatch.setattr(llm_router, "_probe_official_call_method", fake_probe)

    resp = client.post("/api/llm/routes/tp:vmodel/probe-multimodal")
    assert resp.status_code == 200

    route = load_credentials(credentials_path()).provider_routes["tp:vmodel"]
    vision = route.capabilities["vision"]
    assert vision.value is True
    assert vision.source == "probed_verified"
    modalities = route.capabilities["input_modalities"]
    assert modalities.source == "probed_verified"
    assert "image" in modalities.value


def test_a_route_known_only_by_its_input_modalities_is_still_language_capable() -> None:
    """Absent output modalities mean nobody asked, not "it emits no text".

    The image measurement writes input modalities and nothing else, so reading a
    missing output list as a negative would drop a working text route out of
    every language-capable list the moment it was measured.
    """
    from app.models.llm_config import CapabilityValue

    route = ProviderRoute(
        route_id="tp:vmodel",
        endpoint_id="tp",
        route_slug="vmodel",
        provider_model_id="vmodel",
        canonical_id="vmodel",
        capabilities={
            "input_modalities": CapabilityValue(value=["text"], source="probed_verified"),
        },
    )

    assert llm_router._route_is_language_capable(route, allow_unknown=False) is True


def test_the_registry_projection_of_an_official_route_keeps_the_measurement() -> None:
    """The read seam must hand a measured refusal back as measured.

    Live 2026-08-12 on the Ark Official route of the DeepSeek V4 Flash group:
    the probe wrote the refusal, the file on disk said `probed_verified`, and
    `GET /api/llm/registry` has to say so too — the projection enriches official
    routes from provider documents, and a document that claims image support
    must not be able to reappear over an answer the model gave.
    """
    from app.models.llm_config import CapabilityValue

    endpoint = ProviderEndpoint(
        endpoint_id="ark-official",
        display_name="Ark Official",
        protocol="openai_compatible",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key="k",
        provider_kind="official",
    )
    route = ProviderRoute(
        route_id="ark-official:vmodel",
        endpoint_id="ark-official",
        route_slug="vmodel",
        provider_model_id="vmodel",
        canonical_id="vmodel",
        capabilities={"vision": CapabilityValue(value=False, source="probed_verified")},
    )

    projected = llm_router._normalize_route_for_registry_response(route, endpoint)

    assert projected.capabilities["vision"].value is False
    assert projected.capabilities["vision"].source == "probed_verified"
