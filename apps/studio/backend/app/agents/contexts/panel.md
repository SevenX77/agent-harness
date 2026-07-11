<!--
  studio-agents source file — contexts/panel.md
  Assembled into: SDK session append
  Editing rules: English only · delta over the Claude Code base prompt (never
  restate or contradict it) · facts belong in knowledge/ (link, don't copy) ·
  no tool mechanics (enforced in code) · edit THIS file, never the assembled outputs.
-->

# Studio Panel Context Delta

This document outlines the surface mechanisms and runtime assumptions unique to the Studio Panel SDK environment.

## Context and Input Contracts
- **No Implicit State Injection**: Studio does not automatically pass active settings, selected nodes/edges, or user interface state. Rely only on explicitly mentioned entities or referenced objects passed in the query.
- **Golden Evaluation Tasks (`<judge_context>`)**: The appearance of a `<judge_context>` XML block signifies a golden dataset comparison and diagnostic run. It specifies file paths for the comparison run (`compare`) and the reference baseline (`baseline`). You must retrieve and read these files before analyzing the diagnostic differences or rendering judgment.

## Interface Presentation
- **Automatic Diff Visualization**: When writing or editing files via available tools, the panel automatically renders file changes as interactive diff cards for the user. Do not detail the specific character or line changes in your responses; state only the rationale behind the edits.

## Subagent Fleet Operations
- **Resident Subagent Availability**: The three specialized subagents (Clotho, Lachesis, Atropos) function as persistent, background-registered entities accessible at all times through native subagent dispatching tools. No status queries or initialization commands are needed to interact with them.
