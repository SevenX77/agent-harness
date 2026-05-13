"""Skill lifecycle endpoint scaffold."""

from __future__ import annotations

import asyncio
from typing import NoReturn

import httpx
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.backends import get_auth_user_id, get_git_collab, get_metadata, get_registry_client, get_storage
from app.core.exceptions import error_response, raise_error_response, raise_not_implemented
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import ErrorResponse
from app.models.git_collab import SyncSkillReq
from app.models.git_history import GitHistoryItem, RevertSkillReq
from app.models.publish import PublishResult, PublishSkillReq
from app.models.skills import (
    CreateSkillReq,
    ForkSkillReq,
    SkillDetail,
    SkillSummary,
    UpdateSkillReq,
)
from app.models.validation import ValidateInputReq, ValidateInputResponse
from app.services.artifact_registry import (
    ArtifactRegistryApiError,
    ArtifactRegistryClient,
    build_publish_metadata,
    build_publish_package,
)
from app.services.git_local import (
    GitCommandError,
    GitLocalService,
    GitObjectNotFoundError,
    GitRevertConflictError,
)
from app.services.git_collab import CollaborateResult, GiteaApiError, GitCollaborateService
from app.services.skills import (
    create_new_skill,
    fork_skill,
    get_skill_detail,
    list_skill_summaries,
    update_skill_content,
    resolve_skill_dir_async,
)
from app.services.validator import ValidationHttpError, validate_skill_input_file

router = APIRouter(prefix="/api/skills", tags=["skills"])
git_service = GitLocalService()


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
        request.content,
        storage,
        metadata,
        directory_path=request.directory_path,
    )


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    return await get_skill_detail(user_id, skill_id, storage, metadata)


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
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
    registry: ArtifactRegistryClient = Depends(get_registry_client),
) -> PublishResult:
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    app_settings = await metadata.read_app_settings()
    if not app_settings.user_id.strip():
        response = error_response(
            error_code="APP_SETTINGS_INCOMPLETE",
            http_status=400,
            message="User ID 未配置, 请到 Settings 设置",
            details={"field": "user_id"},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    if not registry.host:
        response = error_response(
            error_code="REGISTRY_NOT_CONFIGURED",
            http_status=400,
            message="Artifact Registry Host 未配置",
            details={"field": "registry_host"},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    if not registry.token:
        response = error_response(
            error_code="REGISTRY_NOT_CONFIGURED",
            http_status=400,
            message="Artifact Registry Token 未配置",
            details={"field": "registry_token"},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    try:
        package = await asyncio.to_thread(build_publish_package, skill_dir)
        publish_metadata = build_publish_metadata(skill_id, app_settings, version=request.version)
        server_response = await asyncio.to_thread(
            registry.upload_artifact,
            skill_id=skill_id,
            package=package,
            metadata=publish_metadata,
        )
    except ValueError as exc:
        if "skill_dir" in str(exc) or "directory" in str(exc):
            response = error_response(
                error_code="SKILL_DIR_MISSING",
                http_status=404,
                message=f"Skill directory missing for publish: {skill_id}",
                details={"skill_id": skill_id, "error": str(exc)},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)
        raise
    except ArtifactRegistryApiError as exc:
        response = error_response(
            error_code="REGISTRY_API_ERROR",
            http_status=502,
            message=str(exc),
            details={"status_code": exc.status_code, "body": exc.body},
            retry_strategy="backoff",
        )
        raise_error_response(response)
    except httpx.RequestError as exc:
        response = error_response(
            error_code="REGISTRY_NETWORK_ERROR",
            http_status=503,
            message=str(exc),
            details={"error": str(exc)},
            retry_strategy="backoff",
        )
        raise_error_response(response)

    artifact_id_value = server_response.get("artifact_id")
    artifact_id = artifact_id_value if isinstance(artifact_id_value, str) else None
    return PublishResult(
        status="ok",
        message="Published to registry",
        artifact_id=artifact_id,
        extra={
            "version": request.version,
            "package_bytes": len(package),
            "skill_id": skill_id,
        },
    )


@router.put("/{skill_id}", response_model=SkillDetail)
async def update_skill(
    skill_id: str,
    request: UpdateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillDetail:
    return await update_skill_content(user_id, skill_id, request.content, storage, metadata)


@router.get("/{skill_id}/history", response_model=list[GitHistoryItem])
async def get_skill_history(
    skill_id: str,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> list[GitHistoryItem]:
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        return git_service.list_history(skill_dir)
    except GitCommandError:
        return []


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


@router.delete(
    "/{skill_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_skill(skill_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete skill {skill_id}")


def _raise_missing_required_field(field: str) -> NoReturn:
    response = error_response(
        error_code="MISSING_REQUIRED_FIELD",
        http_status=400,
        message=f"Missing required field: {field}",
        details={"field": field},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)
