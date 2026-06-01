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
   Only the names listed in "Public API" are part of the stable API surface. Internal modules (`core.*`, `io.*`, `models.*`, etc.) can be re-organised without breaking downstream consumers.

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
from pathlib import Path
from graph_agent import LocalWorkspaceResolver, run_skill

resolver = LocalWorkspaceResolver(search_paths=[Path.cwd(), Path.cwd() / 'skills'])
result = run_skill(
    'path/to/v030-skill-root',
    skill_resolver=resolver,
    user_name='Developer',
)
print('Success:', result.success)
"
```

### 4. Choose Entry Point

- `run_skill(...)` — Most common entry point for direct V0.3 skill-root execution; pass an explicit resolver with `skill_resolver=...`.
- `compile_skill(...)` — Static validation; used by Studio Frontend's lint flow.
- `LocalWorkspaceResolver(...)` — Standard local filesystem resolver for CLI-like and host-project usage.

---

## Public API

The stable names re-exported from `graph_agent`:

| Name | Purpose |
|---|---|
| `run_skill` | High-level execution entry point |
| `predict_skill` | High-level prediction/mocking entry point |
| `RunResult` | Unified return result contract (source="run" or "predict") |
| `PathDiff` | Unified prediction path comparison diagnostics |
| `PhaseRecord` | Unified single phase execution diagnostic record |
| `compile_skill` | Static skill validation |
| `CompileResult` | Legacy compile diagnostic container |
| `assemble_graph` | Assemble a compiled skill into a runnable graph |
| `CompiledSkill` | Compiled skill model |
| `CompiledStateGraph` | Assembled graph wrapper |
| `BlackboardState` | Runtime blackboard state |
| `LocalWorkspaceResolver` | Local filesystem skill-id resolver |
| `SkillManifest` | Pydantic schema for SKILL.md / GRAPH.md |
| `serialize_skill` | Stable skill serialization helper |
| `GraphAgentError` | Base exception for all graph agent errors |
| `GraphCompileError` | Subclass: compilation, validation, reference, schema/contract errors |
| `GraphExecutionError` | Subclass: runtime execution, state, tool, checkpointer errors |
| `ModelProviderError` | Subclass: gateway, model role resolver, LLM service provider errors |
| `ResourceNotFoundError` | Subclass: workspace, skill, resolver path resolution failures |

Internal helpers (`Phase`, `WorkflowState`, `IOManager`, `ContextResolver`, `ModelResolver`, etc.) are reachable through their sub-module paths but are **not** part of the SDK contract.

---

## Directory Structure

```text
graph_agent/
├── __init__.py              # public re-exports
├── py.typed                 # PEP 561 type marker
│
├── core/                    # Core orchestration engine
│   ├── harness.py           # GraphAgentHarness
│   ├── runner.py            # run_skill + predict_skill
│   ├── result.py            # RunResult + PhaseRecord + PathDiff
│   ├── loader.py            # load_workflow_from_md (internal)
│   ├── compiler.py          # compile_skill
│   ├── manifest.py          # SkillManifest schema
│   ├── exceptions.py        # GraphAgentError hierarchy
│   ├── checkpointer.py      # LangGraph checkpoint plumbing
│   └── ...
│
├── callbacks/               # Observability & Tracing Sink (internal)
│   ├── events.py            # CallbackEvent definitions
│   └── ...
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
from pathlib import Path

from graph_agent import GraphCompileError, GraphExecutionError, LocalWorkspaceResolver
from graph_agent import RunResult, run_skill

# 3. Run
resolver = LocalWorkspaceResolver(search_paths=[Path.cwd(), Path.cwd() / "skills"])

def my_subscriber(event):
    print("Received event:", event.event_type)

result: RunResult = run_skill(
    "path/to/v030-skill-root",
    skill_resolver=resolver,
    event_subscriber=my_subscriber,
    **{...},
)
```

`skill_resolver` is required for filesystem skill lookup. Tests and host
integrations should construct an explicit resolver instead of relying on
pytest or framework-level default injection.

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

- `docs/skills/SKILL_AUTHORING_GUIDE.md` — How to write SKILL.md
- `docs/engine/INTEGRATION_GUIDE.md` — Integration into host projects
- `docs/engine/COGNITIVE_LOOP_GUIDE.md` — Cognitive control architecture
- `docs/architecture/REPO_SPLIT_AND_SDK_PLAN.md` — V2 monorepo + SDK contract

---

## License

Apache-2.0 (see repo root `LICENSE`).
