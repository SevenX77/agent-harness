---
mode: logic
name: assemble
metadata:
  legacy_validator: script.validators.validate_batch_analysis
  legacy_execute_steps:
  - script.paths.assemble_batch_results
  - script.accumulator.update_accumulator
  - script.accumulator.save_accumulated_state
---
<!--TODO: CODEMOD_REVIEW: logic phase has multiple execute_steps-->
<!--TODO: CODEMOD_REVIEW: missing exit_contract; generated default candidate-->
<!--TODO: CODEMOD_REVIEW: legacy validator requires human mapping-->
<python_callable>
script.paths.assemble_batch_results
</python_callable>
