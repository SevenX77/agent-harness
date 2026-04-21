# GraphAgent SKILL.md 完美模板（Graph 模式）

以下是一个完全符合 GraphAgent 规范的 SKILL.md，可直接复制使用。

---

```markdown
---
name: my-awesome-skill
description: 完成 XXX 任务的多阶段工作流
type: graph
version: "1.0"
io:
  inputs:
    - name: raw_data
      type: dict
      source: runtime
    - name: output_dir
      type: str
      source: runtime
  outputs:
    - name: result
      type: dict
      target: file
context_mapping:
  # 深度取值（从 runtime 输入中提取）
  data_text: "{input.raw_data.text}"
  data_id: "{input.raw_data.id}"

  # 辅助函数调用（helpers.py 中定义）
  formatted_summary: "$format_summary({input.raw_data})"

  # 字符串字面量传递（引号会被自动剥离）
  protocols: "$get_protocols_for_phase('processing')"

  # ⚠️ JSON 示例正确注入方式（不要在 prompt 中直接写 JSON！）
  output_format_example: "$load_file('data/output_example.json')"

  # 初始空值
  intermediate_result: "（Phase 1 尚未执行）"
---

# My Awesome Skill

<node id="analysis">
  <ref path="nodes/01_analysis.md" />
</node>

<node id="generation" depends_on="analysis">
  <ref path="nodes/02_generation.md" />
</node>

<node id="validation" depends_on="generation">
  <ref path="nodes/03_validation.md" />
</node>
```

---

## 节点文件模板 (`nodes/01_analysis.md`)

```markdown
<phase_config>
name: analysis
tier: premium
max_iterations: 10
max_nudges: 3
tools:
  - script.analyzer.extract_entities
  - script.analyzer.tag_content
validator: script.validators.validate_analysis
max_retries: 2
</phase_config>

<system_prompt>
你是数据分析专家。

## 核心任务
逐段阅读输入数据，提取所有关键实体和它们的关系。

## 执行步骤
1. 通读全部数据，在思考过程中拟定分析计划。
2. 调用 update_working_memory 记录你的计划（推荐）。
3. 对每个实体调用 extract_entities 工具。
4. 对每段内容调用 tag_content 工具。
5. 完成后**必须调用 finish_task**，提供自检结论和证据。

## 输出格式参考
{output_format_example}

## 适用协议
{protocols}
</system_prompt>

<user_prompt>
数据 {data_id}：

{data_text}
</user_prompt>
```

---

## 关键规范提醒

### 占位符命名
- ✅ `{protocols_entity}` — 明确前缀，不与 JSON 碰撞
- ✅ `{output_format_example}` — 语义清晰
- ❌ `{name}` — 太通用，易与 JSON `{"name": ...}` 碰撞
- ❌ `{type}` — 同上

### JSON 处理
- ✅ 抽离到 `data/output_example.json`，通过 `$load_file()` 注入
- ❌ 直接在 `<system_prompt>` 中写 `{"name": "张三", ...}`

### LLM 阶段（自动启用认知循环）
- 所有 LLM 阶段自动注入 `finish_task` + `update_working_memory`，无需配置 `cognitive_loop`
- ✅ prompt 中明确要求"完成后**必须调用 finish_task**"
- ✅ 建议包含 `update_working_memory` 步骤用于规划和 Checkpoint
- ❌ prompt 中只写"完成任务"而不提及 `finish_task`

### context_mapping 表达式
- `{input.xxx.yyy}` — 深度取值，路径必须与 `io.inputs` 对应
- `$func({arg})` — 函数调用，`func` 必须在 `helpers.py` 中定义
- `$func('literal')` — 字面量传递，引号自动剥离
- `"plain string"` — 直接传递
