"""Connectivity checks and model discovery for Copilot providers."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.models.copilot import ModelInfo, ProviderKind

DEFAULT_BASE_URLS: dict[ProviderKind, str] = {
    "anthropic": "https://api.anthropic.com",
    "openai-compat": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
}


class BaseClient(Protocol):
    async def ping(self) -> None: ...

    async def get_models(self) -> list[ModelInfo]: ...


class _Unauthorized(Exception):
    pass


class _RateLimited(Exception):
    pass


class _QuotaExceeded(Exception):
    pass


class _NetworkError(Exception):
    pass


class _HTTPModelsClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = self._normalize_base_url(base_url)
        self._models_response: httpx.Response | None = None

    async def ping(self) -> None:
        self._models_response = await self._request_models()

    async def get_models(self) -> list[ModelInfo]:
        response = self._models_response or await self._request_models()
        return _parse_models(response)

    async def _request_models(self) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await self._get(client)
        except httpx.TimeoutException as exc:
            raise TimeoutError from exc
        except httpx.HTTPError as exc:
            raise _NetworkError(str(exc)) from exc

        _raise_for_status(response)
        return response

    async def _get(self, client: httpx.AsyncClient) -> httpx.Response:
        raise NotImplementedError

    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.rstrip("/")


class AnthropicClient(_HTTPModelsClient):
    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.rstrip("/") or DEFAULT_BASE_URLS["anthropic"]

    async def _get(self, client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(
            f"{self.base_url}/v1/models",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )


class OpenAICompatClient(_HTTPModelsClient):
    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.rstrip("/") or DEFAULT_BASE_URLS["openai-compat"]

    async def _get(self, client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )


class GoogleClient(_HTTPModelsClient):
    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.rstrip("/") or DEFAULT_BASE_URLS["google"]

    async def _get(self, client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(f"{self.base_url}/models", params={"key": self.api_key})


def make_client(kind: ProviderKind, api_key: str, base_url: str) -> BaseClient:
    if kind == "anthropic":
        return AnthropicClient(api_key, base_url)
    if kind == "openai-compat":
        return OpenAICompatClient(api_key, base_url)
    return GoogleClient(api_key, base_url)


def supports_thinking(model_id: str) -> bool:
    normalized = model_id.lower()
    prefixes = (
        "claude-opus-4-",
        "claude-sonnet-4-",
        "claude-3-7-",
        "claude-3-opus-",
        "o1-",
        "o3-",
        "o4-",
        "gpt-5-thinking",
        "gemini-2.5-thinking-",
        "gemini-3.",
        "deepseek-r1",
        "deepseek-reasoner",
    )
    return any(normalized.startswith(prefix) for prefix in prefixes) and (
        not normalized.startswith("gemini-3.") or "thinking" in normalized
    )


def supports_vision(model_id: str) -> bool:
    normalized = model_id.lower()
    return normalized.startswith(("claude-", "gpt-4o", "gpt-5", "gemini-"))


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise _Unauthorized
    if response.status_code == 429:
        raise _RateLimited
    if response.status_code in (402, 403):
        raise _QuotaExceeded
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _NetworkError(f"Provider returned HTTP {response.status_code}") from exc


def _parse_models(response: httpx.Response) -> list[ModelInfo]:
    try:
        payload = response.json()
    except ValueError:
        return []

    items = payload.get("data")
    if items is None:
        items = payload.get("models")
    if not isinstance(items, list):
        return []

    models: list[ModelInfo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if not isinstance(model_id, str) or not model_id:
            continue
        normalized_id = model_id.removeprefix("models/")
        models.append(
            ModelInfo(
                id=normalized_id,
                supports_thinking=supports_thinking(normalized_id),
                supports_vision=supports_vision(normalized_id),
            )
        )
    return models


__all__ = [
    "AnthropicClient",
    "BaseClient",
    "DEFAULT_BASE_URLS",
    "GoogleClient",
    "ModelInfo",
    "OpenAICompatClient",
    "_NetworkError",
    "_QuotaExceeded",
    "_RateLimited",
    "_Unauthorized",
    "make_client",
    "supports_thinking",
    "supports_vision",
]
