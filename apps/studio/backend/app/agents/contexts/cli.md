<!--
  studio-agents source file — contexts/cli.md
  Assembled into: .ah/rules/master.md, .ah/rules/clotho.md, .ah/rules/lachesis.md, .ah/rules/atropos.md
  Editing rules: English only · delta over the Claude Code base prompt (never
  restate or contradict it) · facts belong in knowledge/ (link, don't copy) ·
  no tool mechanics (enforced in code) · edit THIS file, never the assembled outputs.

  Baseline Version Note: This document is based on ah >= 1.4.0 as the CLI command base.
-->

# Studio CLI Context Delta

This document outlines the surface mechanisms and runtime assumptions unique to the CLI (ah / MoirAI) orchestration environment.

## Workspace Fact
- **Skill Workspace Root**: The project root directory is the active skill workspace. All operations, verification tests, compilation commands, and file edits should be scoped and executed within this directory.

## Knowledge Base Location
- The graph_skill knowledge base is materialized at `.ah/knowledge/` inside this workspace. `[[KB-xx-...]]` links resolve to files in that directory by stem filename (start at `.ah/knowledge/KB-00-hub.md`).

## Studio Tool Surface
- When Studio launched this session with its sidecar running, the `studio` MCP server is registered and the tool map in `[[KB-13-studio-gates-tools]]` applies here — call `compile_skill` / `predict_skill` directly instead of invoking the engine through ad-hoc Python.
- Read and probe tools are pre-allowed. Write and execute tools (skill create/fork/publish, run/resume/pause/stop, golden writes, LLM configuration) surface this CLI's own approval prompt: answer it in the terminal. The two credential-cascading deletes (`delete_llm_endpoint`, `delete_llm_route`) are intentionally absent from the CLI surface; do those in the Studio UI.
- If the `studio` tools are absent, the sidecar was unreachable at launch (Studio not running, or a WSL distro without mirrored networking). Say so and continue without them — do not reconstruct them by shelling into the engine.

## Subagent Dispatch and ID Bindings
- **Fate Agent ID Bindings**: The three specialized subagents (Clotho, Lachesis, Atropos) are dispatched from the CLI using the standard `ah ask` command.
- **Dispatch Command**: Use `ah ask <id> --wait` to delegate a subtask, where the `<id>` maps to the target Fate's agent identifier:
  - `clotho`: Domain Analysis, Graph Design, and Agent Prompt Design.
  - `lachesis`: Compile Error Repair and Graph Design.
  - `atropos`: Evaluation Judgement and Agent Prompt Design.
