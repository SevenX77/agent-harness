---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Mention Syntax Spec

本文定义 `@type:NAME` 的统一解析规则、7 类引用的静态可达性算法和 Loader 拦截边界。它服务于 [Agent SKILL.md](./05-agent-md-spec.md#引用注入校验-frontmatter--body)、[Resource Mechanisms](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) 和 [错误码字典](./11-error-code-spec.md#mention-domain)。

> ~~已迁移: `@type:NAME` regex、字段级定义和解析行为 → [mvp1 skill-syntax §2.7.1](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#271-typename-语法规范)。~~
> ~~已迁移: 7 大分类静态可达性算法 → [mvp1 skill-syntax §2.7.2](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#272-7-大分类静态可达性算法)。mvp1 delta:`@subgraph` 仍查 `frontmatter.subgraphs[].name`,但子项校验从 `target_skill` 改为绝对 `path`。~~
> ~~已迁移: 语法滥用与容错 → [mvp1 skill-syntax §2.7.3](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#273-语法滥用与容错)。错误码全集不在 skill-syntax 重复,见 [mvp1 compile-rules §4 mention domain](../../mvp1/01-contract/03-compile-rules/mvp1-alignment.md#mention-domain)。~~

## @-Mention 语法规范

全局 regex:

```regex
@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)
```

字段级定义:

| 部分 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `type` | enum string | 是 | 无 | 只能是 `subagent`, `tool`, `subgraph`, `protocol`, `step`, `reference`, `example` | `[F-v3-mention-type-unknown]` | 决定后续查哪个静态 registry |
| `NAME` | string | 是 | 无 | 正则 `^[a-zA-Z0-9_-]+$`; 区分大小写 | `[F-v3-mention-syntax-invalid]` | registry key |
| 完整 token | string | 是 | 无 | 必须无空格, 形如 `@reference:R1` | `[F-v3-mention-syntax-invalid]` | Studio 自动补全和 Loader 静态扫描的共同格式 |

解析行为:

1. Loader 只扫描 Agent `SKILL.md` body XML 的文本节点, 不扫描 frontmatter 字符串。
2. 匹配到合法 token 后生成 `MentionRef(type, name, source_tag, source_id, span)`。
3. 残缺写法如 `@reference:`, `@tool`, `@ reference:R1` 必须 FATAL, 不能当普通文本忽略。
4. Studio 编辑器按同一 7 类提供自动填充; 空分类不显示, 避免提示不存在资产。

为什么统一语法: `@reference:R1` 在正文里既是给人看的业务引用, 也是 Loader 可验证的静态依赖。它比自然语言“参考 R1”更硬, 能在编译期发现文档改名、示例删除、tool 未注册等问题。

语法错误的 FATAL 行为见 [F-v3-mention 错误契约](./11-error-code-spec.md#mention-domain)。

## 7 大分类静态可达性算法

Loader 必须按 mention 类型查对应可达域:

| 类型 | 查询域 | 注册来源 | 额外校验 | 失败错误码 |
|---|---|---|---|---|
| `subagent` | `frontmatter.subagents[].name` | Agent SKILL.md frontmatter | `target_skill` 字段合法 | `[F-v3-mention-target-not-found]` |
| `tool` | `frontmatter.tools[]` + framework builtin tools | Agent SKILL.md frontmatter + Engine builtin registry | tool 已注册且可暴露给当前 llm_role | `[F-v3-mention-target-not-found]` / `[F-v3-agent-tool-unknown]` |
| `subgraph` | `frontmatter.subgraphs[].name` | Agent SKILL.md frontmatter | `target_skill` 走 SkillResolverProtocol | `[F-v3-mention-target-not-found]` / `[F-v3-skill-not-registered]` |
| `protocol` | body `<protocol id="...">` | 当前 SKILL.md body AST | id 唯一 | `[F-v3-mention-target-not-found]` |
| `step` | body `<step id="...">` | 当前 SKILL.md body AST | id 唯一 | `[F-v3-mention-target-not-found]` |
| `reference` | `frontmatter.references[].id` | Agent SKILL.md frontmatter | path 合法; summary 非空 | `[F-v3-mention-target-not-found]` / `[F-v3-resource-reference-invalid]` |
| `example` | body `<example id>` + frontmatter document `examples[].id` | Agent SKILL.md body + frontmatter | inline body example 或 document example 合法 | `[F-v3-mention-target-not-found]` / `[F-v3-resource-example-invalid]` |

算法步骤:

1. 构建本地 registry: `subagents`, `tools`, `subgraphs`, `references`, document `examples`。
2. 构建 body registry: `protocols`, `steps`, inline `examples`。
3. 扫描所有 body 文本节点, 得到 mention refs。
4. 对每个 ref 按 type 查域; 不跨域 fallback。例如存在 tool `P1` 不能满足 `@protocol:P1`。
5. 聚合全部不可达 ref, 一次性报 `[F-v3-mention-target-not-found]`, payload 带 `type`, `name`, `source_tag`, `source_id`。

subgraph 寻址需经 [SkillResolverProtocol](./10-skill-resolver-protocol-spec.md#protocol-interface-定义), reference/example 寻址需经 [Resource Mechanisms](./08-resource-mechanisms-spec.md#frontmatter-挂载格式)。

## 语法滥用与容错

V0.3.0 对 mention 采用“语法宽入口、语义强校验”: token 字符允许大小写、数字、下划线和短横线, 但目标必须静态可达。

| 场景 | 示例 | 等级 | 错误码 | 处理 |
|---|---|---|---|---|
| 类型不存在 | `@asset:R1` | FATAL | `[F-v3-mention-type-unknown]` | 停止编译 |
| token 残缺 | `@reference:` | FATAL | `[F-v3-mention-syntax-invalid]` | 停止编译 |
| 目标不存在 | `@reference:R9` | FATAL | `[F-v3-mention-target-not-found]` | 停止编译 |
| 大小写不一致 | `@reference:r1` 但注册 `R1` | FATAL | `[F-v3-mention-target-not-found]` | 要求作者修正 |
| 未使用的注册项 | frontmatter 注册 R2 但 body 未引用 | WARN | `[F-v3-mention-unused-registry-entry]` | 不中断, trace 记录 |
| 普通邮箱/文本误伤 | `user@example.com` | 无 | — | regex 不匹配, 忽略 |

未使用注册项只 WARN, 因为 reference 可能通过 template registry listing 或 tool 按需读取, 不一定必须在 step 文本中显式出现。目标不存在必须 FATAL, 因为这代表正文已依赖一个无法装配的能力。

Loader 拦截位置见 [编译期校验流](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow)。
