# graph_agent

Document-driven multi-phase Agent orchestration engine, distributed as the `graph-agent` Python package.

Its sole responsibility: execute SKILL.md-described workflows reliably. The agent loop is built on **LangGraph + LangChain native `create_agent`**. The outer layer is `GraphAgentHarness` for phase orchestration, cognitive constraints, validation/retry, tracing, and I/O boundaries.

---

## Core Principles

1. **Document-driven, not code-driven**
   PMs author skills as `SKILL.md` files (YAML frontmatter + Markdown body). The framework compiles these into LangGraph state machines at runtime.

2. **Framework layer contains no business logic**
   `graph_agent` only provides general orchestration: Phase, tool wrappers, model resolution, tracing, context compression, validation/retry. Business-specific tools, field semantics, and domain rules belong in the skill directory.

3. **Kitchen-pass pattern**
   Phase results are written to `WorkflowState.context` first. Persistence is delegated to `IOManager` through `file` output or `artifact_saver` injected by the caller. The framework prepares the "food" without depending on the host project's file-management implementation.

4. **Hexagonal SDK boundary**
   Only 12 names are part of the public API surface (see "Public API" below). Internal modules (`core.*`, `io.*`, `models.*`, etc.) can be re-organised without breaking downstream consumers.

5. **Multimodal tools are general capabilities**
   Tools under `tools/` for images, video, and voice remain in the framework layer as cross-project reusable capabilities, not business-specific logic.

---

## Quick Start

### 1. Install (uv workspace)

In the agent-harness monorepo root:

```bash
uv sync
```

This installs `graph-agent` as a workspace member alongside `studio-backend`.

For external host projects (downstream):

```bash
# Pin via git+ssh
pip install git+ssh://git@github.com/SevenX77/agent-harness.git@v0.2.0#subdirectory=packages/graph-agent
```

**Python Version**: 3.11+.

### 2. Provide Configuration

Minimum required:
- `config/llm_roles.yaml` — role-to-provider mapping
- `.env` — API keys

`llm_roles.yaml` lookup order:
1. Environment variable `GRAPH_AGENT_ROLES_PATH`
2. Upward search for `config/llm_roles.yaml` from CWD
3. Built-in minimal default config

### 3. Verify Installation

Run the hello_world example from repo root:

```bash
uv run python3 -c "
from graph_agent import run_skill

result = run_skill(
    'packages/graph-agent/src/graph_agent/examples/hello_world/SKILL.md',
    initial_context={'user_name': 'Developer'}
)
print('Success:', result.context.get('greeting', 'No greeting'))
"
```

### 4. Choose Entry Point

- `run_skill(...)` — Most common entry point for direct SKILL.md execution; returns a `WorkflowResult`.
- `compile_skill(...)` — Static validation; used by Studio Frontend's lint flow.
- `GraphAgentHarness` — Low-level orchestrator for advanced cases when you need to hand-write Phase lists or wire custom callbacks.

---

## Public API

The 12 names re-exported from `graph_agent`:

| Name | Purpose |
|---|---|
| `run_skill` | High-level entry point |
| `WorkflowResult` | Pydantic-typed return contract |
| `GraphAgentHarness` | Low-level orchestrator |
| `compile_skill` | Static skill validation |
| `SkillManifest` | Pydantic schema for SKILL.md |
| `Callback` | Base class for extensibility |
| `LoggingCallback` | Default structured-log callback |
| `MetricsCallback` | Default metrics-recording callback |
| `TracingCallback` | JSONL trace-emitting callback |
| `GraphAgentError` | Base exception |
| `SkillLoadError` | Subclass: SKILL.md load failures |
| `SkillCompilationError` | Subclass: compile/validation failures with `skill_path/line/field_path/suggestion` context |

Internal helpers (`Phase`, `WorkflowState`, `IOManager`, `ContextResolver`, `ModelResolver`, etc.) are reachable through their sub-module paths but are **not** part of the SDK contract.

---

## Directory Structure

```text
graph_agent/
├── __init__.py              # 12 public re-exports
├── py.typed                 # PEP 561 type marker
│
├── core/                    # Core orchestration engine
│   ├── harness.py           # GraphAgentHarness
│   ├── runner.py            # run_skill + WorkflowResult
│   ├── result.py            # WorkflowResult Pydantic schema
│   ├── loader.py            # load_workflow_from_md (internal)
│   ├── compiler.py          # compile_skill
│   ├── manifest.py          # SkillManifest schema
│   ├── exceptions.py        # GraphAgentError hierarchy
│   ├── checkpointer.py      # LangGraph checkpoint plumbing
│   └── ...
│
├── callbacks/               # Observability callbacks
│   ├── base.py              # Callback base class
│   ├── logging_cb.py        # LoggingCallback
│   ├── metrics.py           # MetricsCallback
│   └── tracing.py           # TracingCallback
│
├── cognitive/               # Cognitive control
│   ├── finish.py            # finish_task + nudges
│   ├── memory.py            # update_working_memory
│   ├── middlewares.py       # PAOR / WorkingMemory / DeadEnd
│   └── ...
│
├── io/                      # Declarative I/O
│   ├── manager.py           # IOManager
│   └── context_resolver.py
│
├── models/                  # Model resolution
│   └── resolver.py          # ModelResolver
│
├── tools/                   # Multimodal tools
│   ├── generate_image.py
│   ├── generate_video.py
│   └── synthesize_speech.py
│
├── skills/                  # Built-in skills (compiler etc.)
└── examples/                # Runnable examples
    └── hello_world/
```

---

## Migrating to a New Project (host integration)

```python
# 1. Install via uv workspace OR git+ssh pin
# 2. Import only public API
from graph_agent import (
    run_skill,
    WorkflowResult,
    SkillManifest,
    Callback,
    GraphAgentError,
)

# 3. Run
result: WorkflowResult = run_skill(
    "path/to/SKILL.md",
    initial_context={...},
    callbacks=[MyCustomCallback()],
)
```

Do not import from internal sub-modules (`graph_agent.core.*`, `graph_agent.io.*`, etc.) in production host code; those are subject to change.

---

## Type Safety

`graph_agent` ships `py.typed` for PEP 561 compliance. Use with `mypy --strict`:

```bash
uv run mypy --strict packages/graph-agent/src
```

The package is verified clean under `mypy --strict` (143 source files, 0 errors as of v0.2.0).

---

## Extended Documentation

- `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` — How to write SKILL.md
- `docs/graph_agent_docs/INTEGRATION_GUIDE.md` — Integration into host projects
- `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md` — Cognitive control architecture
- `docs/architecture/REPO_SPLIT_AND_SDK_PLAN.md` — V2 monorepo + SDK contract

---

## License

Apache-2.0 (see repo root `LICENSE`).
