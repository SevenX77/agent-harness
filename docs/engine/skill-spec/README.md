---
status: active
ssot: graph_skill_format_templates
updated: 2026-06-28
---

# Skill Spec 文档入口

`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` 是 `graph_skill` 文件格式模板的唯一真相源。

当前规则：

- 新建、编辑、校验、Studio Properties 面板、fixture 和示例，都以 [`00-FORMAT-GROUND-TRUTH.md`](./00-FORMAT-GROUND-TRUTH.md) 为准。
- MVP1 设计文档只保留架构意图和跨模块链接，不再重复 YAML 模板。
- 本目录内其他拆分文档只作为背景说明或历史索引页；如果它们与 `00-FORMAT-GROUND-TRUTH.md` 冲突，一律以 `00` 为准，并应修正文档。
- `_migration-src` 已退役删除；需要历史细节时看 git 历史，不再保留第二套迁移源。

## Canonical Template

- [00-FORMAT-GROUND-TRUTH.md](./00-FORMAT-GROUND-TRUTH.md): 完整目录结构、`GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`、IO、iterate、mention/resource、Studio Properties 映射。

## Supporting Pages

这些页面不再承载模板真相源：

- [01-physical-layout.md](./01-physical-layout.md)
- [02-graph-md-spec.md](./02-graph-md-spec.md)
- [03-logic-md-spec.md](./03-logic-md-spec.md)
- [04-subgraph-md-spec.md](./04-subgraph-md-spec.md)
- [05-agent-md-spec.md](./05-agent-md-spec.md)
- [06-cognitive-template-spec.md](./06-cognitive-template-spec.md)
- [07-mention-syntax-spec.md](./07-mention-syntax-spec.md)
- [08-resource-mechanisms-spec.md](./08-resource-mechanisms-spec.md)
- [09-builtin-modules-spec.md](./09-builtin-modules-spec.md)
- [10-skill-resolver-protocol-spec.md](./10-skill-resolver-protocol-spec.md)
- [11-error-code-spec.md](./11-error-code-spec.md)
- [12-compile-runtime-flow-spec.md](./12-compile-runtime-flow-spec.md)
