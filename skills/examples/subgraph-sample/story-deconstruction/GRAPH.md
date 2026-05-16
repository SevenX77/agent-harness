---
schema_version: "2.1"
name: story-deconstruction-subgraph
description: "Reference composition of the four-stage story deconstruction pipeline using V2.1 SUBGRAPH phases."
metadata:
  legacy_type: graph
  context_mapping:
    chapters: "{input.chapters}"
    project_id: "{input.project_id}"
    segmented_chapters: ""
    events_by_chapter: ""
    batch_outputs: ""
    accumulated_context: ""
    entity_registry: ""
    story_framework: ""
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="segmentation" src="phases/segmentation" />
<phase id="event_extraction" src="phases/event_extraction" depends_on="segmentation" />
<phase id="batch_analysis" src="phases/batch_analysis" depends_on="event_extraction" />
<phase id="global_synthesis" src="phases/global_synthesis" depends_on="batch_analysis" />
