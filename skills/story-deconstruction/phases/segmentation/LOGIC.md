---
actions:
  - segment_all_chapters
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters:
        type: array
        items:
          type: object
  outputs:
    type: object
    required: [all_segmentations]
    properties:
      all_segmentations:
        type: array
        items:
          type: object
---
<action>segment_all_chapters</action>
