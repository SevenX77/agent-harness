"""Phase 2 no-gate upload client.

The SIMPLE write-path: instead of POSTing to a Cloudflare gate, the desktop
pushes sanitized EvidenceUpload batches straight into the public catalog repo's
`incoming/` staging area using the user's own GitHub token. A scheduled Action
re-screens + publishes them.

- Dormant by default: needs an explicit enable flag + a GitHub token + a repo.
- The pushed object carries only sanitized record fields (never a secret).
- Idempotent: the object name is content-derived, so re-pushing the same batch
  is a no-op (skip when the file already exists).
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from app.core.adapters.gateway import EvidenceRecord, ProviderImportDraft
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint
from app.services.community_catalog import build_upload_record
from app.services.community_catalog_nogate import (
    AutosharePlan,
    NoGateUploadClient,
    PushResult,
    autoshare_probe_evidence,
    build_incoming_object,
    incoming_object_path,
    nogate_upload_configured,
    plan_autoshare,
)

from tests.helpers_community_catalog import probe_record  # type: ignore[import-not-found]


def _credentials_with_openai() -> LLMCredentialsFile:
    endpoint = ProviderEndpoint.model_validate(
        {
            "endpoint_id": "openai-main",
            "protocol": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "display_name": "OpenAI",
        }
    )
    return LLMCredentialsFile(provider_endpoints={"openai-main": endpoint})


def _library_with(records: list[EvidenceRecord]) -> ProviderImportDraft:
    return ProviderImportDraft.model_validate(
        {
            "draft_id": "evidence-library",
            "source": {"kind": "studio_evidence_library"},
            "status": "pending",
            "evidence_records": [r.model_dump(mode="json") for r in records],
        }
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _upload() -> object:
    return build_upload_record(probe_record(), base_url="https://api.openai.com/v1")


def _transport(captured: list[httpx.Request], *, exists: bool = False) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "GET":
            if exists:
                return httpx.Response(200, json={"sha": "existing-sha"})
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(201, json={"content": {"path": "incoming/x.json"}, "commit": {"sha": "new"}})

    return httpx.MockTransport(handle)


def _client(transport: httpx.MockTransport, *, token: str = "ghp-test") -> NoGateUploadClient:
    return NoGateUploadClient(
        github_token=token,
        owner="testowner",
        repo="testrepo",
        branch="main",
        transport=transport,
    )


def test_nogate_upload_dormant_by_default() -> None:
    assert nogate_upload_configured(github_token="", catalog_repo="", enabled=False) is False


def test_nogate_upload_requires_enabled_token_and_repo() -> None:
    assert nogate_upload_configured(github_token="ghp", catalog_repo="r", enabled=False) is False
    assert nogate_upload_configured(github_token="", catalog_repo="r", enabled=True) is False
    assert nogate_upload_configured(github_token="ghp", catalog_repo="", enabled=True) is False
    assert nogate_upload_configured(github_token="ghp", catalog_repo="r", enabled=True) is True


def test_incoming_object_path_is_content_addressed_json() -> None:
    assert incoming_object_path("abc123") == "incoming/abc123.json"


def test_build_incoming_object_carries_only_sanitized_record_fields() -> None:
    body = json.loads(build_incoming_object([_upload()]).decode("utf-8"))
    assert list(body.keys()) == ["records"]
    assert len(body["records"]) == 1
    record = body["records"][0]
    assert record["evidence_type"] == "probe_result"
    assert record["trust_state"] == "probe-verified"
    # No secret / repo-write / free-form field may ride along.
    for forbidden in ("api_key", "credential_ref", "metadata", "token"):
        assert forbidden not in record


@pytest.mark.anyio
async def test_push_batch_creates_incoming_file_when_absent() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured))
    result = await client.push_batch([_upload()], idempotency_key="batch-key")

    assert result.path == "incoming/batch-key.json"
    assert result.created is True
    # GET (existence probe) then PUT (create).
    assert [r.method for r in captured] == ["GET", "PUT"]
    put = captured[1]
    assert str(put.url) == (
        "https://api.github.com/repos/testowner/testrepo/contents/incoming/batch-key.json"
    )
    assert put.headers["Authorization"] == "Bearer ghp-test"
    sent = json.loads(put.content.decode("utf-8"))
    assert sent["branch"] == "main"
    decoded = json.loads(base64.b64decode(sent["content"]).decode("utf-8"))
    assert decoded["records"][0]["evidence_type"] == "probe_result"


@pytest.mark.anyio
async def test_push_batch_is_idempotent_when_file_already_exists() -> None:
    captured: list[httpx.Request] = []
    client = _client(_transport(captured, exists=True))
    result = await client.push_batch([_upload()], idempotency_key="batch-key")

    assert result.created is False
    # Only the existence probe; no PUT when the same batch is already staged.
    assert [r.method for r in captured] == ["GET"]


def test_client_refuses_empty_token_owner_or_repo() -> None:
    with pytest.raises(ValueError):
        NoGateUploadClient(github_token="", owner="o", repo="r")
    with pytest.raises(ValueError):
        NoGateUploadClient(github_token="ghp", owner="", repo="r")
    with pytest.raises(ValueError):
        NoGateUploadClient(github_token="ghp", owner="o", repo="")


def test_plan_autoshare_returns_none_when_dormant() -> None:
    library = _library_with([probe_record(endpoint_id="openai-main")])
    plan = plan_autoshare(
        library,
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        enabled=False,
    )
    assert plan is None


def test_plan_autoshare_returns_none_when_no_uploadable_evidence() -> None:
    plan = plan_autoshare(
        _library_with([]),
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        enabled=True,
    )
    assert plan is None


def test_plan_autoshare_builds_plan_from_uploadable_evidence() -> None:
    library = _library_with(
        [probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")]
    )
    plan = plan_autoshare(
        library,
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        enabled=True,
    )
    assert isinstance(plan, AutosharePlan)
    assert len(plan.uploads) == 1
    assert plan.uploads[0].provider_model_id == "gpt-4o"
    assert plan.idempotency_key  # stable, content-derived


@pytest.mark.anyio
async def test_autoshare_pushes_when_configured_with_owner() -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        async def push_batch(self, uploads: list, *, idempotency_key: str) -> PushResult:
            captured["uploads"] = uploads
            return PushResult(path=incoming_object_path(idempotency_key), created=True)

    library = _library_with(
        [probe_record(endpoint_id="openai-main", provider_id="openai", provider_model_id="gpt-4o")]
    )
    result = await autoshare_probe_evidence(
        library,
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        catalog_owner="SevenX77",
        branch="main",
        enabled=True,
        client_factory=FakeClient,
    )
    assert isinstance(result, PushResult)
    assert result.created is True
    init = captured["init"]
    assert isinstance(init, dict)
    assert init["owner"] == "SevenX77"
    assert init["repo"] == "studio-llm-model-catalog"
    assert len(captured["uploads"]) == 1  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_autoshare_skips_when_dormant() -> None:
    called = False

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def push_batch(self, *args: object, **kwargs: object) -> PushResult:
            nonlocal called
            called = True
            return PushResult(path="x", created=True)

    result = await autoshare_probe_evidence(
        _library_with([probe_record(endpoint_id="openai-main")]),
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        catalog_owner="SevenX77",
        branch="main",
        enabled=False,
        client_factory=FakeClient,
    )
    assert result is None
    assert called is False


@pytest.mark.anyio
async def test_autoshare_skips_when_owner_missing() -> None:
    called = False

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def push_batch(self, *args: object, **kwargs: object) -> PushResult:
            nonlocal called
            called = True
            return PushResult(path="x", created=True)

    result = await autoshare_probe_evidence(
        _library_with([probe_record(endpoint_id="openai-main")]),
        _credentials_with_openai(),
        github_token="ghp",
        catalog_repo="studio-llm-model-catalog",
        catalog_owner="",
        branch="main",
        enabled=True,
        client_factory=FakeClient,
    )
    assert result is None
    assert called is False
