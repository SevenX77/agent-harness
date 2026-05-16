---
mode: subgraph
name: event_extraction
---
<sub_skill_ref>
../../../../../event-extraction
</sub_skill_ref>
<context_bridge>
inputs:
  segmentation_result: "{context.segmented_chapters}"
outputs:
  events_by_chapter: "{subgraph.event_timeline}"
</context_bridge>
