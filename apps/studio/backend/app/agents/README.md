# Prompt Assembly Contract

This document defines the assembly contract and rules for all assets in the `apps/studio/backend/app/agents/` directory. It is an editing reference for human developers and agent system components to ensure prompts are correctly maintained and assembled across different runtime modes (SDK Panel / CLI).

---

## 1. Source File Header Template

Every source file under `roles/`, `operating-manual.md`, and `contexts/` must begin with the following HTML comment block. This serves as metadata defining the file's role, destination targets, and editing constraints.

```markdown
<!--
  studio-agents source file — <relative-path-to-file>
  Assembled into: <destination-targets-separated-by-semicolons>
  Editing rules: English only · delta over the Claude Code base prompt (never
  restate or contradict it) · facts belong in knowledge/ (link, don't copy) ·
  no tool mechanics (enforced in code) · edit THIS file, never the assembled outputs.
-->
```

### Path & Destination Examples
- For `roles/moirai.md`:
  ```markdown
  <!--
    studio-agents source file — roles/moirai.md
    Assembled into: SDK session append; SDK subagent prompts; .ah/rules/master.md
    Editing rules: English only · delta over the Claude Code base prompt (never
    restate or contradict it) · facts belong in knowledge/ (link, don't copy) ·
    no tool mechanics (enforced in code) · edit THIS file, never the assembled outputs.
  -->
  ```

---

## 2. Assembly Output Specifications

Prompts are assembled differently depending on whether they are written to disk or loaded directly into memory for API sessions.

### A. Disk-Bound Assembly (e.g., `.ah/rules/*.md`)
For physical files materialized in the workspace, the full assembly path and details must be tracked using explicit start/end markers for each source file segment.

- **Header marker**: Declares the assembler and all files used in the assembly.
- **Section boundaries**: Surrounds the content of each contributing source file with a source path and its SHA-256 checksum (first 8 hex characters).

**Format Example:**
```markdown
<!-- assembled-by=studio sources=roles/moirai.md,operating-manual.md,contexts/cli.md -->
<!-- BEGIN assembled-section source=roles/moirai.md sha256=a1b2c3d4 -->
<content of roles/moirai.md>
<!-- END assembled-section source=roles/moirai.md -->
<!-- BEGIN assembled-section source=operating-manual.md sha256=e5f6a7b8 -->
<content of operating-manual.md>
<!-- END assembled-section source=operating-manual.md -->
```

*(Note: In actual workspace files, these are wrapped with the standard Studio managed file header and content hash for integrity and overwrite protection).*

### B. Memory-Bound Assembly (e.g., SDK Session Append, subagent system prompts)
For internal prompts loaded directly into memory for LLM execution, section-specific start/end markers are omitted to avoid polluting the LLM's context with implementation-level paths and files.

- **Header marker**: Declares the assembler and source files.
- **Body**: The raw joined content of the source files.

**Format Example:**
```markdown
<!-- assembled-by=studio sources=roles/moirai.md,operating-manual.md,contexts/panel.md -->
<content of roles/moirai.md>

<content of operating-manual.md>

<content of contexts/panel.md>
```

---

## 3. Editing Guidelines
1. **English Only**: All documentation and prompt source files must be written in English.
2. **Delta Principle**: Write only the delta relative to the Claude Code base prompt. Never duplicate, restate, or contradict standard rules or mechanics already provided by the base system.
3. **Externalize Facts to Knowledge**: Never inline configuration details, schemas, or factual parameters. Place them in `knowledge/` and reference them using `[[KB-XX]]` obsidian-style links.
4. **No Tool Mechanics**: The code enforces hard tool boundaries. Do not write procedural/mechanical rules about tools inside the prompt text.
5. **Single Source of Truth**: Always edit the source files in `apps/studio/backend/app/agents/`. Never modify assembled files directly, as they are regenerated automatically and will be overwritten.
