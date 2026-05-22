# Physical Layout Spec

本文规定 graph_skill 的物理目录结构、文件命名和 mode/path 双向校验边界, 是 Loader 开始解析前的第一层约束。错误处理需和 [错误码契约](./11-error-code-spec.md#todo-phase-b) 对齐, 后续编译顺序见 [Compile Runtime Flow](./12-compile-runtime-flow-spec.md#todo-phase-b)。

## 物理结构拓扑 (Directory Tree)

<!-- Phase B: 待填字段级内容 -->

[编译期校验流](./12-compile-runtime-flow-spec.md#todo-phase-b) 将引用本节目录拓扑。

## 文件命名规约 (Naming Conventions)

<!-- Phase B: 待填字段级内容 -->

[GRAPH.md 字段契约](./02-graph-md-spec.md#todo-phase-b)、[LOGIC.md 字段契约](./03-logic-md-spec.md#todo-phase-b)、[SUBGRAPH.md 字段契约](./04-subgraph-md-spec.md#todo-phase-b)、[SKILL.md 字段契约](./05-agent-md-spec.md#todo-phase-b) 将引用本节命名规则。

## mode↔路径双向校验 (Mode-Path Cross Validation)

<!-- Phase B: 待填字段级内容 -->

[F-v3-graph-mode-mismatch 错误契约](./11-error-code-spec.md#todo-phase-b) 将覆盖本节 FATAL 行为。

## IO 物理文件退役声明 (Inline IO Deprecation)

<!-- Phase B: 待填字段级内容 -->

[Root IO Schema](./02-graph-md-spec.md#todo-phase-b) 与 [State and IO Contract MVP0 Alignment](../state-and-io-contract/mvp0-alignment.md#todo-phase-b) 将说明 inline `io:` dict 的收敛边界。
