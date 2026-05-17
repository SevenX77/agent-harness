# MVP-3 Loader Pipeline & Middleware 简化 — CHANGELOG (Partial)

**期间**: 2026-04-29 → 2026-04-29
**Spec**: `.kiro/specs/v1-reset-mvp-3-loader-startup-middleware/`
**Direction**: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Scope**: `v1-reset-mvp-3-loader`

## 目标

重画 A2 Loader 为三阶段 Pipeline (parse → validate → build)。通过 A9-bis/A9-original 清理启动期的环境变量和 `sys.modules` 污染，建立安全的 `ModuleSandbox`。简化 B3 的散乱 Middleware 到四大核心类，最终实现系统加载和运行拓扑的一致性和透明性。

## 完成清单 (16-dim 维度 → MVP-3 落点)

| 维度 | 目标 | 落点 |
|---|---|---|
| **A9-bis / 启动序列清理** | `Bootstrap` 单次调用保护，`Settings` 数据替代 `os.environ` | T1 (25679e0) |
| **A2 / Phase 1: 纯文本解析** | `parse_skill_md` 剥离正则，仅做 Markdown 块与 YAML 切分 | T2 (aeda937) |
| **A2 / SkillManifest 模型** | 强类型模型替代散装配置，编译期注入 Schema | T2 (aeda937) |
| **A9-original / 模块沙箱隔离** | `ModuleSandbox` 消除 `sys.modules` 幽灵模块污染 | T5-skeleton (f4a1aa5) |
| **A2 / Phase 2: Schema 集成** | 接入 `SchemaEngine` 与 `IOManager` 验证 | T3 / T4 (4f5fed3 / 777df8d) |
| **A2 / Phase 3: 节点编译** | `build_graph_nodes` 生成 `PhaseNode` | T5-full (cee481f) |

*(注：由于 MVP-3 尚在实施中，T6-T12 相关 Middleware、Loader 替代与验收测试将在后续完善)*

## 关键度量 (baseline diff - Partial)

| 指标 | Pre-MVP-3 | Current | Δ |
|---|---|---|---|
| `runner.py` 内 `os.environ.set` 站点 | 多处 | 0 (逐步迁移) | 清理中 |
| `sys.modules` 写入站点 | ≥ 1 | 0 | 被 ModuleSandbox 隔离 |
| Loader 解析复杂度 | 极高 (混合 Regex) | 分层 | T2 分割了纯文本解析 |
| `**state` 解包模式 | 0 | 0 | — |
| Pytest passed | ~720 | TBD | — |

## Commits 时间线 (部分)

| Commit | 类别 | 摘要 |
|---|---|---|
| 25679e0 | T1 / feat | Bootstrap class + Settings + patches 集中模块 |
| f4a1aa5 | T5-skel / feat | ModuleSandbox 模块沙箱与 PhaseNode 接口骨架 |
| aeda937 | T2 / feat | Pipeline Phase 1 (`parse_skill_md`) + `SkillManifest` 模型定义 |
| 4f5fed3 | T3/T4 / feat | Loader validate / Phase 2 解析对接 |
| 777df8d | T3/T4 / feat | Loader validate / Phase 2 解析对接 |
| cee481f | T5-full / feat | 完整实现 Phase 3 `build_graph_nodes` |

## Deferred items (实施中)

1. **Middleware 集成**: 尚待 T7-T9 实施 `ProtocolValidationMiddleware` 等。
2. **废弃旧 SkillLoader**: 尚待 T6 用新 Pipeline 全面替换。

## 学习 / 风险记录

### L1 / Pydantic Discriminated Union 技巧
在含有 `mode: logic/llm` 等多态类型中，通过 PrivateAttr (`_compiled_schemas`) 配合 Property 实现编译期状态暂存，比破坏 `extra='forbid'` 或基类更具伸缩性。

### L2 / 细粒度并行实施
a1 和 a3 在此阶段高效执行并行作业：a1 推进核心的 T1、T2 基础类型；同时 a1 的 T5-skeleton 预留接口，避免了后期由于复杂依赖造成的主线阻塞。

## 下一步

继续推进 MVP-3 的剩余子任务 (T6-T12)，包含废除旧上帝类 `SkillLoader` 和 Middleware 梳理。