---
schema_version: "v0.3.0"
name: event-extraction
description: Extract event timeline from ABC-segmented paragraphs using 3-pass system.
io:
  inputs:
    type: object
    required: [chapter_segmentation]
    properties:
      chapter_segmentation:
        type: object
        required: [paragraphs]
        properties:
          paragraphs:
            type: array
            items:
              type: object
  outputs:
    type: object
    required: [chapter_event_timeline]
    properties:
      chapter_event_timeline:
        type: object
        required: [chapter_number, events, settings]
        properties:
          chapter_number:
            type: integer
          events:
            type: array
            items:
              type: object
              required: [event_id, title, type, paragraph_indices, summary, location, time]
              properties:
                event_id:
                  type: string
                title:
                  type: string
                type:
                  type: string
                  enum: [B, C, M]
                paragraph_indices:
                  type: array
                  items:
                    type: integer
                summary:
                  type: string
                location:
                  type: string
                time:
                  type: string
          settings:
            type: array
            items:
              type: object
          metadata:
            type: object
phases:
  - setup
  - aggregate
  - review
  - settings
---
<phase depends_on="input">setup</phase>
<phase depends_on="setup">aggregate</phase>
<phase depends_on="aggregate">review</phase>
<phase depends_on="review" output>settings</phase>
