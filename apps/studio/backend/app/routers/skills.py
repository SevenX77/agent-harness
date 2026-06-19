"""Skill lifecycle endpoint scaffold."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core import config
from app.core.adapters.http_transport import StudioAdapterError
from app.core.adapters.product_store_local import LocalProductArtifactStore
from app.core.backends import (
    get_auth_user_id,
    get_git_collab,
    get_metadata,
    get_registry_client,
    get_storage,
)
from app.core.exceptions import error_response, raise_error_response
from app.core.native_fs_write_boundary import (
    FULL_SKILL_SOURCE_WRITE_ROUTE,
    SKILL_FILE_SOURCE_WRITE_ROUTE,
    source_write_fallback_header,
    source_write_fallback_value,
)
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.git_collab import SyncSkillReq
from app.models.git_history import GitHistoryItem, RevertSkillReq
from app.models.publish import PublishResult, PublishSkillReq
from app.models.runs import RunMetadata, RunRequest
from app.models.skills import (
    ChildGraphTopology,
    CompileSuccess,
    CreateSkillReq,
    ForkSkillReq,
    SerializeGraphReq,
    SerializeGraphRes,
    SkillDetail,
    SkillSummary,
    UpdateSkillFileReq,
    UpdateSkillFileRes,
    UpdateSkillReq,
)
from app.models.validation import ValidateInputReq, ValidateInputResponse
from app.services.artifact_registry import (
    ArtifactRegistryClient,
)
from app.services.canvas_errors import CanvasConflictError, CanvasSerializerFatal
from app.services.git_collab import CollaborateResult, GitCollaborateService, GiteaApiError
from app.services.git_local import (
    RELEASE_ARTIFACT_ID_TRAILER,
    RELEASE_CONTENT_HASH_TRAILER,
    RELEASE_MANIFEST_REF_TRAILER,
    RELEASE_MARKER_TRAILER,
    RELEASE_VERSION_TRAILER,
    GitCommandError,
    GitLocalService,
    GitObjectNotFoundError,
    GitRevertConflictError,
)
from app.services.run_manager import run_manager
from app.services.skills import (
    CompileFailedError,
    compile_skill_for_studio,
    create_new_skill,
    delete_skill,
    fork_skill,
    get_child_graph_topology,
    get_skill_detail,
    list_skill_summaries,
    resolve_skill_dir_async,
    serialize_skill_graph_markdown,
    update_skill_file,
    update_skill_files,
)
from app.services.validator import ValidationHttpError, validate_skill_input_file

router = APIRouter(prefix="/api/skills", tags=["skills"])
git_service = GitLocalService()
RELEASE_SNAPSHOT_PREFIX = "release-"
SKILL_FILE_WRITE_FALLBACK_HEADER = source_write_fallback_header(SKILL_FILE_SOURCE_WRITE_ROUTE)
FULL_SKILL_WRITE_FALLBACK_HEADER = source_write_fallback_header(FULL_SKILL_SOURCE_WRITE_ROUTE)


def _require_browser_write_fallback(
    write_fallback: str | None,
    *,
    route_key: tuple[str, str],
) -> None:
    fallback_header = source_write_fallback_header(route_key)
    fallback_value = source_write_fallback_value(route_key).strip().lower()
    if write_fallback is not None and write_fallback.strip().lower() == fallback_value:
        return
    raise_error_response(
        error_response(
            error_code="NATIVE_FS_REQUIRED",
            http_status=409,
            message="Mutating workspace writes require native-fs unless browser fallback is explicit",
            details={
                "required_header": fallback_header,
                "required_value": fallback_value,
            },
            retry_strategy="not_retryable",
        )
    )


def _record_release_history_snapshot(skill_dir: Path | None, release_manifest: dict[str, object]) -> None:
    if skill_dir is None or not (skill_dir / ".git").exists():
        return
    trailers = _release_marker_trailers(release_manifest)
    release_version = trailers.get(RELEASE_VERSION_TRAILER)
    if release_version is None:
        return
    try:
        git_service.commit_empty_snapshot(
            skill_dir,
            f"{RELEASE_SNAPSHOT_PREFIX}{release_version}",
            trailers=trailers,
        )
    except GitCommandError:
        return


def _release_marker_trailers(release_manifest: dict[str, object]) -> dict[str, str]:
    release_version = release_manifest.get("release_version")
    content_hash = release_manifest.get("content_hash")
    manifest_ref = release_manifest.get("manifest_ref")
    artifact_ref = release_manifest.get("artifact_ref")
    if isinstance(artifact_ref, dict):
        if not isinstance(content_hash, str):
            content_hash = artifact_ref.get("content_hash")
        if not isinstance(manifest_ref, str):
            manifest_ref = artifact_ref.get("manifest_ref")
    artifact_id = _committed_artifact_id(release_manifest)
    if not (
        isinstance(release_version, str)
        and release_version.strip()
        and isinstance(content_hash, str)
        and content_hash.strip()
        and isinstance(manifest_ref, str)
        and manifest_ref.strip()
    ):
        return {}
    trailers = {
        RELEASE_MARKER_TRAILER: "true",
        RELEASE_VERSION_TRAILER: release_version,
        RELEASE_CONTENT_HASH_TRAILER: content_hash,
        RELEASE_MANIFEST_REF_TRAILER: manifest_ref,
    }
    if artifact_id is not None:
        trailers[RELEASE_ARTIFACT_ID_TRAILER] = artifact_id
    return trailers


def _release_version_from_history_message(message: str) -> str | None:
    if not message.startswith(RELEASE_SNAPSHOT_PREFIX):
        return None
    release_version = message.removeprefix(RELEASE_SNAPSHOT_PREFIX)
    if release_version != release_version.strip() or any(char.isspace() for char in release_version):
        return None
    return release_version or None


def _release_manifests_by_version(skill_id: str) -> dict[str, dict[str, object]]:
    store = _product_artifact_store()
    releases = store.list_releases(skill_id)
    return {
        str(release["release_version"]): release
        for release in releases
        if isinstance(release, dict) and isinstance(release.get("release_version"), str)
    }


def _release_history_key(release: dict[str, object]) -> tuple[object, object, object, object]:
    return (
        release.get("release_version"),
        release.get("artifact_id"),
        release.get("content_hash"),
        release.get("manifest_ref"),
    )


def _release_history_timestamp(
    release: dict[str, object],
    representative: GitHistoryItem | None,
) -> datetime:
    if representative is not None:
        return representative.timestamp
    created_at = release.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        try:
            return datetime.fromisoformat(created_at)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=UTC)


def _release_history_sha(release: dict[str, object], representative: GitHistoryItem | None) -> str:
    if representative is not None:
        return representative.sha
    release_version = str(release.get("release_version") or "unknown")
    content_hash = str(release.get("content_hash") or "")
    manifest_ref = str(release.get("manifest_ref") or "")
    return f"release:{release_version}:{content_hash or manifest_ref}"


def _release_history_item(
    release: dict[str, object],
    representative: GitHistoryItem | None,
) -> GitHistoryItem:
    release_version = str(release.get("release_version") or "")
    git_backed = representative is not None
    return GitHistoryItem(
        sha=_release_history_sha(release, representative),
        message=f"{RELEASE_SNAPSHOT_PREFIX}{release_version}",
        author=representative.author if representative is not None else "product-store",
        timestamp=_release_history_timestamp(release, representative),
        kind="release",
        source="git" if git_backed else "manifest",
        revertable=git_backed,
        release_version=release_version,
        artifact_id=release.get("artifact_id") if isinstance(release.get("artifact_id"), str) else None,
        content_hash=release.get("content_hash") if isinstance(release.get("content_hash"), str) else None,
        manifest_ref=release.get("manifest_ref") if isinstance(release.get("manifest_ref"), str) else None,
    )


def _publish_idempotency_key(skill_id: str, release_version: str, idempotency_key: str | None) -> str:
    return (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else f"publish-idem-{skill_id}-{release_version}"
    )


def _studio_error_code(exc: Exception) -> str | None:
    if not isinstance(exc, HTTPException) or not isinstance(exc.detail, dict):
        return None
    error_code = exc.detail.get("error_code")
    return error_code if isinstance(error_code, str) else None


async def _has_current_user_skill_ownership_evidence(
    user_id: str,
    skill_id: str,
    metadata: MetadataStore,
) -> bool:
    if skill_id in await metadata.list_unregistered_skill_ids(user_id):
        return False
    return await metadata.get_skill_summary(user_id, skill_id) is not None


def _committed_artifact_id(release_manifest: dict[str, object]) -> str | None:
    artifact_ref = release_manifest.get("artifact_ref")
    artifact_ref_id = artifact_ref.get("artifact_id") if isinstance(artifact_ref, dict) else None
    committed_artifact_id = release_manifest.get("artifact_id")
    if isinstance(committed_artifact_id, str) and committed_artifact_id:
        return committed_artifact_id
    return artifact_ref_id if isinstance(artifact_ref_id, str) and artifact_ref_id else None


def _registry_artifact_id(server_response: dict[str, object]) -> str | None:
    remote_artifact_id = server_response.get("artifact_id")
    return remote_artifact_id if isinstance(remote_artifact_id, str) and remote_artifact_id.strip() else None


def _release_history_items_from_manifests(
    release_by_version: dict[str, dict[str, object]],
    history: list[GitHistoryItem],
) -> list[GitHistoryItem]:
    representative_by_key: dict[tuple[object, object, object, object], GitHistoryItem] = {}
    for item in history:
        release = release_by_version.get(item.release_version or "")
        if release is None or not _history_item_matches_release(item, release):
            continue
        key = _release_history_key(release)
        representative_by_key.setdefault(key, item)
    return [
        _release_history_item(release, representative_by_key.get(_release_history_key(release)))
        for release in release_by_version.values()
    ]


def _history_item_matches_release(item: GitHistoryItem, release: dict[str, object]) -> bool:
    return (
        item.kind == "release"
        and item.source == "git"
        and item.release_version == release.get("release_version")
        and item.content_hash == release.get("content_hash")
        and item.manifest_ref == release.get("manifest_ref")
    )


def _merge_release_and_git_history(skill_id: str, history: list[GitHistoryItem]) -> list[GitHistoryItem]:
    release_by_version = _release_manifests_by_version(skill_id)
    release_items = _release_history_items_from_manifests(release_by_version, history)
    non_release_history = [
        item
        for item in history
        if not any(_history_item_matches_release(item, release) for release in release_by_version.values())
    ]
    return sorted(
        [*release_items, *non_release_history],
        key=lambda item: item.timestamp,
        reverse=True,
    )


@router.get("", response_model=list[SkillSummary])
async def list_skills(
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> list[SkillSummary]:
    return await list_skill_summaries(user_id, storage, metadata)


@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(
    request: CreateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillSummary:
    return await create_new_skill(
        user_id,
        request.skill_id,
        request.files,
        storage,
        metadata,
        directory_path=request.directory_path,
        import_existing=request.import_existing,
    )


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    return await get_skill_detail(user_id, skill_id, storage, metadata)


@router.get("/{skill_id}/subgraph", response_model=ChildGraphTopology)
async def get_subgraph_child_topology(
    skill_id: str,
    path: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> ChildGraphTopology:
    """Resolve a subgraph's child GRAPH.md by absolute path within the boundary."""
    return await get_child_graph_topology(user_id, skill_id, path, storage, metadata)


