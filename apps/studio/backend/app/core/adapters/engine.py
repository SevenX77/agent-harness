from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

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
from graph_agent.core._predict_internal.stub import generate_heuristic_stub as generate_heuristic_stub
from graph_agent.core.event_contracts import DeltaEnvelope as DeltaEnvelope
from graph_agent.core.event_contracts import EventEnvelope as EventEnvelope
from graph_agent.core.event_contracts import StreamCursorExpiredError as StreamCursorExpiredError
from graph_agent.core.event_contracts import StreamCursorGapError as StreamCursorGapError
from graph_agent.core.event_contracts import TransportErrorPayload as TransportErrorPayload
from graph_agent.core.event_contracts import make_event_envelope as make_event_envelope
from graph_agent.core.exceptions import make_error_payload as make_error_payload
from graph_agent.core.graph_serializer import (
    GraphTopologySerializationError as GraphTopologySerializationError,
)
from graph_agent.core.graph_serializer import serialize_graph as serialize_graph
from graph_agent.core.graph_serializer import (
    serialize_graph_topology as serialize_graph_topology,
)
from graph_agent.core.graph_serializer import (
    serialize_graph_topology_from_markdown as serialize_graph_topology_from_markdown,
)
from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderError, LLMProviderRequest
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
from graph_agent.core.manifest import (
    effective_llm_role as effective_llm_role,
)
from graph_agent.core.parser import parse_markdown_parts as parse_markdown_parts
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
from graph_agent.core.topology_projection import (
    ChildGraphTopologyProjection as ChildGraphTopologyProjection,
)
from graph_agent.core.topology_projection import GraphTopologyProjection as GraphTopologyProjection
from graph_agent.core.topology_projection import (
    SubgraphTopologyProjectionError as SubgraphTopologyProjectionError,
)
from graph_agent.core.topology_projection import (
    load_child_graph_topology_projection as load_child_graph_topology_projection,
)
from graph_agent.core.topology_projection import (
    load_graph_topology_projection as load_graph_topology_projection,
)
from graph_agent.core.topology_projection import phase_mode_for as phase_mode_for
from graph_agent.core.topology_projection import read_subgraph_path as read_subgraph_path
from graph_agent_gateway import answer_restarts_here

from app.core.adapters.http_transport import HttpTransport, StudioAdapterError

logger = logging.getLogger(__name__)

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


def _runtime_input_fields_for_engine(
    runtime_config: dict[str, Any] | None,
) -> dict[str, set[str]] | None:
    if not isinstance(runtime_config, dict):
        return None
    inputs = runtime_config.get("inputs")
    active = inputs.get("active") if isinstance(inputs, dict) else None
    phases = active.get("phases") if isinstance(active, dict) else None
    if not isinstance(phases, dict):
        return None
    result: dict[str, set[str]] = {}
    for phase_id, bindings in phases.items():
        if not isinstance(phase_id, str) or not isinstance(bindings, dict):
            continue
        fields = {
            field for field, binding in bindings.items() if isinstance(field, str) and isinstance(binding, dict)
        }
        if fields:
            result[phase_id] = fields
    return result or None


