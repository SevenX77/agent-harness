"""Media generation domain: schema, catalog integrity, settings validation, probe."""

from __future__ import annotations

import httpx
import pytest
from graph_agent_gateway.media import (
    MediaModelSettings,
    MediaProviderCredential,
    probe_runninghub_account,
    runninghub_catalog,
    validate_model_settings,
)
from graph_agent_gateway.media.schema import EnumParamSpec, MediaModelSpec
from pydantic import SecretStr, ValidationError


def test_catalog_has_ten_unique_models_with_endpoints() -> None:
    catalog = runninghub_catalog()
    assert len(catalog) == 10
    ids = [spec.id for spec in catalog]
    assert len(set(ids)) == len(ids)
    for spec in catalog:
        assert spec.endpoint
        assert spec.provider == "runninghub"
        assert "/" not in spec.id


def test_catalog_modality_matches_task() -> None:
    image_tasks = {"t2i", "i2i"}
    for spec in runninghub_catalog():
        if spec.task in image_tasks:
            assert spec.modality == "image", spec.id
        else:
            assert spec.modality == "video", spec.id


def test_catalog_enum_defaults_are_members_of_their_values() -> None:
    for spec in runninghub_catalog():
        for name, param in spec.params.items():
            if isinstance(param, EnumParamSpec) and param.default is not None:
                assert param.default in param.values, f"{spec.id}.{name}"


def test_validate_model_settings_accepts_legal_enum_default() -> None:
    settings = MediaModelSettings(defaults={"resolution": "1k"})
    validate_model_settings("rh-image-v2-t2i", settings)


def test_validate_model_settings_rejects_illegal_enum_value() -> None:
    settings = MediaModelSettings(defaults={"resolution": "8k"})
    with pytest.raises(ValueError, match="resolution"):
        validate_model_settings("rh-image-v2-t2i", settings)


def test_validate_model_settings_rejects_out_of_range_int() -> None:
    settings = MediaModelSettings(defaults={"duration": 31})
    with pytest.raises(ValueError, match="duration"):
        validate_model_settings("rh-video-x-i2v", settings)


def test_validate_model_settings_accepts_in_range_int() -> None:
    settings = MediaModelSettings(defaults={"duration": 8})
    validate_model_settings("rh-video-x-i2v", settings)


def test_validate_model_settings_rejects_unknown_param() -> None:
    settings = MediaModelSettings(defaults={"nonexistent": "x"})
    with pytest.raises(ValueError, match="nonexistent"):
        validate_model_settings("rh-image-v2-t2i", settings)


def test_validate_model_settings_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="no-such-model"):
        validate_model_settings("no-such-model", MediaModelSettings())


def test_validate_model_settings_rejects_defaults_for_non_defaultable_param() -> None:
    settings = MediaModelSettings(defaults={"imageUrls": "x"})
    with pytest.raises(ValueError, match="imageUrls"):
        validate_model_settings("rh-image-v2-i2i", settings)


def test_model_spec_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MediaModelSpec.model_validate(
            {
                "id": "x",
                "provider": "runninghub",
                "display_name": "x",
                "modality": "image",
                "task": "t2i",
                "channel": "economy",
                "endpoint_kind": "standard",
                "endpoint": "x/y",
                "params": {},
                "surprise": True,
            }
        )


def _credential() -> MediaProviderCredential:
    return MediaProviderCredential(
        api_key=SecretStr("k" * 32),
        base_url="https://www.runninghub.cn",
    )


@pytest.mark.anyio
async def test_probe_ok_extracts_balance_and_latency() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {
                    "remainCoins": "99999",
                    "currentTaskCounts": "0",
                    "remainMoney": "999",
                },
            },
        )

    result = await probe_runninghub_account(
        _credential(), transport=httpx.MockTransport(handler)
    )
    assert result.status == "ok"
    assert result.remain_coins == "99999"
    assert result.remain_money == "999"
    assert result.latency_ms is not None and result.latency_ms >= 0
    assert captured["url"] == "https://www.runninghub.cn/uc/openapi/accountStatus"
    assert '"apikey"' in str(captured["body"])


@pytest.mark.anyio
async def test_probe_nonzero_code_is_auth_failed_with_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 433, "msg": "APIKEY_INVALID"})

    result = await probe_runninghub_account(
        _credential(), transport=httpx.MockTransport(handler)
    )
    assert result.status == "auth_failed"
    assert result.message is not None and "APIKEY_INVALID" in result.message
    assert result.remain_coins is None


@pytest.mark.anyio
async def test_probe_transport_error_is_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = await probe_runninghub_account(
        _credential(), transport=httpx.MockTransport(handler)
    )
    assert result.status == "network_error"
    assert result.message is not None


@pytest.mark.anyio
async def test_probe_non_json_body_is_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    result = await probe_runninghub_account(
        _credential(), transport=httpx.MockTransport(handler)
    )
    assert result.status == "network_error"
