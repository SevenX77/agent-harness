---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-07-compile-diagnostics
  - KB-08-predict
  - KB-12-llm-roles
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
The Studio exposes six specialized Model Context Protocol (MCP) tools to conversational agents. All six tools run with **zero approval** (implicitly allowed by the host environment):

| MCP Tool | Purpose | Primary Consumer |
|---|---|---|
| `compile_skill` | Compiles the skill and returns the complete set of diagnostics. | Lachesis, MoirAI |
| `predict_skill` | Runs a dry-run prediction simulation and returns diffs. | Lachesis, MoirAI |
| `get_llm_roles` | Queries registered LLM roles and route configurations. | MoirAI, Clotho |
| `run_role_test` | Initiates a 1-token probe request to test route connectivity. | MoirAI |
| `create_llm_role` | Creates a new role configuration via the FastAPI service layer. | MoirAI |
| `update_llm_role` | Modifies model parameters, routing, or fallbacks for a role. | MoirAI |

## 3. Rust Native-FS Writing Boundary
To prevent write conflicts and guarantee file integrity:
*   **The Sole Writer**: The Tauri Rust native-fs layer (`apps/studio/tauri`) is the **sole writer** authorized to modify skill source files (`GRAPH.md`, phase `.md` files) on disk.
*   **Agent Boundary**: The Python backend and conversation agents operate in a read-only space for skill files. They cannot write source files directly. Instead, agents propose changes as patch requests to the client, which are then written to disk by the Rust native-fs layer.

## 4. Configuration Map
Configurations and environment mappings are partitioned to prevent unauthorized access:
*   **Workspace Runtime Config**: `.workspace/runtime_config.json` stores import file bindings, model override candidates, and runtime parameters (`[[KB-11-workspace-runtime]]`).
*   **Application Settings**: `app_settings.json` holds host configurations, editor options, and global paths.
*   *Note: Application settings files are excluded from direct edit access by conversational agents. Changes must flow through service-layer APIs.*
