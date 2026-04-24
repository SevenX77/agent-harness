from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import warnings
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# DEPRECATED: ArtifactManager is kept only to avoid breaking existing host
# projects during the migration window. New code should use
# graph_agent.io.storage.StorageManager.save_artifact(...) which follows
# the same responsibility but without the project_id coupling. This module
# will be removed once callers have migrated (see
# docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md).
logger.warning(
    "src.core.artifact_manager is deprecated; new code should use "
    "graph_agent.io.storage.StorageManager.save_artifact."
)
warnings.warn(
    "src.core.artifact_manager is deprecated; use graph_agent.io.storage."
    "StorageManager.save_artifact. See docs/graph_agent_docs/"
    "FRAMEWORK_UNDERSTANDING.md.",
    DeprecationWarning,
    stacklevel=2,
)

_TS_DIR_RE = re.compile(r"^\d{8}_\d{6}")


class ArtifactManager:
    @staticmethod
    def save_artifact(
        content: object,
        artifact_type: str,
        project_id: str,
        base_dir: str,
        extension: str = "json",
    ) -> str:
        filename = f"{artifact_type}.{extension}"
        filepath = os.path.join(base_dir, filename)
        os.makedirs(base_dir, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            if extension == "json":
                if hasattr(content, "model_dump"):
                    serializable = json.loads(content.model_dump_json())  # type: ignore[attr-defined]
                elif isinstance(content, str):
                    serializable = json.loads(content)
                else:
                    serializable = content
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(content))

        logger.info("Saved artifact [%s]: %s", project_id, filename)
        return filepath

    @staticmethod
    def load_latest_artifact(
        artifact_type: str,
        base_dir: str,
        extension: str = "json",
    ) -> object | None:
        filepath = os.path.join(base_dir, f"{artifact_type}.{extension}")
        if os.path.exists(filepath):
            return ArtifactManager._read_file(filepath, extension)

        # Backward compat: fall back to old _latest_* naming
        candidates = glob.glob(os.path.join(base_dir, f"{artifact_type}_latest_*.{extension}"))
        if not candidates:
            return None
        return ArtifactManager._read_file(sorted(candidates)[-1], extension)

    @staticmethod
    def archive_output(node_base: Path) -> Path | None:
        """Move current output into ``.history/``.

        Handles two layouts:

        * **Timestamped dirs** (new format): directories matching
          ``YYYYMMDD_HHMMSS*`` are moved into ``.history/`` as-is.
        * **Flat files** (old format): loose files/dirs are bundled into
          ``.history/{mtime_timestamp}/``.

        Skips ``.history``, ``input``, ``.DS_Store``, and symlinks.
        Migrates old ``history/`` to ``.history/`` automatically.
        Returns the last archive directory path, or ``None`` when nothing
        was archived.
        """
        if not node_base.exists():
            return None

        # Migrate old history/ → .history/
        old_history = node_base / "history"
        dot_history = node_base / ".history"
        if old_history.is_dir() and not old_history.is_symlink():
            if dot_history.exists():
                for item in old_history.iterdir():
                    shutil.move(str(item), str(dot_history / item.name))
                old_history.rmdir()
            else:
                old_history.rename(dot_history)

        _skip = {".history", "history", "input", ".DS_Store"}
        entries = [
            e
            for e in node_base.iterdir()
            if e.name not in _skip and not e.is_symlink()
        ]
        if not entries:
            return None

        dot_history.mkdir(parents=True, exist_ok=True)

        archived: Path | None = None

        # Separate timestamp dirs from flat entries
        ts_dirs = [e for e in entries if e.is_dir() and _TS_DIR_RE.match(e.name)]
        flat_entries = [e for e in entries if e not in ts_dirs]

        # Move timestamp dirs directly into .history/
        for ts_dir in ts_dirs:
            dest = dot_history / ts_dir.name
            if dest.exists():
                dest = dot_history / f"{ts_dir.name}_{os.getpid()}"
            shutil.move(str(ts_dir), str(dest))
            archived = dest

        # Bundle flat files/dirs into .history/{mtime_timestamp}/
        if flat_entries:
            max_mtime = 0.0
            for entry in flat_entries:
                if entry.is_file():
                    max_mtime = max(max_mtime, entry.stat().st_mtime)
                elif entry.is_dir():
                    for root, _dirs, files in os.walk(entry):
                        for fname in files:
                            mt = Path(root, fname).stat().st_mtime
                            max_mtime = max(max_mtime, mt)

            ts = datetime.fromtimestamp(max_mtime, tz=UTC).strftime("%Y%m%d_%H%M%S")
            archive = dot_history / ts
            if archive.exists():
                archive = dot_history / f"{ts}_{os.getpid()}"
            archive.mkdir()

            for entry in flat_entries:
                shutil.move(str(entry), str(archive / entry.name))
            archived = archive

        # Clean up legacy latest symlink if present
        latest = node_base / "latest"
        if latest.is_symlink():
            latest.unlink()

        return archived

    @staticmethod
    def _read_file(path: str, extension: str) -> object | None:
        try:
            with open(path, encoding="utf-8") as f:
                if extension == "json":
                    return json.load(f)  # type: ignore[no-any-return]
                return f.read()
        except Exception as e:
            logger.error("Failed to load artifact %s: %s", path, e)
            return None
