---
mode: subgraph
name: batch_analysis
---
<sub_skill_ref>
../../../../../batch-analysis
</sub_skill_ref>
<context_bridge>
inputs:
  batch_events: "{context.events_by_chapter}"
  accumulated_context: "{context.accumulated_context}"
outputs:
  batch_outputs: "{subgraph.batch_result}"
  entity_registry: "{subgraph.entity_registry}"
</context_bridge>
