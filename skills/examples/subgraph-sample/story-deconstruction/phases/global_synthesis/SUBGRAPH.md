---
mode: subgraph
name: global_synthesis
---
<sub_skill_ref>
../../../../../global-synthesis
</sub_skill_ref>
<context_bridge>
inputs:
  batch_outputs: "{context.batch_outputs}"
  accumulated_context: "{context.accumulated_context}"
  entity_registry: "{context.entity_registry}"
outputs:
  story_framework: "{subgraph.story_framework}"
</context_bridge>
