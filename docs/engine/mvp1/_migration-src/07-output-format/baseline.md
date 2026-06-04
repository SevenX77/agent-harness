---
module: 07-output-format
doc: baseline
status: drafted
last_verified: 2026-06-02
---

# 07-output-format — Baseline(现状)

核心结论：当前 engine 的实际输出兜底是 markdown → md2json → schema validation → patcher，而不是 provider structured-output。rich `tools/md_to_json.py` 还保留面向弱模型的 markdown 分块、类型提示和 surgical patch；live finish_task 接线虽接错到简化版，但仍体现了“markdown 入参 + schema 校验 + patcher”的设计方向。

## 覆盖范围

覆盖范围：本文覆盖决策记录 §9、§13 的现状基础。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| finish_task markdown 入参 | `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24` | 提交格式是 markdown。 |
| rich markdown parser | `packages/graph-agent/src/graph_agent/tools/md_to_json.py:284-438` | `##` 块、bullet 字段、nested/list/scalar coercion。 |
| rich schema constraint helper | `packages/graph-agent/src/graph_agent/tools/md_to_json.py:675-684` | 能生成字段类型约束文本。 |
| patcher | `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:59-84` | LLM patcher 只修格式和机械类型。 |
| create_agent structured-output API | 本地 LangChain | `create_agent` 有 `response_format` 参数，但 engine 当前未用。 |

## 编号执行流程(现状)

1. finish_task 当前 tool args 是 `markdown`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`。

2. `apply_v030_cognitive_template` 在 `<exit_contract>` 里输出 JSON schema 文本，见 `packages/graph-agent/src/graph_agent/cognitive/prompt.py:235-240`。

3. rich `parse_md` 用 `##` header 切分 item，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:284-329`。

4. rich `_parse_block_data` 从 bullet lines 提取字段，支持 flat 和 nested 字段，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:332-372`。

5. rich `_coerce_scalar` 会根据 schema annotation 尝试 list/int/float coercion；失败保留原字符串交给 Pydantic 报错，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:414-438`。

6. rich `schema_to_type_dict` 能把 Pydantic 字段输出成文本约束，例如 int/float bounds/list/Literal，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:675-684`。

7. `LLMMdPatchClient.patch` 通过 chat model 修 markdown，prompt 明确“Fix only formatting and mechanical type issues”，见 `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:74-82`。

8. 当前 `create_agent` API 支持 `response_format` 参数，签名中该参数在 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:664`；但 live `_build_skill_node` 没有传 structured-output response_format，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:483-576`。

9. `LLMPhaseNode` 并存路径调用 `create_agent` 时也只传 `model/tools/system_prompt/middleware`，没有 response_format，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:570-575`。

## Baseline / Alignment 差异

baseline 没有采用 provider structured-output 作为主路径。alignment 目标是保留 markdown+md2json+patcher 兜底，同时把 structured-output 仅作为“每模型待测优化项”，不能在弱模型兼容性未证实前替换。

## 决策原因

当前代码基础说明 engine 已为 markdown 兜底投入了完整解析、诊断、patch 能力。直接删除它会把弱模型格式污染风险推回 provider/tool-calling，而用户已指出 DeepSeek v3.2、Seed 2.0、Gemini 3.1 flash 等弱模型经常输出污染或转义异常。

yaml 被否决不是因为没有 parser，而是因为它把脆弱点换成缩进、标量歧义、多行文本问题；对嵌套叙事类业务输出仍需要兜底层。

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:284-438`: rich markdown parser。
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:675-684`: schema_to_type_dict。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:664`: create_agent response_format 参数存在但未用。

## 待办/疑点

1. 待办：D-test-1 优先测试弱模型 structured-output 可靠性，不拿强模型结果替代。
2. 待办：md2json 接回 rich 版本后，重新评估 schema_to_type_dict 是否进入 prompt。
3. 疑点：structured-output 若作为优化，触发条件是 per model profile、per route capability，还是手动实验开关。
