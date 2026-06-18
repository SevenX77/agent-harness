from __future__ import annotations

import io
import json
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from graph_agent import (
    CompiledSkill as CompiledSkill,
)

# Additional re-exports required by app.services.*:
from graph_agent import GraphAgentError as GraphAgentError
from graph_agent import (
    GraphCompileError as GraphCompileError,
)
from graph_agent import ResourceNotFoundError as ResourceNotFoundError
from graph_agent import (
    compile_skill as compile_skill,
)
from graph_agent import evaluate_golden_baseline as evaluate_golden_baseline
from graph_agent.callbacks.events import CallbackEvent as CallbackEvent
from graph_agent.core._predict_internal.golden_eval import calculate_score as calculate_score
from graph_agent.core._predict_internal.golden_eval import diff_outputs as diff_outputs
from graph_agent.core._predict_internal.path_diff import compute_diff as compute_diff
from graph_agent.core.event_contracts import EventEnvelope as EventEnvelope
from graph_agent.core.event_contracts import StreamCursorExpiredError as StreamCursorExpiredError
from graph_agent.core.event_contracts import StreamCursorGapError as StreamCursorGapError
from graph_agent.core.event_contracts import TransportErrorPayload as TransportErrorPayload
from graph_agent.core.event_contracts import make_event_envelope as make_event_envelope
from graph_agent.core.exceptions import make_error_payload as make_error_payload
from graph_agent.core.graph_serializer import serialize_graph as serialize_graph
from graph_agent.core.graph_serializer import (
    serialize_graph_topology as serialize_graph_topology,
)
from graph_agent.core.llm_provider import LLMProviderError, LLMProviderRequest, LLMProviderResponse
from graph_agent.core.loader import SkillLoader as SkillLoader
from graph_agent.core.manifest import (
    AgentNodeAST as AgentNodeAST,
)
from graph_agent.core.manifest import (
    GraphManifest as GraphManifest,
)
from graph_agent.core.manifest import (
    GraphPhaseRef as GraphPhaseRef,
)
from graph_agent.core.manifest import (
    LogicNodeAST as LogicNodeAST,
)
from graph_agent.core.manifest import (
    PhaseIOSchema as PhaseIOSchema,
)
from graph_agent.core.manifest import (
    SkillManifest as SkillManifest,
)
from graph_agent.core.manifest import (
    SubgraphNodeAST as SubgraphNodeAST,
)
from graph_agent.core.result import (
    PathDiff as PathDiff,
)
from graph_agent.core.result import (
    PhaseRecord as PhaseRecord,
)
from graph_agent.core.result import RunResult as RunResult
from graph_agent.core.result import (
    WorkflowMetrics as WorkflowMetrics,
)
from graph_agent.core.result import (
    WorkflowResult as WorkflowResult,
)
from graph_agent.core.result_contracts import GoldenInputRef as GoldenInputRef
from graph_agent.core.result_contracts import NodeRunResult as NodeRunResult
from graph_agent.core.result_contracts import RunResultSnapshot as RunResultSnapshot
from graph_agent.core.result_contracts import RunResultsRef as RunResultsRef
from graph_agent.core.runner import (
    predict_artifact,
    run_artifact,
)

from app.core.adapters.http_transport import HttpTransport, StudioAdapterError

_SAFE_STUDIO_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_HEX_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


def _safe_studio_segment(value: str, label: str) -> str:
    segment = Path(value).name
    if (
        not value
        or segment != value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or not _SAFE_STUDIO_SEGMENT_RE.fullmatch(value)
    ):
        raise ValueError(f"Invalid {label}: {value}")
    return segment


def _safe_child_path(root: Path, *segments: str) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate = root_resolved.joinpath(*segments).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Unsafe path outside root: {candidate}") from exc
    return candidate


def _sha256_hex_from_content_hash(content_hash: str) -> str | None:
    if not content_hash.startswith("sha256:"):
        return None
    sha256_val = content_hash.split(":", 1)[1]
    return sha256_val if _SHA256_HEX_RE.fullmatch(sha256_val) else None


class _PrivateStudioSkillResolver:
    """Resolve Studio skill ids through local index, workspace, then bundled skills."""

    def resolve_skill(self, skill_id: str) -> Path:
        from graph_agent import ResourceNotFoundError

        from app.core import config

        safe_skill_id = _safe_studio_segment(skill_id, "skill_id")
        indexed = self._skill_index_entry(safe_skill_id)
        if indexed:
            indexed_root = Path(indexed["absolute_path"])
            if self._is_skill_root(indexed_root):
                return indexed_root
            message = f"skill {safe_skill_id!r}: indexed path is not a skill root: {indexed_root}"
            raise ResourceNotFoundError(
                message,
                payload=make_error_payload(
                    "[F-v3-resolver-path-invalid]",
                    message,
                    skill_id=safe_skill_id,
                    source_path=indexed_root,
                ),
            )

        workspace_root = _safe_child_path(config.default_workspace_skills_dir(), safe_skill_id)
        if self._is_skill_root(workspace_root):
            return workspace_root

        bundled_root = _safe_child_path(config.SKILLS_DIR, safe_skill_id)
        if self._is_skill_root(bundled_root):
            return bundled_root

        message = f"skill {safe_skill_id!r}: skill is not registered in Studio"
        raise ResourceNotFoundError(
            message,
            payload=make_error_payload(
                "[F-v3-skill-not-registered]",
                message,
                skill_id=safe_skill_id,
            ),
        )

    def _skill_index_entry(self, skill_id: str) -> dict[str, str] | None:
        from app.core import config

        index_path = config.SKILL_INDEX_PATH
        if not index_path.exists():
            return None
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        entry = raw.get(skill_id)
        if not isinstance(entry, dict) or not isinstance(entry.get("absolute_path"), str):
            return None
        return {
            "absolute_path": entry["absolute_path"],
            "l2_remote_url": (entry.get("l2_remote_url") if isinstance(entry.get("l2_remote_url"), str) else ""),
        }

    def _is_skill_root(self, path: Path) -> bool:
        return path.is_dir() and (path / "GRAPH.md").is_file()


