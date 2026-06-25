from __future__ import annotations

import base64
import json

import httpx
import pytest
from app.models.llm_config import ProviderImportDraft
from app.services.github_catalog import GitHubCatalogClient


def test_github_catalog_ensure_creates_repo_and_seed_file() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer ghp-test"
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
        if request.method == "GET" and request.url.path == "/user":
            return httpx.Response(200, json={"login": "sevenx"})
        if request.method == "GET" and request.url.path == "/repos/sevenx/studio-llm-model-catalog":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path == "/user/repos":
            assert json.loads(request.content) == {
                "name": "studio-llm-model-catalog",
                "private": False,
                "auto_init": False,
            }
            return httpx.Response(
                201,
                json={
                    "name": "studio-llm-model-catalog",
                    "full_name": "sevenx/studio-llm-model-catalog",
                    "html_url": "https://github.com/sevenx/studio-llm-model-catalog",
                    "default_branch": "main",
                },
            )
        if (
            request.method == "GET"
            and request.url.path == "/repos/sevenx/studio-llm-model-catalog/contents/llm_probe_catalog.json"
        ):
            assert request.url.params["ref"] == "main"
            return httpx.Response(404, json={"message": "Not Found"})
        if (
            request.method == "PUT"
            and request.url.path == "/repos/sevenx/studio-llm-model-catalog/contents/llm_probe_catalog.json"
        ):
            body = json.loads(request.content)
            assert body["branch"] == "main"
            assert body["message"] == "chore: initialize Studio LLM catalog"
            decoded = base64.b64decode(body["content"]).decode("utf-8")
            payload = json.loads(decoded)
            draft = ProviderImportDraft.model_validate(payload["drafts"]["studio-evidence-library"])
            assert draft.draft_id == "studio-evidence-library"
            assert draft.source["repo"] == "sevenx/studio-llm-model-catalog"
            return httpx.Response(201, json={"content": {"sha": "seed-sha"}})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = GitHubCatalogClient(
        token="ghp-test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).ensure_repository()

    assert result.owner == "sevenx"
    assert result.repo == "studio-llm-model-catalog"
    assert result.repository_created is True
    assert result.catalog_created is True
    assert result.raw_url == (
        "https://raw.githubusercontent.com/sevenx/studio-llm-model-catalog/main/llm_probe_catalog.json"
    )
    assert [request.method for request in requests] == ["GET", "GET", "POST", "GET", "PUT"]


def test_github_catalog_ensure_reuses_existing_repo_and_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/repos/alice/models":
            return httpx.Response(
                200,
                json={
                    "name": "models",
                    "full_name": "alice/models",
                    "html_url": "https://github.com/alice/models",
                    "default_branch": "main",
                },
            )
        if request.method == "GET" and request.url.path == "/repos/alice/models/contents/catalog.json":
            return httpx.Response(200, json={"sha": "existing-sha"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    result = GitHubCatalogClient(
        token="ghp-test",
        owner="alice",
        repo="models",
        catalog_path="catalog.json",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).ensure_repository()

    assert result.repository_created is False
    assert result.catalog_created is False
    assert result.raw_url == "https://raw.githubusercontent.com/alice/models/main/catalog.json"


def test_github_catalog_requires_token() -> None:
    with pytest.raises(ValueError, match="GitHub token is not configured"):
        GitHubCatalogClient(token="").ensure_repository()
