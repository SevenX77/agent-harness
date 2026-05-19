---
name: event-extraction
description: >
  Extract event timeline from ABC-segmented paragraphs using 3-pass system.
  Pass 1: event aggregation + timeline reordering.
  Pass 1R: semantic coherence review.
  Pass 2: setting extraction + correlation.
  Use after text-segmentation completes.
type: graph
context_mapping:
  segmentation_result: "{input.segmentation_result}"
  chapter_number: "{input.chapter_number}"
  prev_chapter_last_event: "{input.prev_chapter_last_event}"
  output_dir: "{input.output_dir}"
  formatted_paragraphs: ""
  events_raw: ""
  parsed_events: ""
  event_timeline: ""
io:
  inputs:
    - name: segmentation_result
      type: dict
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
    - name: prev_chapter_last_event
      type: dict
      source: runtime
  outputs:
    - name: event_timeline
      type: dict
      target: file
      path: "{context.output_dir}/chapter_{context.chapter_number}_events.json"
---

<node id="setup">
<ref path="nodes/01_setup.md" />
</node>

<node id="aggregate" depends_on="setup">
<ref path="nodes/02_aggregate.md" />
</node>

<node id="review" depends_on="aggregate">
<ref path="nodes/03_review.md" />
</node>

<node id="settings" depends_on="review">
<ref path="nodes/04_settings.md" />
</node>