def _private_build_gateway_model_resolver() -> Any:

    from app.core import config
    from app.core.adapters.gateway import ModelResolver
    from app.models.llm_config import LLMCredentialsFile, RolesData

    cred_path_env = os.environ.get("STUDIO_LLM_CREDENTIALS_PATH")
    cred_path = (
        Path(cred_path_env).expanduser() if cred_path_env else config.APP_SETTINGS_DIR / "llm" / "llm_credentials.json"
    )
    if cred_path.exists():
        try:
            cred_data = LLMCredentialsFile.model_validate(json.loads(cred_path.read_text(encoding="utf-8")))
        except Exception:
            cred_data = LLMCredentialsFile()
    else:
        cred_data = LLMCredentialsFile()

    roles_path_env = os.environ.get("STUDIO_LLM_ROLES_PATH")
    roles_path = (
        Path(roles_path_env).expanduser() if roles_path_env else config.APP_SETTINGS_DIR / "llm" / "llm_roles.yaml"
    )
    if roles_path.exists():
        try:
            from ruamel.yaml import YAML

            yaml = YAML(typ="rt")
            payload = yaml.load(roles_path.read_text(encoding="utf-8")) or {}

            def _to_plain(val: Any) -> Any:
                if isinstance(val, dict):
                    return {str(k): _to_plain(v) for k, v in val.items()}
                if isinstance(val, list):
                    return [_to_plain(v) for v in val]
                return val

            roles_data = RolesData.model_validate(_to_plain(payload))
        except Exception:
            roles_data = RolesData()
    else:
        roles_data = RolesData()

    from app.core.adapters.gateway import _filter_gateway_credentials, _filter_gateway_roles, _put_config_if_absent
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
    from app.services.llm_credentials import _credentials_payload_for_storage

    config_store = LocalGatewayConfigStore(root=config.APP_SETTINGS_DIR)
    _put_config_if_absent(
        config_store,
        config.DEFAULT_USER_ID,
        "credentials",
        _filter_gateway_credentials(_credentials_payload_for_storage(cred_data)),
    )
    _put_config_if_absent(
        config_store,
        config.DEFAULT_USER_ID,
        "roles",
        _filter_gateway_roles(roles_data.model_dump(mode="json")),
    )
    return ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)


class _GatewayBackedLLMProvider:
    def __init__(self, resolver: Any) -> None:
        self._resolver = resolver

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        metadata = dict(request.metadata)
        try:
            model = self._resolver.resolve(
                request.role,
                model_override=metadata.get("model_override"),
                callbacks=tuple(metadata.get("callbacks") or ()),
                phase_name=metadata.get("phase_name"),
            )
            tools = metadata.get("bound_tools") or []
            if tools and hasattr(model, "bind_tools"):
                model = model.bind_tools(
                    tools,
                    tool_choice=metadata.get("tool_choice"),
                    **dict(metadata.get("tool_kwargs") or {}),
                )
            result = model._generate(
                request.messages,
                stop=metadata.get("stop"),
            )
            message = result.generations[0].message
            response_metadata = dict(getattr(message, "response_metadata", None) or {})
            llm_output = dict(getattr(result, "llm_output", None) or {})
            response_metadata.update(llm_output)
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if tool_calls:
                response_metadata["tool_calls"] = tool_calls
            usage_metadata = getattr(message, "usage_metadata", None)
            if usage_metadata is not None:
                response_metadata["usage_metadata"] = usage_metadata
            model_name = (
                getattr(model, "model_name", None)
                or getattr(model, "model", None)
                or getattr(model, "name", None)
            )
            if model_name is not None:
                response_metadata.setdefault("model_name", str(model_name))
            return LLMProviderResponse(content=message.content, metadata=response_metadata)
        except Exception as exc:
            details = _safe_provider_error_details(getattr(exc, "details", {}))
            details.setdefault("exception_type", type(exc).__name__)
            raise LLMProviderError(
                error_code=str(getattr(exc, "error_code", "llm.provider_invoke_failed")),
                message=_safe_provider_error_message(exc),
                retryable=bool(getattr(exc, "retryable", False)),
                details=details,
            ) from None


