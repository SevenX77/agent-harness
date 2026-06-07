---
module: 01-contract/05-invalidation
doc: mvp1-alignment
status: audited-ready（**U6 单元锁定 2026-06-05**:变更轴+消费者矩阵成段、codex 已审、反转前编译期块已退役;文件未 FROZEN——invalidation 仍参与 U5/U12）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 05-invalidation — 契约 A · 源变更 → 失效

> **Tier**: 契约层 A(声明式规则) | **Owns**: 「编辑 skill 后哪些派生物失效」的变更轴 taxonomy + 消费者矩阵 | **现状**: ⏳ + mvp1 delta | **Related**: `06-golden-eval`(golden 失效)· `03-checkpoint`(checkpoint 失效)· `03-compile-rules`/`01-compile`(cache 失效)

## 1. 定义
invalidation = **编辑 skill 后,哪些从它算出来并缓存/存档的派生物失效**——派生物 = **golden**(各节点期望输出)、**checkpoint**(存档运行状态)、**compile cache**(编译产物)。**一套变更轴定义,三个消费者各取所需**(不是一个检测器、也不是三套发散的"什么算变")。

## 2. 变更轴 + 消费者矩阵
**变更轴(taxonomy)**:A1 改 prompt/model/params/tools · A2a `io.outputs` 必填字段增删 · A2b 类型改 · A2c 非必填增删 · A3 `io.inputs` 改 · A4 上游输出改 · A5 拓扑改。

| 消费者 | 关心的轴 | 时机 | 后果 |
|---|---|---|---|
| **golden 失效** | **仅 A2a**(必填字段增→golden 缺) | **eval 期**(mvp1 改) | 该节点 golden stale,提示补齐 |
| **checkpoint 失效** | A2/A4/A5 | resume 期 | 下游 checkpoint 置脏 → 前端 [Resume] 置灰(软) |
| **compile cache** | 任意源改(源 hash) | 编译期 | 透明重编译 |

**实现原则**:一个检测器 `diff_skill(old,new)->set[ChangeAxis]`,消费者各取子集。

## 3. 接口契约
`diff_skill` 签名(skill×skill → set[ChangeAxis]);各消费者订阅自己关心的轴(golden→A2a、checkpoint→A2/A4/A5、cache→源 hash)。golden 失效落点见 `06-golden-eval`(eval 期),不再是编译期 `[F-v3-*]`。

## 4. 设计决策基础(用户原话)
> golden→workspace 连带(2026-06-03 PM):golden 是会失效临时产物,留 `.workspace` → golden 失效校验从编译期移到 eval 期(compile 读不到 workspace)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| IV1 | **一套变更轴 + 多消费者各取子集**(非一个检测器、非三套) | 防 golden/checkpoint/cache 各造发散的 staleness 检测器 |
| IV2 | **golden 失效从编译期移到 eval 期** | golden 在 `.workspace`,compile 读不到(连带 golden→workspace 反转) |
| IV3 | 退役旧 `io_outputs_schema_hash` 整哈希漂移检测 | 粒度太粗(改 prompt 也变 hash → 误报) |

## 6. 测试关键点
1. golden:改 prompt **不**失效;加 `io.outputs` 必填字段 → 该节点 golden stale(**eval 期**,非编译期)。
2. checkpoint:上游/拓扑/输出契约变 → 下游 checkpoint 置灰。
3. `diff_skill` 算出的 ChangeAxis 集正确(单元测试 A1–A5)。

## 7. 涉及 region / platform
engine 全权;失效语义影响作者(改 skill 后什么 stale)+ studio([Resume] 置灰 UI)。

## 8. gaps / 待设计
1. `ChangeAxis` 枚举 + `diff_skill` 实现(kiro,TDD)。
2. **golden 失效从编译期码移到 eval 期**的落地(与 `06-golden-eval` 协同;原 `[F-v3-golden-stale-fields]` 编译期码归属调整,见 `compile-rules` CR3)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `05-run-inner/06-golden-eval` · `04-run-outer/03-checkpoint` · `03-compile-rules`(CR3)· `02-mechanism/01-compile`(cache)
