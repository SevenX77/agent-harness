---
io:
  inputs:
    type: object
    required: [chapter]
    properties:
      chapter:
        type: object
  outputs:
    type: object
    required: [chapter_with_line_numbers, chapter_lines, chapter_number]
    properties:
      chapter_with_line_numbers:
        type: string
      chapter_lines:
        type: array
        items:
          type: string
      chapter_number:
        type: integer
actions:
  - prepare_chapter
validator: false
---
<action>prepare_chapter</action>
