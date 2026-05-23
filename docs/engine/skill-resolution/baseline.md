# skill-resolution (engine) — Baseline (当下代码实现逻辑)

> **Status**: Added by a1 (Codex), 2026-05-23
> **Scope**: V2.1 子 skill / subagent 物理路径解析现状、`_resolve_subagent_root` 死代码盘点、V0.3.0 `SkillResolverProtocol` 的域边界准备。
> **配套**: 见 [SkillResolverProtocol Spec](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义)。

## 子模块定位 (Scope)

`skill-resolution` 是 Engine 内部的 Skill 资源寻址层。它回答一个问题: 给定 `skill_id`, Engine 如何找到对应 graph skill 根目录, 并确认它是一个可编译的 skill root。

它和 LLM routing 的哲学平行: LLM routing 把 `llm_role` 解析成模型实例; skill-resolution 把 `target_skill` 解析成磁盘上的 graph skill 根目录。两者都不应该把 Studio 配置、用户文件选择器、生产 registry 细节硬编码进 Engine。

本模块不是:

- 不是 `GRAPH.md` / `SKILL.md` schema 解析器; schema 在 [skill-spec](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义) 和 skill-compilation 中定义。
- 不是 Studio 导入 UI; 未注册 skill 的导入流程在 Studio backend/frontend 实现。
- 不是 Reference / Example 资源 resolver; V0.3.0 决议中 `SkillResolverProtocol` 只有 `resolve_skill(skill_id) -> Path` 单方法, 不提供 `resolve_resource()`。

## 现有实现盘点 (Current Implementation Inventory)

当前代码没有独立 skill-resolution 子模块。子 skill 寻址散落在 `packages/graph-agent/src/graph_agent/core/loader.py`, 且只服务 V2.1 subagent 相对路径。

| 代码位置 | 函数 / 对象 | 当前输入 | 当前输出 | 现状缺陷 | V0.3.0 处理 |
|---|---|---|---|---|---|
| `packages/graph-agent/src/graph_agent/core/loader.py:447` | `_resolve_subagent_root(skill_root, phase_path, subagent_path, subagent_name)` | phase-local relative path | `Path` | 只允许相对当前 phase 目录; 不支持跨 workspace / registry; 错误与 `phase_config` 绑定 | 废除, 改 `SkillResolverProtocol.resolve_skill(target_skill)` |
| `packages/graph-agent/src/graph_agent/core/loader.py:340` | `_compile_subagent_metadata(skill_root, phase_docs)` | `SkillNodeAST.subagents[].path` | `CompiledSubagent` 列表 | 递归 compile 依赖物理路径; 无 DI; 子 skill 未注册时只能路径失败 | 改为读取 `target_skill`, 通过 resolver 找 root |
| `packages/graph-agent/src/graph_agent/core/loader.py:387` | `_inject_subagent_tools(registry, subagents_by_phase)` | 编译出的 subagent metadata | 动态 `call_subagent_<name>` tool | tool metadata 绑定旧 `CompiledSubagent.root`; 无 registry provenance | tool 闭包保留 `target_skill` / resolved root metadata |
| `packages/graph-agent/src/graph_agent/core/loader.py:353` | `SkillLoader(...).compile_skill(sub_root)` | `_resolve_subagent_root` 返回路径 | child compiled skill | 子编译与父 skill 目录扫描耦合; 无 SkillResolutionError | resolver 失败映射 `[F-v3-skill-not-registered]` |
| `packages/graph-agent/src/graph_agent/core/loader.py:463` | `candidate.relative_to(skill_root_resolved)` | 本地路径 | path guard | 只防止逃逸父 root, 不能表达 registry 权限 | 权限边界交给 resolver 实现 |

现有实现的核心问题是“路径即身份”。作者在父 skill 的 frontmatter 里写 path, Engine 就按本地目录拼接。这无法支持 Studio Assets Panel 的跨 Skill 导入, 也无法支持生产环境只读 registry、私有 / 公共 skill 分层和 workspace mount。

