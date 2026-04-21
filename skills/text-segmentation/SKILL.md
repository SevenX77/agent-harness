---
name: text-segmentation
description: >
  ABC paragraph segmentation with Two-Pass validation.
  Classifies chapter paragraphs as A(setting)/B(event)/C(system).
  Use when analyzing raw chapter text for story deconstruction.
type: graph
context_mapping:
  chapter_content: "{input.chapter_content}"
  chapter_number: "{input.chapter_number}"
  chapter_with_line_numbers: ""
  chapter_lines: ""
  raw_segmentation: ""
  segments: ""
io:
  inputs:
    - name: chapter_content
      type: str
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
  outputs:
    - name: segmentation_result
      type: dict
      target: file
      path: "output/text-segmentation/chapter_{context.chapter_number}_segments.json"
---

<node id="setup">
<ref path="nodes/01_setup.md" />
</node>

<node id="segment" depends_on="setup">
<ref path="nodes/02_segment.md" />
</node>

<node id="review" depends_on="segment">
<ref path="nodes/03_review.md" />
</node>
