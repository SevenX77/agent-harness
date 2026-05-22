# Mention Syntax Spec

本文定义 `@type:NAME` 的统一解析规则、7 类引用的静态可达性算法和 Loader 拦截边界。它服务于 [Agent SKILL.md](./05-agent-md-spec.md#todo-phase-b)、[Resource Mechanisms](./08-resource-mechanisms-spec.md#todo-phase-b) 和 [错误码字典](./11-error-code-spec.md#todo-phase-b)。

## @-Mention 语法规范

<!-- Phase B: 待填字段级内容 -->

语法错误的 FATAL 行为见 [F-v3-mention 错误契约](./11-error-code-spec.md#todo-phase-b)。

## 7 大分类静态可达性算法

<!-- Phase B: 待填字段级内容 -->

subgraph 寻址需经 [SkillResolverProtocol](./10-skill-resolver-protocol-spec.md#todo-phase-b), reference/example 寻址需经 [Resource Mechanisms](./08-resource-mechanisms-spec.md#todo-phase-b)。

## 语法滥用与容错

<!-- Phase B: 待填字段级内容 -->

Loader 拦截位置见 [编译期校验流](./12-compile-runtime-flow-spec.md#todo-phase-b)。
