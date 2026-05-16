# CODEMOD_REPORT

- source: `SKILL.md`
- out_dir: `<codemod-output>`

## Written files

- `GRAPH.md`
- `io/inputs.json`
- `io/outputs.json`
- `phases/assemble/LOGIC.md`
- `phases/continuity/SKILL.md`
- `phases/entity_and_characters/SKILL.md`
- `phases/parallel_analysis/SKILL.md`
- `phases/prepare/LOGIC.md`

## Review markers

- `phases/prepare/LOGIC.md`: logic phase has multiple execute_steps
- `phases/prepare/LOGIC.md`: missing exit_contract; generated default candidate
- `phases/entity_and_characters/SKILL.md`: missing exit_contract; generated default candidate
- `phases/entity_and_characters/SKILL.md`: legacy output_schema requires human mapping
- `phases/entity_and_characters/SKILL.md`: legacy llm_role requires human review
- `phases/parallel_analysis/SKILL.md`: missing exit_contract; generated default candidate
- `phases/parallel_analysis/SKILL.md`: legacy output_schema requires human mapping
- `phases/parallel_analysis/SKILL.md`: legacy llm_role requires human review
- `phases/continuity/SKILL.md`: missing exit_contract; generated default candidate
- `phases/continuity/SKILL.md`: legacy output_schema requires human mapping
- `phases/continuity/SKILL.md`: legacy llm_role requires human review
- `phases/assemble/LOGIC.md`: logic phase has multiple execute_steps
- `phases/assemble/LOGIC.md`: missing exit_contract; generated default candidate
- `phases/assemble/LOGIC.md`: legacy validator requires human mapping

## Mapping decisions

- io.inputs/io.outputs -> io/inputs.json + io/outputs.json
- YAML phases[] -> GRAPH.md phase tags + phases/<id> node files
