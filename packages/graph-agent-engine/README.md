# graph-agent-engine

**Meta-package alias** for `graph-agent`. Provides backward-compat
pip-pinning for legacy downstream projects (e.g. `video-analysis`) that
were originally built against `graph_agent_engine-0.1.0`.

> **For new code**: depend on `graph-agent` directly.
>
> ```bash
> pip install graph-agent  # recommended
> # equivalent:
> pip install graph-agent-engine  # legacy alias, installs graph-agent transitively
> ```

This package contains **no Python module** - `pip install graph-agent-engine`
just installs `graph-agent` as a transitive dep. Once installed, `import graph_agent`
gives you the canonical SDK plus 14 lazy-loaded deprecated symbols
(`IOManager`, `WorkflowState`, `Phase`, etc) for 1.0.0 backward compat.

## Why this exists

PR #37 of agent-harness moved `src/core/graph_agent/` -> `packages/graph-agent/`
and collapsed the SDK from 26 exports to 12 stable public exports. To
avoid breaking downstream projects vendoring 1.0.0 (notably
`video-analysis`), the 14 demoted internal symbols are still importable
from `graph_agent` via a lazy `__getattr__` shim - accessing them emits
a `DeprecationWarning`.

This `graph-agent-engine` package itself just preserves the wheel name
for downstream pinning convenience. The actual code is in `graph-agent`.

## Deprecation timeline

- `v0.2.0` (2026-05): Lazy aliases active in `graph_agent`, emit warnings on access
- `v0.3.0` (Q3 2026): Warnings escalate to errors with `--error-on-deprecated`
- `v1.0.0` (Q4 2026): Lazy aliases removed; only 12-export SDK remains, `graph-agent-engine` deprecated

## Migration runbook

See `docs/migration/PROMPT_FOR_VIDEO_ANALYSIS_AGENT.md` (Path B salvage merge recommended).

## License

Apache-2.0.
