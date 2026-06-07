---
status: superseded
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Skill Spec 文档入口

> 🔖 **本目录 = mvp0 留底,已整体 superseded(被 mvp1 取代),非 SSOT。** graph_skill 契约的唯一真理现在在 **`docs/engine/mvp1/`**;各 spec 正文保持 FROZEN 不动(历史存档),新读者请直接去 mvp1。架构入口:[`mvp1/00-architecture-overview.md`](../../mvp1/00-architecture-overview.md)。

**mvp0 skill-spec → mvp1 落点(唯一真理):**

| mvp0 skill-spec | mvp1 落点 |
|---|---|
| 00 FORMAT GROUND TRUTH · 02 GRAPH · 03 LOGIC · 04 SUBGRAPH · 05 AGENT · 06 cognitive · 07 mention | `01-contract/02-skill-syntax`(§2.1–§2.7) |
| 01 physical-layout | `01-contract/01-physical-layout` |
| 08 resource-mechanisms · 09 builtin-modules | `02-mechanism/03-assemble` + `05-run-inner/04-tools`(留底,深度待成段) |
| 10 skill-resolver-protocol | `02-mechanism/02-resolver` |
| 11 error-code · 12 compile-runtime-flow | `01-contract/03-compile-rules`(§4 错误码全表 / §2 生命周期) |

## 文档目标 (Purpose)

本文件夹是 Engine 内部最底层契约, 不面向最终 SDK 用户。它用于承接 V0.3.0 graph_skill 字段级规范、Loader 校验边界、认知模板装配约束与运行时错误定位, 后续 Phase B 会在各 spec 内补齐字段表、错误码全集和执行细节。

## 读者决策指南 (Navigation Guide)

- 如果你是 a1 (实施者): 直接查 02-05 字段表 + 11 错误码 (写 Loader 唯一标准依据)
- 如果你是 a2 (架构审阅者): 重点看 06 认知组装 + 08 资源机制流转
- 如果你是 Engine Debug 工程师: 报错查 11 错误码表 → 12 时序图定位

## 严格边界 (Scope Boundary)

本目录描述字段级契约, 不替代 `docs/engine/{5 子模块}/{baseline,mvp0-alignment,logic-explained}.md` 中的模块级实现机制说明。模块文档回答“为什么这样实现”和“模块如何协作”, 本目录回答“字段必须怎么写、Loader 必须怎么判、错误必须怎么报”。

本目录也不同于未来的 `docs/engine/public/`。public 文档应面向 SDK 用户和教程场景, 允许更高层的叙事、示例和迁移引导; 本目录面向 Engine 内部实现、架构审阅和 Debug, 以契约稳定性为第一优先级。

三个读者群体面对的是同一个对象: `graph_skill`。a1 需要把它加载成可信 AST, a2 需要审阅它是否满足 V0.3.0 架构收敛, Debug 工程师需要从错误码与运行流快速定位失败阶段。

## 完整文件索引 (Table of Contents)

- [01-physical-layout.md](./01-physical-layout.md#物理结构拓扑-directory-tree): 约束 graph_skill 物理目录、文件命名和 mode/path 双向校验。
- [02-graph-md-spec.md](./02-graph-md-spec.md#基础元数据字段-metadata): 定义 `GRAPH.md` 根节点 Frontmatter、Phase DAG 和根 IO 契约。
- [03-logic-md-spec.md](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation): 定义 `LOGIC.md` Frontmatter、Action 一级寻址和 validator 生命周期。
- [04-subgraph-md-spec.md](./04-subgraph-md-spec.md#类型推导与节点契约): 定义 `SUBGRAPH.md` 类型推导、SkillResolverProtocol 寻址和父子图 IO 强校验。
- [05-agent-md-spec.md](./05-agent-md-spec.md#frontmatter-字段解析表): 定义 Agent `SKILL.md` Frontmatter、Body XML 扁平化和引用注入校验。
- [06-cognitive-template-spec.md](./06-cognitive-template-spec.md#8-大插槽布局拓扑): 定义 Cognitive Template 8 大插槽的数据来源与装配顺序。
- [07-mention-syntax-spec.md](./07-mention-syntax-spec.md#--mention-语法规范): 定义 `@type:NAME` 7 类引用语法和静态依赖校验。
- [08-resource-mechanisms-spec.md](./08-resource-mechanisms-spec.md#reference-三机制生命周期): 定义 Reference 三机制、Example 双模式和 Frontmatter 挂载格式。
- [09-builtin-modules-spec.md](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名): 定义 builtin reference reader subagent 与按需读取 tools 的 I/O 签名。
- [10-skill-resolver-protocol-spec.md](./10-skill-resolver-protocol-spec.md#protocol-interface-定义): 定义全局 Registry 寻址 DI 接口和 Studio 实现边界。
- [11-error-code-spec.md](./11-error-code-spec.md#错误码设计模式-prefix-f-v3-): 定义 `[F-v3-*]` 错误码命名、等级和速查表骨架。
- [12-compile-runtime-flow-spec.md](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow): 定义编译、装配和运行时生命周期时序骨架。

## V0.3.0 决议溯源 (Decision Provenance)

字段级决议以各 spec doc 头部、[11 错误码](./11-error-code-spec.md) 和 [12 flow doc](./12-compile-runtime-flow-spec.md) 为落地入口。Phase A 只固定文件边界和 H2 骨架, Phase B 再补字段级内容。

模块级决议见 [Skill Compilation MVP0 Alignment](../skill-compilation/mvp0-alignment.md), [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md), [Execution Runtime MVP0 Alignment](../execution-runtime/mvp0-alignment.md), [Tracing and Observability MVP0 Alignment](../tracing-and-observability/mvp0-alignment.md), [Graph Agent Gateway MVP0 Alignment](../graph-agent-gateway/mvp0-alignment.md) 末尾的 "MVP0 死代码清退" 与 "V0.3.0 版本号 cutover" 段。

跨模块宏观决议见 [MVP0 Decisions Explained](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md) 18 Q 全集。该文档解释为什么 V0.3.0 要收敛到当前 graph_skill 契约、状态隔离、运行时和路由边界。

Studio 侧新增需求见 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md), 尤其是 SkillResolverProtocol 接口与 subgraph asset panel 相关要求。