@router.post("/{skill_id}/compile", response_model=CompileSuccess)
async def compile_skill_endpoint(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> CompileSuccess | JSONResponse:
    try:
        return await compile_skill_for_studio(user_id, skill_id, storage, metadata)
    except CompileFailedError as exc:
        return JSONResponse(status_code=422, content=jsonable_encoder(exc.failure.model_dump()))


@router.get("/{skill_id}/releases", response_model=list[dict[str, Any]])
async def list_skill_releases(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> list[dict[str, Any]]:
    await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        return await asyncio.to_thread(_product_artifact_store().list_releases, skill_id)
    except StudioAdapterError as exc:
        _raise_release_store_error(exc)


@router.get("/{skill_id}/releases/{release_version}", response_model=dict[str, Any])
async def get_skill_release(
    skill_id: str,
    release_version: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> dict[str, Any]:
    await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        release = await asyncio.to_thread(
            _product_artifact_store().get_release,
            skill_id,
            release_version,
        )
    except StudioAdapterError as exc:
        _raise_release_store_error(exc)
    if release is None:
        response = error_response(
            error_code="RELEASE_NOT_FOUND",
            http_status=404,
            message=f"Release {release_version} not found for skill {skill_id}",
            details={"skill_id": skill_id, "release_version": release_version},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    return release


@router.post("/{skill_id}/releases/{release_version}/runs", response_model=RunMetadata, status_code=202)
async def run_skill_release(
    skill_id: str,
    release_version: str,
    request: RunRequest,
    user_id: str = Depends(get_auth_user_id),
) -> RunMetadata:
    del user_id
    store = _product_artifact_store()
    artifact_ref: dict[str, Any] | None = None
    try:
        release = await asyncio.to_thread(store.get_release, skill_id, release_version)
        if release is None:
            response = error_response(
                error_code="RELEASE_NOT_FOUND",
                http_status=404,
                message=f"Release {release_version} not found for skill {skill_id}",
                details={"skill_id": skill_id, "release_version": release_version},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)
        artifact_ref = _release_run_artifact_ref(release, release_version)
        await asyncio.to_thread(store.get, artifact_ref["content_hash"])
    except StudioAdapterError as exc:
        if exc.error_code.startswith("artifact."):
            _raise_release_artifact_error(exc, artifact_ref, release_version)
        _raise_release_store_error(exc)
    if artifact_ref is None:
        raise RuntimeError("release artifact_ref missing after validation")
    return await run_manager.start_run_from_artifact(skill_id, request, artifact_ref=artifact_ref)


@router.post("/{skill_id}/graph/serialize", response_model=SerializeGraphRes)
async def serialize_skill_graph(
    skill_id: str,
    request: SerializeGraphReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SerializeGraphRes | JSONResponse:
    try:
        return await serialize_skill_graph_markdown(
            user_id,
            skill_id,
            request,
            storage,
            metadata,
        )
    except CanvasConflictError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "code": "snapshot_conflict",
                "current_hash": exc.current_hash,
                "current_markdown_content": exc.current_markdown_content,
                "current_phase_count": exc.current_phase_count,
            },
        )
    except CanvasSerializerFatal as exc:
        return JSONResponse(
            status_code=422,
            content={
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
                "skill_id": skill_id,
                "elapsed_ms": exc.elapsed_ms,
            },
        )


@router.post("/{skill_id}/sync", response_model=CollaborateResult)
async def sync_skill(
    skill_id: str,
    request: SyncSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
    git_collab: GitCollaborateService = Depends(get_git_collab),
) -> CollaborateResult:
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    app_settings = await metadata.read_app_settings()
    owner = app_settings.user_id.strip()
    gitea_host = app_settings.gitea_host.strip()
    if not owner:
        response = error_response(
            error_code="APP_SETTINGS_INCOMPLETE",
            http_status=400,
            message="User ID 未配置, 请到 Settings 设置",
            details={"field": "user_id"},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    if not gitea_host:
        response = error_response(
            error_code="APP_SETTINGS_INCOMPLETE",
            http_status=400,
            message="Gitea Host 未配置, 请到 Settings 设置",
            details={"field": "gitea_host"},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    git_collab.gitea_host = gitea_host.rstrip("/")
    git_collab.gitea.host = gitea_host.rstrip("/")

    try:
        if request.action == "save_to_team":
            return git_collab.save_to_team(
                skill_dir,
                owner=owner,
                repo=skill_id,
                branch=request.branch,
            )
        if request.action == "sync_from_team":
            return git_collab.sync_from_team(
                skill_dir,
                owner=owner,
                repo=skill_id,
                branch=request.branch,
            )
        if not request.dev_branch:
            _raise_missing_required_field("dev_branch")
        if not request.pr_title:
            _raise_missing_required_field("pr_title")
        return git_collab.submit_for_review(
            skill_dir,
            owner=owner,
            repo=skill_id,
            dev_branch=request.dev_branch,
            pr_title=request.pr_title,
        )
    except GiteaApiError as exc:
        response = error_response(
            error_code="GITEA_API_ERROR",
            http_status=502,
            message=str(exc),
            details={"status_code": exc.status_code, "body": exc.body},
            retry_strategy="backoff",
        )
        raise_error_response(response)
    except GitCommandError as exc:
        response = error_response(
            error_code="GIT_COMMAND_FAILED",
            http_status=500,
            message=str(exc),
            details={
                "args": list(exc.result.args),
                "stdout": exc.result.stdout,
                "stderr": exc.result.stderr,
            },
            retry_strategy="idempotent",
        )
        raise_error_response(response)


@router.post("/{skill_id}/publish", response_model=PublishResult)
async def publish_skill(
    skill_id: str,
    request: PublishSkillReq,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
    registry: ArtifactRegistryClient = Depends(get_registry_client),
) -> PublishResult:
    skill_dir: Path | None = None
    app_settings = await metadata.read_app_settings()
    # N6/F2 + 设计§4: publish (the local product safety net) must NOT be gated on
    # Settings completeness. Only the remote registry sync leg needs an author
    # (user_id); when it is missing, that leg is skipped — the local release
    # still commits. The UI offers a one-click jump to Settings to reconfigure.
    has_publish_identity = bool(app_settings.user_id.strip())

    try:
        from app.services.publish_pipeline import (
            ProductArtifactPublisher,
            PublishArtifactRequest,
            PublishPartialFailure,
            PublishReleaseConflict,
        )

        idem_key = _publish_idempotency_key(skill_id, request.version, idempotency_key)
        from app.core.adapters.transport_factory import build_engine_adapter

        try:
            skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
        except Exception as resolve_exc:
            if _studio_error_code(resolve_exc) != "SKILL_NOT_FOUND":
                raise
            if not await _has_current_user_skill_ownership_evidence(user_id, skill_id, metadata):
                raise
            store = _product_artifact_store()
            publisher = ProductArtifactPublisher(store=store)
            existing_release = store.get_release(skill_id, request.version)
            existing_artifact_ref = existing_release.get("artifact_ref") if isinstance(existing_release, dict) else None
            if not (
                isinstance(existing_release, dict)
                and existing_release.get("idempotency_key") == idem_key
                and isinstance(existing_artifact_ref, dict)
            ):
                raise resolve_exc
            artifact_ref_dict = existing_artifact_ref
        else:
            store = _product_artifact_store()
            publisher = ProductArtifactPublisher(store=store)
            adapter = build_engine_adapter()
            artifact_ref_dict = adapter.compile(
                {
                    "skill_dir": str(skill_dir),
                    "skill_id": skill_id,
                    "artifact_scope": "product",
                }
            )
        if not isinstance(artifact_ref_dict, dict):
            raise ValueError("compile artifact_ref must be an object")

        req = PublishArtifactRequest(
            artifact_ref=artifact_ref_dict,
            release_version=request.version,
            idempotency_key=idem_key,
            atomic_stage="stage_invisible",
        )

        # Registry precheck: reject a version/identity conflict against the local
        # product store before staging or writing the package. Read-only.
        await asyncio.to_thread(
            publisher.precheck_release,
            skill_id=skill_id,
            release_version=request.version,
            artifact_ref=req.artifact_ref,
            idempotency_key=req.idempotency_key,
        )

        if has_publish_identity and registry.host.strip() and registry.token.strip():
            from app.services.artifact_registry import sync_product_artifact_release

            server_response: dict[str, object] = {}

            def remote_sync(release_manifest: dict[str, object]) -> None:
                nonlocal server_response
                server_response = sync_product_artifact_release(
                    skill_id=skill_id,
                    release_manifest=release_manifest,
                    store=store,
                    registry=registry,
                    app_settings=app_settings,
                    version=request.version,
                )

            release_manifest = await asyncio.to_thread(
                publisher.publish_release,
                skill_id=skill_id,
                release_version=request.version,
                artifact_ref=req.artifact_ref,
                idempotency_key=req.idempotency_key,
                remote_sync=remote_sync,
            )

            registry_artifact_id = _registry_artifact_id(server_response)
            artifact_ref = release_manifest["artifact_ref"]
            local_artifact_id_value = artifact_ref.get("artifact_id") if isinstance(artifact_ref, dict) else None
            local_artifact_id = local_artifact_id_value if isinstance(local_artifact_id_value, str) else None
            committed_artifact_id_value = release_manifest.get("artifact_id")
            committed_artifact_id = (
                committed_artifact_id_value
                if isinstance(committed_artifact_id_value, str)
                else local_artifact_id
            )
            remote_sync = release_manifest.get("remote_sync")
            remote_sync_failed = isinstance(remote_sync, dict) and remote_sync.get("status") == "failed"

            extra_dict = {
                "version": request.version,
                "release_version": request.version,
                "skill_id": skill_id,
                "artifact_id": committed_artifact_id,
                "artifact_ref": artifact_ref,
                "content_hash": artifact_ref.get("content_hash") if isinstance(artifact_ref, dict) else None,
                "manifest_ref": artifact_ref.get("manifest_ref") if isinstance(artifact_ref, dict) else None,
                "package_kind": "product_artifact",
            }
            if isinstance(remote_sync, dict):
                extra_dict["remote_sync"] = remote_sync
            if registry_artifact_id is not None and not remote_sync_failed:
                extra_dict["registry_artifact_id"] = registry_artifact_id

            _record_release_history_snapshot(skill_dir, release_manifest)
            return PublishResult(
                status="ok",
                message=(
                    "Published to local product store; registry sync failed"
                    if remote_sync_failed
                    else "Published to registry"
                ),
                artifact_id=committed_artifact_id,
                extra=extra_dict,
            )

        release_manifest = await asyncio.to_thread(
            publisher.publish_release,
            skill_id=skill_id,
            release_version=request.version,
            artifact_ref=req.artifact_ref,
            idempotency_key=req.idempotency_key,
        )
        remote_sync = release_manifest.get("remote_sync")
        if not (isinstance(remote_sync, dict) and remote_sync.get("status") == "succeeded"):
            skip_reason = (
                "registry_not_configured" if has_publish_identity else "app_settings_incomplete"
            )
            remote_sync = {
                "status": "skipped",
                "reason": skip_reason,
            }
            await asyncio.to_thread(
                store.record_remote_sync_state,
                skill_id,
                request.version,
                remote_sync,
            )
            release_manifest["remote_sync"] = remote_sync

    except PublishReleaseConflict as exc:
        details = {"skill_id": skill_id, "version": request.version, "release_version": request.version}
        if isinstance(exc.details, dict):
            details.update(exc.details)
        response = error_response(
            error_code="PUBLISH_CONFLICT",
            http_status=409,
            message=str(exc),
            details=details,
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    except PublishPartialFailure as exc:
        details = {"skill_id": skill_id, "version": request.version}
        if isinstance(exc.details, dict):
            details.update(exc.details)
        response = error_response(
            error_code="PUBLISH_FAILED",
            http_status=500,
            message=str(exc),
            details=details,
            retry_strategy="backoff",
        )
        raise_error_response(response)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise

        import httpx

        from app.services.artifact_registry import ArtifactRegistryApiError

        orig_exc = exc
        if exc.__cause__:
            orig_exc = exc.__cause__
        elif exc.__context__:
            orig_exc = exc.__context__

        if isinstance(orig_exc, ValueError) and ("skill_dir" in str(orig_exc) or "directory" in str(orig_exc)):
            response = error_response(
                error_code="SKILL_DIR_MISSING",
                http_status=404,
                message=f"Skill directory missing for publish: {skill_id}",
                details={"skill_id": skill_id, "error": str(orig_exc)},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)
        elif isinstance(orig_exc, ArtifactRegistryApiError):
            response = error_response(
                error_code="REGISTRY_API_ERROR",
                http_status=502,
                message=str(orig_exc),
                details={"status_code": orig_exc.status_code, "body": orig_exc.body},
                retry_strategy="backoff",
            )
            raise_error_response(response)
        elif isinstance(orig_exc, httpx.RequestError):
            response = error_response(
                error_code="REGISTRY_NETWORK_ERROR",
                http_status=503,
                message=str(orig_exc),
                details={"error": str(orig_exc)},
                retry_strategy="backoff",
            )
            raise_error_response(response)

        response = error_response(
            error_code="PUBLISH_FAILED",
            http_status=500,
            message=f"Failed to publish skill {skill_id}: {exc}",
            details={"skill_id": skill_id},
            retry_strategy="backoff",
        )
        raise_error_response(response)

    _record_release_history_snapshot(skill_dir, release_manifest)
    artifact_ref = release_manifest["artifact_ref"]
    committed_artifact_id_value = release_manifest.get("artifact_id")
    committed_artifact_id = (
        committed_artifact_id_value
        if isinstance(committed_artifact_id_value, str)
        else artifact_ref["artifact_id"]
        if isinstance(artifact_ref, dict)
        else None
    )
    return PublishResult(
        status="ok",
        message="Published to local product store",
        artifact_id=committed_artifact_id,
        extra={
            "version": request.version,
            "release_version": request.version,
            "skill_id": skill_id,
            "artifact_id": committed_artifact_id,
            "artifact_ref": artifact_ref,
            "content_hash": artifact_ref.get("content_hash") if isinstance(artifact_ref, dict) else None,
            "manifest_ref": artifact_ref.get("manifest_ref") if isinstance(artifact_ref, dict) else None,
            "package_kind": "product_artifact",
            "remote_sync": release_manifest.get("remote_sync"),
        },
    )


@router.put("/{skill_id}", response_model=SkillDetail)
async def update_skill(
    skill_id: str,
    request: UpdateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
    write_fallback: str | None = Header(default=None, alias=FULL_SKILL_WRITE_FALLBACK_HEADER),
) -> SkillDetail | JSONResponse:
    _require_browser_write_fallback(write_fallback, route_key=FULL_SKILL_SOURCE_WRITE_ROUTE)
    try:
        return await update_skill_files(
            user_id,
            skill_id,
            request.files,
            storage,
            metadata,
            expected_hash=request.expected_hash,
        )
    except CanvasConflictError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "code": "snapshot_conflict",
                "current_hash": exc.current_hash,
                "current_markdown_content": exc.current_markdown_content,
            },
        )


@router.post("/{skill_id}/files/{file_path:path}", response_model=UpdateSkillFileRes)
async def update_skill_file_endpoint(
    skill_id: str,
    file_path: str,
    request: UpdateSkillFileReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
    write_fallback: str | None = Header(default=None, alias=SKILL_FILE_WRITE_FALLBACK_HEADER),
) -> UpdateSkillFileRes | JSONResponse:
    _require_browser_write_fallback(write_fallback, route_key=SKILL_FILE_SOURCE_WRITE_ROUTE)
    try:
        new_hash = await update_skill_file(
            user_id,
            skill_id,
            file_path,
            request.content,
            storage,
            metadata,
            expected_hash=request.expected_hash,
        )
    except CanvasConflictError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "code": "snapshot_conflict",
                "current_hash": exc.current_hash,
                "current_markdown_content": exc.current_markdown_content,
            },
        )
    return UpdateSkillFileRes(path=file_path, hash=new_hash)


@router.get("/{skill_id}/history", response_model=list[GitHistoryItem])
async def get_skill_history(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> list[GitHistoryItem]:
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        history = git_service.list_history(skill_dir)
    except GitCommandError:
        history = []
    try:
        return _merge_release_and_git_history(skill_id, history)
    except StudioAdapterError as exc:
        _raise_release_store_error(exc)


@router.post("/{skill_id}/revert", response_model=SkillDetail)
async def revert_skill(
    skill_id: str,
    request: RevertSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        git_service.revert_to(skill_dir, request.sha)
    except GitObjectNotFoundError:
        response = error_response(
            error_code="GIT_OBJECT_NOT_FOUND",
            http_status=404,
            message=f"Git commit not found: {request.sha}",
            details={"skill_id": skill_id, "sha": request.sha},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    except GitRevertConflictError:
        response = error_response(
            error_code="GIT_REVERT_CONFLICT",
            http_status=409,
            message=f"Git revert conflict for skill: {skill_id}",
            details={"skill_id": skill_id, "sha": request.sha},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    return await get_skill_detail(user_id, skill_id, storage, metadata)


@router.post("/{skill_id}/fork", response_model=SkillSummary, status_code=201)
async def fork_existing_skill(
    skill_id: str,
    request: ForkSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillSummary:
    return await fork_skill(user_id, skill_id, request.new_skill_id, storage, metadata)


@router.post("/{skill_id}/validate_input", response_model=ValidateInputResponse)
async def validate_input(
    skill_id: str,
    request: ValidateInputReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> ValidateInputResponse | JSONResponse:
    try:
        validated_data = await validate_skill_input_file(
            user_id,
            skill_id,
            request.input_file_path,
            storage,
            metadata,
        )
    except ValidationHttpError as exc:
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(exc.body))
    return ValidateInputResponse(validated_data=validated_data)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill_endpoint(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> Response:
    await delete_skill(user_id, skill_id, storage, metadata)
    return Response(status_code=204)


def _raise_missing_required_field(field: str) -> NoReturn:
    response = error_response(
        error_code="MISSING_REQUIRED_FIELD",
        http_status=400,
        message=f"Missing required field: {field}",
        details={"field": field},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


def _product_artifact_store() -> LocalProductArtifactStore:
    storage_root = (
        Path(config.settings.storage_root)
        if hasattr(config, "settings") and hasattr(config.settings, "storage_root")
        else config.WORKSPACES_DIR / "default"
    )
    return LocalProductArtifactStore(root=storage_root)


def _release_run_artifact_ref(release: dict[str, Any], release_version: str) -> dict[str, Any]:
    artifact_ref = release.get("artifact_ref")
    if not isinstance(artifact_ref, dict):
        raise StudioAdapterError(
            "release.invalid_manifest",
            {"release_version": release_version, "field": "artifact_ref"},
        )
    content_hash = artifact_ref.get("content_hash")
    if not isinstance(content_hash, str):
        raise StudioAdapterError(
            "release.invalid_manifest",
            {"release_version": release_version, "field": "artifact_ref.content_hash"},
        )
    run_ref = dict(artifact_ref)
    run_ref["store"] = "product"
    run_ref["version"] = release_version
    return run_ref


def _raise_release_artifact_error(
    exc: StudioAdapterError,
    artifact_ref: dict[str, Any] | None,
    release_version: str,
) -> NoReturn:
    details = dict(exc.error_payload)
    details.pop("hash", None)
    if artifact_ref is not None:
        details.update(
            {
                "artifact_id": artifact_ref.get("artifact_id"),
                "content_hash": artifact_ref.get("content_hash"),
                "store": artifact_ref.get("store"),
                "version": release_version,
                "release_version": release_version,
            }
        )
    details.setdefault(
        "detail",
        "Product artifact bytes are missing"
        if exc.error_code == "artifact.not_found"
        else f"Product artifact error: {exc.error_code}",
    )
    http_status = 404 if exc.error_code == "artifact.not_found" else 422
    raise_error_response(
        error_response(
            error_code=exc.error_code,
            http_status=http_status,
            message=str(details["detail"]),
            details=details,
            retry_strategy="not_retryable",
        )
    )


def _raise_release_store_error(exc: StudioAdapterError) -> NoReturn:
    http_status = 400 if exc.error_code in {"release.invalid_path", "release.invalid_manifest"} else 500
    response = error_response(
        error_code=exc.error_code.upper().replace(".", "_"),
        http_status=http_status,
        message=str(exc),
        details=exc.error_payload,
        retry_strategy="not_retryable",
    )
    raise_error_response(response)
