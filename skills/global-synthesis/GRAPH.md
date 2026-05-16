---
schema_version: "2.1"
name: global-synthesis
description: "Global synthesis after all batch analyses complete."
metadata:
  legacy_type: graph
  phase_io:
    global_analysis:
      inputs: [batch_outputs, accumulated_context, entity_registry]
      outputs: [climax_ranking, foreshadowing_closure, character_ranking]
    scene_assembly:
      inputs: [batch_outputs, climax_ranking, foreshadowing_closure, character_ranking]
      outputs: [unified_event_stream, scenes]
    retroactive:
      inputs: [unified_event_stream, scenes, accumulated_context]
      outputs: [retroactive_corrections, corrected_event_stream]
    export:
      inputs: [corrected_event_stream, scenes, climax_ranking, foreshadowing_closure, character_ranking, retroactive_corrections]
      outputs: [story_framework]
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="global_analysis" src="phases/global_analysis" />
<phase id="scene_assembly" src="phases/scene_assembly" depends_on="global_analysis" />
<phase id="retroactive" src="phases/retroactive" depends_on="scene_assembly" />
<phase id="export" src="phases/export" depends_on="retroactive" />