def _safe_provider_error_details(raw_details: Any) -> dict[str, Any]:
    if not isinstance(raw_details, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in raw_details.items():
        key_text = str(key)
        if _contains_sensitive_error_text(key_text):
            continue
        safe[key_text] = _sanitize_error_value(value)
    return safe


def _sanitize_error_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _safe_provider_error_details(value)
    if isinstance(value, list):
        return [_sanitize_error_value(item) for item in value]
    if isinstance(value, str) and _contains_sensitive_error_text(value):
        return "[redacted]"
    return value


def _safe_provider_error_message(exc: Exception) -> str:
    error_code = str(getattr(exc, "error_code", ""))
    if isinstance(exc, LLMProviderError) or error_code.startswith("llm."):
        return "Provider invocation failed"
    message = str(exc)
    return "[redacted]" if _contains_sensitive_error_text(message) else message


def _contains_sensitive_error_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "secret",
            "api_key",
            "apikey",
            "authorization",
            "traceback",
            "token",
            "sk-",
        )
    )


def _runtime_state_checkpoint_value(state: dict[str, Any], key: str) -> str | None:
    value = state.get(key)
    if isinstance(value, str) and (value or key == "checkpoint_ns"):
        return value
    for container_key in ("checkpoint", "checkpoint_ref", "resume_checkpoint"):
        nested = state.get(container_key)
        if isinstance(nested, dict):
            nested_value = nested.get(key)
            if isinstance(nested_value, str) and (nested_value or key == "checkpoint_ns"):
                return nested_value
    return None


def _runtime_state_checkpointer_spec(execution_context: dict[str, Any], run_id: str) -> str | None:
    explicit = execution_context.get("checkpointer_spec") or execution_context.get("checkpointer_ref")
    if isinstance(explicit, str) and explicit:
        return explicit
    checkpointer = execution_context.get("checkpointer")
    if isinstance(checkpointer, str) and checkpointer:
        return checkpointer

    workspace_dir = execution_context.get("workspace_dir")
    if not isinstance(workspace_dir, str) or not workspace_dir or "/" in run_id or "\\" in run_id:
        return None
    return f"sqlite:{Path(workspace_dir) / 'runs' / run_id / 'checkpoints.db'}"


def _runtime_state_artifact_ref(restored_state: dict[str, Any], *, skill_id: str) -> dict[str, Any]:
    artifact_ref = restored_state.get("artifact_ref")
    if not isinstance(artifact_ref, dict):
        raise StudioAdapterError(
            "artifact.invalid_ref",
            {"run_id": restored_state.get("run_id"), "detail": "Runtime state snapshot is missing artifact_ref"},
        )

    artifact_id = artifact_ref.get("artifact_id")
    if artifact_id != skill_id:
        raise StudioAdapterError(
            "artifact.identity_mismatch",
            {
                "skill_id": skill_id,
                "artifact_id": artifact_id,
                "detail": "Runtime state artifact_ref does not match requested skill",
            },
        )
    _safe_studio_segment(str(artifact_id), "artifact_id")

    content_hash = artifact_ref.get("content_hash")
    if not isinstance(content_hash, str) or _sha256_hex_from_content_hash(content_hash) is None:
        raise StudioAdapterError("artifact.invalid_hash", {"content_hash": content_hash})

    store = artifact_ref.get("store")
    if store not in {"ephemeral", "product"}:
        raise StudioAdapterError(
            "artifact.invalid_ref",
            {"store": store, "detail": "artifact_ref.store must be ephemeral or product"},
        )

    manifest_ref = artifact_ref.get("manifest_ref")
    if not isinstance(manifest_ref, str) or not manifest_ref:
        raise StudioAdapterError(
            "artifact.invalid_ref",
            {"manifest_ref": manifest_ref, "detail": "artifact_ref.manifest_ref is required"},
        )

    source_map_ref = artifact_ref.get("source_map_ref")
    if source_map_ref is not None and not isinstance(source_map_ref, str):
        raise StudioAdapterError(
            "artifact.invalid_ref",
            {"source_map_ref": source_map_ref, "detail": "artifact_ref.source_map_ref must be a string"},
        )

    return {
        "artifact_id": artifact_id,
        "content_hash": content_hash,
        "store": store,
        "version": artifact_ref.get("version") if isinstance(artifact_ref.get("version"), str) else None,
        "manifest_ref": manifest_ref,
        "source_map_ref": source_map_ref or "",
    }


def _runtime_state_workspace_dir(restored_state: dict[str, Any], *, artifact_id: str, storage_root: Path) -> Path:
    checkpointer_spec = restored_state.get("checkpointer_spec")
    if isinstance(checkpointer_spec, str) and checkpointer_spec.startswith("sqlite:"):
        raw_path = checkpointer_spec.removeprefix("sqlite:")
        checkpointer_path = Path(raw_path)
        if checkpointer_path.is_absolute() and checkpointer_path.name == "checkpoints.db":
            return checkpointer_path.parent.parent.parent
    return storage_root / "skills" / artifact_id / ".workspace"


