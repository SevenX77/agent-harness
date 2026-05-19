# Graph Agent: Fundamental Architectural Axioms

**Status**: Inviolable rules for the entire Graph Agent ecosystem.
**Purpose**: This document defines the macro-level, philosophical, and structural boundaries of the `graph_agent` framework. It is not just about syntax; it is about *what this system is* and *what it is not*. Any feature, refactor, or skill design that violates these axioms undermines the framework's integrity and must be rejected.

---

## Axiom 1: The Kitchen-Pass Principle (Strict Separation of Concerns)
The framework is the Kitchen; the skills are the Recipes.
*   **The Framework is Domain-Agnostic**: The `graph_agent` engine must **never** contain business logic, hardcoded prompt strings for specific tasks, or domain-specific data parsing. Its sole responsibility is orchestration, state management, and error routing.
*   **Skills are Engine-Agnostic**: A `SKILL.md` (or `GRAPH.md`) and its associated Python scripts must **never** attempt to manipulate the LangGraph state machine directly, monkey-patch the engine, or bypass the runtime harness.

## Axiom 2: Document-Driven Orchestration (Docs as Code)
The graph is not built in Python; it is built in Markdown/YAML.
*   **The Manifest is the AST**: The textual document (`GRAPH.md` / `SKILL.md`) is the absolute Single Source of Truth. The execution graph is dynamically compiled from this document.
*   **No Python Orchestration Scripts**: Developers must not write `script/orchestrator.py` loops with manual `run_skill()` calls to compose workflows. If orchestration is needed, it must be declared statically in the Document via `phases` and `depends_on`.

## Axiom 3: The Law of Node Purity (One Brain Per Phase)
A single node (Phase) in the graph can only possess one type of cognition or execution model. Hybrid nodes are strictly forbidden.
*   **LLM Phase (`mode: agent/llm`)**: Driven by an LLM ReAct loop. It thinks, uses bounded tools, and must explicitly call `finish_task`.
*   **Logic Phase (`mode: logic`)**: Driven purely by deterministic Python code. It has god-mode access to the blackboard but zero LLM reasoning capabilities.
*   **Subgraph Phase (`mode: subgraph`)**: Driven by delegation. It executes another completely independent graph and waits for the result.
*   *Violation*: Attempting to put a `<system_prompt>` inside a `Logic` node, or attempting to write a Python `execute_flow` inside an `LLM` node, is an architectural violation.

## Axiom 4: The Global Blackboard (Implicit State Transfer)
Nodes in the graph do not pass data point-to-point like traditional function calls. They communicate via a globally shared dictionary (the LangGraph State/Context).
*   **Convention Over Configuration**: A downstream node reads what an upstream node wrote by agreeing on the variable name (e.g., `{raw_text}`).
*   **No Intra-Skill Mappers**: Do not build translation layers or mapping nodes just to rename variables between Phase 1 and Phase 2.
*   **Explicit Bridges for Subgraphs Only**: The only place explicit data mapping is allowed is at the boundary of a Subgraph, acting as an API gateway to an external skill's blackboard.

## Axiom 5: Deterministic Macro-Routing vs. Autonomous Micro-Routing
The framework dictates *what* happens next; the LLM dictates *how* to solve the current step.
*   **Static Graph Topology**: The sequence of phases (Phase A -> Phase B -> Phase C) is hardcoded by the human in the `GRAPH.md`. **The LLM is never allowed to decide which Phase to execute next.** This prevents catastrophic infinite loops and unpredictable behavior common in AutoGPT-style systems.
*   **Bounded LLM Autonomy**: The LLM's autonomy is strictly contained *within* a single Phase. It can loop, think, and call tools as many times as it needs to satisfy the current phase's goal, but once it calls `finish_task`, control is irrevocably returned to the deterministic Graph engine.

## Axiom 6: Framework-Managed Persistence (Stateless Skills)
Skills must be side-effect free regarding local file persistence unless explicitly configured via the framework.
*   **No Rogue File IO**: Python scripts inside `actions/` or `tools/` should not write `output.json` directly to the local disk using `open()`.
*   **Declarative IO Contracts**: All outputs must be declared in the IO JSON Schemas and yielded to the framework. The framework's `IOManager` (and the host project's Artifact Manager) assumes sole responsibility for determining where, how, and with what versioning the data is stored.