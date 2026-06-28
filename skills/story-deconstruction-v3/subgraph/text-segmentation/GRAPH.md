---
schema_version: "v0.3.0"
name: text-segmentation
description: ABC paragraph segmentation with two-pass validation for one chapter item.
io:
  inputs:
    type: object
    required: [chapter]
    properties:
      chapter:
        type: object
        required: [chapter_number, content]
        properties:
          chapter_number: {type: integer}
          content: {type: string}
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
        required: [chapter_number, total_paragraphs, paragraphs]
        properties:
          chapter_number:
            type: integer
          total_paragraphs:
            type: integer
          paragraphs:
            type: array
            items:
              type: object
              required: [index, type, start_line, end_line, content, description]
              properties:
                index:
                  type: integer
                type:
                  type: string
                  enum: [A, B, C]
                start_line:
                  type: integer
                end_line:
                  type: integer
                content:
                  type: string
                description:
                  type: string
          metadata:
            type: object
phases: [setup, segment, review]
---
<phase depends_on="input">setup</phase>
<phase depends_on="setup">segment</phase>
<phase depends_on="segment" output>review</phase>