def _runtime_state_latest_checkpoint_state(
    runtime_state_store: Any,
    *,
    run_id: str,
    checkpointer: Any | None = None,
    checkpointer_spec: str | None = None,
) -> dict[str, str] | None:
    latest_checkpoint_state = getattr(runtime_state_store, "latest_checkpoint_state", None)
    if not callable(latest_checkpoint_state):
        return None
    kwargs: dict[str, Any] = {"run_id": run_id}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if checkpointer_spec is not None:
        kwargs["checkpointer_spec"] = checkpointer_spec
    try:
        checkpoint_state = latest_checkpoint_state(**kwargs)
    except AttributeError:
        return None
    if not isinstance(checkpoint_state, dict):
        return None
    checkpoint_id = checkpoint_state.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        return None
    checkpoint_ns = checkpoint_state.get("checkpoint_ns", "")
    return {
        "checkpoint_id": checkpoint_id,
        "checkpoint_ns": checkpoint_ns if isinstance(checkpoint_ns, str) else "",
    }


def _adapter_error(exc: Exception, default_error_code: str) -> StudioAdapterError:
    if isinstance(exc, StudioAdapterError):
        return exc
    error_code = getattr(exc, "error_code", default_error_code)
    payload = _safe_adapter_error_payload(exc)
    return StudioAdapterError(str(error_code), payload)


def _safe_adapter_error_payload(exc: Exception) -> dict[str, Any]:
    error_payload = getattr(exc, "error_payload", None)
    if isinstance(error_payload, dict):
        return _sanitize_adapter_payload(error_payload)

    payload: dict[str, Any] = {"detail": _safe_provider_error_message(exc)}
    details = _safe_provider_error_details(getattr(exc, "details", {}))
    if details:
        payload["details"] = details
    retryable = getattr(exc, "retryable", None)
    if isinstance(retryable, bool):
        payload["retryable"] = retryable
    return payload


def _sanitize_adapter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        key_text = str(key)
        if _contains_sensitive_error_text(key_text):
            sanitized[key_text] = "[redacted]"
        else:
            sanitized[key_text] = _sanitize_adapter_payload_value(value)
    return sanitized


def _sanitize_adapter_payload_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_adapter_payload(value)
    if isinstance(value, list):
        return [_sanitize_adapter_payload_value(item) for item in value]
    if isinstance(value, str) and _contains_sensitive_error_text(value):
        return "[redacted]"
    return value


def _attach_suppressed_adapter_error(primary: StudioAdapterError, suppressed: StudioAdapterError) -> None:
    payload = dict(primary.error_payload)
    suppressed_errors = list(payload.get("suppressed_errors") or [])
    suppressed_errors.append(
        {
            "error_code": suppressed.error_code,
            "error_payload": suppressed.error_payload,
        }
    )
    payload["suppressed_errors"] = suppressed_errors
    primary.error_payload = payload
    primary.args = (f"StudioAdapterError: {primary.error_code} - {primary.error_payload}",)
    primary.__cause__ = suppressed


def _tokens_metrics_payload(raw_metrics: Any) -> dict[str, Any] | None:
    if not isinstance(raw_metrics, dict):
        return None
    input_tokens = int(raw_metrics.get("total_input_tokens", raw_metrics.get("input_tokens", 0)) or 0)
    output_tokens = int(raw_metrics.get("total_output_tokens", raw_metrics.get("output_tokens", 0)) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(raw_metrics.get("total_tokens", input_tokens + output_tokens) or 0),
        "cost_estimate": raw_metrics.get("cost_estimate"),
    }


