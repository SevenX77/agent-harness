---
name: graph-design
description: Design and construct a graph_skill (partitioning phases, connecting the DAG, and defining I/O schemas) when creating new skills or refactoring existing graph structures.
---

# Skill: Graph Skill Design

This skill defines the structured sequence for designing, configuring, and organizing a new or refactored graph skill.

## 1. Methodology Workflow

1.  **Define Root Boundaries**: Establish the minimum input fields and final expected outputs. Formulate these boundaries into a root schema contract (`[[KB-02-io-dataflow]]`).
2.  **Partition Workflows (Single Responsibility)**: Slice the business workflow into isolated phases. For each phase, assign one of the following execution modes:
    *   **Deterministic Actions**: Use `LOGIC.md` with Python actions for parser, formatter, or filter operations (`[[KB-03-logic-actions]]`). Never use LLM agents for tasks that can be performed deterministically.
    *   **Language Understanding/Generation**: Use LLM agent nodes (`[[KB-04-agent-nodes]]`).
    *   **Sub-Workflows**: Delegate to a nested subgraph (`[[KB-05-subgraph]]`).
    *   **External Skills**: Outsource to an independent skill (`[[KB-01-skill-anatomy]]`).
3.  **Construct the DAG**: Connect the nodes starting from `depends_on = "input"` to the final output node. Keep execution paths as parallel as possible; avoid forcing sequential dependencies unless data dependencies require them.
4.  **Formulate Phase Schemas**: Map outputs from upstream phases to the inputs of downstream phases, ensuring fields match name, type, and nesting constraints exactly (`[[KB-02-io-dataflow]]`).
5.  **Iterative Implementation**: Build the skill incrementally.
    *   Create the skeleton `GRAPH.md` first and compile it (`[[KB-07-compile-diagnostics]]`).
    *   Add phase folders and modes one by one, compiling at each step.
    *   Run predictions (`[[KB-08-predict]]`) to verify dataflow mappings before executing real runs.

## 2. Structural Mappings
Ensure absolute consistency for all phase identifiers:
*   The folder name under `phases/`.
*   The phase key listed under the `phases` block in `GRAPH.md` frontmatter.
*   The `<phase id="name">` tag in the body of `GRAPH.md`.

Refer to `[[KB-01-skill-anatomy]]` for layout conventions and folder specs.

## 3. Anti-Patterns
*   ❌ Combining parsing, evaluation, and LLM text generation into a single phase.
*   ❌ Implementing a complex skill entirely before running the compiler for the first time.
*   ❌ Accumulating unused fields in I/O schemas for "future possibilities".
