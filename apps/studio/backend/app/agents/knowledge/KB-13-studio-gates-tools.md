---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-07-compile-diagnostics
  - KB-08-predict
  - KB-12-llm-roles
  - KB-14-artifacts-persistence
---

> Distilled from: `docs/studio/mvp1/03_compile.md` & `docs/studio/mvp1/04_run-and-verify.md` & Design Spec §Requirements 8 & 13

# KB-13: Studio Compilation Gates & Tools Map

Studio enforces structured gates to validate a skill's health from design to live execution. Tool access is organized around these gates to ensure safety and system integrity.

## 1. The Compilation-to-Execution Gates
A skill must pass three sequential gates before full deployment:

```text
Design ──> [ Compile Gate ] ──> [ Predict Gate ] ──> [ Run / Execution ]
```

1.  **Compile Gate**: Performs static analysis on the skill structure (`[[KB-01-skill-anatomy]]`), DAG topology, I/O schemas (`[[KB-02-io-dataflow]]`), actions signatures (`[[KB-03-logic-actions]]`), and mention reachability (`[[KB-04-agent-nodes]]`). A compile-pass is a hard prerequisite for prediction or execution.
2.  **Predict Gate**: Runs an LLM-free dry-run simulation using mock responses (`[[KB-08-predict]]`). It verifies the state-mapping, path logic, and output schemas under mocked workloads. A predict-pass is required before initiating a full execution.
3.  **Run / Execution**: Executes the graph using live LLM connections and actual inputs, producing full trace files (`[[KB-09-run-trace-checkpoint]]`) and outputs.

## 2. MCP Tools Map
The Studio panel exposes its MCP tools through an in-process server named `studio`. Two approval classes exist — do not assume zero approval for writes:

*   **Read / probe tools run with zero approval** (declaratively allowed).
*   **Write / execute tools always hold for an explicit user approval card** before anything happens. Expect the card; never try to route around it.

**Read / probe (zero approval):**

| MCP Tool | Purpose |
|---|---|
| `get_skill_overview` | First call of a session: graph io + per-phase io field names/types, validator, llm_role — structure only, never body text. |
| `read_skill_file` | Bounded file read confined to the skill directory (line ranges; 400-line cap; escape paths rejected). |
| `get_workspace_config` | Structured projection of `.workspace/runtime_config.json`: input bindings (paths, not payloads), artifacts declarations, node llm overrides, fingerprint. |
| `list_run_artifacts` / `read_run_artifact` | Enumerate / read (48 KB-bounded) files under `runs/<run_id>/artifacts/` (`[[KB-14-artifacts-persistence]]`). |
| `query_run_trace` / `wait_for_run` | Bounded trace slices with per-phase aggregates / block until a run terminates instead of polling. |
| `get_skill_output_contract` | The skill's output contract projection. |
| `compile_skill` | Compiles the skill and returns the complete diagnostics set. |
| `predict_skill` | LLM-free dry run: phase path, path diff, diagnostics. |
| `get_run_detail` | Bounded projection of a real run: status, token metrics, event counts, error excerpts, final output. |
| `list_golden` / `get_golden_content` | List golden baselines / read a baseline's actual expected_output. |
| `get_resume_validity` | Check whether a run can resume from a checkpoint or node range, and why not. |
| `get_llm_roles` / `search_llm_registry` | Role snapshot / fuzzy search of legal canonical groups and routes. |
| `run_role_test` / `test_llm_endpoint` / `test_llm_endpoint_models` / `probe_llm_route` | Real connectivity probes; never mutate config vocabulary. |

**Write / execute (approval card required):**

| MCP Tool | Purpose |
|---|---|
| `create_skill` | Create a skill in the default Skills root, registered in the index (UI-visible), scaffolded when no seed files are given. |
| `run_skill` / `resume_run` | Start a real run / resume from a checkpoint (real LLM calls, costs tokens). Poll with `get_run_detail`. |
| `pause_run` / `stop_run` | The human's Pause/Stop buttons, as tools: pause keeps the checkpoint (resume later), stop ends the run for good but keeps everything it produced. Use stop to cut a doomed run's losses instead of waiting it out. |
| `set_output_artifacts` | Replace the skill's `runtime_config.artifacts` declarations via the same service as the I/O panel. |
| `write_skill_file` | Write one skill source file through the validated service chain (path whitelist, conflict hash) — never raw `Write`/`Edit` into a skill directory. |
| `bind_test_input` | Drop a JSON test input into `.workspace/import_files/` (same chain as the I/O panel import) and re-derive the input bindings. |
| `set_golden_baseline` / `delete_golden_baseline` | Promote a sealed run to golden / delete a baseline. |
| `publish_skill` / `fork_skill` | Local release archive (+ remote registry sync when identity configured) / clone any skill into an editable copy. |
| `create_llm_role` / `update_llm_role` / `delete_llm_role` / `apply_model_profile_to_role` | Role configuration writes via the same service chain as Settings. |
| `upsert_llm_endpoint` / `delete_llm_endpoint` / `update_llm_route` / `delete_llm_route` | Credential / route vocabulary writes (api_key redacted in approval details). |

**Surface caveat**: an Open-in-CLI session (codex / claude launched from Studio) gets the same tools over HTTP, minus `delete_llm_endpoint` and `delete_llm_route` (credential-cascading deletes stay UI-only), and its human gate is the CLI's own approval prompt rather than Studio's approval card. The surface is present only when the Studio sidecar was reachable at launch; if the tools are missing, work without them instead of shelling into the engine.

## 3. Skill File Writing Boundary
Three write paths coexist, each with its own guard:
*   **Studio's own writes** (editor save, graph serialize, test inputs, golden promote from UI, publish artifacts) go through the Tauri Rust native-fs layer — the sole writer for Studio-originated file mutations (D12).
*   **Agent direct writes**: conversational agents MAY use `Write`/`Edit` directly on skill files — an accepted MVP1 exception (PM ruling 2026-06-14, DEF-027). A PreToolUse hard boundary confines them to the workspace and skills root and excludes the `llm/` config directory and `app_settings.json`; every write emits a patch event for review/undo.
*   **Agent structured writes** (skill create/fork/publish, golden set/delete, run/resume, LLM config) go through the approval-gated MCP tools above — never by hand-editing config files.
*   **Shell / execution tools** (`Bash`, `PowerShell`) always hold for a user approval card, every invocation, read-only commands included; any tool outside the declarative read list holds for approval by default. A denied `Write`/`Edit` means the target is out of bounds — never retry the same write through a shell command or any other tool.

## 4. Configuration Map
Configurations and environment mappings are partitioned to prevent unauthorized access:
*   **Workspace Runtime Config**: `.workspace/runtime_config.json` stores import file bindings, model override candidates, and runtime parameters (`[[KB-11-workspace-runtime]]`).
*   **Application Settings**: `app_settings.json` holds host configurations, editor options, and global paths.
*   *Note: Application settings files are excluded from direct edit access by conversational agents. Changes must flow through service-layer APIs.*
