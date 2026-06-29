---
name: segmentation
path: subgraph/text-segmentation
io:
  inputs:
    type: object
    required:
      - chapters
      - chapter
    properties:
      chapters:
        type: array
        items:
          type: object
      chapter:
        type: object
  outputs:
    type: object
    required:
      - segmentation_result
    properties:
      segmentation_result:
        type: array
        items:
          type: object
iterate:
  mode: batch
  over: chapter_event_timeline
  item_var: chapter
---
