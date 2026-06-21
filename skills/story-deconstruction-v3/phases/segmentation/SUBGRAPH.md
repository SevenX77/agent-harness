---
name: segmentation
path: subgraph/text-segmentation
validator: false
iterate:
  mode: batch
  over: chapters
  item_var: chapter
  concurrency: 10
io:
  inputs:
    type: object
    required: [chapters, chapter]
    properties:
      chapters:
        type: array
        items: {type: object}
      chapter: {type: object}
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: array
        items: {type: object}
---
