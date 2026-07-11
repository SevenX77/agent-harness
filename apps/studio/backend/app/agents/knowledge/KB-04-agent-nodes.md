---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-05-subgraph
  - KB-08-predict
  - KB-12-llm-roles
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §5 & §8 & §2 (Effective Role Chain)

# KB-04: Agent Nodes & Mentions

An Agent phase (`SKILL.md`) executes an LLM-powered agent node. It defines the agent's persona, goals, operating steps, protocols, and allowable tool/subagent resources.

## 1. SKILL.md Structure
An Agent phase must declare its boundary metadata and resources in its frontmatter, and define its prompt instructions in its XML-formatted body.

### Frontmatter Schema:
*   `llm_role`: The LLM role for the node (`[[KB-12-llm-roles]]`).
*   `use_graph_llm_role`: Boolean switch (default `false`). When `true`, the root `llm_role` declared in `GRAPH.md` takes precedence over this node's `llm_role` without deleting the local value.
*   `max_iterations`: Integer (default `10`). Limits the maximum reasoning cycles for the agent.
*   `tools`: List of tools the agent can invoke.
*   `subagents`: List of sub-skills the agent can delegate tasks to at runtime.
*   `subgraphs`: List of child subgraphs the agent can execute.
*   `references` / `examples`: Reference resources.

### Body XML Tags:
The body of `SKILL.md` must adhere to these precise XML elements:
*   `<role>`: Exactly one tag defining the agent's persona.
*   `<goal>`: Exactly one tag defining the target.
*   `<step id="..." name="...">`: Zero or more tags defining recommended steps.
*   `<protocol id="...">`: Zero or more tags defining rules the agent must obey.
*   `<example id="...">`: Zero or more inline dialogue or behavior examples.

*Note: Grouping containers such as `<steps>`, `<protocols>`, or `<examples>` are prohibited. Writing `<exit_contract>` in the body is also forbidden.*

## 2. Mentions & Reachability
Agent prompts reference declared resources using obsidian-style `@` mentions. The compiler strictly validates that all mentions are statically reachable:

*   **Tools**: `@tool:<name>` must resolve to an entry in `tools`.
*   **Subagents**: `@subagent:<name>` must resolve to `subagents[].name`.
*   **Subgraphs**: `@subgraph:<name>` must resolve to `subgraphs[].name`.
*   **References**: `@reference:<id>` must resolve to `references[].id`.
*   **Examples**: `@example:<id>` must resolve to body inline `<example id>` or frontmatter `examples[].id`.
*   **Protocols**: `@protocol:<id>` must resolve to body `<protocol id>`.

Unresolvable mentions trigger a compilation failure (`[[KB-07-compile-diagnostics]]`).

## 3. Subagents vs. Subgraphs
There is a clear architectural boundary between delegating to a subagent and calling a subgraph:

*   **Subagent delegation**: Declared as `subagents`. A subagent is a runtime reference using `target_skill` (e.g., `target_skill: producer_review_skill`). The host materializes and coordinates it dynamically.
*   **Subgraph invocation**: Declared as `subgraphs`. A subgraph is a structural compile-time inclusion using a physical relative directory `path` (e.g., `path: subgraph/evidence_pipeline`). The compiler packages and validates the sub-skill layout statically.
*   *Note: Defining `target_skill` inside a `subgraphs` entry is invalid.*

## 4. LLM Role Decision Chain
The host resolve chain for determining which LLM configuration an agent phase runs with is:
1.  If `use_graph_llm_role: true` -> use root `llm_role` defined in `GRAPH.md` -> fallback.
2.  If `use_graph_llm_role: false` (default) -> use node-level `llm_role` -> root `llm_role` -> fallback.
3.  **Fallback**: The system-level default role name is `"graph_agent"`.
