# Changelog

## Unreleased

### Breaking Changes

- Moved the SDK from `src/core/graph_agent` to
  `packages/graph-agent/src/graph_agent`.
- Converted the repository to a uv workspace with SDK and Studio packages.
- Collapsed the top-level `graph_agent` public exports to the SDK contract.
- Split tests by ownership under `packages/graph-agent/tests`,
  `apps/studio/backend/tests`, and `apps/studio/tests-e2e`.
- Removed legacy broken `data_manager.py` and `artifact_manager.py`.

### Added

- `WorkflowResult` and `WorkflowMetrics` typed SDK result models.
- Detailed `SkillCompilationError` context fields for skill path, line,
  field path, and suggestions.
- Studio backend Ports and Local Adapters for Storage, Metadata, EventBus, and
  Auth.
- import-linter contracts for SDK and Studio boundary enforcement.
- Restored Studio frontend dark mode UI.

### Changed

- Studio backend skill routes now use async Storage and Metadata ports.
- Studio event WebSocket now subscribes through the EventBus port.
- Studio run manager main process now persists run metadata and final state
  through backend ports.
- README now documents the monorepo layout and uv-based workflows.

### Verification

- `packages/graph-agent`: 1018 passed, 1 skipped.
- `apps/studio/backend`: 28 passed.
- `lint-imports`: 2 contracts kept, 0 broken.
- `mypy --strict packages/graph-agent/src apps/studio/backend/app`: 5 known errors
  remain deferred.
