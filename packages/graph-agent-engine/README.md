# graph-agent-engine

A standalone wheel of the **GraphAgent engine** extracted from
[`agent-harness`](https://github.com/sevenx/agent-harness) so downstream
projects (e.g. `video-analysis`) can depend on it without pulling in the
Studio backend or any business-domain skills.

This subproject is a thin packaging shim:

- `graph_agent/` is a **symlink** to `../../src/core/graph_agent/` — the real
  source still lives in the main repo. The symlink lets `hatchling` see the
  package locally without any `..` path tricks.
- `pyproject.toml` here pins the same dependency versions as the root
  `pyproject.toml` but only declares the engine package as a build target
  (no `studio-backend/app`).

When the upstream Task 7.6 physical move lands (engine → `packages/graph-agent/`),
this directory becomes the canonical home and the symlink is replaced with
the real tree.

## Build

```bash
# from repo root
.build-venv/bin/python -m build packages/graph-agent-engine
ls packages/graph-agent-engine/dist/
# graph_agent_engine-0.1.0-py3-none-any.whl
```

## What's inside the wheel

The wheel ships **only** the GraphAgent engine:

```
graph_agent/
├── core/                # harness, runner, loader, compiler
├── callbacks/           # observability hooks (Tracing, Metrics, Logging)
├── cognitive/           # working memory / dead-end pruning / finish gate
├── config/              # llm_roles + multimodal_roles loaders
├── io/                  # IOManager, ContextResolver, kitchen-pass saver
├── models/              # ModelResolver with provider failover
├── tools/               # multimodal tools (image / video / speech)
├── skills/builtin/      # built-in compiler skill, md-patch
└── examples/hello_world/
```

## Public API

```python
from graph_agent import (
    run_skill,
    load_workflow_from_md,
    GraphAgentHarness,
    Phase,
    WorkflowState,
    ContextBridge,
    ModelResolver,
    IOManager,
    ContextResolver,
    Callback,
    LoggingCallback,
    MetricsCallback,
    TracingCallback,
    SkillManifest,
    compile_skill,
    parse_skill_file,
    serialize_skill,
)
```

See `docs/migration/2026-04-30-graph-agent-to-video-analysis.md` in the main
repo for the migration runbook.
