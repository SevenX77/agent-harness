# CODEMOD_REPORT

- source: `skills/examples/subgraph-sample/story-deconstruction/SKILL.md`
- written candidate files: 5
- initial review markers: 1
- remaining review markers: 0

## Manual decisions

- Codemod only emitted the first phase as a SKILL candidate, so this migration was completed manually.
- All four legacy `subgraph:` phases are V2.1 `SUBGRAPH.md` phases.
- `sub_skill_ref` values point to V2.1 skill root directories, not legacy `SKILL.md` files.
- Legacy context bridge text is preserved as raw documentation inside each SUBGRAPH phase.
