---
actions:
  - format_segments_for_prompt
io:
  inputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
  outputs:
    type: object
    required: [formatted_paragraphs]
    properties:
      formatted_paragraphs:
        type: string
---

<action>format_segments_for_prompt</action>
