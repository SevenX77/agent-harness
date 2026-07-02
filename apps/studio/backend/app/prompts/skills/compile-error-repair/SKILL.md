---
name: compile-error-repair
description: 修复 graph_skill 编译/lint 错误（[F-v3-*] 错误码）的固定流程。用户问"为什么编译失败"、上下文出现 lint 错误、或粘贴了错误码时使用。
---

# 编译错误修复流程

严格按顺序走，不跳步、不凭印象猜语法。

## 1. 拿全错误信息
- 看 `<copilot_context>` 的 `<lint_status>` 与用户消息里的错误码全文（形如 `[F-v3-...]` + 行号 + 描述）。
- 错误不全时先让用户把 Compile 面板的完整输出贴过来，不要对着半截错误开修。

## 2. 查错误码语义（挂载 spec 是唯一权威）
- 到挂载的 `02-skill-syntax` / `03-compile-rules` 目录 Grep 错误码，读它的触发条件与修复指引。
- 规则文档里的心智模型只是速览；**精确语义以挂载 spec 为准**。

## 3. Read 涉事文件全文
- 按错误里的文件+行号 Read 完整文件（GRAPH.md / phases/<name>/LOGIC.md / actions/*.py）。
- 行号语义注意：body 内错误是 body 相对行还是文件绝对行，以 spec 描述为准。

## 4. 定位根因层
常见错误模式（先对号入座再动手）：
- **三处名字不一致**：frontmatter `phases` / body `<phase>` / `phases/<name>/` 目录，三处必须完全一致。
- **DAG 引用悬空**：`depends_on` 引用了不存在的 phase 名；入口必须 `depends_on="input"`。
- **io schema 不接**：下游声明的输入字段在上游输出里不存在，或类型不匹配。
- **phase 目录模式文件不对**：每个 phase 目录**恰好一个** LOGIC.md / SUBGRAPH.md / SKILL.md。
- **action 缺失或签名不对**：`<action>名</action>` 对应 `actions/<名>.py`，签名 `def 名(inputs): ...`。
- **frontmatter 字段错**：`schema_version: "v0.3.0"` 必须精确；`name` 匹配 `^[a-z][a-z0-9_-]*$`。

## 5. 最小修复
- 只改根因，不顺手重构；一次修一类错误。
- 改完说明"改了什么、为什么这是根因"，让用户重新 Compile 验证；还有残留错误就带着新错误码回到第 1 步。

## 反模式
- ❌ 不读文件就给"可能是 X"的清单。
- ❌ 把错误码语义凭记忆复述而不查 spec。
- ❌ 一次性大改多处让用户无法定位是哪个改动生效。
