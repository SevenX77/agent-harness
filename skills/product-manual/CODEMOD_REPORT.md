# CODEMOD_REPORT

- source: `skills/product-manual/SKILL.md`
- written candidate files: 5
- initial review markers: 3
- remaining review markers: 0

## Manual decisions

- `product_specs` legacy `json` maps to an object schema in `io/inputs.json`.
- `final_manual` legacy `markdown` maps to a string artifact in `io/outputs.json`.
- Legacy `script.extract.get_highlights`, `script.scenarios.generate`, and `script.report.synthesize` had no local script package, so they were not migrated as V2.1 Actions or Tools.
- The three legacy prompt phases are preserved as SKILL phases with explicit `exit_contract` blocks.
