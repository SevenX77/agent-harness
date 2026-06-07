# skill-resolution (engine) — Baseline

> **Status**: Updated by a1 (Codex), 2026-05-25  
> **Scope**: 当前 V0.3.0 PR δ ship 后 baseline。旧 V2.1 相对路径寻址已不是 active baseline。

## 1. 当前 baseline

当前 baseline 是 `target_skill + SkillResolverProtocol`。

Engine 不再把 child skill 的位置写成父 skill 内部路径。所有跨 skill 寻址必须先写稳定 id：

```yaml
target_skill: demo.child
```

然后由调用方注入的 resolver 把 `demo.child` 解析成本地 skill root。

## 2. 当前代码清单

| 文件 | 当前职责 |
|---|---|
| `core/skill_resolver_protocol.py` | 定义 resolver 协议、错误、id 校验、root 校验、缺 resolver fast-fail |
| `core/manifest.py` | 定义 `SubagentSpec.target_skill` 和 `SubgraphNodeAST.target_skill` |
| `core/compiler.py` | public compile facade，必填 `skill_resolver` |
| `core/loader.py` | 编译 skill root；subagent metadata 通过 resolver 找 child root |
| `core/graph_assembler.py` | SUBGRAPH runtime 通过 resolver 找 child root；subagent runtime 复用 resolver |
| `core/runner.py` | runtime 入口必填 resolver，并传给 compile / assemble |
| `core/skill_tool_factory.py` | path-based legacy tool wrapper 调 `run_skill` 时也要透传 resolver |
| `tools/builtin/parallel_map.py` | 每个 child run 透传 resolver |
| `tools/md_to_json.py` | patch agent run 透传 resolver |
| `apps/studio/backend/app/services/skill_resolver.py` | Studio backend resolver 实现 |

## 3. active schema

### Subagent

当前 Agent / Skill phase 的 subagent 配置：

```yaml
phase_config:
  subagents:
    - name: echo_expert
      target_skill: fixture.echo_expert
      description: Echoes text from a child expert skill.
```

active 字段：

- `name`
- `target_skill`
- `description`

旧 path 字段已移除。传旧字段会被 Pydantic extra-forbid 拒绝。

### SUBGRAPH

当前 `SUBGRAPH.md` frontmatter：

```yaml
---
mode: subgraph
name: child
target_skill: demo.child
---
```

active 字段：

- `mode`
- `name`
- `target_skill`
- `io`
- `validator`

旧 child 相对引用字段已退役。

## 4. 当前解析流程

### subagent 编译流程

1. `SkillLoader.compile_skill` 解析 phase document。
2. AST 中的 `SubagentSpec.target_skill` 已是必填字符串。
3. `_compile_subagent_metadata` 调 `resolve_skill_root(skill_resolver, spec.target_skill)`。
4. `resolve_skill_root` 校验 id、调用 resolver、校验返回 root。
5. child skill 使用同一个 resolver 递归 compile。
6. child `io.inputs` 生成动态 input model。
7. 动态 tool 注入到 parent phase。

### SUBGRAPH 装配流程

1. Loader 构建 `SubgraphNodeAST(target_skill=...)`。
2. `assemble_graph` 必须收到 resolver。
3. `_build_subgraph_node` 调 `resolve_skill_root(skill_resolver, phase_ast.target_skill)`。
4. child skill compile + assemble 都复用 resolver。
5. 运行时调用 child graph。

## 5. 错误语义

| 错误码 | baseline 含义 |
|---|---|
| `[F-v3-resolver-missing]` | 调用方没有注入 resolver |
| `[F-v3-resolver-skill-id-invalid]` | `target_skill` / `skill_id` 不是合法 registry key |
| `[F-v3-resolver-path-invalid]` | resolver 返回的 root 不是合法 graph skill root |
| `[F-v3-skill-not-registered]` | resolver 找不到这个 skill |
| `[F-v3-resolver-interface-invalid]` | 预留错误码；当前 src 无主动 runtime trigger |

## 6. Studio baseline

Studio backend 当前有自己的 resolver：

```text
StudioSkillResolver.resolve_skill(skill_id)
```

解析顺序：

1. 全局 skill index。
2. 默认 workspace skills 目录。
3. bundled skills 目录。

Studio 在 predict、run、validator、skills service compile/load 路径里显式注入 `build_studio_skill_resolver()`。

## 7. 非目标

当前 baseline 不覆盖：

- child graph state/IO 隔离深化。
- tracing event 扩展。
- Studio frontend 导入 UI。
- LLM model resolver。

这些属于其他 PR / 模块边界。

## 8. baseline 变更说明

旧 baseline 曾把相对路径寻址作为“当前实现盘点”。PR δ 后这已经过期。当前 baseline 以 hard cutover 后的代码为准：

- 不保旧 path alias。
- 不保旧 SUBGRAPH child ref。
- 不在 Engine 内部猜默认 resolver。
- 不从父 skill 目录扫描 child skill。
