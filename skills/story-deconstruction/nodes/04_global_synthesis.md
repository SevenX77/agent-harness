<phase_config>
name: global_synthesis
subgraph: ../global-synthesis/SKILL.md
context_bridge:
  inputs:
    all_batch_results: batch_outputs
    final_accumulated: accumulated_context
    entity_registry: entity_registry
  outputs:
    story_framework: story_framework
</phase_config>
