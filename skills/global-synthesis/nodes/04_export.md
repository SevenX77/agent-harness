<phase_config>
name: export
tools:
  - script.scene_builder.export_story_framework
validator: script.validators.validate_global_synthesis
max_retries: 1
retry_target: global_analysis
</phase_config>
