---
name: bad-subgraph-with-prompt
description: >
  Intentional anti-pattern: declares `subgraph:` together with a
  <system_prompt> block. Use by the compiler test suite only — the
  F-subgraph-exclusive-prompt rule must fire on this file with FATAL
  severity.
type: graph
---

<phase id="bad_phase">
<phase_config>
name: bad_phase
subgraph: ../../subgraph-sample/story-deconstruction/SKILL.md
</phase_config>
<system_prompt>
This prompt will be silently ignored because subgraph mode does not run
an LLM. The compiler must fail-fast instead of letting the author ship
a skill with dead prompts.
</system_prompt>
</phase>
