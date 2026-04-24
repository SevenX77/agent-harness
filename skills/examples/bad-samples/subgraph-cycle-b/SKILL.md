---
name: bad-subgraph-cycle-b
description: >
  Paired anti-pattern for F-subgraph-cycle — references cycle-a, which
  references this file back. Never referenced directly; only reachable
  through compile(cycle-a).
type: graph
context_mapping:
  input: "{input}"
io:
  inputs:
    - name: input
      type: str
      source: runtime
---

<phase id="cycle_phase_b">
<phase_config>
name: cycle_phase_b
subgraph: ../subgraph-cycle-a/SKILL.md
context_bridge:
  inputs: {input: input}
  outputs: {}
</phase_config>
</phase>
