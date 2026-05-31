---
io:
  inputs:
    type: object
    required: [chapter_content, chapter_number]
    properties:
      chapter_content:
        type: string
      chapter_number:
        type: integer
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
---
<action>prepare_chapter</action>
