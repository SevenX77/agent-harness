---
name: product-manual
description: 生成面向消费者的产品说明书
type: graph
io:
  inputs:
    - name: product_specs
      type: json
      source: runtime
  outputs:
    - name: final_manual
      type: markdown
---

<phase_config>
name: extract_highlights
tier: balanced
tools:
  - script.extract.get_highlights
</phase_config>

<system_prompt>
你是一个产品专家。请从参数表中提取3-5个核心亮点。
</system_prompt>

<phase_config>
name: write_scenarios
tier: balanced
depends_on:
  - extract_highlights
tools:
  - script.scenarios.generate
</phase_config>

<system_prompt>
根据产品亮点，构思3个具体的使用场景。
注意：至少举3个具体使用场景！
</system_prompt>

<phase_config>
name: synthesize_report
tier: premium
depends_on:
  - write_scenarios
tools:
  - script.report.synthesize
</phase_config>

<system_prompt>
综合亮点和场景，写出一份吸引人的产品说明书。
</system_prompt>