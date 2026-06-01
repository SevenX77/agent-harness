---
actions:
  - extract_all_events
io:
  inputs:
    type: object
    required: [all_segmentations]
    properties:
      all_segmentations:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [all_events, total_events, total_chapters]
    properties:
      all_events:
        type: array
        items:
          type: object
      total_events:
        type: integer
      total_chapters:
        type: integer
---
<action>extract_all_events</action>
