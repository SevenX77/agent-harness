---
doc: skill-spec-index
role: index
status: living
ssot: graph_skill_format_templates
updated: 2026-09-01
---

# Skill Spec 文档入口

[`00-FORMAT-GROUND-TRUTH.md`](./00-FORMAT-GROUND-TRUTH.md) 是**本仓** `packages/graph-agent` 所接受的 `graph_skill` 文件格式模板唯一真相源。它的状态是 `FROZEN`，仍被本仓代码与 contract maps 消费。它**不**定义新 engine 仓的格式，边界见下一段。

独立 Graph Skill Runtime 的 portable gSkill v1 格式**已经实现**，它的格式真相源在**新仓** `graph-skill-runtime`（远端 `SevenX77/graph-skill-runtime`）的 `docs/skill-spec/01-PORTABLE-GSKILL-V1.md`，该文 frontmatter 为 `status: audited-ready`、`ssot: graph_skill_format_templates`，开篇原文：「Phase 2 已完成原子切换：production compile、predict、run、inspect、SDK、CLI 与 MCP 只读取本文格式；legacy v0.3 parser 只在显式 `gskill migrate studio-skill` converter 边界可达。」它提出的根 `SKILL.md` + `graph.yaml` + phase `AGENT.md` + 扁平 `graphs/` registry 就是新仓当前的实现形态，不再是「未来目标」。

**两个 `00-FORMAT-GROUND-TRUTH.md` 是不同的文件，不要混指。** 新仓那一份已是 `status: superseded`、`superseded_by: ./01-PORTABLE-GSKILL-V1.md`，只留作 converter 输入契约与历史证据；**本目录**这一份 [`00-FORMAT-GROUND-TRUTH.md`](./00-FORMAT-GROUND-TRUTH.md) 仍是本仓 `packages/graph-agent` 所消费格式的真相源。按 [`gskill-restructure-decision-2026-08-31.md`](../../design/gskill-restructure-decision-2026-08-31.md) §4.2「engine 的唯一 owner 立即收敛到 graph-skill-runtime」——原文「本仓 `packages/graph-agent` **冻结为只读镜像**，只接受『从新仓回灌』这一个方向的变更」——本仓 `00` 的效力范围随之收窄为**已冻结的本仓 engine 代码**；新格式的权威只在新仓 `01-PORTABLE-GSKILL-V1.md`，本目录不另立一套，也不再需要「实现后再 cutover」这一前置条件（cutover 已在新仓内部完成）。

新仓 runtime 的实现进度、验收边界与发布状态由新仓 `docs/design/v1-alignment.md` 自己维护；本文只给指针，不复制它的状态，以免留下第二份会过期的并行副本。本仓 [`../graph-skill-runtime/v1-alignment.md`](../graph-skill-runtime/v1-alignment.md) 是 2026-08-28 提取设计当时（PR #1046）的本仓快照，已落后于新仓同名文档，不作为格式或进度依据。

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

## 修订记录

### 2026-09-01：跨仓格式指针实况化（F-T2）

**原文（本文 2026-08-27 版）**：「独立 Graph Skill Runtime 的未来 v1 格式目标目前为 `drafted`。它提出根 `SKILL.md` + `graph.yaml` + phase `AGENT.md` + `graphs/` registry，但尚未实现，也没有替代当前 `00`。只有实现、迁移验证和引用重钉完成后的显式 cutover，才可以更换当前格式 SSOT。」

**被什么实证推翻**（按仓规「三道检验」，三道同向）：

1. **日期**：本文这句由 PR #1046（`be6edcf3`，2026-08-28）写下；新仓同日的 `1e1a3540`（PR #5，`feat: adopt portable gSkill v1 format`）已把该格式实现并切换为唯一读取格式。两者时间上擦肩而过，本文自落笔即滞后。
2. **原话**：新仓 `docs/skill-spec/01-PORTABLE-GSKILL-V1.md` frontmatter `status: audited-ready`（非 `drafted`）、`ssot: graph_skill_format_templates`，正文「Phase 2 已完成原子切换：production compile、predict、run、inspect、SDK、CLI 与 MCP 只读取本文格式」；同仓 `docs/skill-spec/00-FORMAT-GROUND-TRUTH.md` 已 `status: superseded`、`superseded_by: ./01-PORTABLE-GSKILL-V1.md`。「尚未实现」与「没有替代当前 `00`」两句因此均被推翻——后者仅对**本仓**的 `00` 仍成立，对**新仓**的 `00` 已不成立。
3. **第一性原理**：原句把两件事捆在一句里——「提出某结构」（仍为真）与「尚未实现」（已为假）；且「替代当前 `00`」中的 `00` 未限定属于哪个仓，一个词指向两个文件，本身就是一次歧义。本次修订按「指代落到唯一对象」把两个 `00` 分别限定，并按「文档事实唯一所有权」只留指针、不复制新仓的进度状态。

**同批改动**：`00-FORMAT-GROUND-TRUTH.md` 卷首新增「适用范围边界」一节，明确其 `FROZEN` 只覆盖已冻结的本仓 engine 代码（依据同一决议 §4.2）。该文件受 `packages/graph-agent/tests/test_contract_hash_lock.py` 的 SHA-256 哈希锁保护，已在同一 PR 内重钉。

**未纳入本次范围**：本仓 `docs/engine/graph-skill-runtime/v1-alignment.md` 与 `docs/engine/mvp1/01-contract/02-skill-syntax` 系列的 `format_ssot:` 指针同样滞后，属盘点工单 F-T8 与后续跨仓收敛批次，不在本目录内修。
