---
module: 07-output-format
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 07-output-format — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 决策：保留 `md → md2json → schema → patcher` 作为主兜底。provider structured-output 只作为每模型待测优化项，必须优先测弱模型兼容性；yaml 否决。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖输出格式、structured-output 待测、yaml 否决、弱模型验收。

| 范围 | MVP1 目标 |
|---|---|
| `tools/md_to_json.py` | 主输出解析与 repair 兜底。 |
| `cognitive/md_patch.py` | structural repair 工具保留。 |
| `create_agent(response_format=...)` | 实验优化项，不是默认替换。 |
| gateway A' | provider 差异由 GatewayChatModel/RouteChatModelFactory 吸收，engine 不分 provider 写格式分支。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. finish_task 主路径仍提交 markdown。当前 tool args 证据见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`。

2. markdown 经 rich `md_to_json` 校验和 repair。目标接线见 `../03-finish-task-validation/mvp1-alignment.md`；rich 入口见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-604`。

3. patcher 只修 structural/mechanical 问题，不修 semantic 问题。当前 patcher prompt 证据见 `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:74-82`。

4. structured-output 不作为默认替代。虽然本地 `create_agent` 有 `response_format` 参数，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:664`，但 MVP1 只把它列为实验开关。

5. structured-output D-test-1 必须优先测弱模型：DeepSeek v3.2、Seed 2.0、Gemini 3.1 flash。验收目标是弱模型不过就不能全量替换 markdown 兜底。

6. 测试路径必须走 gateway A' 的实际 `GatewayChatModel` / route 路径，不用裸 SDK。engine 的 `_resolve_phase_chat_model` 当前从 `model_resolver.resolve` 得到模型，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`；实验也应从这条路径进。

7. yaml 否决。MVP1 不新增 yaml 输出 schema，也不把 markdown 改成 yaml，因为 yaml 的缩进、布尔/数字标量歧义、多行叙事文本都需要额外兜底。

8. prompt 可以加入更清楚的字段类型提示，但 frozen V0.3.0 spec 不在本轮修改。`schema_to_type_dict` 已有实现，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:675-684`；是否接入 prompt 属于 V4 spec 后续工作。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

已实现：markdown parser、diagnose、semantic/structural 分流、patcher、schema_to_type_dict 均已存在，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:81-181`、`packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-684`。

未实现：structured-output 弱模型实验还没有成为测试矩阵。

未实现：prompt 里还没有明确使用 rich `schema_to_type_dict` 的字段类型约束；当前 `<exit_contract>` 主要嵌 JSON schema，见 `packages/graph-agent/src/graph_agent/cognitive/prompt.py:235-240`。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

保留 md2json+patcher，是因为它是 provider-agnostic 的弱模型兜底层。create_agent / ChatX 能修 provider 消息处理问题，不等于每个 provider 都能可靠产出 typed JSON。

structured-output 作为优化项，是为了给强模型或未来 provider profile 留空间；但不能用理论能力覆盖弱模型实证风险。

yaml 否决，是为了避免把 JSON 转义污染问题换成 yaml 缩进和标量语义污染问题。engine 需要的是可诊断、可 patch、可打回的输出流水线，而不是换一种同样脆弱的文本格式。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-604`: semantic/structural path。
- `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:74-82`: patcher 边界。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:664`: response_format 参数。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`: gateway model resolver 入口。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. 待办：建立 D-test-1 弱模型 structured-output 兼容性测试清单。
2. 待办：若 structured-output 通过弱模型测试，也只能作为 route/profile 优化开关，不删除 markdown 兜底。
3. 待办：V4 spec 需定义字段类型提示和 markdown 输出格式；本轮不改 frozen skill-spec。
