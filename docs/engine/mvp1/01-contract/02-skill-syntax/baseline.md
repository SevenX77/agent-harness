---
module: 01-contract/02-skill-syntax
doc: baseline
status: living
updated: 2026-06-28
binds_alignment: ./mvp1-alignment.md
format_ssot: ../../../skill-spec/00-FORMAT-GROUND-TRUTH.md
---

# 02-skill-syntax - Baseline

本文只记录当前代码与 MVP1 格式规范之间的差异。格式规范唯一真相源见：

[`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md)

## 1. Current Implementation Snapshot

当前 loader/compiler 已能解析 `GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md`、Agent `SKILL.md`，并支持部分统一 `iterate` AST。但仍存在历史实现残留。

这些残留只代表代码现状，不代表合法格式：

| Area | Current code behavior | MVP1 required behavior |
| --- | --- | --- |
| SUBGRAPH addressing | 代码中仍有逻辑 id / resolver 路径 | `SUBGRAPH.md` 使用 `path` 指向子图目录 |
| Agent `subgraphs[]` | 代码中仍有历史逻辑 id 字段 | Agent `subgraphs[]` 使用 `path` |
| Agent `subagents[]` | 运行期子 agent 仍使用 `target_skill` | 保持合法，因为它不是 subgraph path |
| phase type | 代码内部有 mode discriminator | 作者不在 frontmatter 写 `mode` |
| phase id | 代码内部有 phase id | 作者不在 frontmatter 写 `phase_id` |
| iterate | 代码中仍可能读非规范循环字段 | 新规范只允许 `iterate` |
| LOGIC action signature | 部分路径仍按非规范 Context 形态校验 | `def <action_name>(inputs) -> dict` |
| SUBGRAPH IO | 已对齐:编译期不再有任何父子 schema 相等判断(inputs 由 WS-E1 Step5 放宽,outputs 由 `cad7dbc0` 移除) | 父图子图 IO 都是黑板切片/合并边界，不要求全集 1:1 |
| AGENT frontmatter | 部分路径仍会提升非规范包装层字段 | 新规范只允许 skill-spec 中列出的顶层字段 |

## 2. Drift Rule

任何当前代码仍接受、但不在 `skill-spec/00` 中列出的字段，都是 implementation drift。

后续实现必须让代码向 `skill-spec/00` 收敛，不能反向修改 skill-spec 来迁就当前实现偏差。

## 3. Test Focus

- fixture 和 Studio 新写入逻辑只生成 `skill-spec/00` 字段。
- 非法字段进入新 fixture 时应被视为错误。
- Properties 面板只从当前 `.md` 文件 frontmatter 的规范字段生成表单。
- `SUBGRAPH.md` 和 Agent `subgraphs[]` 都按 `path` 处理。
- `iterate` 字段完整覆盖 batch / loop / range / accumulate 语义。
