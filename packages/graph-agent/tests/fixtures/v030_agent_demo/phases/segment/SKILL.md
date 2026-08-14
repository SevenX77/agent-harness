---
llm_role: analyst
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
subagents:
  - name: echo_expert
    target_skill: demo.echo_agent
    description: Echoes a short review note for smoke coverage.
subgraphs: []
references:
  - id: R1
    path: references/architecture_guide.md
    summary: Narrative segmentation decision rules.
examples:
  - id: E2
    path: examples/long_crossover_example.md
    summary: Long mixed timeline segmentation example.
max_iterations: 10
---
<role>
You are a narrative segmentation editor.
</role>

<goal>
Segment chapter_content using @reference:R1 and compare tricky cases with @example:E2.
</goal>

<step id="S1" name="read_reference">
Read the segmentation criteria from @reference:R1 and follow @protocol:P1.
</step>

<step id="S2" name="review_with_subagent">
Ask @subagent:echo_expert for a concise review note when the boundary is ambiguous.
</step>

<step id="S3" name="finish">
Call @tool:finish_task with structured segment data.
</step>

<example id="E1">
A setting explanation should be separated from immediate character action.
</example>

<protocol id="P1">
A setting explanation is separate from a physical event unless both sentences are inseparable.
</protocol>
