# Test Fixture: broken story-deconstruction (inline `<phase>` XML)

Preserved on 2026-05-12 for future "一键修复" (one-click repair) feature testing in Studio Copilot.

## Validation error this fixture reproduces

```
Field required at /home/sevenx/coding/agent-harness/skills/story-deconstruction/SKILL.md
  field: graph.phases
```

## Why it fails

The SKILL.md declares phases using inline `<phase id="...">` XML blocks instead of a YAML `phases:` list. The schema-2.0 loader (graph-agent MVP-0 B1 onwards) only recognizes the YAML form — inline phase XML was a V2-subgraph-style draft that never landed.

## How the "一键修复" feature should treat this

When a user opens a SKILL whose compile-guard returns a `graph.phases required` error AND the file contains `<phase ...>` blocks, Studio Copilot's repair flow should:

1. Detect that the structure is "inline-phase XML" (regex match on `<phase[^>]*>`).
2. Offer a single button: **一键修复 → 转换为 YAML phases**.
3. Click → pre-fill Copilot prompt with:
   - The current SKILL.md content as context.
   - Instruction: "convert inline `<phase>` XML blocks to a top-level YAML `phases:` list; preserve every phase's name, depends_on, and child fields verbatim under the new YAML phase entry; drop `subgraph:` references since the loader no longer supports them, replace with `mode: logic` + `execute_steps` stub OR `mode: llm` + inline prompt; emit fixed SKILL.md back."
   - Send to selected LLM (Claude / DeepSeek / Gemini / OpenAI).

## Counterpart "correct" version

After repair, the expected target shape is what now ships at `skills/story-deconstruction/SKILL.md` (the working version).
