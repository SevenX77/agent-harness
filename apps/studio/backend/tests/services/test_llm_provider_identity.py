"""W3-B: provider canonical name = registrable domain (eTLD+1), not the full host."""

from __future__ import annotations

import pytest
from app.services.llm_provider_identity import registrable_provider_name


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.qnaigc.com/v1", "qnaigc"),
        ("https://anthropic.qnaigc.com", "qnaigc"),
        # Both WaveSpeed hosts collapse to ONE provider (registrable domain, not host).
        ("https://llm.wavespeed.ai/v1", "wavespeed"),
        ("https://api.wavespeed.ai/api/v3", "wavespeed"),
        ("https://api.openai.com/v1", "openai"),
        ("https://api.deepseek.com/v1", "deepseek"),
        ("https://ark.cn-beijing.volces.com/api/v3", "volces"),
        ("https://api.together.xyz/v1", "together"),
        # Multi-level ccTLD SLDs.
        ("https://api.foo.com.cn/v1", "foo"),
        ("https://bar.co.uk", "bar"),
        # Not classifiable → None.
        ("https://10.1.2.3/v1", None),
        ("http://localhost:8080", None),
        ("https://intranet/v1", None),
        ("", None),
        ("not a url", None),
    ],
)
def test_registrable_provider_name(base_url: str, expected: str | None) -> None:
    assert registrable_provider_name(base_url) == expected


def test_model_probe_evidence_is_attributed_to_registrable_provider() -> None:
    # W3-B / R-B7: probe evidence carries the provider's registrable-domain name so
    # the community catalog can attribute it to a provider (api.qnaigc.com -> qnaigc).
    from app.models.llm_config import ProviderEndpoint
    from app.routers.llm import _build_model_probe_evidence
    from app.services.copilot_test import ModelProbeResult

    endpoint = ProviderEndpoint(
        endpoint_id="ep-qnaigc",
        display_name="Qiniu",
        protocol="openai_compatible",
        base_url="https://api.qnaigc.com/v1",
        api_key="secret",
    )
    evidence = _build_model_probe_evidence(
        endpoint,
        ModelProbeResult(model_id="deepseek-v3", status="invalid_model", message="x"),
        route_id="ep-qnaigc:deepseek-v3",
    )
    assert evidence.provider_id == "qnaigc"
    assert evidence.endpoint_id == "ep-qnaigc"
