"""A listed route says which transport it is, not just whose it is.

Two endpoints can carry the same provider's display name — that is the normal
shape of an aggregator that serves several base URLs, or one base URL under two
protocols. `provider_label` is then the same word for both, and every surface
that shows a route by its provider label shows the reader two identical rows.

Measured 2026-08-21 on the developer's real credentials, in the node
`Add compare LLM` dialog: one model, `deepseek-v4-flash`, offered **17**
endpoint options, of which `Qiniu` appeared 7 times, `Ark Official` twice,
`Jiekou` twice and `OpenRouter` twice. What actually told them apart —
the base URL and the protocol — was not in the projection at all, so no surface
could have shown it.

`00_settings-ux-spec.md` §2.1「provider chip 聚合 = 真聚合，不是丢弃」names the
transport as the thing a reader has to be given: 「tooltip 列出每条 transport
（URL × 协议 × 各自 6 态）」. This test pins the bottom half of that: the projection
carries the URL and the protocol, so the surfaces above it have something to say.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.llm_credentials import credentials_path, save_credentials
from fastapi.testclient import TestClient

_OPENAI_ROUTE = "qiniu-openai:deepseek-v4-flash"
_ANTHROPIC_ROUTE = "qiniu-anthropic:deepseek-v4-flash"


def _write_credentials() -> None:
    """One provider name, two transports — the shape that makes a label ambiguous."""
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "qiniu-openai": ProviderEndpoint(
                    endpoint_id="qiniu-openai",
                    display_name="Qiniu",
                    protocol="openai_compatible",
                    base_url="https://api.qnaigc.example/v1",
                    api_key="secret",
                    provider_kind="third_party",
                ),
                "qiniu-anthropic": ProviderEndpoint(
                    endpoint_id="qiniu-anthropic",
                    display_name="Qiniu",
                    protocol="anthropic_compatible",
                    base_url="https://anthropic.qnaigc.example",
                    api_key="secret",
                    provider_kind="third_party",
                ),
            },
            provider_routes={
                _OPENAI_ROUTE: ProviderRoute(
                    route_id=_OPENAI_ROUTE,
                    endpoint_id="qiniu-openai",
                    route_slug="deepseek-v4-flash",
                    provider_model_id="deepseek-v4-flash",
                    canonical_id="deepseek-v4-flash",
                    display_name="DeepSeek V4 Flash",
                    status="verified",
                ),
                _ANTHROPIC_ROUTE: ProviderRoute(
                    route_id=_ANTHROPIC_ROUTE,
                    endpoint_id="qiniu-anthropic",
                    route_slug="deepseek-v4-flash",
                    provider_model_id="deepseek-v4-flash",
                    canonical_id="deepseek-v4-flash",
                    display_name="DeepSeek V4 Flash",
                    status="verified",
                ),
            },
        ),
        credentials_path(),
    )


@pytest.fixture()
def settings_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", directory)
    return directory


def _options_by_route(client: TestClient) -> dict[str, dict]:
    body = client.get("/api/llm/registry").json()
    return {
        option["route_id"]: option
        for group in body["model_groups"]
        for option in group["provider_models"]
    }


def test_each_listed_route_carries_its_base_url_and_protocol(
    settings_dir: Path,
    client: TestClient,
) -> None:
    _write_credentials()

    options = _options_by_route(client)

    assert set(options) == {_OPENAI_ROUTE, _ANTHROPIC_ROUTE}
    assert options[_OPENAI_ROUTE]["base_url"] == "https://api.qnaigc.example/v1"
    assert options[_OPENAI_ROUTE]["protocol"] == "openai_compatible"
    assert options[_ANTHROPIC_ROUTE]["base_url"] == "https://anthropic.qnaigc.example"
    assert options[_ANTHROPIC_ROUTE]["protocol"] == "anthropic_compatible"


def test_two_routes_sharing_a_provider_label_differ_in_what_is_projected(
    settings_dir: Path,
    client: TestClient,
) -> None:
    """The point of the two fields: they are what a reader can tell apart by.

    Both options say `Qiniu`. If the projection stopped there, a surface listing
    them would print the same row twice and picking one would be a coin toss.
    """
    _write_credentials()

    options = _options_by_route(client)
    labels = {option["provider_label"] for option in options.values()}
    transports = {(option["base_url"], option["protocol"]) for option in options.values()}

    assert labels == {"Qiniu"}, "the fixture's whole point is that the label is ambiguous"
    assert len(transports) == 2, "the transports are what disambiguates them"
