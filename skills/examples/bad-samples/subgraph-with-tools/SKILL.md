---
name: bad-subgraph-with-tools
description: >
  Intentional anti-pattern: declares `subgraph:` together with `tools:`.
  Use by the compiler test suite only — the F-subgraph-exclusive-tools
  rule must fire on this file with FATAL severity.
type: graph
---

<phase id="bad_phase">
<phase_config>
name: bad_phase
subgraph: ../../subgraph-sample/story-deconstruction/SKILL.md
tools:
  - script.fake.noop
</phase_config>
</phase>
