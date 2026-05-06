# graph-agent-harness

GraphAgent Harness is a document-driven LLM workflow engine plus a local Skill
Studio. Workflows are described as reviewable `SKILL.md` files, compiled into
LangGraph execution graphs, and run with schema validation, retry feedback,
callbacks, tracing, and Studio-side inspection.

## Status

This branch uses a uv workspace monorepo layout:

```text
.
├── packages/
│   └── graph-agent/          # Python SDK package: graph_agent
├── apps/
│   └── studio/
│       ├── backend/          # FastAPI sidecar app
│       ├── frontend/         # Vite/React Studio UI
│       └── tests-e2e/        # Studio e2e tests
├── skills/                   # Live SKILL.md examples
├── config/                   # repo-local runtime config, including llm_roles.yaml
├── docs/                     # architecture notes, plans, audits
├── scripts/                  # repo maintenance scripts
└── pyproject.toml            # uv workspace root
```

The SDK is intentionally separated from the Studio app. The top-level
`graph_agent` package exposes a small public API; Studio code should import SDK
internals only where an explicit submodule contract exists.

## Quickstart

Install the workspace:

```bash
uv sync
```

Run the SDK test suite:

```bash
cd packages/graph-agent
uv run pytest
```

Run the Studio backend tests:

```bash
cd apps/studio/backend
uv run pytest
```

Run architecture boundary checks:

```bash
uv run lint-imports
```

Run the Studio frontend build:

```bash
cd apps/studio/frontend
npm run build
```

## Development

Common commands from the repo root:

```bash
uv sync
uv run mypy --strict packages/graph-agent/src apps/studio/backend/app
uv run lint-imports
```

SDK-only development:

```bash
cd packages/graph-agent
uv run pytest
uv run python -c "import graph_agent; print(graph_agent.__file__)"
```

Studio backend development:

```bash
cd apps/studio/backend
uv run pytest
uv run python -m app.main
```

Studio frontend development:

```bash
cd apps/studio/frontend
npm run dev
```

## Core Concepts

- `SKILL.md`: Docs-as-code workflow definition for inputs, phases, outputs,
  validators, tools, and subskills.
- Phase: One workflow step. Phases can run logic, LLM calls, validation, and
  retry loops.
- State: Shared workflow state passed between phases.
- Validator: Pydantic and business-rule checks that produce actionable retry
  feedback.
- `WorkflowResult`: Typed SDK return object with dict-compatible access for
  older callers.
- Studio Ports: Storage, Metadata, EventBus, and Auth abstractions that keep
  the backend local-first while ready for cloud adapters.

## Packages

- `packages/graph-agent/src/graph_agent/`: SDK implementation.
- `packages/graph-agent/tests/`: SDK unit and integration tests.
- `apps/studio/backend/app/`: FastAPI app and local Hexagonal Architecture
  adapters.
- `apps/studio/backend/tests/`: Studio backend API/model/security tests.
- `apps/studio/frontend/src/`: React UI.

## License

Apache-2.0. See `LICENSE`.
