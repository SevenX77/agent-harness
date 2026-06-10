"""StorageManager — default artifact saver for SKILL.md-driven runs.

Produces a deterministic on-disk layout keyed on ``skill_id`` and ``run_id``,
with optional ``pipeline_prefix`` (e.g. an episode or season id passed via
``runtime_inputs._pipeline_prefix``), and a retention policy that trims old
runs while leaving any ``.golden``-suffixed run directory untouched.

Layout::

    {workspace_root}/runs/
        [{pipeline_prefix}/]              # optional grouping
        {skill_id}/
            {run_id}/                     # this run's artifacts
                <artifact files ...>
                phases/                   # optional phase-scoped subdir
                    <phase_name>/
                        <artifact files ...>
            {run_id}.golden/              # never deleted by cleanup

Design constraints (see ``.kiro/specs/graph-agent-optimizations/design.md``):

* **No ``user_id`` in the signature.** Per-user partitioning is a UI-layer
  concern and must not leak into the engine.
* **``pipeline_prefix`` is runtime-only.** It arrives via ``runtime_inputs``
  and is *not* a construction-time field on the manager — different runs of
  the same skill can belong to different pipelines.
* **Retention is per skill_id scope.** Cleanup only touches the run
  directories for the same ``skill_id`` (and ``pipeline_prefix`` when set);
  it never walks other skills.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GOLDEN_SUFFIX = ".golden"
_DEFAULT_HISTORY_RETENTION = 10


def _dir_size_bytes(path: Path) -> int:
    """Return the total size in bytes of all files under ``path``."""
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                # Race with deletion — ignore so cleanup can continue.
                continue
    return total


class StorageManager:
    """Default on-disk artifact saver for a single skill run.

    The manager is constructed once per skill invocation with the triple
    ``(workspace_root, skill_id, run_id)``. All subsequent calls write
    into the run-scoped directory returned by :meth:`get_output_dir`.

    Retention cleanup runs opportunistically on instantiation so a long-
    running workspace does not accumulate dead runs; ``.golden`` runs are
    excluded from the retention set entirely.

    Tier 1 Commit B (T-B10): when the caller passes ``callbacks=`` to
    :meth:`attach_callbacks`, each successful :meth:`save_artifact` emits
    an ``ArtifactSavedEvent`` so Studio's artifact panel can populate
    directly from the event stream without polling the filesystem.
    """

    def __init__(
        self,
        workspace_root: Path | str,
        skill_id: str,
        run_id: str,
        *,
        history_retention: int = _DEFAULT_HISTORY_RETENTION,
    ) -> None:
        if not skill_id:
            raise ValueError("skill_id must be a non-empty string")
        if not run_id:
            raise ValueError("run_id must be a non-empty string")
        if history_retention < 0:
            raise ValueError("history_retention must be >= 0")

        self._workspace_root = Path(workspace_root).resolve()
        self._skill_id = skill_id
        self._run_id = run_id
        self._history_retention = history_retention
        # Pipeline prefix is stored on the instance only after the first call
        # to :meth:`get_output_dir` that declares one, so the same manager
        # can be reused across phases that share a prefix.
        self._pipeline_prefix: str | None = None
        # Callbacks optionally attached by the harness so save_artifact can
        # emit ArtifactSavedEvent. Empty by default — the manager works
        # standalone even without a harness.
        self._callbacks: list[Any] = []

        logger.info(
            "StorageManager init: workspace=%s skill_id=%s run_id=%s retention=%d",
            self._workspace_root,
            skill_id,
            run_id,
            history_retention,
        )

    @property
    def run_id(self) -> str:
        return self._run_id

    def attach_callbacks(self, callbacks: list[Any]) -> None:
        """Attach a callback list so save_artifact can emit ArtifactSavedEvent."""
        self._callbacks = list(callbacks or [])

    @property
    def skill_id(self) -> str:
        return self._skill_id

    def get_output_dir(self, pipeline_prefix: str | None = None) -> Path:
        """Return (and create) the run-scoped output directory.

        The first call establishes the pipeline prefix on the manager; later
        calls may omit it and will reuse the cached value.
        """
        if pipeline_prefix is not None:
            if self._pipeline_prefix is not None and self._pipeline_prefix != pipeline_prefix:
                raise ValueError(
                    f"StorageManager already bound to pipeline_prefix "
                    f"{self._pipeline_prefix!r}; refusing to rebind to "
                    f"{pipeline_prefix!r} mid-run."
                )
            self._pipeline_prefix = pipeline_prefix

        run_dir = self._run_dir(self._run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Retention runs lazily on the first get_output_dir call per process
        # to avoid doing disk work when a skill is only inspecting the path.
        self._cleanup_history()

        return run_dir

    def save_artifact(
        self,
        name: str,
        content: Any,
        phase: str | None = None,
    ) -> Path:
        """Persist ``content`` under the current run directory.

        * ``str`` / ``bytes`` content is written verbatim.
        * Anything else is JSON-serialised with ``indent=2, ensure_ascii=False``.
        * When ``phase`` is provided the artifact goes into
          ``<run_dir>/phases/<phase>/<name>``.
        """
        target = self._artifact_path(self._run_id, name, phase)
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            target.write_bytes(content)
        elif isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_text(
                json.dumps(content, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        # Tier 1 Commit B (T-B10): emit ArtifactSavedEvent so Studio can
        # render the artifact panel from the event stream.
        if self._callbacks:
            try:
                from graph_agent.callbacks.events import ArtifactSavedEvent

                event = ArtifactSavedEvent(
                    phase_name=phase,
                    name=name,
                    path=str(target),
                    size_bytes=target.stat().st_size if target.exists() else 0,
                )
                for cb in self._callbacks:
                    try:
                        cb.on_event(event)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "StorageManager: callback %r raised on ArtifactSavedEvent",
                            type(cb).__name__,
                        )
            except Exception:  # noqa: BLE001
                logger.exception("StorageManager: failed to build ArtifactSavedEvent")

        logger.info(
            "StorageManager save: run_id=%s phase=%s name=%s path=%s",
            self._run_id,
            phase or "-",
            name,
            target,
        )
        return target

    def load_latest(self, phase: str | None, name: str) -> Any:
        """Load the most recent artifact with the given ``(phase, name)``.

        Scans sibling run directories (same ``skill_id`` / ``pipeline_prefix``)
        in descending lexicographic order — which, because callers are
        expected to pass timestamped run_ids, amounts to most-recent-first.
        Golden directories are included in the search.
        """
        runs_dir = self._runs_dir()
        if not runs_dir.exists():
            return None

        candidates = sorted(
            (p for p in runs_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for run_dir in candidates:
            # Strip the .golden suffix so load_latest can reach into locked runs.
            artifact = self._artifact_path_for_dir(run_dir, name, phase)
            if artifact.exists() and artifact.is_file():
                logger.info(
                    "StorageManager load_latest hit: skill_id=%s phase=%s name=%s source=%s",
                    self._skill_id,
                    phase or "-",
                    name,
                    artifact,
                )
                return self._read_artifact(artifact)

        logger.info(
            "StorageManager load_latest miss: skill_id=%s phase=%s name=%s",
            self._skill_id,
            phase or "-",
            name,
        )
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _runs_dir(self) -> Path:
        root = self._workspace_root / "runs"
        if self._pipeline_prefix:
            root = root / self._pipeline_prefix
        return root / self._skill_id

    def _run_dir(self, run_id: str) -> Path:
        return self._runs_dir() / run_id

    def _artifact_path(self, run_id: str, name: str, phase: str | None) -> Path:
        run_dir = self._run_dir(run_id)
        base_dir = run_dir / "phases" / phase if phase else run_dir
        return self._artifact_path_under(base_dir, name)

    @staticmethod
    def _artifact_path_under(base_dir: Path, name: str) -> Path:
        if not name:
            raise ValueError("artifact name must be non-empty")
        relative_name = Path(str(name))
        if relative_name.is_absolute():
            raise ValueError(f"artifact path escapes run directory: {name!r}")
        base_resolved = base_dir.resolve(strict=False)
        target = (base_resolved / relative_name).resolve(strict=False)
        try:
            target.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError(f"artifact path escapes run directory: {name!r}") from exc
        return target

    def _artifact_path_for_dir(self, run_dir: Path, name: str, phase: str | None) -> Path:
        base_dir = run_dir / "phases" / phase if phase else run_dir
        return self._artifact_path_under(base_dir, name)

    @staticmethod
    def _read_artifact(path: Path) -> Any:
        if path.suffix.lower() == ".json":
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.warning("StorageManager load_latest: invalid JSON in %s: %s", path, exc)
                return path.read_text(encoding="utf-8")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_bytes()

    def _cleanup_history(self) -> None:
        """Trim old runs so only the newest ``history_retention`` survive.

        ``.golden`` directories are always preserved and do **not** count
        against the retention budget.
        """
        if self._history_retention <= 0:
            return

        runs_dir = self._runs_dir()
        if not runs_dir.exists():
            return

        # Partition: protected golden runs vs. regular retention-counted runs.
        protected: list[Path] = []
        regular: list[Path] = []
        for entry in runs_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.endswith(_GOLDEN_SUFFIX):
                protected.append(entry)
            else:
                regular.append(entry)

        # Keep the newest `history_retention` regular runs. "Newest" ==
        # lexicographically greatest name; callers are expected to pass
        # timestamped run_ids.
        regular.sort(key=lambda p: p.name, reverse=True)
        keep = regular[: self._history_retention]
        prune = regular[self._history_retention :]

        if not prune:
            return

        for stale in prune:
            size_bytes = _dir_size_bytes(stale)
            try:
                shutil.rmtree(stale)
            except OSError as exc:
                logger.warning(
                    "StorageManager cleanup failed for %s: %s",
                    stale,
                    exc,
                )
                continue
            logger.info(
                "StorageManager cleanup removed run_id=%s path=%s freed_bytes=%d",
                stale.name,
                stale,
                size_bytes,
            )

        # Defensive sanity-log so ops can see the retention decision.
        logger.info(
            "StorageManager cleanup summary: skill_id=%s kept=%d pruned=%d protected_golden=%d",
            self._skill_id,
            len(keep),
            len(prune),
            len(protected),
        )


_RUN_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_run_id(raw: str) -> str:
    """Replace characters that would break filesystem path assumptions."""
    cleaned = _RUN_ID_SAFE_RE.sub("-", raw).strip("-")
    return cleaned or "run"


__all__ = ["StorageManager", "sanitize_run_id"]
