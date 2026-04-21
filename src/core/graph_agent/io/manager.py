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
            io_config = {}
        self._inputs = io_config.get("inputs", [])
        self._outputs = io_config.get("outputs", [])

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
                    logger.warning(
                        "[IOManager] Runtime input '%s' not provided, using None",
                        name,
                    )
                result[name] = runtime_args.get(name)

            elif source == "file":
                file_path = input_spec.get("path")
                if not file_path:
                    raise ValueError(
                        f"Input '{name}' has source='file' but no 'path' specified"
                    )
                result[name] = self._load_file(Path(file_path))

            else:
                raise ValueError(
                    f"Unknown input source '{source}' for input '{name}'. "
                    f"Supported: runtime, file"
                )

        return result

    def save_outputs(
        self,
        context: dict[str, Any],
        *,
        output_dir: str | Path | None = None,
        project_id: str | None = None,
        artifact_saver: Callable[..., Any] | None = None,
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

        Returns:
            List of saved file paths.

        """
        saved_paths: list[str] = []

        for output_spec in self._outputs:
            name = output_spec.get("name")
            if not name:
                raise ValueError(f"Output spec missing 'name' field: {output_spec}")
            target = output_spec.get("target", "file")
            data = context.get(name)

            if data is None:
                logger.warning(
                    "[IOManager] Output '%s' not found in context, skipping",
                    name,
                )
                continue

            if target == "artifact_manager":
                paths = self._save_via_artifact_saver(
                    name,
                    data,
                    context=context,
                    artifact_saver=artifact_saver,
                    project_id=project_id,
                )
                saved_paths.extend(paths)

            elif target == "file":
                file_path = output_spec.get("path")
                if not file_path and output_dir:
                    file_path = str(Path(output_dir) / f"{name}.json")
                if not file_path:
                    raise ValueError(
                        f"Output '{name}' has target='file' but no path could be determined"
                    )
                # Replace {context.key} placeholders in path
                file_path = self._resolve_path_template(file_path, context)
                self._save_file(Path(file_path), data)
                saved_paths.append(file_path)

            else:
                raise ValueError(
                    f"Unknown output target '{target}' for output '{name}'. "
                    f"Supported: artifact_manager, file"
                )

        return saved_paths

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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

        def replace_placeholder(match):
            placeholder = match.group(1)
            if placeholder.startswith("context."):
                key = placeholder[8:]  # Remove "context." prefix
                value = context.get(key)
                if value is None:
                    logger.warning(f"Path template placeholder {{{placeholder}}} not found in context")
                    return match.group(0)  # Keep original placeholder
                return str(value)
            return match.group(0)

        return re.sub(r'\{([^}]+)\}', replace_placeholder, path)

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

    @staticmethod
    def _save_via_artifact_saver(
        name: str,
        data: Any,
        *,
        context: dict[str, Any],
        artifact_saver: Callable[..., Any] | None,
        project_id: str | None = None,
    ) -> list[str]:
        """Save data via caller-injected artifact callback."""
        if artifact_saver is None:
            logger.warning("[IOManager] Output '%s' will be lost: no artifact_saver provided", name)
            IOManager._record_io_error(
                context,
                f"Output '{name}' declared target=artifact_manager but no artifact_saver was provided",
            )
            return []

        try:
            sig = inspect.signature(artifact_saver)
            accepts_project_id = "project_id" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
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
            IOManager._record_io_error(
                context,
                f"artifact_saver failed for '{name}': {exc}",
            )
            return []

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

    @staticmethod
    def _record_io_error(context: dict[str, Any], message: str) -> None:
        logger.error("[IOManager] %s", message)
        errors = context.get("_io_errors")
        if not isinstance(errors, list):
            errors = []
            context["_io_errors"] = errors
        errors.append(message)
