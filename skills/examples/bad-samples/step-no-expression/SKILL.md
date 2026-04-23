---
name: bad-step-no-expression
description: >
  Intentional anti-pattern: a <step> tag with a when= expression
  attribute. The compiler's F-step-no-expression rule must fire —
  framework does not evaluate business expressions (F006 red line);
  conditional branches are expressed via code-only phase + validator
  + retry_target, not as inline step attributes.
type: graph
context_mapping:
  input: "{input}"
io:
  inputs:
    - name: input
      type: str
      source: runtime
---

<phase id="bad_phase">
<phase_config>
name: bad_phase
tier: balanced
</phase_config>
<system_prompt>
You will perform a series of steps.
<step name="first" goal="get started">OK</step>
<step when="context.flag == true" name="second" goal="maybe run">
  This step has a when= expression attribute which the framework
  refuses to evaluate.
</step>
</system_prompt>
<user_prompt>
Do the thing: {input}
</user_prompt>
</phase>
