---
actions:
  - format_continuity_context
validator: false
io:
  inputs:
    type: object
    required: [character_results]
    properties:
      character_results:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [batch_character_changes_text]
    properties:
      batch_character_changes_text:
        type: string
---

<action>format_continuity_context</action>
