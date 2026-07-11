---
related:
  - KB-01-skill-anatomy
  - KB-02-io-dataflow
  - KB-03-logic-actions
  - KB-04-agent-nodes
  - KB-05-subgraph
  - KB-06-iterate
  - KB-07-compile-diagnostics
  - KB-08-predict
  - KB-09-run-trace-checkpoint
  - KB-10-golden
  - KB-11-workspace-runtime
  - KB-12-llm-roles
  - KB-13-studio-gates-tools
---

# KB-00: Knowledge Hub Index

Welcome to the Graph Skill Knowledge Base. This index maps development scenarios, compiler contracts, and tooling specifications to dedicated Knowledge Base (KB) documents.

## 1. Linking Rules & Resolution
*   **Obsidian-style Links**: All knowledge documents use `[[KB-xx-name]]` format for concepts and reference mappings.
*   **Resolution Protocol**: The system resolves links dynamically by matching the stem filename of the target document within the `knowledge/` directory.

## 2. Scenario-to-KB Routing Map

| Scenario / Development Stage | Recommended KB Entry | Description |
|---|---|---|
| **Skill Layout & File Grammar** | `[[KB-01-skill-anatomy]]` | *[Placeholder]* Layout, `GRAPH.md` format, and name consistency. |
| **Dataflow, Schemas, & Blackboard** | `[[KB-02-io-dataflow]]` | *[Placeholder]* Schema rules and blackboard operations. |
| **Python Actions & Logic Purity** | `[[KB-03-logic-actions]]` | *[Placeholder]* Action signatures, purity limits, and validators. |
| **LLM Agent Nodes & Prompts** | `[[KB-04-agent-nodes]]` | *[Placeholder]* Structuring agent instructions and mentions. |
| **Subgraph Inclusion** | `[[KB-05-subgraph]]` | *[Placeholder]* Subgraph path resolution and contracts. |
| **Loops & Batch Iterations** | `[[KB-06-iterate]]` | *[Placeholder]* Iterate loop mechanics and accumulators. |
| **Compilation & Syntax Errors** | `[[KB-07-compile-diagnostics]]` | SSOT diagnostic pipelines and `[F-v3-*]` error codes. |
| **LLM-Free Dry Runs & Mocks** | `[[KB-08-predict]]` | Predict mock levels (P0-P2) and the 409 conflict guard. |
| **Runtime Execution & Debugging** | `[[KB-09-run-trace-checkpoint]]` | `trace.jsonl` logs, checkpoints, namespaces, and overrides. |
| **Output Evaluation & Baselines** | `[[KB-10-golden]]` | Seeding baselines, schema invalidation, and diff reports. |
| **Workspace Paths & Configurations** | `[[KB-11-workspace-runtime]]` | `.workspace/` layout, runtime configurations, and mirrors. |
| **LLM Roles, Credentials, & fallbacks**| `[[KB-12-llm-roles]]` | *[Placeholder]* Model routing, fallback chain, and configs. |
| **Compilation Gates & Tool Maps** | `[[KB-13-studio-gates-tools]]` | *[Placeholder]* Build pipeline gates and tool boundaries. |
