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

## Subagent Dispatch and ID Bindings
- **Fate Agent ID Bindings**: The three specialized subagents (Clotho, Lachesis, Atropos) are dispatched from the CLI using the standard `ah ask` command.
- **Dispatch Command**: Use `ah ask <id> --wait` to delegate a subtask, where the `<id>` maps to the target Fate's agent identifier:
  - `clotho`: Domain Analysis, Graph Design, and Agent Prompt Design.
  - `lachesis`: Compile Error Repair and Graph Design.
  - `atropos`: Evaluation Judgement and Agent Prompt Design.
