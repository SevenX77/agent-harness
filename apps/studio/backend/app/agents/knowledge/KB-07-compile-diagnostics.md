---
related:
  - KB-00-hub
  - KB-08-predict
  - KB-11-workspace-runtime
  - KB-13-studio-gates-tools
---

> Distilled from: `docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md` (F6 + 2026-07-05 Data-Chain Clarification) & engine `error_registry.py` & `docs/studio/mvp1/01_workflows/03_compile.md`

# KB-07: Compile & Diagnostics Pipeline

The compilation and diagnostic pipeline serves as the primary gateway for validating a skill's structure and configuration before execution. 

## 1. Single Exit Architecture (SSOT)
*   **Engine Core Exit**: The sole engine compile entry point is `graph_agent.core.compiler.compile_skill(...)` (implemented internally by `SkillLoader.compile_skill(...)`).
*   **Studio Pipeline Integration**: The Studio backend routes all real-time linting, first-screen checks, and manual compile commands through this single pipeline. It combines engine diagnostics with Studio-owned preflight diagnostics (e.g. checking `.workspace/runtime_config.json`, `.workspace/import_files/`, and `.workspace/golden`).
*   **Aggregated Output**: The compilation pipeline yields the **entire set** of errors and warnings rather than stopping at the first failure. Correcting one defect will not mask subsequent syntax or configuration errors of the same compile stage.

## 2. Compile Capabilities

### What Compilation Can Check:
*   **Skill Layout & Format**: Confirms the presence and format of `GRAPH.md`, ensuring the `schema_version` matches precisely `"v0.3.0"`.
*   **DAG Topology**: Detects circular dependencies (`[F-v3-graph-phase-cycle]`), unreachable phases (`[F-v3-graph-phase-island]`), and phase name mismatches.
*   **Phase/Directory Mappings**: Validates "three-name consistency": the frontmatter phase key, the body `<phase>` tag, and the corresponding subdirectory under `phases/` must match exactly.
*   **Input/Output Schemas**: Validates draft2020-12 JSON schemas and checks that downstream inputs match upstream outputs.
*   **Action Signatures & Purity**: Verifies that Python actions under `actions/` exist and match signatures (`def <name>(inputs): ...`), rejecting unsafe imports or dynamic scripting.
*   **Mentions Reachability**: Assures that mentions like `@tool:`, `@subagent:`, `@subgraph:`, `@reference:`, `@example:`, and `@protocol:` point to valid resources.

### What Compilation Cannot Check:
*   **Workspace Input Values**: Actual data shapes or contents stored in `.workspace/` at runtime.
*   **LLM Role Accessibility**: Whether LLM routes, credentials, or remote endpoints are valid and responsive (`[[KB-12-llm-roles]]`).
*   **Runtime Execution Failures**: Semantic Python logic exceptions or non-structural execution-stage errors.

## 3. Error Codes & Diagnostics
Defects are reported using structured `[F-v3-*]` error codes (e.g., `[F-v3-graph-phase-cycle]`, `[F-v3-io-schema-mismatch]`). Each code maps to a precise remediation step registered within the engine's error catalog.

## 4. Engineering & Repair Disciplines
*   **Compile-Pass Gate**: A compile-pass is a hard prerequisite for running prediction or execution (`[[KB-13-studio-gates-tools]]`).
*   **Structured Repair**: Resolve compilation errors at the root cause (e.g., correcting mismatched schema fields or fixing topology connections). Never override values manually to bypass gates.