def _runtime_config_fingerprint(runtime_config: dict[str, Any] | None) -> str | None:
    if not isinstance(runtime_config, dict):
        return None
    existing = runtime_config.get("fingerprint")
    if isinstance(existing, str) and existing:
        return existing
    stable = {
        key: value for key, value in runtime_config.items() if key not in {"updated_at", "fingerprint", "golden", "ui"}
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


class _PrivateStudioSkillResolver:
    """Resolve Studio skill ids through the opened-skill absolute path index."""

    def resolve_skill(self, skill_id: str) -> Path:
        from graph_agent import ResourceNotFoundError

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


def _load_resolver_credentials(cred_path: Path) -> Any:
    """Load resolver credentials, upgrading v4->v5 through the shared loader. A
    missing file is first-run empty; a malformed/corrupt file stays FATAL (matching
    ``load_credentials``) — we do NOT swallow a broken file into empty config (P2)."""
    from app.services.llm_credentials import load_credentials

    return load_credentials(cred_path)


def _private_build_gateway_model_resolver() -> Any:

    from app.core import config
    from app.core.adapters.gateway import ModelResolver
    from app.models.llm_config import RolesData

    cred_path_env = os.environ.get("STUDIO_LLM_CREDENTIALS_PATH")
    cred_path = (
        Path(cred_path_env).expanduser() if cred_path_env else config.APP_SETTINGS_DIR / "llm" / "llm_credentials.json"
    )
    cred_data = _load_resolver_credentials(cred_path)

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

    from graph_agent_gateway.storage_contracts import InMemoryConfigTruthStore

    from app.core.adapters.gateway import _filter_gateway_credentials, _filter_gateway_roles, _put_config_if_absent
    from app.services.llm_credentials import _credentials_payload_for_storage

    # 底座一: read the single on-disk config truth fresh into a throwaway in-memory
    # store; no persistent gateway snapshot to go stale (matches gateway_resolver +
    # GatewayAdapter.resolve_routes).
    config_store = InMemoryConfigTruthStore()
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


def _node_param_overrides(phase_name: str | None) -> dict[str, Any]:
    """Per-node LLM param overrides for ``phase_name`` (PR3), or empty.

    Read from the run-scoped ``STUDIO_RUNTIME_CONFIG_PATH`` file (set by the run
    worker to the skill's ``.workspace/runtime_config.json``). A node's override
    of thinking / max_output_tokens / temperature is passed straight to the
    gateway resolver, where it wins over the role default. Keeps node overrides a
    studio-side concern — the engine and the gateway resolver stay skill-agnostic.
    """
    if not phase_name:
        return {}
    path_str = os.environ.get("STUDIO_RUNTIME_CONFIG_PATH")
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    llm = loaded.get("llm") if isinstance(loaded, dict) else None
    node_params = llm.get("node_params") if isinstance(llm, dict) else None
    nodes = node_params.get("nodes") if isinstance(node_params, dict) else None
    node = nodes.get(phase_name) if isinstance(nodes, dict) else None
    if not isinstance(node, dict):
        return {}
    if node.get("enabled") is not True:
        return {}
    overrides: dict[str, Any] = {}
    for key in ("thinking", "max_output_tokens", "temperature"):
        value = node.get(key)
        if value is not None:
            overrides[key] = value
    return overrides


class _GatewayBackedLLMProvider:
    def __init__(self, resolver: Any) -> None:
        self._resolver = resolver

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        """Pass the gateway model's own stream through, slice by slice.

        The closing slice carries no text and all of the metadata: tool calls,
        usage and the model that answered are only complete once the accumulated
        message is, and LangChain's own chunk addition is what completes them —
        re-deriving them from the slices here would be a second, worse
        implementation of merging the provider already defined.
        """
        metadata = dict(request.metadata)
        try:
            model = self._bound_model(request, metadata)
            accumulated: Any = None
            for chunk in model.stream(request.messages, stop=metadata.get("stop")):
                if answer_restarts_here(chunk):
                    # The gateway went back for a different answer — a bigger
                    # budget, or another route. Accumulating across that would
                    # hand the engine one message stitched from two attempts,
                    # so the accumulation starts over and the engine is told to
                    # do the same with what it has.
                    accumulated = None
                    yield LLMProviderChunk(restarts_answer=True)
                    continue
                accumulated = chunk if accumulated is None else accumulated + chunk
                reasoning = _reasoning_of(chunk)
                if chunk.content or reasoning:
                    yield LLMProviderChunk(content=chunk.content, reasoning=reasoning)
            yield LLMProviderChunk(content="", metadata=_answer_metadata(accumulated, model))
        except Exception as exc:
            details = _safe_provider_error_details(getattr(exc, "details", {}))
            details.setdefault("exception_type", type(exc).__name__)
            raise LLMProviderError(
                error_code=str(getattr(exc, "error_code", "llm.provider_invoke_failed")),
                message=_safe_provider_error_message(exc),
                retryable=bool(getattr(exc, "retryable", False)),
                details=details,
            ) from None

    def _bound_model(self, request: LLMProviderRequest, metadata: dict[str, Any]) -> Any:
        phase_name = metadata.get("phase_name")
        overrides = _node_param_overrides(phase_name)
        model = self._resolver.resolve(
            request.role,
            model_override=metadata.get("model_override"),
            callbacks=tuple(metadata.get("callbacks") or ()),
            phase_name=phase_name,
            thinking_enabled=overrides.get("thinking"),
            max_output_tokens=overrides.get("max_output_tokens"),
            temperature=overrides.get("temperature"),
        )
        tools = metadata.get("bound_tools") or []
        if tools and hasattr(model, "bind_tools"):
            model = model.bind_tools(
                tools,
                tool_choice=metadata.get("tool_choice"),
                **dict(metadata.get("tool_kwargs") or {}),
            )
        return model


def _reasoning_of(chunk: Any) -> str:
    """What the model said while working out the answer, on this slice.

    An openai-compatible provider reports it in its own key next to an empty
    ``content``, which is the provider saying it is not part of the reply. Only
    that shape is read here: a provider that puts its reasoning in the content
    as typed blocks has already made it part of the content, and picking those
    blocks apart would mean this adapter deciding which of a provider's own
    content blocks count as the answer.
    """
    reasoning = (getattr(chunk, "additional_kwargs", None) or {}).get("reasoning_content")
    return reasoning if isinstance(reasoning, str) else ""


def _answer_metadata(accumulated: Any, model: Any) -> dict[str, Any]:
    """Everything about the answer that is not its text."""
    if accumulated is None:
        return {}
    metadata = dict(getattr(accumulated, "response_metadata", None) or {})
    tool_calls = list(getattr(accumulated, "tool_calls", None) or [])
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    usage_metadata = getattr(accumulated, "usage_metadata", None)
    if usage_metadata is not None:
        metadata["usage_metadata"] = usage_metadata
    model_name = (
        getattr(model, "model_name", None)
        or getattr(model, "model", None)
        or getattr(model, "name", None)
    )
    if model_name is not None:
        metadata.setdefault("model_name", str(model_name))
    return metadata


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
    return f"sqlite:{(Path(workspace_dir) / 'runs' / run_id / 'checkpoints.db').as_posix()}"


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


def _artifact_identity_value(artifact_ref: Any, key: str) -> str | None:
    if not isinstance(artifact_ref, dict):
        return None
    value = artifact_ref.get(key)
    return value if isinstance(value, str) and value else None


def _resume_validity_payload(
    *,
    run_id: str,
    resume_allowed: bool,
    reason: str,
    checkpoint_id: str | None,
    checkpoint_ns: str | None,
    resume_from_node_id: str | None,
    resume_to_node_id: str | None,
    dirty_fields: list[str] | None = None,
    dirty_node_ids: list[str] | None = None,
    affected_downstream: list[str] | None = None,
    snapshot_content_hash: str | None = None,
    current_content_hash: str | None = None,
    snapshot_execution_fingerprint: str | None = None,
    current_execution_fingerprint: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "resume_allowed": resume_allowed,
        "reason": reason,
        "checkpoint_id": checkpoint_id,
        "checkpoint_ns": checkpoint_ns,
        "resume_from_node_id": resume_from_node_id,
        "resume_to_node_id": resume_to_node_id,
        "dirty_fields": dirty_fields or [],
        "dirty_node_ids": dirty_node_ids or [],
        "affected_downstream": affected_downstream or [],
        "snapshot_content_hash": snapshot_content_hash,
        "current_content_hash": current_content_hash,
        "snapshot_execution_fingerprint": snapshot_execution_fingerprint,
        "current_execution_fingerprint": current_execution_fingerprint,
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
        # ⑧a: carry the engine's wall_time_sec through the adapter wire so the resume DTO can surface 耗时.
        "wall_time_sec": raw_metrics.get("wall_time_sec"),
    }


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
    raw_path = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
    return Path(url2pathname(unquote(raw_path)))


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
        runtime_config = payload.get("runtime_config")
        if not isinstance(runtime_config, dict):
            runtime_config = None
        storage_root = _studio_storage_root()

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
                artifact_output_root=storage_root / "engine_artifacts",
                runtime_input_fields=_runtime_input_fields_for_engine(runtime_config),
                runtime_config_fingerprint=_runtime_config_fingerprint(runtime_config),
            )
        except Exception as exc:
            raise StudioAdapterError("engine.compile_failed", {"detail": str(exc)}) from exc

        artifact_bytes = getattr(compiled_manifest, "artifact_bytes", None)
        if not isinstance(artifact_bytes, bytes):
            raise StudioAdapterError(
                "engine.compile_failed",
                {"detail": "compiled artifact bytes are required for product artifact storage"},
            )

        from app.core.adapters.product_store_local import LocalProductArtifactStore

        product_store = LocalProductArtifactStore(root=storage_root)
        artifact_ref = product_store.put(artifact_bytes, artifact_id=skill_id, store=store_type)
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
        manifest_path = _file_uri_to_path(core_artifact_ref.manifest_ref)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
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
        _attach_dev_rebuild_audit(execution_context, artifact_ref_data)
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
        if "event_subscriber" in payload and "event_subscriber" not in execution_context:
            execution_context["event_subscriber"] = payload["event_subscriber"]
        artifact_root = self._ensure_local_artifact_root(
            artifact_ref_data,
            allow_dev_refresh=bool(payload.get("dev_mode", True)),
        )
        _attach_dev_rebuild_audit(execution_context, artifact_ref_data)
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
                run_payload = _bytes_result_payload(result, run_artifact_store)
                if run_payload is not None:
                    return run_payload
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
            resume_from_node_id = _runtime_state_checkpoint_value(payload, "resume_from_node_id")
            resume_to_node_id = _runtime_state_checkpoint_value(payload, "resume_to_node_id")
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
                resume_from_node_id=resume_from_node_id,
                resume_to_node_id=resume_to_node_id,
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

    def resume_validity(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.transport == "http_loopback":
            if not self.http_transport:
                raise ValueError("http_transport is required for http_loopback")
            result = self.http_transport.post("/engine/resume_validity", payload)
            if not isinstance(result, dict):
                raise StudioAdapterError(
                    "transport.serialization_failed",
                    {"detail": "resume_validity response data is not a dict"},
                )
            return result

        skill_id = payload["skill_id"]
        run_id = payload["run_id"]
        checkpoint_id = _runtime_state_checkpoint_value(payload, "checkpoint_id")
        checkpoint_ns = _runtime_state_checkpoint_value(payload, "checkpoint_ns")
        resume_from_node_id = _runtime_state_checkpoint_value(payload, "resume_from_node_id")
        resume_to_node_id = _runtime_state_checkpoint_value(payload, "resume_to_node_id")

        runtime_state_store = self._build_runtime_state_store()
        try:
            restored_snapshot = runtime_state_store.restore(run_id=run_id)
        except StudioAdapterError as exc:
            if exc.error_code == "state.not_found":
                return _resume_validity_payload(
                    run_id=run_id,
                    resume_allowed=False,
                    reason="state.not_found",
                    checkpoint_id=checkpoint_id,
                    checkpoint_ns=checkpoint_ns,
                    resume_from_node_id=resume_from_node_id,
                    resume_to_node_id=resume_to_node_id,
                )
            raise
        restored_state = dict(getattr(restored_snapshot, "state", {}) or {})
        if checkpoint_id is None:
            checkpoint_id = _runtime_state_checkpoint_value(restored_state, "checkpoint_id")
        if checkpoint_ns is None:
            checkpoint_ns = _runtime_state_checkpoint_value(restored_state, "checkpoint_ns")

        snapshot_artifact_ref = restored_state.get("artifact_ref")
        snapshot_content_hash = _artifact_identity_value(snapshot_artifact_ref, "content_hash")
        snapshot_execution_fingerprint = _artifact_identity_value(
            snapshot_artifact_ref,
            "execution_fingerprint",
        ) or _artifact_identity_value(restored_state, "execution_fingerprint")

        if checkpoint_id is None:
            return _resume_validity_payload(
                run_id=run_id,
                resume_allowed=False,
                reason="checkpoint.not_found",
                checkpoint_id=None,
                checkpoint_ns=checkpoint_ns,
                resume_from_node_id=resume_from_node_id,
                resume_to_node_id=resume_to_node_id,
                snapshot_content_hash=snapshot_content_hash,
                snapshot_execution_fingerprint=snapshot_execution_fingerprint,
            )
        if not isinstance(snapshot_artifact_ref, dict):
            return _resume_validity_payload(
                run_id=run_id,
                resume_allowed=False,
                reason="artifact.invalid_ref",
                checkpoint_id=checkpoint_id,
                checkpoint_ns=checkpoint_ns,
                resume_from_node_id=resume_from_node_id,
                resume_to_node_id=resume_to_node_id,
            )
        if snapshot_artifact_ref.get("artifact_id") != skill_id:
            return _resume_validity_payload(
                run_id=run_id,
                resume_allowed=False,
                reason="artifact.identity_mismatch",
                checkpoint_id=checkpoint_id,
                checkpoint_ns=checkpoint_ns,
                resume_from_node_id=resume_from_node_id,
                resume_to_node_id=resume_to_node_id,
                snapshot_content_hash=snapshot_content_hash,
                snapshot_execution_fingerprint=snapshot_execution_fingerprint,
            )

        from app.services.skills import resolve_skill_dir

        try:
            current_artifact_ref = self.compile(
                {
                    "skill_id": skill_id,
                    "skill_dir": str(resolve_skill_dir(skill_id)),
                    "artifact_scope": "ephemeral",
                }
            )
        except Exception:
            return _resume_validity_payload(
                run_id=run_id,
                resume_allowed=False,
                reason="compile_failed",
                checkpoint_id=checkpoint_id,
                checkpoint_ns=checkpoint_ns,
                resume_from_node_id=resume_from_node_id,
                resume_to_node_id=resume_to_node_id,
                snapshot_content_hash=snapshot_content_hash,
                snapshot_execution_fingerprint=snapshot_execution_fingerprint,
            )

        current_content_hash = _artifact_identity_value(current_artifact_ref, "content_hash")
        current_execution_fingerprint = _artifact_identity_value(current_artifact_ref, "execution_fingerprint")
        dirty_fields: list[str] = []
        if snapshot_content_hash != current_content_hash:
            dirty_fields.append("content_hash")
        if snapshot_execution_fingerprint != current_execution_fingerprint:
            dirty_fields.append("execution_fingerprint")

        # n5-node#3: when dirty and a resume node is named, slice the dirtiness by
        # the compiled graph's depends_on order so the frontend grays only the
        # downstream phases the resume node can dirty. Side-branches stay clean.
        is_dirty = bool(dirty_fields)
        affected_downstream = self._affected_downstream_for_resume(
            skill_id=skill_id,
            resume_from_node_id=resume_from_node_id,
            is_dirty=is_dirty,
        )

        # n5-node#3 (spec F3): resume_allowed is PER-NODE once a resume node is
        # named -- an unrelated side-branch stays resumable even when the whole
        # skill is dirty. With no node target (global Trace Resume) the gate stays
        # whole-skill: any dirt blocks. resume_allowed_for_node branches explicitly
        # so a per-node predicate never silently flips the global resume.
        from app.services.resume_downstream import resume_allowed_for_node

        resume_allowed = resume_allowed_for_node(
            resume_from_node_id=resume_from_node_id,
            is_dirty=is_dirty,
            affected_downstream=affected_downstream,
        )
        # `affected_downstream is None` means the slice was unavailable (compile
        # failed). The gate already degraded to a conservative block above; the
        # payload's node lists must stay a real list (the FE grays from them), so
        # project the unknown slice as empty -- nothing to gray when unknown.
        slice_for_payload = affected_downstream if affected_downstream is not None else []

        return _resume_validity_payload(
            run_id=run_id,
            resume_allowed=resume_allowed,
            reason="dirty_upstream" if dirty_fields else "ok",
            checkpoint_id=checkpoint_id,
            checkpoint_ns=checkpoint_ns,
            resume_from_node_id=resume_from_node_id,
            resume_to_node_id=resume_to_node_id,
            dirty_fields=dirty_fields,
            dirty_node_ids=slice_for_payload,
            affected_downstream=slice_for_payload,
            snapshot_content_hash=snapshot_content_hash,
            current_content_hash=current_content_hash,
            snapshot_execution_fingerprint=snapshot_execution_fingerprint,
            current_execution_fingerprint=current_execution_fingerprint,
        )

    def _affected_downstream_for_resume(
        self,
        *,
        skill_id: str,
        resume_from_node_id: str | None,
        is_dirty: bool,
    ) -> list[str] | None:
        """Downstream phases a dirty resume node can stale (n5-node#3 slice).

        Returns an empty *list* when the graph is clean or no resume node is named
        (nothing downstream). Returns ``None`` when the slice is UNAVAILABLE -- the
        skill could not be compiled to walk its ``depends_on`` graph. The caller
        must treat ``None`` differently from ``[]``: an empty list means "computed,
        nothing affected" (so a side-branch resume is allowed), while ``None`` means
        "unknown", which degrades resume to the conservative whole-skill gate rather
        than silently allowing. Compiles in-process (same boundary as the dirty
        compare above); never raises.
        """
        if not is_dirty or not resume_from_node_id:
            return []
        from app.services.resume_downstream import affected_downstream_nodes
        from app.services.skills import resolve_skill_dir

        try:
            loader = SkillLoader()
            compiled = loader.compile_skill(
                Path(resolve_skill_dir(skill_id)),
                skill_resolver=self._build_studio_skill_resolver(),
            )
        except Exception as exc:  # noqa: BLE001 -- slice is best-effort, log + degrade
            logger.warning(
                "resume_validity downstream slice unavailable for skill=%s node=%s: %s "
                "-> resume degrades to conservative whole-skill gate",
                skill_id,
                resume_from_node_id,
                exc,
            )
            return None
        return affected_downstream_nodes(compiled, resume_from_node_id)

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

    def get_output_contract(self, skill_dir: str) -> dict[str, Any]:
        """Project what the graph can produce and what it declares as its output.

        The engine owns this because it is a fact about the graph, derived from
        the same compile that validates those schemas — not something a surface
        should work out for itself from the files.
        """
        from graph_agent.core.blackboard_contract import (
            blackboard_fields_at_output,
            undeclared_output_names,
        )

        loader = SkillLoader()
        compiled = loader.compile_skill(
            Path(skill_dir),
            skill_resolver=self._build_studio_skill_resolver(),
        )
        return {
            "fields": [
                {
                    "name": field.name,
                    "type": field.type,
                    "produced_by": field.produced_by,
                    "declared_output": field.declared_output,
                }
                for field in blackboard_fields_at_output(compiled)
            ],
            "declared_but_unproduced": undeclared_output_names(compiled),
        }

    def resolve_agent_node_output_schema(self, skill_dir: str, node_id: str) -> dict[str, Any] | None:
        """Return an agent node's ``io.outputs`` JSON schema for golden-template generation.

        Compiles the skill in-process (same boundary as ``get_fallback_trace``) and
        resolves the named agent node's output schema, mirroring the predict runner's
        per-node schema lookup. Returns ``None`` when the phase is absent or is not an
        agent node (logic nodes never get golden — N4 #33/g-c), so the caller can map
        that to a 422 without leaking SDK types past this port.
        """
        loader = SkillLoader()
        compiled = loader.compile_skill(
            Path(skill_dir),
            skill_resolver=self._build_studio_skill_resolver(),
        )
        for node in compiled.nodes:
            if node.phase_name != node_id:
                continue
            if node.mode != "agent":
                return None
            io = getattr(getattr(node, "ast", None), "io", None)
            outputs = getattr(io, "outputs", None)
            if outputs is None:
                return None
            if hasattr(outputs, "model_dump"):
                dumped = outputs.model_dump()
                return dumped if isinstance(dumped, dict) else None
            return outputs if isinstance(outputs, dict) else None
        return None

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

                old_artifact_ref = _artifact_ref_audit_snapshot(artifact_ref_data)
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
                artifact_ref_data["_dev_rebuild"] = {
                    "reason": "ephemeral.artifact_missing",
                    "old_artifact_ref": old_artifact_ref,
                    "new_artifact_ref": _artifact_ref_audit_snapshot(artifact_ref_data),
                }
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


def _artifact_ref_audit_snapshot(artifact_ref_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact_ref_data.get("artifact_id"),
        "content_hash": artifact_ref_data.get("content_hash"),
        "store": artifact_ref_data.get("store"),
        "manifest_ref": artifact_ref_data.get("manifest_ref"),
        "source_map_ref": artifact_ref_data.get("source_map_ref"),
        "version": artifact_ref_data.get("version"),
    }


def _attach_dev_rebuild_audit(execution_context: dict[str, Any], artifact_ref_data: dict[str, Any]) -> None:
    dev_rebuild = artifact_ref_data.get("_dev_rebuild")
    if isinstance(dev_rebuild, dict) and "artifact_dev_rebuild" not in execution_context:
        execution_context["artifact_dev_rebuild"] = dev_rebuild


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


_BUILTIN_LLM_ROLE_RE = re.compile(r"^\s*llm_role:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def required_builtin_roles() -> frozenset[str]:
    """引擎 builtin skill 硬依赖的 `llm_role` 集合 —— md-patch 声明 `llm_role: fast`
    (md2json 校验失败项的外科式修补 agent)。Studio 业务层经此 adapter 边界读取这个
    引擎事实,不直接 import SDK(见 test_productization_import_boundary_red)。返回纯
    ``frozenset[str]``,不泄露任何 SDK 具体类型。"""

    import graph_agent

    builtin = Path(graph_agent.__file__).resolve().parent / "skills" / "builtin"
    if not builtin.is_dir():
        return frozenset()
    roles: set[str] = set()
    for skill_md in builtin.rglob("SKILL.md"):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        roles.update(_BUILTIN_LLM_ROLE_RE.findall(text))
    return frozenset(roles)
