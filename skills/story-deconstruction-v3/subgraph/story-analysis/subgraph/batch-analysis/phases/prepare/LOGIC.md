---
actions:
  - prepare_batch
validator: false
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
  outputs:
    type: object
    required: [batch_events, batch_events_text, accumulated_context_text, batch_chapter_range, dynamic_dimensions_hint, batch_event_count, accumulator_state, character_latest_states_text, batch_character_changes_text]
    properties:
      batch_events:
        type: array
      batch_events_text:
        type: string
      accumulated_context_text:
        type: string
      batch_chapter_range:
        type: string
      dynamic_dimensions_hint:
        type: string
      batch_event_count:
        type: integer
      accumulator_state:
        type: object
      character_latest_states_text:
        type: string
      batch_character_changes_text:
        type: string
---

<action>prepare_batch</action>
