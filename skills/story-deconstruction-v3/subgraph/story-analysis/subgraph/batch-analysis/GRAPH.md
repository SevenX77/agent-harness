---
schema_version: "v0.3.0"
name: batch-analysis
description: Analyze one event batch with entity registration, six parallel dimensions, and continuity checks.
io:
  inputs:
    type: object
    required: [current_batch, analysis_state, para_text_lookup, dynamic_dimensions]
    properties:
      current_batch: {type: object}
      analysis_state: {type: object}
      para_text_lookup:
        type: object
      dynamic_dimensions:
        type: array
        items:
          type: string
  outputs:
    type: object
    required: [updated_state]
    properties:
      updated_state: {type: object}
phases: [prepare, entity_and_characters, tension, system, prop, arc, foreshadow, spatiotemporal, format_continuity, continuity, assemble]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare">entity_and_characters</phase>
<phase depends_on="entity_and_characters">tension</phase>
<phase depends_on="entity_and_characters">system</phase>
<phase depends_on="entity_and_characters">prop</phase>
<phase depends_on="entity_and_characters">arc</phase>
<phase depends_on="entity_and_characters">foreshadow</phase>
<phase depends_on="entity_and_characters">spatiotemporal</phase>
<phase depends_on="entity_and_characters">format_continuity</phase>
<phase depends_on="format_continuity">continuity</phase>
<phase depends_on="tension,system,prop,arc,foreshadow,spatiotemporal,continuity" output>assemble</phase>
