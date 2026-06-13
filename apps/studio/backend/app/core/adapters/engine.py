from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Literal

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
from graph_agent.core.exceptions import make_error_payload as make_error_payload
from graph_agent.core.graph_serializer import serialize_graph as serialize_graph
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
from graph_agent.core.runner import (
    predict_artifact,
    run_artifact,
)

from app.core.adapters.http_transport import HttpTransport, StudioAdapterError


class _PrivateStudioSkillResolver:
    """Resolve Studio skill ids through local index, workspace, then bundled skills."""

    def resolve_skill(self, skill_id: str) -> Path:
        from graph_agent import ResourceNotFoundError

        from app.core import config

        indexed = self._skill_index_entry(skill_id)
        if indexed:
            indexed_root = Path(indexed["absolute_path"])
            if self._is_skill_root(indexed_root):
                return indexed_root
            message = f"skill {skill_id!r}: indexed path is not a skill root: {indexed_root}"
            raise ResourceNotFoundError(
                message,
                payload=make_error_payload(
                    "[F-v3-resolver-path-invalid]",
                    message,
                    skill_id=skill_id,
                    source_path=indexed_root,
                ),
            )

        workspace_root = config.default_workspace_skills_dir() / skill_id
        if self._is_skill_root(workspace_root):
            return workspace_root

        bundled_root = config.SKILLS_DIR / skill_id
        if self._is_skill_root(bundled_root):
            return bundled_root

        message = f"skill {skill_id!r}: skill is not registered in Studio"
        raise ResourceNotFoundError(
            message,
            payload=make_error_payload(
                "[F-v3-skill-not-registered]",
                message,
                skill_id=skill_id,
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

    from app.core.adapters.gateway import _filter_gateway_credentials, _filter_gateway_roles
    from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore
    from app.services.llm_credentials import _credentials_payload_for_storage

    config_store = LocalGatewayConfigStore(root=config.APP_SETTINGS_DIR)
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "credentials",
        _filter_gateway_credentials(_credentials_payload_for_storage(cred_data)),
    )
    config_store.put_config(
        config.DEFAULT_USER_ID,
        "roles",
        _filter_gateway_roles(roles_data.model_dump(mode="json")),
    )
    return ModelResolver(config_store=config_store, user_id=config.DEFAULT_USER_ID)


def _zip_directory(dir_path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in dir_path.rglob("*"):
            if ".workspace" in file.parts:
                continue
            if file.is_file():
                zf.write(file, file.relative_to(dir_path))
    return buf.getvalue()


def _unzip_directory(zip_bytes: bytes, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(target_dir)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _file_result_payload(result: Any) -> dict[str, Any] | None:
    result_ref = getattr(result, "result_ref", None)
    if not isinstance(result_ref, str) or not result_ref.startswith("file://"):
        return None
    result_path = Path(result_ref.removeprefix("file://"))
    if not result_path.is_file():
        return None
    loaded = json.loads(result_path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"value": loaded}


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

        try:
            loader = SkillLoader()
            loader.compile_skill(Path(skill_dir), skill_resolver=self._build_studio_skill_resolver())
        except Exception as exc:
            raise StudioAdapterError("engine.compile_failed", {"detail": str(exc)}) from exc

        zip_bytes = _zip_directory(Path(skill_dir))

        from app.core import config
        from app.core.adapters.product_store_local import LocalProductArtifactStore

        has_settings = hasattr(config, "settings") and hasattr(config.settings, "storage_root")
        storage_root = Path(config.settings.storage_root) if has_settings else (config.WORKSPACES_DIR / "default")
        product_store = LocalProductArtifactStore(root=storage_root)
        artifact_ref = product_store.put(zip_bytes, artifact_id=skill_id, store=store_type)

        return {
            "artifact_id": artifact_ref.artifact_id,
            "content_hash": artifact_ref.content_hash,
            "store": artifact_ref.store,
            "manifest_ref": artifact_ref.manifest_ref,
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
        if "event_subscriber" in payload and "event_subscriber" not in execution_context:
            execution_context["event_subscriber"] = payload["event_subscriber"]
        artifact_root = self._ensure_local_artifact_root(artifact_ref_data)
        if artifact_root is not None and "artifact_root" not in execution_context:
            execution_context["artifact_root"] = str(artifact_root)

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

            result = run_artifact(
                req,
                skill_resolver=self._build_studio_skill_resolver(),
                model_resolver=self._build_gateway_model_resolver(),
            )
            return _file_result_payload(result) or _jsonable(result)
        except Exception as exc:
            error_code = getattr(exc, "error_code", "engine.run_failed")
            error_payload = getattr(exc, "error_payload", {"detail": str(exc)})
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
        artifact_root = self._ensure_local_artifact_root(artifact_ref_data)
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
                result = predict_artifact(
                    req,
                    skill_resolver=self._build_studio_skill_resolver(),
                    model_resolver=self._build_gateway_model_resolver(),
                )
                return _file_result_payload(result) or _jsonable(result)
            except SDKPredictDeadlockError as exc:
                raise StudioAdapterError(
                    "engine.predict_deadlock", {"phase_name": exc.phase_name, "actual_path": exc.actual_path}
                ) from exc
        except Exception as exc:
            if isinstance(exc, StudioAdapterError):
                raise exc
            error_code = getattr(exc, "error_code", "engine.predict_failed")
            error_payload = getattr(exc, "error_payload", {"detail": str(exc)})
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

        skill_dir = self._build_studio_skill_resolver().resolve_skill(skill_id)
        art_ref = self.compile(
            {
                "skill_dir": str(skill_dir),
                "skill_id": skill_id,
                "artifact_scope": "ephemeral",
            }
        )
        content_hash = art_ref["content_hash"]

        from app.core import config
        from app.core.adapters.product_store_local import LocalProductArtifactStore

        has_settings = hasattr(config, "settings") and hasattr(config.settings, "storage_root")
        storage_root = Path(config.settings.storage_root) if has_settings else (config.WORKSPACES_DIR / "default")

        sha256_val = content_hash.split(":", 1)[1]
        ephemeral_dir = storage_root / "ephemeral_run_skills" / sha256_val
        if not ephemeral_dir.exists():
            product_store = LocalProductArtifactStore(root=storage_root)
            zip_bytes = product_store.get(content_hash)
            _unzip_directory(zip_bytes, ephemeral_dir)

        human_response = None
        if human_input is not None:
            human_response = {"content": human_input}

        workspace_dir = storage_root / "skills" / skill_id / ".workspace"

        from graph_agent import resume_skill

        try:
            res = resume_skill(
                ephemeral_dir,
                workspace_dir=workspace_dir,
                run_id=run_id,
                context_overrides=context_overrides,
                human_response=human_response,
                skill_resolver=self._build_studio_skill_resolver(),
                model_resolver=self._build_gateway_model_resolver(),
            )
            from datetime import UTC, datetime

            return {
                "run_id": run_id,
                "status": "success" if res.success else "failed",
                "started_at": (res.started_at or datetime.now(UTC)).isoformat(),
                "input_summary": "resumed",
                "metrics": _jsonable(res.metrics),
            }
        except Exception as exc:
            error_code = getattr(exc, "error_code", "engine.resume_failed")
            error_payload = getattr(exc, "error_payload", {"detail": str(exc)})
            raise StudioAdapterError(error_code, error_payload) from exc

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

    def _ensure_local_artifact_root(self, artifact_ref_data: dict[str, Any]) -> Path | None:
        content_hash = artifact_ref_data.get("content_hash")
        if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
            return None

        from app.core import config
        from app.core.adapters.product_store_local import LocalProductArtifactStore

        has_settings = hasattr(config, "settings") and hasattr(config.settings, "storage_root")
        storage_root = Path(config.settings.storage_root) if has_settings else (config.WORKSPACES_DIR / "default")
        sha256_val = content_hash.split(":", 1)[1]
        ephemeral_dir = storage_root / "ephemeral_run_skills" / sha256_val
        if (ephemeral_dir / "GRAPH.md").is_file():
            return ephemeral_dir

        product_store = LocalProductArtifactStore(root=storage_root)
        try:
            zip_bytes = product_store.get(content_hash)
        except StudioAdapterError:
            return None
        _unzip_directory(zip_bytes, ephemeral_dir)
        return ephemeral_dir if (ephemeral_dir / "GRAPH.md").is_file() else None
