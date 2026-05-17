# CODEMOD_REPORT

- source: `SKILL.md`
- out_dir: `<codemod-output>`

## Written files

- `GRAPH.md`
- `io/inputs.json`
- `io/outputs.json`
- `phases/greet/SKILL.md`

## Review markers

- `phases/greet/SKILL.md`: missing exit_contract; generated default candidate

## Mapping decisions

- io.inputs/io.outputs -> io/inputs.json + io/outputs.json
- XML body simple skill -> one SKILL phase candidate
