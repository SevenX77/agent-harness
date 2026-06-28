"""GitHub-backed Studio LLM catalog repository management."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.adapters.gateway import EVIDENCE_LIBRARY_DRAFT_ID, new_evidence_library

GITHUB_API_VERSION = "2022-11-28"
DEFAULT_CATALOG_REPO = "studio-llm-model-catalog"
DEFAULT_CATALOG_BRANCH = "main"
DEFAULT_CATALOG_PATH = "llm_probe_catalog.json"


class GitHubCatalogApiError(RuntimeError):
    """Raised when GitHub refuses a catalog management request."""

    def __init__(self, *, status_code: int, body: str) -> None:
        super().__init__(f"GitHub catalog API failed with status {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class GitHubCatalogEnsureResult(BaseModel):
    """Result of ensuring the remote model catalog repository exists."""

    model_config = ConfigDict(extra="forbid")

    owner: str
    repo: str
    html_url: str
    raw_url: str
    catalog_path: str
    branch: str
    repository_created: bool
    catalog_created: bool


@dataclass
class GitHubCatalogClient:
    """Create and seed the GitHub repository used as Studio's catalog source."""

    token: str
    owner: str = ""
    repo: str = DEFAULT_CATALOG_REPO
    branch: str = DEFAULT_CATALOG_BRANCH
    catalog_path: str = DEFAULT_CATALOG_PATH
    http_client: httpx.Client | None = None

    def ensure_repository(self) -> GitHubCatalogEnsureResult:
        """Ensure the configured GitHub repository and catalog file exist."""
        if not self.token.strip():
            raise ValueError("GitHub token is not configured")

        owner = self.owner.strip() or self._current_user()
        repo = self.repo.strip() or DEFAULT_CATALOG_REPO
        branch = self.branch.strip() or DEFAULT_CATALOG_BRANCH
        catalog_path = self.catalog_path.strip() or DEFAULT_CATALOG_PATH

        repository = self._get_repo(owner, repo)
        repository_created = repository is None
        if repository is None:
            repository = self._create_repo(repo)

        catalog_created = not self._catalog_file_exists(owner, repo, catalog_path, branch)
        if catalog_created:
            self._create_catalog_file(owner, repo, catalog_path, branch)

        html_url = str(repository.get("html_url") or f"https://github.com/{owner}/{repo}")
        return GitHubCatalogEnsureResult(
            owner=owner,
            repo=repo,
            html_url=html_url,
            raw_url=f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{catalog_path}",
            catalog_path=catalog_path,
            branch=branch,
            repository_created=repository_created,
            catalog_created=catalog_created,
        )

    @property
    def _client(self) -> httpx.Client:
        if self.http_client is not None:
            return self.http_client
        self.http_client = httpx.Client(timeout=10.0)
        return self.http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    def _current_user(self) -> str:
        response = self._request("GET", "/user")
        login = response.get("login")
        if not isinstance(login, str) or not login.strip():
            raise GitHubCatalogApiError(status_code=502, body="GitHub /user response did not include login")
        return login

    def _get_repo(self, owner: str, repo: str) -> dict[str, Any] | None:
        response = self._client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=self._headers(),
        )
        if response.status_code == 404:
            return None
        return self._json_or_raise(response)

    def _create_repo(self, repo: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/user/repos",
            json={"name": repo, "private": False, "auto_init": False},
        )

    def _catalog_file_exists(
        self,
        owner: str,
        repo: str,
        catalog_path: str,
        branch: str,
    ) -> bool:
        response = self._client.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{catalog_path}",
            headers=self._headers(),
            params={"ref": branch},
        )
        if response.status_code == 404:
            return False
        self._json_or_raise(response)
        return True

    def _create_catalog_file(
        self,
        owner: str,
        repo: str,
        catalog_path: str,
        branch: str,
    ) -> None:
        payload = self._catalog_seed(owner, repo)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        encoded = base64.b64encode(f"{serialized}\n".encode()).decode("ascii")
        self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{catalog_path}",
            json={
                "message": "chore: initialize Studio LLM catalog",
                "content": encoded,
                "branch": branch,
            },
        )

    def _catalog_seed(self, owner: str, repo: str) -> dict[str, Any]:
        draft = new_evidence_library(EVIDENCE_LIBRARY_DRAFT_ID).model_copy(
            update={
                "source": {
                    "kind": "studio_remote_model_catalog",
                    "location": "github",
                    "repo": f"{owner}/{repo}",
                }
            }
        )
        return {"drafts": {EVIDENCE_LIBRARY_DRAFT_ID: draft.model_dump(mode="json")}}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(
            method,
            f"https://api.github.com{path}",
            headers=self._headers(),
            **kwargs,
        )
        return self._json_or_raise(response)

    def _json_or_raise(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise GitHubCatalogApiError(status_code=response.status_code, body=response.text)
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubCatalogApiError(status_code=response.status_code, body="GitHub response was not an object")
        return data
