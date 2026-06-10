"""IOManager — Declarative I/O for SKILL.md driven workflows.

Handles input loading and output saving based on ``io`` declarations
in SKILL.md frontmatter, eliminating manual file I/O code in business layer.

Supported input sources:
- ``runtime``  — value passed directly via run() kwargs
- ``file``     — loaded from a file path

Supported output targets:
- ``artifact_manager`` — saved via caller-injected artifact_saver callback
- ``file``             — written to a specified path
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IOManager:
    """Manage declarative I/O for one skill workflow.

    The constructor receives the raw ``io`` mapping from SKILL.md frontmatter
    and splits it into cached input/output specifications.

    ``IOManager`` intentionally stays storage-agnostic. When an output targets
    ``artifact_manager``, the actual persistence is delegated to a caller-
    injected ``artifact_saver`` callback instead of importing host-project code.
    """

    def __init__(self, io_config: dict[str, Any]) -> None:
        """Cache declared input and output specifications."""
        if not isinstance(io_config, dict):
            raise TypeError(f"IOManager io_config must be a dict, got {type(io_config).__name__}")
        self._inputs = io_config.get("inputs", [])
        self._outputs = io_config.get("outputs", [])
        # MVP-2 T7: io_errors accumulate on the IOManager instance instead
        # of leaking into ``context["_io_errors"]``. The caller (harness's
        # ``_save_outputs_via_io``) reads ``io_mgr.io_errors`` after
        # ``save_outputs`` returns or raises and routes them into
        # ``state["flow"].io_errors`` via
        # :meth:`StateManager.update_framework`. The MVP-1 ``_io_errors``
        # ctx-dict path is gone; ``state["flow"].io_errors`` is the single
        # source of truth.
        self._io_errors: list[str] = []

    @property
    def io_errors(self) -> list[str]:
        """Return the io_errors recorded during the last save_outputs run.

        The list lives on the IOManager instance so a caller can lift the
        errors into ``state["flow"].io_errors`` after ``save_outputs``
        returns or raises. Returns a copy so callers cannot mutate the
        accumulator from the outside.
        """
        return list(self._io_errors)

    def load_inputs(self, **runtime_args: Any) -> dict[str, Any]:
        """Load input data based on declared input sources.

        Args:
            **runtime_args: Values for inputs with ``source: runtime``.
                Key names must match the input ``name`` field.

        Returns:
            Dict mapping input names to loaded values.

        """
        result: dict[str, Any] = {}

        for input_spec in self._inputs:
            name = input_spec.get("name")
            if not name:
                raise ValueError(f"Input spec missing 'name' field: {input_spec}")
            source = input_spec.get("source", "runtime")

            if source == "runtime":
                if name not in runtime_args:
                    required = input_spec.get("required", True)
                    if required:
                        raise ValueError(f"Required runtime input '{name}' was not provided")
                    logger.warning(
                        "[IOManager] Optional runtime input '%s' not provided, using None",
                        name,
                    )
                result[name] = runtime_args.get(name)

            elif source == "file":
                file_path = input_spec.get("path")
                if not file_path:
                    raise ValueError(f"Input '{name}' has source='file' but no 'path' specified")
                result[name] = self._load_file(Path(file_path))

            else:
                raise ValueError(
                    f"Unknown input source '{source}' for input '{name}'. Supported: runtime, file"
                )

        return result

    def save_outputs(
        self,
        context: dict[str, Any],
        *,
        output_dir: str | Path | None = None,
        project_id: str | None = None,
        artifact_saver: Callable[..., Any] | None = None,
        storage_manager: Any | None = None,
    ) -> list[str]:
        """Save output data based on declared output targets.

        Args:
            context: The final workflow context containing output data.
            output_dir: Base directory for file outputs.
            project_id: Project identifier for artifact_manager outputs.
            artifact_saver: Optional callback injected by the caller to persist
                ``artifact_manager`` outputs outside the framework layer.
                This keeps graph_agent portable across projects that use
                different artifact registries or file management abstractions.
            storage_manager: Optional ``StorageManager`` instance used as a
                *default* saver when ``artifact_saver`` is not provided. The
                caller-supplied ``artifact_saver`` still wins if both are set,
                preserving the Kitchen-Pass red line (host projects keep full
                control over persistence).

        Returns:
            List of saved file paths.

        """
        saved_paths: list[str] = []

        for output_spec in self._outputs:
            name = output_spec.get("name")
            if not name:
                raise ValueError(f"Output spec missing 'name' field: {output_spec}")
            target = output_spec.get("target", "file")
            data = self._resolve_output_data(output_spec, context, name)

            if data is None:
                public_keys = sorted(str(key) for key in context if not str(key).startswith("_"))
                legacy_message = f"Declared output '{name}' was not found in context"
                message = (
                    f"{legacy_message}. "
                    f"Did you forget to set 'hoist_to: {name}' on the producing "
                    f"phase, or write to ctx[{name!r}] in a logic step? "
                    f"Available ctx keys: {public_keys}"
                )
                self._record_io_error(legacy_message)
                raise ValueError(message)

            # Cohesion plan 方针 1.5 (2026-04-26): the schema's canonical
            # value is "artifact" (IoOutput.target: Literal["file", "artifact"]).
            # The legacy "artifact_manager" wording is kept as an in-process
            # alias so older io_config dicts and the docstring above keep
            # working — but new SKILL.md files write "artifact".
            if target in ("artifact", "artifact_manager"):
                if artifact_saver is None and storage_manager is not None:
                    # Kitchen-Pass default: no caller-supplied saver, so fall
                    # back to the framework's built-in StorageManager.
                    phase = context.get("current_phase") or context.get("phase")
                    artifact_name = self._resolve_artifact_name(output_spec, context, name)
                    path = storage_manager.save_artifact(artifact_name, data, phase=phase)
                    saved_paths.append(str(path))
                    logger.info(
                        "[IOManager] Output '%s' saved via StorageManager fallback: %s",
                        name,
                        path,
                    )
                elif artifact_saver is None and output_dir is not None:
                    file_path = self._resolve_output_file_path(
                        output_spec,
                        context,
                        output_dir=output_dir,
                        default_name=name,
                        default_suffix="",
                    )
                    self._save_file(file_path, data)
                    saved_paths.append(str(file_path))
                else:
                    paths = self._save_via_artifact_saver(
                        name,
                        data,
                        artifact_saver=artifact_saver,
                        project_id=project_id,
                    )
                    saved_paths.extend(paths)

            elif target == "file":
                if not output_spec.get("path") and not output_spec.get("filename") and not output_dir:
                    raise ValueError(
                        f"Output '{name}' has target='file' but no path could be determined"
                    )
                file_path = self._resolve_output_file_path(
                    output_spec,
                    context,
                    output_dir=output_dir,
                    default_name=f"{name}.json",
                    default_suffix=".json",
                )
                self._save_file(file_path, data)
                saved_paths.append(str(file_path))

            else:
                raise ValueError(
                    f"Unknown output target '{target}' for output '{name}'. "
                    f"Supported: file, artifact (legacy alias: artifact_manager)"
                )

        return saved_paths

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_output_data(
        output_spec: dict[str, Any],
        context: dict[str, Any],
        name: str,
    ) -> Any:
        source = output_spec.get("source")
        content_type = str(output_spec.get("content_type") or "").lower()
        if source == "business_data_md" or (
            not source and content_type == "text/markdown" and "business_data_md" in context
        ):
            return context.get("business_data_md")
        return context.get(name)

    @staticmethod
    def _resolve_artifact_name(
        output_spec: dict[str, Any],
        context: dict[str, Any],
        name: str,
    ) -> str:
        declared = output_spec.get("path") or output_spec.get("filename") or name
        resolved = IOManager._resolve_path_template(str(declared), context)
        if not resolved:
            raise ValueError(f"Output '{name}' resolved to an empty artifact path")
        return resolved

    @staticmethod
    def _resolve_output_file_path(
        output_spec: dict[str, Any],
        context: dict[str, Any],
        *,
        output_dir: str | Path | None,
        default_name: str,
        default_suffix: str,
    ) -> Path:
        declared = output_spec.get("path") or output_spec.get("filename")
        if declared:
            raw_path = IOManager._resolve_path_template(str(declared), context)
        else:
            raw_path = default_name
            if default_suffix and not Path(raw_path).suffix:
                raw_path = f"{raw_path}{default_suffix}"

        path = Path(raw_path)
        if output_dir is None:
            return path

        base_dir = Path(output_dir).resolve()
        target = path.resolve(strict=False) if path.is_absolute() else (base_dir / path).resolve(strict=False)
        try:
            target.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError(f"Declared output path {raw_path!r} escapes output_dir") from exc
        return target

    @staticmethod
    def _resolve_path_template(path: str, context: dict[str, Any]) -> str:
        """Resolve {context.key} placeholders in path template.

        Args:
            path: Path template with {context.key} placeholders
            context: Context dictionary to resolve values from

        Returns:
            Resolved path string
        """
        import re

        def replace_placeholder(match: re.Match[str]) -> str:
            placeholder = match.group(1)
            if placeholder.startswith("context."):
                key = placeholder[8:]  # Remove "context." prefix
                value = context.get(key)
                if value is None:
                    available = sorted(str(k) for k in context)
                    raise ValueError(
                        f"Path template placeholder {{{placeholder}}} not found "
                        f"in context. Available keys: {available}"
                    )
                return str(value)
            return match.group(0)

        return re.sub(r"\{([^}]+)\}", replace_placeholder, path)

    @staticmethod
    def _load_file(path: Path) -> Any:
        """Load data from a JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        content = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            return json.loads(content)
        return content

    @staticmethod
    def _save_file(path: Path, data: Any) -> None:
        """Save data to a file (JSON for dicts/lists, text otherwise)."""
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, (dict, list)):
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            path.write_text(str(data), encoding="utf-8")

        logger.info("[IOManager] Saved output to %s", path)

    def _save_via_artifact_saver(
        self,
        name: str,
        data: Any,
        *,
        artifact_saver: Callable[..., Any] | None,
        project_id: str | None = None,
    ) -> list[str]:
        """Save data via caller-injected artifact callback."""
        if artifact_saver is None:
            self._record_io_error(f"Artifact target output '{name}' has no saver")
            raise ValueError(
                f"Artifact target output '{name}' has no saver; if this output "
                "is optional, mark it so in IoOutput schema"
            )

        try:
            sig = inspect.signature(artifact_saver)
            accepts_project_id = "project_id" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if accepts_project_id and project_id is not None:
                raw_result = artifact_saver(name, data, project_id=project_id)
            else:
                raw_result = artifact_saver(name, data)
            paths = IOManager._normalize_saved_paths(raw_result)
            logger.info(
                "[IOManager] Saved '%s' via artifact_saver: %s",
                name,
                paths,
            )
            return paths
        except Exception as exc:
            self._record_io_error(f"artifact_saver failed for '{name}': {exc}")
            raise

    @staticmethod
    def _normalize_saved_paths(result: Any) -> list[str]:
        """Normalize artifact_saver return values to list[str]."""
        if result is None:
            return []
        if isinstance(result, Path):
            return [str(result)]
        if isinstance(result, str):
            return [result]
        if isinstance(result, (list, tuple)):
            normalized: list[str] = []
            for item in result:
                if isinstance(item, Path):
                    normalized.append(str(item))
                elif isinstance(item, str):
                    normalized.append(item)
                else:
                    normalized.append(str(item))
            return normalized
        return [str(result)]

    def _record_io_error(self, message: str) -> None:
        """Append ``message`` to the instance-level io_errors accumulator.

        MVP-2 T7: legacy versions of this method appended to
        ``context["_io_errors"]`` (a snapshot dict the caller never read
        back). The accumulator now lives on ``self`` so the caller can
        lift it into ``state["flow"].io_errors`` after ``save_outputs``.
        """
        logger.error("[IOManager] %s", message)
        self._io_errors.append(message)
