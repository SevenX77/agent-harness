# 05 · Debug(调试续跑) — Workflow 节点

> **Tier**: workflow
> **旅程**: [04 运行与验收](./04_run-and-verify.md) 运行失败/暂停 → 就地节点级干预续跑
> **走查完整记录**(全部 atom actions + 决策 + 原话 + 测试关键点)。
> **定性**: 能力表标"全孤儿待新建";后端零碎原语(resume 端点 501、checkpoint 仅 thread/run 级),前端几乎全无。**真要新建,核心难点落引擎。**

## 旅程位
04 真跑失败/暂停 → 在**出问题的那个节点/那条边上就地干预**,从该点精准续跑(不重跑上游)。三场景:B 节点级续跑、A HitL 人工干预、C 篡改 Context 续跑。

## Atom actions（三场景 A/B/C）
| # | 动作 | 场景 | status |
|---|---|---|---|
| F1 | 失败节点亮红灯 + Error Message(Timeline 停在错误节点) | B 视觉 | placeholder |
| F2 | **节点级 [Resume] 按钮**(节点上;改完 prompt/代码点它,用 checkpoint 已有数据从该节点精准续跑,上游不重跑) | B 核心 | backend-only(端点 501) |
| F3 | **脏状态失效**:改上游节点/拓扑/输出 schema → 受影响下游节点 [Resume] 自动置灰,只有上游 checkpoint 有效的节点可 Resume | B | target-design |
| F4 | 场景A HitL:agent 调请求人类输入 → run 暂停 → **节点 debug bar 上方悬浮富文本输入框**(锚定节点,非固定顶栏)→ PM 输入 | A | target-design |
| F5 | 场景A 注入答案续跑:答完点 [Resume] → 答案作为消息注入,Graph 续跑 | A | backend-only |
| F6 | 场景C 篡改 Context:点边 dot → **复用 Monaco 编辑器(切可写)**展开上轮真实 Context → 手改 JSON → 存 | C | target-design |
| F7 | 场景C 用伪造数据续跑:篡改保存后点下游 [Resume] → 拿伪造 JSON 续跑下游 | C | backend-only |
| F8 | 上游入口:进 debug 前需先有一次真实 Run(产出 trace+checkpoint) | 前置 | placeholder(Run 桩) |

## 决策
- **Q3 编辑器复用**:篡改用的可写 Monaco = trace 只读编辑器切 readonly。
- **Q4 "事件→节点态"派生器归 trace-observability**(run 节点灯 + debug 红灯共用同一份派生)。
- 核心难点(节点级 checkpoint、HitL 通道、篡改续跑)**归引擎**。

## 原话(留底)
> "1. 没问题(debug UX 三场景) / 2. 节点级 checkpoint 粒度 要,但是提出你前端UI的要求和设计, 你是设计用户交互心智的 / 3. 编辑器复用 / 4. (事件→节点态派生器)你先来定一下"

## 测试关键点
- 节点级 Resume:从节点 X 续 → 1..X-1 用 checkpoint 不重跑。
- 脏状态:改上游 → 受影响下游 [Resume] 置灰;无关节点仍可 Resume。
- HitL:agent 请求输入 → 暂停 + 顶部问题框 → 答案注入 → 续跑。
- 篡改:点 dot → 可写编辑器改黑板 → 存 → 下游 Resume 用篡改数据。
- [Resume] 锚在节点上(非全局)。

## 引擎需求
节点级 checkpoint + checkpoint 失效追踪 + HitL 注入续跑 + 篡改续跑 → 引擎契约 [`03-checkpoint`](../../../engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md)。
> ⚠️ debug checkpoint 与 batch/loop 的 loop 状态机同源 → 引擎须设计**统一状态机**。
