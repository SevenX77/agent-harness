---
mode: logic
name: prepare
metadata:
  legacy_execute_steps:
  - script.accumulator.load_accumulated_state
  - script.accumulator.build_batch_context_text
  - script.paths.format_batch_events
---
<!--TODO: CODEMOD_REVIEW: logic phase has multiple execute_steps-->
<!--TODO: CODEMOD_REVIEW: missing exit_contract; generated default candidate-->
<python_callable>
script.accumulator.load_accumulated_state
</python_callable>
