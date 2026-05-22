# Agent SKILL.md Spec

本文定义 Agent 节点 `SKILL.md` 的 Frontmatter、Body XML 扁平化规则和引用注入校验。它是 [Cognitive Template](./06-cognitive-template-spec.md#todo-phase-b) 的主要静态输入, 也和 [Mention Syntax](./07-mention-syntax-spec.md#todo-phase-b) 强关联。

## Frontmatter 字段解析表

<!-- Phase B: 待填字段级内容 -->

[错误码速查表](./11-error-code-spec.md#todo-phase-b) 将覆盖字段缺失、默认值和类型错误。

## Body XML 扁平化容器

<!-- Phase B: 待填字段级内容 -->

[Cognitive Template 内部插槽布局](./06-cognitive-template-spec.md#todo-phase-b) 将引用 Body AST 到插槽的映射。

## 必须持有的业务核心标签

<!-- Phase B: 待填字段级内容 -->

缺失 `<role>` 或 `<goal>` 的 FATAL 行为见 [F-v3-agent 错误契约](./11-error-code-spec.md#todo-phase-b)。

## 引用注入校验 (Frontmatter ↔ Body)

<!-- Phase B: 待填字段级内容 -->

Body 中的 `@reference` 与 `@example` 校验需对齐 [Mention Syntax](./07-mention-syntax-spec.md#todo-phase-b) 和 [Resource Mechanisms](./08-resource-mechanisms-spec.md#todo-phase-b)。
