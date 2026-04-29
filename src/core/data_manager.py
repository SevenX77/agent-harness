from __future__ import annotations

import logging
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]  # PyYAML runtime dependency has no local stubs.

# DEPRECATED: DataManager is kept only to avoid breaking existing host
# projects (story_forge) during the migration window. New code should use
# graph_agent.io.storage.StorageManager instead — it does not depend on
# story_forge's config/pipeline.yaml and has no user_id/project_id in its
# signature. This module will be removed once all host projects have
# migrated (see docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md).
logging.getLogger(__name__).warning(
    "src.core.data_manager is deprecated; new code should use "
    "graph_agent.io.storage.StorageManager."
)
warnings.warn(
    "src.core.data_manager is deprecated; use graph_agent.io.storage."
    "StorageManager. See docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md.",
    DeprecationWarning,
    stacklevel=2,
)

_TS_DIR_RE = re.compile(r"^\d{8}_\d{6}")

if TYPE_CHECKING:
    class OutputSpec:
        def __init__(
            self,
            *,
            aspect_ratio: str | None = None,
            resolution: str | None = None,
            frame_rate: int | None = None,
        ) -> None: ...

    class ProjectConfig:
        aspect_ratio: str | None
        resolution: str | None
        frame_rate: int | None

        def __init__(self) -> None: ...

        @classmethod
        def load(cls, path: Path) -> "ProjectConfig": ...

        def save(self, path: Path) -> None: ...
else:
    from story_forge.core.config import OutputSpec, ProjectConfig

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PIPELINE_PATH = _PROJECT_ROOT / "config" / "pipeline.yaml"

_node_order: dict[str, int] | None = None


def _load_node_order() -> dict[str, int]:
    global _node_order
    if _node_order is not None:
        return _node_order
    with open(_PIPELINE_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    nodes = config.get("nodes", [])
    _node_order = {node["name"]: i + 1 for i, node in enumerate(nodes)}
    return _node_order


def _format_dir_name(index: int, name: str) -> str:
    return f"{index:02d}_{name}"


def _resolve_project_root(project_id: str) -> Path:
    """Resolve project_id to a project root directory.

    Tries exact match first, then prefix match (e.g. ``001`` finds
    ``001_末哥超凡公路``).  Falls back to the exact id path for new
    projects.
    """
    projects_base = _PROJECT_ROOT / "data" / "projects"
    exact = projects_base / project_id
    if exact.exists():
        return exact

    if projects_base.is_dir():
        for d in sorted(projects_base.iterdir()):
            if d.is_dir() and d.name.startswith(f"{project_id}_"):
                return d

    return exact


class DataManager:
    """Pipeline-aware data access layer.

    Resolves node names to numbered directories based on pipeline.yaml ordering.
    Skills use this instead of hardcoding sibling node paths.
    """

    def __init__(
        self,
        project_id: str,
        current_node: str,
        *,
        project_root: Path | None = None,
        _run_dir: Path | str | None = None,
    ) -> None:
        order = _load_node_order()
        if current_node not in order:
            msg = f"Unknown node '{current_node}'. Available: {', '.join(order)}"
            raise ValueError(msg)
        self._project_id = project_id
        self._current_node = current_node
        self._order = order
        self._output_spec: OutputSpec | None = None
        self._project_config: ProjectConfig | None = None
        self._run_dir = Path(_run_dir) if _run_dir else None
        if project_root is not None:
            self._project_root = project_root if isinstance(project_root, Path) else Path(project_root)
        else:
            self._project_root = _resolve_project_root(project_id)

    # -- Serialization support (LangGraph checkpoint via ormsgpack) --

    def _asdict(self) -> dict[str, str | None]:
        """Return serializable dict for LangGraph checkpoint.

        LangGraph's ormsgpack serializer recognises ``_asdict()`` (namedtuple
        protocol) and reconstructs via ``DataManager(**kwargs)`` on
        deserialisation.  All values must be msgpack-native types (str/None).
        """
        return {
            "project_id": self._project_id,
            "current_node": self._current_node,
            "project_root": str(self._project_root),
            "_run_dir": str(self._run_dir) if self._run_dir else None,
        }

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def current_node(self) -> str:
        return self._current_node

    @property
    def output_dir(self) -> Path:
        if self._run_dir is not None:
            return self._run_dir
        return self.node_dir(self._current_node)

    def node_base_dir(self, node_name: str) -> Path:
        """Return the node container directory (e.g. ``05_adaptation/``)."""
        if node_name not in self._order:
            msg = f"Unknown node '{node_name}'. Available: {', '.join(self._order)}"
            raise ValueError(msg)
        index = self._order[node_name]
        return self._project_root / _format_dir_name(index, node_name)

    def node_dir(self, node_name: str) -> Path:
        """Resolve to the newest timestamped output directory for a node.

        Scans ``{base}/`` for directories matching ``YYYYMMDD_HHMMSS*``,
        returns the lexicographically latest one.  Falls back to a legacy
        ``latest`` symlink, then to the base directory itself.
        """
        base = self.node_base_dir(node_name)
        if base.is_dir():
            ts_dirs = sorted(
                (d for d in base.iterdir() if d.is_dir() and _TS_DIR_RE.match(d.name)),
                key=lambda d: d.name,
                reverse=True,
            )
            if ts_dirs:
                return ts_dirs[0]
        # Legacy fallback: symlink from older runs
        latest = base / "latest"
        if latest.exists():
            return latest
        return base

    def all_node_names(self) -> list[str]:
        return sorted(self._order, key=lambda n: self._order[n])

    @property
    def project_config(self) -> ProjectConfig:
        if self._project_config is None:
            self._project_config = self._load_project_config()
        return self._project_config

    def _load_project_config(self) -> ProjectConfig:
        config_path = self._project_root / "project_config.json"
        if config_path.exists():
            return ProjectConfig.load(config_path)
        return ProjectConfig()

    def save_project_config(self, config: ProjectConfig) -> None:
        self._project_root.mkdir(parents=True, exist_ok=True)
        config.save(self._project_root / "project_config.json")
        self._project_config = config
        self._output_spec = None  # invalidate cached output_spec

    @property
    def output_spec(self) -> OutputSpec:
        if self._output_spec is None:
            self._output_spec = self._load_output_spec()
        return self._output_spec

    def _load_output_spec(self) -> OutputSpec:
        pc = self.project_config
        return OutputSpec(
            aspect_ratio=pc.aspect_ratio,
            resolution=pc.resolution,
            frame_rate=pc.frame_rate,
        )

    def ensure_dirs(self) -> None:
        """Create project root and a new timestamped output directory.

        Creates ``{node_base}/{YYYYMMDD_HHMMSS}/``.  The newest
        timestamped directory is resolved by :meth:`node_dir` at read
        time, so no ``latest`` symlink is needed.
        """
        self._project_root.mkdir(parents=True, exist_ok=True)
        base = self.node_base_dir(self._current_node)
        base.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        run_dir = base / ts
        run_dir.mkdir(exist_ok=True)

        self._run_dir = run_dir
