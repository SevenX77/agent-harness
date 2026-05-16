---
schema_version: '2.1'
name: text-segmentation
description: 'ABC paragraph segmentation with Two-Pass validation. Classifies chapter
  paragraphs as A(setting)/B(event)/C(system). Use when analyzing raw chapter text
  for story deconstruction.

  '
metadata:
  legacy_type: graph
  context_mapping:
    chapter_content: '{input.chapter_content}'
    chapter_number: '{input.chapter_number}'
    chapter_with_line_numbers: ''
    chapter_lines: ''
    raw_segmentation: ''
    segments: ''
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" depends_on="" />
<phase id="segment" src="phases/segment" depends_on="setup" />
<phase id="review" src="phases/review" depends_on="segment" />
