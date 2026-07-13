---
name: compile-error-repair
description: Debug and repair compilation or linting errors (identifying [F-v3-*] error codes, locating root causes, and applying minimal fixes) for a graph_skill.
---

# Skill: Compilation Error Repair

This skill defines the debugging process to resolve graph compilation, linting, and structural configuration defects.

## 1. Troubleshooting Workflow

1.  **Retrieve Complete Diagnostic Details**: Read the entire diagnostic log containing the `[F-v3-*]` error codes and target line numbers. Never start fixing issues based on partial or hearsay errors (`[[KB-07-compile-diagnostics]]`).
2.  **Lookup Error Semantics**: Search for the exact error code inside the knowledge base (`[[KB-07-compile-diagnostics]]`) to understand its triggers, constraints, and standard remediations. Do not guess the meaning of an error code.
3.  **Read Referenced Files**: Load and read the files containing the errors (e.g. `GRAPH.md`, Mode files, Python actions) at the absolute line numbers provided (`[[KB-11-workspace-runtime]]`).
4.  **Identify the Error Category**:
    *   *Name Mismatch*: Verify name alignment across phases (`GRAPH.md` frontmatter, `<phase>` tags, and subdirectory paths).
    *   *DAG Cycle or Island*: Check `depends_on` connections to ensure all nodes trace back to `"input"` and resolve to `"output"`.
    *   *Schema Incompatibilities*: Align upstream output schemas with downstream input keys.
    *   *Action Signature Defects*: Match Python function definitions (`def phase_name(inputs): ...`) with LOGIC file specifications (`[[KB-03-logic-actions]]`).
    *   *Predict Mock / finish_task Shape*: If the failure appears only in Predict with custom mocks on an agent node using `tools: [finish_task]`, check the P1 mock format in `[[KB-08-predict]]`. The mock must be a `{phase_name: output_object}` JSON payload; Predict wraps it into the `finish_task` tool call and `## item-1` fenced JSON internally.
5.  **Apply Minimal Target Repairs**: Modify only the code or files responsible for the root defect. Avoid broad, unrelated refactorings that mask the primary issue.
6.  **Re-Compile & Verify**: Trigger compilation to verify the fix. Repeat the steps if new error codes emerge.

## 2. Anti-Patterns
*   ❌ Guessing solutions or modifying code before reading the source files and checking the exact error lines.
*   ❌ Attempting to fix multiple unrelated error categories at once, preventing incremental verification.
*   ❌ Relying on memory or outdated assumptions instead of looking up error code contracts in the knowledge base.
