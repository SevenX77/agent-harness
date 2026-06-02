# skill-lifecycle — Baseline (技能生命周期基线对齐文档)

> **Status**: Completed (Aligned with V0.3.0)
> **Scope**: Skill Inception, Canvas Graph Compile, Overwrite Collision Whitelists, Batch Runs Scaffolds

---

## 1. Core Codebase Structures

The execution pipelines and lifecycle controls are integrated via:

### Key Components
* **[skills.py (Service)](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/backend/app/services/skills.py)**: Compiles skill configurations, handles git version backups, and manages local markdown updates.
* **[runs.py (Router)](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/backend/app/routers/runs.py)**: Spawns sub-processes for runs, dispatches model predictions, and schedules batch executions.
* **[ConflictDialog.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/ConflictDialog.tsx)**: Displays popovers when file modifications encounter hash collisions.

---

## 2. In-Code Graph Compilation Flows

1. The frontend Workspace triggers a compile by hitting `/api/skills/{skill_id}/compile`.
2. The backend resolves the directory, compiles ASTs, and verifies frontmatter parameters. If compilation succeeds, it serializes nodes to matching formats.
3. If an upstream node modifies a field output that is overwritten downstream, the frontend throws a `Sequential Overwrite Detected` visual popover.

### Identified Logical Gaps
* **The "Allow Overwrite" 403 Locking Error**: Clicking `Allow Overwrite` attempts to patch the backing `.md` files. If the backing file's server-side hash has drifted from the client's cached state, the backend rejects it. Since there is no automatic hash-fetch or client-merge recovery loop, the operation fails with a fatal 403, locking up the modal.
* **Batch Ingestion Vacuums**: The interface completely lacks mechanisms to import raw non-JSON corpus files. The backend `start_batch_run` expects JSON files in `test_inputs` but the API endpoints to create those files return `501 Not Implemented`.
