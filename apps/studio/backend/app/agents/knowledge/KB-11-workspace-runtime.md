---
related:
  - KB-00-hub
  - KB-07-compile-diagnostics
  - KB-09-run-trace-checkpoint
  - KB-13-studio-gates-tools
---

> Distilled from: engine skill-spec runtime appendix & `docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md`

# KB-11: Workspace & Runtime Specifications

This document outlines the local directory structure, configuration contracts, and membership rules that govern the active skill workspace.

## 1. Directory Structure (`.workspace/`)
The `.workspace/` directory contains all transient configurations, execution outputs, and state mirrors. It must not be committed to the skill's source control repository.

```text
<skill-root>/
├── GRAPH.md                          # Skill DAG and topology definition
├── phases/                           # Directory containing phase implementations
└── .workspace/                       # Runtime environment folder (gitignored)
    ├── runtime_config.json           # Single source of truth for runtime config
    ├── import_files/                 # Temp mirrors of imported external files
    ├── runs/                         # Execution records (trace.jsonl, checkpoints)
    └── golden/                       # Golden evaluation data and reports
```

## 2. Configuration Contracts
*   **Single Source of Truth**: `.workspace/runtime_config.json` is the sole file that configures active run parameters, variable inputs, and endpoint mappings.
*   **Import Mirroring**: Any external files imported into the workspace (e.g. source documents or test cases) are mirrored under `.workspace/import_files/` to ensure the running engine accesses files locally and consistently.

## 3. Subgraph Workspace Membership
*   **Inline Subgraph Resolution**: Subgraph references within a skill resolve via absolute file system paths.
*   **Membership Inclusion Rule**:
    *   If a subgraph's absolute path lies **inside** the parent skill's directory tree (e.g., `<skill-root>/subgraph/sub-a/`), it is automatically considered a member of the workspace.
    *   If the subgraph path is located **outside** the parent skill's directory tree, the path must be registered in the workspace configurations so the compiler and copilot can resolve it.