def _zip_directory(dir_path: Path) -> bytes:
    # codeql[py/path-injection] Studio callers pass a resolved skill root; archive entries are made relative to it.
    source_root = dir_path.resolve(strict=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # codeql[py/path-injection] The directory is resolved above and archived without following user path segments.
        for file in source_root.rglob("*"):
            if file.is_file():
                rel_path = file.relative_to(source_root)
                if ".workspace" in rel_path.parts or any(part.startswith(".") for part in rel_path.parts):
                    continue
                zf.write(file, rel_path)
    return buf.getvalue()


def _unzip_directory(zip_bytes: bytes, target_dir: Path) -> None:
    target_root = target_dir.resolve(strict=False)
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            raw_name = info.filename
            member_path = PurePosixPath(raw_name)
            if (
                not raw_name
                or "\\" in raw_name
                or member_path.is_absolute()
                or any(part in {"", ".", ".."} for part in member_path.parts)
            ):
                raise ValueError(f"Unsafe zip member: {raw_name}")
            destination = target_root.joinpath(*member_path.parts).resolve(strict=False)
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise ValueError(f"Unsafe zip member: {raw_name}") from exc
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def _studio_storage_root() -> Path:
    from app.core import config

    settings_obj = getattr(config, "settings", None)
    storage_root = getattr(settings_obj, "storage_root", None)
    if storage_root is not None:
        return Path(storage_root)
    return config.WORKSPACES_DIR / "default"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _bytes_result_payload(result: Any, run_artifact_store: Any) -> dict[str, Any] | None:
    result_ref = getattr(result, "result_ref", None)
    if not isinstance(result_ref, str) or not result_ref.startswith("bytes://"):
        return None

    hash_value = result_ref.removeprefix("bytes://")
    if not hash_value:
        return None

    stored = run_artifact_store.get_object(hash=hash_value)
    content = stored.content if hasattr(stored, "content") else stored
    if not isinstance(content, bytes):
        return None

    loaded = json.loads(content.decode("utf-8"))
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _reject_file_result_ref(result: Any) -> None:
    result_ref = getattr(result, "result_ref", None)
    if isinstance(result_ref, str) and result_ref.startswith("file://"):
        raise StudioAdapterError(
            "artifact.unsupported_result_ref",
            {
                "result_ref": result_ref,
                "detail": "D2.2 run/predict results must be read from RunArtifactStore bytes refs",
            },
        )


def _file_uri_to_path(ref: str) -> Path:
    parsed = urlparse(ref)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file URI ref, got: {ref}")
    return Path(unquote(parsed.path))


class EngineAdapter:
    def __init__(
        self,
        transport: Literal["in_process", "http_loopback"],
        http_transport: HttpTransport | None = None,
    ):
        if transport not in ("in_process", "http_loopback"):
            raise ValueError(f"Unknown transport: {transport}")
        self.transport = transport
        self.http_transport = http_transport

    def compile(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            return self.http_transport.post("/engine/compile", payload)

        # in_process mode
        skill_dir = payload["skill_dir"]
        skill_id = payload["skill_id"]
        store_type = payload.get("artifact_scope", "ephemeral")

        resolver = self._build_studio_skill_resolver()
        try:
            from graph_agent.core.artifacts import (
                ArtifactRef as CoreArtifactRef,
            )
            from graph_agent.core.artifacts import (
                build_compiled_artifact_manifest,
                compile_artifact,
            )

            compiled_manifest = compile_artifact(
                source_root=Path(skill_dir),
                skill_resolver=resolver,
                store="product" if store_type == "product" else "ephemeral",
                version=payload.get("version") if isinstance(payload.get("version"), str) else None,
            )
        except Exception as exc:
            raise StudioAdapterError("engine.compile_failed", {"detail": str(exc)}) from exc

        zip_bytes = _zip_directory(Path(skill_dir))

        from app.core.adapters.product_store_local import LocalProductArtifactStore

        storage_root = _studio_storage_root()
        product_store = LocalProductArtifactStore(root=storage_root)
        artifact_ref = product_store.put(zip_bytes, artifact_id=skill_id, store=store_type)
        core_artifact_ref = CoreArtifactRef(
            artifact_id=artifact_ref.artifact_id,
            content_hash=artifact_ref.content_hash,
            store="product" if artifact_ref.store == "product" else "ephemeral",
            version=payload.get("version") if isinstance(payload.get("version"), str) else None,
            manifest_ref=compiled_manifest.artifact_ref.manifest_ref,
            source_map_ref=compiled_manifest.source_map_ref,
        )
        manifest = build_compiled_artifact_manifest(
            compiled=None,
            artifact_ref=core_artifact_ref,
            execution_fingerprint=compiled_manifest.execution_fingerprint,
            diagnostics=compiled_manifest.diagnostics,
        )
        _file_uri_to_path(core_artifact_ref.manifest_ref).write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return {
            "artifact_id": core_artifact_ref.artifact_id,
            "content_hash": core_artifact_ref.content_hash,
            "store": core_artifact_ref.store,
            "version": core_artifact_ref.version,
            "manifest_ref": core_artifact_ref.manifest_ref,
            "source_map_ref": core_artifact_ref.source_map_ref,
            "execution_fingerprint": manifest.execution_fingerprint,
        }

    def run_artifact(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            idem_key = payload.get("idempotency_key")
            return self.http_transport.post("/engine/run_artifact", payload, idempotency_key=idem_key)

        # in_process mode
        artifact_ref_data = payload["artifact_ref"]
        inputs = payload.get("inputs", {})
        execution_context = payload.get("execution_context", {})
        import uuid
        idempotency_key = (
            payload.get("idempotency_key")
            or payload.get("thread_id")
            or payload.get("run_id")
            or f"idem-{uuid.uuid4()}"
        )

        if "workspace_dir" in payload and "workspace_dir" not in execution_context:
            execution_context["workspace_dir"] = payload["workspace_dir"]
        if "thread_id" in payload and "thread_id" not in execution_context:
            execution_context["thread_id"] = payload["thread_id"]
        if "run_id" in payload and "run_id" not in execution_context and "thread_id" not in execution_context:
            execution_context["run_id"] = payload["run_id"]
        if "event_subscriber" in payload and "event_subscriber" not in execution_context:
            execution_context["event_subscriber"] = payload["event_subscriber"]
        artifact_root = self._ensure_local_artifact_root(
            artifact_ref_data,
            allow_dev_refresh=bool(payload.get("dev_mode", True)),
        )
        if artifact_root is not None and "artifact_root" not in execution_context:
            execution_context["artifact_root"] = str(artifact_root)
        run_id_for_state = str(execution_context.get("thread_id") or execution_context.get("run_id") or idempotency_key)
        if "thread_id" not in execution_context and "run_id" not in execution_context:
            execution_context["thread_id"] = run_id_for_state
        checkpointer_spec = _runtime_state_checkpointer_spec(execution_context, run_id_for_state)
        if checkpointer_spec is not None and "checkpointer_spec" not in execution_context:
            execution_context["checkpointer_spec"] = checkpointer_spec

        try:
            from graph_agent.core.adapter_contracts import RunArtifactRequest
            from graph_agent.core.artifacts import ArtifactRef

            req = RunArtifactRequest(
                artifact_ref=ArtifactRef(
                    artifact_id=artifact_ref_data["artifact_id"],
                    content_hash=artifact_ref_data["content_hash"],
                    store=artifact_ref_data["store"],
                    manifest_ref=artifact_ref_data.get("manifest_ref") or "",
                    source_map_ref=artifact_ref_data.get("source_map_ref") or "",
                    version=artifact_ref_data.get("version"),
                ),
                inputs=inputs,
                execution_context=execution_context,
                idempotency_key=idempotency_key,
            )

            from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

            run_artifact_store = LocalRunArtifactStore(root=_studio_storage_root())
            result = run_artifact(
                req,
                skill_resolver=self._build_studio_skill_resolver(),
                llm_provider=self._build_engine_llm_provider(),
                run_artifact_store=run_artifact_store,
            )
            run_payload = _bytes_result_payload(result, run_artifact_store)
            if run_payload is not None:
                self._snapshot_runtime_state_after_run(
                    run_id=run_id_for_state,
                    run_payload=run_payload,
                    artifact_ref_data=artifact_ref_data,
                    result_ref=getattr(result, "result_ref", None),
                    checkpointer_spec=checkpointer_spec,
                )
                return run_payload
            _reject_file_result_ref(result)
            return _jsonable(result)
        except Exception as exc:
            error_code = getattr(exc, "error_code", "engine.run_failed")
            error_payload = _safe_adapter_error_payload(exc)
            raise StudioAdapterError(error_code, error_payload) from exc

    def predict_artifact(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            idem_key = payload.get("idempotency_key")
            return self.http_transport.post("/engine/predict_artifact", payload, idempotency_key=idem_key)

        # in_process mode
        artifact_ref_data = payload["artifact_ref"]
        inputs = payload.get("inputs", {})
        execution_context = payload.get("execution_context", {})
        import uuid
        idempotency_key = (
            payload.get("idempotency_key")
            or payload.get("thread_id")
            or payload.get("run_id")
            or f"idem-{uuid.uuid4()}"
        )

        if "workspace_dir" in payload and "workspace_dir" not in execution_context:
            execution_context["workspace_dir"] = payload["workspace_dir"]
        if "thread_id" in payload and "thread_id" not in execution_context:
            execution_context["thread_id"] = payload["thread_id"]
        if "mock_llm" in payload and "mock_llm" not in execution_context:
            execution_context["mock_llm"] = payload["mock_llm"]
        if "current_hashes" in payload and "current_hashes" not in execution_context:
            execution_context["current_hashes"] = payload["current_hashes"]
        artifact_root = self._ensure_local_artifact_root(
            artifact_ref_data,
            allow_dev_refresh=bool(payload.get("dev_mode", True)),
        )
        if artifact_root is not None and "artifact_root" not in execution_context:
            execution_context["artifact_root"] = str(artifact_root)

        try:
            from graph_agent.core.adapter_contracts import PredictArtifactRequest
            from graph_agent.core.artifacts import ArtifactRef

            req = PredictArtifactRequest(
                artifact_ref=ArtifactRef(
                    artifact_id=artifact_ref_data["artifact_id"],
                    content_hash=artifact_ref_data["content_hash"],
                    store=artifact_ref_data["store"],
                    manifest_ref=artifact_ref_data.get("manifest_ref") or "",
                    source_map_ref=artifact_ref_data.get("source_map_ref") or "",
                    version=artifact_ref_data.get("version"),
                ),
                inputs=inputs,
                execution_context=execution_context,
                idempotency_key=idempotency_key,
            )

            from graph_agent.core.runner import PredictDeadlockError as SDKPredictDeadlockError

            try:
                from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

                run_artifact_store = LocalRunArtifactStore(root=_studio_storage_root())
                result = predict_artifact(
                    req,
                    skill_resolver=self._build_studio_skill_resolver(),
                    llm_provider=None,
                    run_artifact_store=run_artifact_store,
                )
                payload = _bytes_result_payload(result, run_artifact_store)
                if payload is not None:
                    return payload
                _reject_file_result_ref(result)
                return _jsonable(result)
            except SDKPredictDeadlockError as exc:
                raise StudioAdapterError(
                    "engine.predict_deadlock", {"phase_name": exc.phase_name, "actual_path": exc.actual_path}
                ) from exc
        except Exception as exc:
            if isinstance(exc, StudioAdapterError):
                raise exc
            error_code = getattr(exc, "error_code", "engine.predict_failed")
            error_payload = _safe_adapter_error_payload(exc)
            raise StudioAdapterError(error_code, error_payload) from exc

    def resume(self, payload: dict[str, Any]) -> Any:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            idem_key = payload.get("idempotency_key")
            return self.http_transport.post("/engine/resume", payload, idempotency_key=idem_key)

        # in_process mode
        skill_id = payload["skill_id"]
        run_id = payload["run_id"]
        context_overrides = payload.get("context_overrides")
        human_input = payload.get("human_input")
        payload_human_response = payload.get("human_response")

        runtime_state_store = self._build_runtime_state_store()
        lease = None
        primary_error: StudioAdapterError | None = None
        try:
            owner_id = f"engine.resume:{run_id}:{uuid.uuid4()}"
            lease = runtime_state_store.acquire_lease(
                run_id=run_id,
                owner_id=owner_id,
                ttl_ms=30_000,
            )
            restored_snapshot = runtime_state_store.restore(run_id=run_id)
            restored_state = dict(getattr(restored_snapshot, "state", {}) or {})
            checkpoint_id = _runtime_state_checkpoint_value(payload, "checkpoint_id")
            if checkpoint_id is None:
                checkpoint_id = _runtime_state_checkpoint_value(restored_state, "checkpoint_id")
            checkpoint_ns = _runtime_state_checkpoint_value(payload, "checkpoint_ns")
            if checkpoint_ns is None:
                checkpoint_ns = _runtime_state_checkpoint_value(restored_state, "checkpoint_ns")
            if checkpoint_id is None:
                raise StudioAdapterError(
                    "state.invalid_checkpoint",
                    {
                        "run_id": run_id,
                        "detail": "Restored runtime state is missing checkpoint_id",
                    },
                )
            checkpointer = runtime_state_store.restore_checkpointer(restored_snapshot)
            artifact_ref_data = _runtime_state_artifact_ref(restored_state, skill_id=skill_id)

            storage_root = _studio_storage_root()
            artifact_root = self._ensure_local_artifact_root(artifact_ref_data, allow_dev_refresh=False)
            if artifact_root is None:
                raise StudioAdapterError(
                    "artifact.not_found",
                    {
                        "artifact_id": artifact_ref_data["artifact_id"],
                        "content_hash": artifact_ref_data["content_hash"],
                        "detail": "Runtime state artifact bytes are not materialized",
                    },
                )

            human_response = None
            if isinstance(payload_human_response, dict):
                human_response = dict(payload_human_response)
            elif human_input is not None:
                human_response = {"content": human_input}

            workspace_dir = _runtime_state_workspace_dir(
                restored_state,
                artifact_id=str(artifact_ref_data["artifact_id"]),
                storage_root=storage_root,
            )

            runtime_state_store.heartbeat(run_id=run_id, lease=lease)

            from app.core.adapters.runtime_state_resume_bridge import resume_restored_runtime_state

            res = resume_restored_runtime_state(
                artifact_root,
                workspace_dir=workspace_dir,
                run_id=run_id,
                checkpoint_id=checkpoint_id,
                checkpoint_ns=checkpoint_ns,
                checkpointer=checkpointer,
                context_overrides=context_overrides,
                human_response=human_response,
                skill_resolver=self._build_studio_skill_resolver(),
                llm_provider=self._build_engine_llm_provider(),
            )
            from datetime import UTC, datetime

            raw_metrics = _jsonable(res.metrics)
            snapshot_metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
            result = {
                "run_id": run_id,
                "status": "success" if res.success else "failed",
                "started_at": (res.started_at or datetime.now(UTC)).isoformat(),
                "input_summary": "resumed",
                "metrics": _tokens_metrics_payload(snapshot_metrics),
            }
            next_state = dict(restored_state)
            next_state.update(
                {
                    "status": result["status"],
                    "metrics": snapshot_metrics,
                    "input_summary": result["input_summary"],
                }
            )
            latest_checkpoint_state = _runtime_state_latest_checkpoint_state(
                runtime_state_store,
                run_id=run_id,
                checkpointer=checkpointer,
            )
            if latest_checkpoint_state is not None:
                next_state.update(latest_checkpoint_state)
            runtime_state_store.snapshot(
                run_id=run_id,
                state=next_state,
                lease=lease,
            )
            return result
        except Exception as exc:
            primary_error = _adapter_error(exc, "engine.resume_failed")
            if primary_error is exc:
                raise
            raise primary_error from exc
        finally:
            if lease is not None:
                try:
                    runtime_state_store.release(run_id=run_id, lease=lease)
                except Exception as release_exc:
                    release_error = _adapter_error(release_exc, "state.release_failed")
                    if primary_error is not None:
                        _attach_suppressed_adapter_error(primary_error, release_error)
                    else:
                        raise release_error from release_exc

    def get_fallback_trace(self, skill_dir: str) -> list[dict[str, Any]]:
        loader = SkillLoader()
        compiled = loader.compile_skill(
            Path(skill_dir),
            skill_resolver=self._build_studio_skill_resolver(),
        )
        mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
        return [
            {
                "phase_name": phase_name,
                "type": "llm" if mode_by_phase.get(phase_name) == "agent" else "logic",
                "inputs": {},
                "outputs": {},
            }
            for phase_name in compiled.manifest.phases
        ]

    def _build_studio_skill_resolver(self) -> Any:
        return _PrivateStudioSkillResolver()

    def _build_gateway_model_resolver(self) -> Any:
        return _private_build_gateway_model_resolver()

    def _build_engine_llm_provider(self) -> Any:
        return _GatewayBackedLLMProvider(_private_build_gateway_model_resolver())

    def _build_runtime_state_store(self) -> Any:
        from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore

        return LocalRuntimeStateStore(root=_studio_storage_root())

    def _snapshot_runtime_state_after_run(
        self,
        *,
        run_id: str,
        run_payload: dict[str, Any],
        artifact_ref_data: dict[str, Any],
        result_ref: str | None,
        checkpointer_spec: str | None,
    ) -> None:
        if checkpointer_spec is None:
            return
        runtime_state_store = self._build_runtime_state_store()
        checkpoint_state = _runtime_state_latest_checkpoint_state(
            runtime_state_store,
            run_id=run_id,
            checkpointer_spec=checkpointer_spec,
        )
        if checkpoint_state is None:
            return

        lease = runtime_state_store.acquire_lease(
            run_id=run_id,
            owner_id=f"engine.run_artifact:{run_id}:{uuid.uuid4()}",
            ttl_ms=30_000,
        )
        try:
            state = {
                "schema_version": "studio.runtime_state.v1",
                "run_id": run_id,
                "artifact_ref": _jsonable(artifact_ref_data),
                "checkpointer_spec": checkpointer_spec,
                "checkpoint_id": checkpoint_state["checkpoint_id"],
                "checkpoint_ns": checkpoint_state["checkpoint_ns"],
                "result_ref": result_ref,
                "status": run_payload.get("status") or ("success" if run_payload.get("success") else "failed"),
                "metrics": run_payload.get("metrics") if isinstance(run_payload.get("metrics"), dict) else {},
            }
            runtime_state_store.snapshot(run_id=run_id, state=state, lease=lease)
        finally:
            runtime_state_store.release(run_id=run_id, lease=lease)

    def _ensure_local_artifact_root(
        self,
        artifact_ref_data: dict[str, Any],
        *,
        allow_dev_refresh: bool = True,
    ) -> Path | None:
        content_hash = artifact_ref_data.get("content_hash")
        if not isinstance(content_hash, str):
            return None
        sha256_val = _sha256_hex_from_content_hash(content_hash)
        if sha256_val is None:
            return None

        from app.core.adapters.product_store_local import LocalProductArtifactStore

        storage_root = _studio_storage_root()
        ephemeral_dir = _safe_child_path(storage_root / "ephemeral_run_skills", sha256_val)
        if (ephemeral_dir / "GRAPH.md").is_file():
            return ephemeral_dir

        product_store = LocalProductArtifactStore(root=storage_root)
        try:
            zip_bytes = product_store.get(content_hash)
        except StudioAdapterError as exc:
            if exc.error_code != "artifact.not_found":
                raise exc
            if artifact_ref_data.get("store") == "product" or not allow_dev_refresh:
                raise StudioAdapterError(
                    "artifact.not_found",
                    _missing_artifact_payload(artifact_ref_data),
                ) from exc
            try:
                from app.services.run_artifact_flow import compile_ephemeral_for_dev_missing_hash

                refreshed = compile_ephemeral_for_dev_missing_hash(str(artifact_ref_data.get("artifact_id", "")))
                artifact_ref_data.update(
                    {
                        "artifact_id": refreshed.artifact_id,
                        "content_hash": refreshed.content_hash,
                        "store": refreshed.store,
                        "manifest_ref": refreshed.manifest_ref,
                        "source_map_ref": refreshed.source_map_ref,
                    }
                )
                refreshed_hash = _sha256_hex_from_content_hash(refreshed.content_hash)
                if refreshed_hash is None:
                    return None
                ephemeral_dir = _safe_child_path(storage_root / "ephemeral_run_skills", refreshed_hash)
                zip_bytes = product_store.get(refreshed.content_hash)
            except StudioAdapterError:
                raise
            except Exception as refresh_exc:
                raise StudioAdapterError(
                    "artifact.dev_rebuild_failed",
                    {
                        "artifact_id": artifact_ref_data.get("artifact_id"),
                        "content_hash": content_hash,
                        "detail": str(refresh_exc),
                    },
                ) from refresh_exc
        _unzip_directory(zip_bytes, ephemeral_dir)
        return ephemeral_dir if (ephemeral_dir / "GRAPH.md").is_file() else None


def _missing_artifact_payload(artifact_ref_data: dict[str, Any]) -> dict[str, Any]:
    version = artifact_ref_data.get("release_version") or artifact_ref_data.get("version")
    return {
        "artifact_id": artifact_ref_data.get("artifact_id"),
        "content_hash": artifact_ref_data.get("content_hash"),
        "store": artifact_ref_data.get("store"),
        "version": version,
        "release_version": version,
        "detail": (
            "Product artifact bytes are missing"
            if artifact_ref_data.get("store") == "product"
            else "Artifact bytes are missing"
        ),
    }
