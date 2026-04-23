<phase_config>
name: assemble
tools:
  - script.paths.assemble_batch_results
  - script.accumulator.update_accumulator
  - script.accumulator.save_accumulated_state
validator: script.validators.validate_batch_analysis
max_retries: 1
retry_target: parallel_analysis
</phase_config>
