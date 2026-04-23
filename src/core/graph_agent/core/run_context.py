from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..callbacks.base import Callback


@dataclass(frozen=True)
class RunContext:
    """Explicit per-run context — replaces threading.local() plumbing.

    Introduced by Task 7.0 as a pre-requisite for the upcoming Harness split
    (Tasks 7.1-7.4). All new emit sites in B-tier / A-tier trace work should
    accept RunContext as a parameter instead of reading self._runtime_local.options
    in harness.py.
    """

    thread_id: str
    trace_dir: Path | None = None
    runtime_inputs: dict[str, Any] = field(default_factory=dict)
    storage_manager: Any | None = None
    artifact_saver: Callable[..., Any] | None = None
    callbacks: list["Callback"] = field(default_factory=list)
