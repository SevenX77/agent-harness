from __future__ import annotations

import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graph_agent.callbacks.base import Callback


@dataclass(frozen=True)
class RunContext:
    """Explicit per-run context — replaces threading.local() plumbing.

    Introduced by Task 7.0 as a pre-requisite for the upcoming Harness split
    (Tasks 7.1-7.4). All new emit sites in B-tier / A-tier trace work should
    accept RunContext as a parameter instead of reading self._runtime_local.options
    in harness.py.

    ``run_id`` identifies a single ``harness.run`` (or ``resume``) invocation.
    It stays empty by default so the historical test fixtures that only care
    about ``thread_id`` keep working without being rewritten; production
    call sites in ``run()`` and ``resume()`` MUST fill it so downstream sidecar
    writers (e.g. ``_save_compaction_sidecar``) can address the per-run dir.

    ``runtime_inputs`` is normalised into a ``types.MappingProxyType`` and
    ``callbacks`` into a ``tuple`` at construction time so that runtime
    collaborators (``PhaseExecutor``, ``NudgeInjector``, subgraph nodes) that
    only receive a reference cannot accidentally mutate them. Both are shallow
    freezes — mutating *nested* objects inside ``runtime_inputs`` values is not
    blocked (CPython has no cheap deep-freeze; enforcing it here would force
    every caller to clone). Both callers currently pass freshly built locals,
    so the conversion is zero-cost beyond the proxy/tuple wrapping.
    """

    thread_id: str
    run_id: str = ""
    trace_dir: Path | None = None
    runtime_inputs: Mapping[str, Any] = field(default_factory=dict)
    storage_manager: Any | None = None
    artifact_saver: Callable[..., Any] | None = None
    callbacks: tuple[Callback, ...] = field(default_factory=tuple)
    unattended: bool = False

    def __post_init__(self) -> None:
        # ``frozen=True`` blocks attribute *reassignment* but not container
        # mutation; wrap the mutable defaults behind read-only shims so
        # callers who hold a reference can't ``runtime_inputs["x"] = ...``
        # or ``callbacks.append(cb)`` and silently corrupt a sibling run's
        # state. ``object.__setattr__`` is the documented escape hatch for
        # in-place init of frozen dataclasses.
        if not isinstance(self.runtime_inputs, types.MappingProxyType):
            source = (
                self.runtime_inputs
                if isinstance(self.runtime_inputs, dict)
                else dict(self.runtime_inputs)
            )
            object.__setattr__(self, "runtime_inputs", types.MappingProxyType(source))
        if not isinstance(self.callbacks, tuple):
            object.__setattr__(self, "callbacks", tuple(self.callbacks))
