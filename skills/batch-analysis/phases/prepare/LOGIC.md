---
actions:
  - prepare_batch
io:
  inputs:
    type: object
    required: [batch_events, accumulated_context, para_text_lookup, dynamic_dimensions, chapter_range]
    properties:
      batch_events:
        type: array
      accumulated_context:
        type: object
      para_text_lookup:
        type: object
      dynamic_dimensions:
        type: array
      chapter_range:
        type: array
  outputs:
    type: object
    required: [batch_events_text, accumulated_context_text, batch_chapter_range, dynamic_dimensions_hint, batch_event_count, accumulator]
    properties:
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
      accumulator:
        type: object
---

<action>prepare_batch</action>
