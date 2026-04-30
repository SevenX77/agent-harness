# MVP-2 SchemaEngine + IOManager 抽出 — CHANGELOG

**期间**: 2026-04-29 → 2026-04-29
**Spec**: `.kiro/specs/v1-reset-mvp-2-schema-io/`
**Direction**: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md`
**Scope**: `v1-reset-mvp-2-schema-io`

## 目标

抽出 A5 `SchemaEngine` 与 A7 `IOManager` 独立组件。将散落在 loader、finish_task、md_to_json 等 5 处的 Schema 解析逻辑收拢进统一的 SchemaEngine 接口；把跨 Phase 状态搬运硬编码的 `hoist_to` 逻辑收拢到 IOManager。打通从 Markdown 到 Pydantic 的完整验证及类型提取闭环，消除“弥散性”数据处理逻辑。

## 完成清单 (16-dim 维度 → MVP-2 落点)

| 维度 | 目标 | 落点 |
|---|---|---|
| **A5 / SchemaEngine 抽出** | SchemaEngine 接口，`parse_from_md` / `get_pydantic_model` | T1 (6199f25) + T2 (d0c59ed) |
| **A7 / IOManager 抽出** | IOManager 接口，`resolve_hoist` 状态不可变搬运 | T3 (85ee76c) |
| **A8 / ContextBridge 对接** | `to_business_data_schema` 经由 SchemaEngine 路由 | T4 (095d1cc) |
| **A4 / finish_task 通道对接** | finish.py 接入 SchemaEngine.validate 与 IOManager | T5 (5946638) + T5-hotfix (537c6bb) |
| **A2 / loader wiring** | 引入 `get_schema_engine` 单例做编译期/运行期双轨预热 | T6 (e2d28fe) |
| **A7 / io_errors 闭环** | io_errors 集中累积于 IOManager 并流入 `state["flow"]` | T7 (13175d9) + T7-bis (cd3c337) |
| **Part E / 测试与覆盖率** | 核心模块 SchemaEngine + IOManager 覆盖率 ≥ 95% | T8 (a0728ef) |

## 关键度量 (baseline diff)

| 指标 | Pre-MVP-2 | After MVP-2 | Δ |
|---|---|---|---|
| `state["data"]` 含 `_` 前缀字段数 | 0 | 0 | 保持纯净 |
| Schema 解析路径散落数 | 5 | 1 | 统一收口 |
| `ContextBridge` 内部解析器 | 有 | 无 | T4 移除 |
| finish_task 纯手动词典赋值 | 有 | 无 | T5 移除 |
| Pytest passed | 643 | >720 | +80左右 |
| SchemaEngine / IOManager 覆盖率 | N/A | ≥ 95% | 达标 |

## Commits 时间线

| Commit | 类别 | 摘要 |
|---|---|---|
| 6199f25 | T1 / feat | SchemaEngine 模块骨架 + 单测 |
| d0c59ed | T2 / feat | SchemaEngine 完整解析逻辑 (支持嵌套、Optional、Literal等) |
| 85ee76c | T3 / feat | IOManager 模块 + hoist_to 不可变状态搬运 |
| 095d1cc | T4 / feat | ContextBridge 重构使依赖 SchemaEngine |
| 5946638 | T5 / feat | finish.py 改造接入 SchemaEngine 验证机制 |
| 537c6bb | T5-hotfix | finish.py Markdown 解析链断层与测试用例障眼法修复 |
| e2d28fe | T6 / feat | loader.py 引入 `get_schema_engine` 单例做双轨过渡 |
| 13175d9 | T7 / feat | io_errors 路径迁移至 IOManager 实例累积 |
| cd3c337 | T7-bis / fix | T7 的补充修复 |
| a0728ef | T8 / test | 端到端集成测试，SchemaEngine/IOManager 覆盖率超 95% |

## Deferred items (不阻塞 MVP-2 ship，记录在册)

1. **Loader 完整拆解**: T6 仅做了 wiring 预热缓存，真正的解析迁移推入 MVP-3 (T3/T4)。
2. **SchemaObject Field Names**: `fields` 为嵌套 tuple，需给 `SchemaObject` 提供一个更友好的 Property。
3. **旧 io_manager.py**: 尚未完全废弃，待旧 SaveOutputs 机制移除后彻底下线。

## 学习 / 风险记录

### L1 / Defense-in-depth 需有扎实基础 
T5 中的 `finish_task` 把防御性 SchemaEngine 验证退化为了透传 raw markdown，多亏 a2 的 audit 和 T5-hotfix 才免于破坏数据通道。这告诉我们，不要让防御性设计绕过真实的解析前置逻辑。

### L2 / 假性测试绿灯风险
T5 的障眼法测试利用了 Pydantic `extra='forbid'` 在空 schema 情况下的报错假性通过了测试。严格的单测必须包括真实的 Schema。

## 下一步: MVP-3

**A2 Loader 重画 / A9 启动序列清理 / B3 middleware 简化**:
将全面重画 Loader 三阶段 Pipeline，拆解巨大的单体 Loader，并实施 `ModuleSandbox` 隔离与 4 核心 Middleware 收敛。
