---
actions:
  - format_segments_for_prompt
validator: false
io:
  inputs:
    type: object
    required: [chapter_segmentation]
    properties:
      chapter_segmentation:
        type: object
  outputs:
    type: object
    required: [formatted_paragraphs, chapter_number, chapter_segmentation]
    properties:
      formatted_paragraphs:
        type: string
      chapter_number:
        type: integer
      chapter_segmentation:
        type: object
---

<action>format_segments_for_prompt</action>
