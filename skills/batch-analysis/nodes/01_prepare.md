<phase_config>
name: prepare
tools:
  - script.accumulator.load_accumulated_state
  - script.accumulator.build_batch_context_text
  - script.paths.format_batch_events
  - script.paths.format_dynamic_dimensions_hint
</phase_config>
