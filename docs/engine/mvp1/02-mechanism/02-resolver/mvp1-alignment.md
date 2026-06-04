---
module: 02-mechanism/02-resolver
doc: mvp1-alignment
status: drafted（机制·编译期;⏳ 成段）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·编译）
---

# 02-resolver — 机制 B · 引用解析(DI 接缝)

> **Tier**: 机制层 B · 编译期 | **Owns**: `SkillResolverProtocol` DI 接缝 · local_workspace 解析(stable skill id → 本地 root) | **现状**: ⏳ | **Related**: `01-compile`(用它解析 SUBGRAPH/subagent)· `07-subagent`(运行期子代理)· mvp0 `10-skill-resolver-protocol`

## 1. 定义
resolver = 把 skill 里的**引用**(SUBGRAPH 的 `target_skill`、subagent 目标、registry 寻址)解析成**本地 skill root** 的 DI 接缝。**接口在引擎、实现由 studio 注入**(studio 是 registry 真相源)。

## 2. 数据流 / 机制
`SkillResolverProtocol.resolve_skill(skill_id) -> 本地 root`;缺 resolver 时 `require_skill_resolver` 抛 `[F-v3-resolver-missing]`。loader 校验 SUBGRAPH io / 编译 AgentNode subagent 时经它递归解析 child skill。机制权威 mvp0 `10-skill-resolver-protocol`,链接不复制。

## 3. 接口契约
`resolve_skill(skill_id) -> root`(producer=studio 实现,consumer=engine loader);**DI 不得被 middleware 隐式全局化**——`07-subagent` 的中间件只消费 `_build_skill_node` 已备好的 runtime map,不自己找 resolver。

## 4. 设计决策基础(用户原话)
> resolver 独立(2026-06-03 PM):"当然是独立, 不能用内容多少来判断模块是否独立" —— 它是 studio 注入的外部协议接缝,独立成模块。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RS1 | resolver 是独立 DI 接缝(非并进 compile) | 外部注入的集成点,职责独立(非按大小) |
| RS2 | DI 显式、不全局化(中间件消费已编译 runtime map) | uncovered §2:防隐式全局依赖 |
| RS3 | SUBGRAPH(编译期解析)vs subagent(运行期派发)分清 | 断层#7,两种子执行不同生命周期 |

## 6. 测试关键点
1. 缺 resolver → `[F-v3-resolver-missing]`。
2. SUBGRAPH/subagent target_skill 递归解析正确;循环引用防护。
3. middleware 不绕过 resolver 重新解析(消费已备 map)。

## 7. 涉及 region / platform
engine 定义协议;studio 实现(registry 真相源)。

## 8. gaps / 待设计
1. 成段化 resolver_protocol + local_workspace(现散 uncovered/mvp0)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-compile` · `05-run-inner/07-subagent`(断层#7)· mvp0/`10-skill-resolver-protocol`(FROZEN)
