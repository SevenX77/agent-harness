---
name: extrac
path: subgraph/event-extraction
validator: false
iterate:
  mode: batch
  over: segmentation_result
  item_var: chapter_segmentation
  concurrency: 10
io:
  inputs:
    type: object
    required:
      - segmentation_result
      - chapter_segmentation
    properties:
      segmentation_result:
        type: array
        items:
          type: object
      chapter_segmentation:
        type: object
  outputs:
    type: object
    required:
      - chapter_event_timeline
    properties:
      chapter_event_timeline:
        type: array
        items:
          type: object
---
