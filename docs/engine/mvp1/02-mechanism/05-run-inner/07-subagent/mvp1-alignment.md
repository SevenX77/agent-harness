---
module: 02-mechanism/05-run-inner/07-subagent
doc: mvp1-alignment
status: drafted（机制·运行内层;⏳ 迁自 05-subagent-dispatch）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 07-subagent — 机制 B · 运行期子代理派发(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: 运行期子代理派发(`_invoke_subagent_tool` → `wrap_tool_call` 中间件) | **现状**: ⏳ | **Related**: `02-middleware`(本域是 wrap_tool_call 中间件)· `02-resolver`(SUBGRAPH 编译期对照,断层#7)· `06-seam/02-observability`(lifecycle 事件)· `05-exit-control`(对称)

## 1. 定义
subagent = **运行期**派发子代理:AGENT 在 loop 里调子代理工具(`call_subagent_*`)时,经 `wrap_tool_call` 中间件把调用派发成一次 child graph 运行。**实现为中间件但职责独立**(像 `05-exit-control`)→ 独立模块。区别于 SUBGRAPH(**编译期**子图,归 `02-resolver`/`01-compile`,断层#7)。

## 2. 数据流 / 机制
`SubagentDispatchMiddleware.wrap_tool_call`:非 `call_subagent_*` 透传;命中则从 `request.state` 取 WorkflowState → depth guard → 调 child graph(`_invoke_subagent_once` 构 BusinessData、继承 child flow、`_dict_delta` 只返回变化)→ 维护 `subagent_validation_retries`/`subagent_depth`、parent metadata。runtime map(预编译 child graph)在 `03-assemble` 的 `_build_skill_node` 构造。

## 3. 接口契约
子代理工具签名(`call_subagent_<name>`,skill-spec 产出,不改 frozen)→ 派发契约;child config 保留 `parent_run_id`/`subagent_depth`/`tags`;**DI 不全局化**——中间件只消费已备 runtime map,不自己找 resolver(`02-resolver` RS2)。lifecycle 事件(start/end/error)→ `02-observability`(**当前缺 A2**)。

## 4. 设计决策基础(用户原话)
> subagent 放 inner(2026-06-03 PM):"运行期子代理派发…这个放在 outer 是什么原因??" → 它是 `wrap_tool_call` 中间件、被 agent 的 tool call 触发,归内层。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SA1 | 派发收进 `wrap_tool_call` 中间件,独立模块(像 exit-control) | 机制相同≠同模块,职责独立 |
| SA2 | subagent(运行期)vs SUBGRAPH(编译期)分清 | 断层#7,两种子执行不同生命周期 |
| SA3 | 中间件只消费已备 runtime map,不全局找 resolver | uncovered §2:DI 显式 |

## 6. 测试关键点
1. create_agent 路径下 subagent 仍走 engine dispatcher(depth/隔离/parent metadata 保留)。
2. subagent lifecycle 事件补全(A2),trace 不缺子代理段(→ `02-observability`)。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计
1. **subagent lifecycle 事件缺(A2)**——补 start/end/error(与 `02-observability` 协同)。
2. **断层#7**:SUBGRAPH vs subagent 归属边界(与 `02-resolver` 协同)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3(断层#7)· `02-middleware`(本域=wrap_tool_call 中间件)· `02-resolver`(SUBGRAPH 对照)· `06-seam/02-observability`(lifecycle)· `05-exit-control`(对称)
