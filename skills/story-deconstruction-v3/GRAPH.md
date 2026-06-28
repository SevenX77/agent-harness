---
schema_version: "v0.3.0"
name: story-deconstruction-v3
description: MVP1-compliant recursive story deconstruction pipeline.
io:
  inputs:
    type: object
    required: [chapters, project_id]
    properties:
      chapters:
        type: array
        items:
          type: object
          required: [chapter_number, content]
          properties:
            chapter_number: {type: integer}
            content: {type: string}
      project_id: {type: string}
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework: {type: object}
phases: [segmentation, event_timeline, story_analysis, global_synthesis]
---

<phase depends_on="input">segmentation</phase>
<phase depends_on="segmentation">event_timeline</phase>
<phase depends_on="event_timeline">story_analysis</phase>
<phase depends_on="story_analysis" output>global_synthesis</phase>
