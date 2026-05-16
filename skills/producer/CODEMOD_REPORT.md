# CODEMOD_REPORT

- source: `skills/producer/SKILL.md`
- codemod candidate: generated but not adopted
- legacy type: `persona`
- migration: manual V2.1 single SKILL phase

## Manual decisions

- The former persona role profile is now the producer phase `<system_prompt>`.
- The legacy review subskill prompt and scoring rules are internalized into the producer phase.
- `reviewer` is declared as a critic Tool and is intentionally not a graph dependency.
- Terminal output is validated through `finish_task` and `io/outputs.json`.
