# CODEMOD_REPORT

- source: `SKILL.md`
- out_dir: `<codemod-output>`

## Written files

- `GRAPH.md`
- `io/inputs.json`
- `io/outputs.json`
- `phases/review/SKILL.md`
- `phases/segment/SKILL.md`
- `phases/setup/LOGIC.md`

## Review markers

- `phases/setup/LOGIC.md`: missing exit_contract; generated default candidate
- `phases/segment/SKILL.md`: missing exit_contract; generated default candidate
- `phases/segment/SKILL.md`: legacy validator requires human mapping
- `phases/segment/SKILL.md`: legacy output_schema requires human mapping
- `phases/segment/SKILL.md`: legacy llm_role requires human review
- `phases/review/SKILL.md`: missing exit_contract; generated default candidate
- `phases/review/SKILL.md`: legacy validator requires human mapping
- `phases/review/SKILL.md`: legacy output_schema requires human mapping
- `phases/review/SKILL.md`: legacy retry_target requires human mapping
- `phases/review/SKILL.md`: legacy max_retries requires human mapping
- `phases/review/SKILL.md`: legacy llm_role requires human review

## Mapping decisions

- io.inputs/io.outputs -> io/inputs.json + io/outputs.json
- YAML phases[] -> GRAPH.md phase tags + phases/<id> node files
