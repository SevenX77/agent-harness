---
mode: subgraph
name: segmentation
---
<sub_skill_ref>
../../../../../text-segmentation
</sub_skill_ref>
<context_bridge>
inputs:
  chapters: "{context.chapters}"
outputs:
  segmented_chapters: "{subgraph.segmentation_result}"
</context_bridge>
