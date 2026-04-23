---
name: bad-subgraph-with-sub-skills
description: >
  Intentional anti-pattern: declares `subgraph:` together with
  `sub_skills:`. Use by the compiler test suite only — the
  F-subgraph-exclusive-sub-skills rule must fire on this file with
  FATAL severity (the two mechanisms are mutually exclusive; subgraph
  is static composition, sub_skills is dynamic LLM-driven dispatch).
type: graph
---

<phase id="bad_phase">
<phase_config>
name: bad_phase
subgraph: ../../subgraph-sample/story-deconstruction/SKILL.md
sub_skills:
  - name: render
    path: ../../subgraph-sample/story-deconstruction/SKILL.md
</phase_config>
</phase>
