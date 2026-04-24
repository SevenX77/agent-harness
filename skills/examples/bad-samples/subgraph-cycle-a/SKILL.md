---
name: bad-subgraph-cycle-a
description: >
  Intentional anti-pattern: this skill has a subgraph phase pointing
  to bad-subgraph-cycle-b, which points back at this file. The compiler's
  F-subgraph-cycle rule must fire — subgraph references must form a DAG,
  otherwise runtime loader will raise SkillLoadError at load time.
type: graph
context_mapping:
  input: "{input}"
io:
  inputs:
    - name: input
      type: str
      source: runtime
---

<phase id="cycle_phase_a">
<phase_config>
name: cycle_phase_a
subgraph: ../subgraph-cycle-b/SKILL.md
context_bridge:
  inputs: {input: input}
  outputs: {}
</phase_config>
</phase>