## SkillResolverProtocol 域边界

V0.3.0 的 resolver 域只处理 graph skill root 寻址。输入是逻辑 id, 输出是物理 root path, 失败用结构化错误表达。

| 域 | 字段 / 对象 | 类型 | 必填 | 校验规则 | 失败模式 | 业务作用 |
|---|---|---|---|---|---|---|
| 输入域 | `skill_id` | string | 是 | `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | registry 查询 key |
| 输出域 | `root_path` | `pathlib.Path` | 是 | 路径存在、是目录、含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` | graph skill 根目录 |
| 未注册 | registry miss | exception | — | resolver 找不到 skill id | `[F-v3-skill-not-registered]` | Studio 可触发导入 |
| 未注入 | `skill_resolver` | Protocol | 需要子 skill 时必填 | 编译 / 运行入口必须传入 | `[F-v3-resolver-missing]` | 防止 Engine 猜路径 |
| 接口错误 | resolver object | Protocol | 是 | 只暴露 `resolve_skill` 语义 | `[F-v3-resolver-interface-invalid]` | 防止加回 `resolve_resource()` |

不归 resolver 管的场景:

| 场景 | 归属 |
|---|---|
| `references[].path` / `examples[].path` | 当前 skill root 内资源校验, 见 resource mechanisms |
| `actions/<name>.py` | LOGIC action 一级寻址, 见 [LOGIC Actions](../skill-spec/03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| LLM role 到模型实例 | llm-routing / ModelResolverProtocol |
| Studio 文件选择器导入 | Studio backend / frontend |

## 跟其他 engine 子模块的关系

| 子模块 | skill-resolution 提供什么 | 对方负责什么 | Cross-link |
|---|---|---|---|
| skill-compilation | `target_skill` -> skill root 的 DI 能力 | 解析 `SUBGRAPH.md` / Agent `subagents` / `subgraphs`, 构建 AST | [子图寻址 DI 注入](../skill-compilation/mvp0-alignment.md#3-子图寻址-di-注入-c6) |
| execution-runtime | 运行期 child graph / subagent 调用的同一 resolver | 调用 child graph, StateMapper 切片, tool 注入 | [SkillResolverProtocol DI 边界](../execution-runtime/mvp0-alignment.md#15-skillresolverprotocol-di-注入边界-c10-new-d) |
| state-and-io-contract | resolver 找到 target skill 后提供 child root | 按 target `GRAPH.md io.inputs` 做 child input funnel | [Child Graph 黑板隔离](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation) |
| tracing-and-observability | resolver failure 的错误码和 target metadata | 发 `EXCEPTION` / subagent trace / fallback trace | [Execution Runtime 调用点绑定](../tracing-and-observability/mvp0-alignment.md#3-execution-runtime-调用点绑定) |
| skill-spec | 协议字段级规范和错误码命名 | 定义文档契约 | [SkillResolverProtocol Spec](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义) |

## V2.1 → V0.3.0 改造概述

V2.1 痛点:

- subagent 身份由相对路径表示, 不能表达“这个 skill 已注册但不在当前目录下”。
- `_resolve_subagent_root` 把权限边界限制成“不能逃逸当前 skill root”, 但 Studio 需要跨 Skill 导入。
- 编译器和运行时都无法区分 registry miss、路径无效、resolver 未注入这几种失败。
- 生产环境无法用只读 workspace mount 或公共 / 私有 registry 替代本地路径扫描。

V0.3.0 战略意义:

- `SUBGRAPH.md target_skill`、Agent `subagents[].target_skill`、Agent `subgraphs[].target_skill` 都走同一个 resolver。
- Engine 只依赖单方法 Protocol, Studio / production / tests 分别注入实现。
- 未注册 skill 统一报 `[F-v3-skill-not-registered]`, Studio 可据此标红并引导导入。

本 baseline 只盘点现状和边界。改造目标与字段级实现顺序见 [mvp0-alignment.md](./mvp0-alignment.md)。
