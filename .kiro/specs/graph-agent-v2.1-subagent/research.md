# Research: Subagent Framework

> Spec owner: a2 Gemini (designer/analyst)

## 1. V2.1 Engine 现有 Subgraph 机制的实证

在决定 subagent 的底层依靠什么时, 我们审视了 V2.1 已有的基建。

源码实证: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:140-157` (`_subgraph_node`):

```python
def _subgraph_node(state: BlackboardState) -> dict[str, Any]:
    result = sub_assembled.graph.invoke({
        "data": before_data,
        "flow": state.get("flow", {}),
        "messages": [],   # 关键: 强制清空对话上下文
        "run_id": state.get("run_id"),
    })
    ...
```

这证明现有的 `sub_assembled.graph.invoke()` **天生具备完全隔离上下文的"黑盒代理"属性**, 可以直接充当 subagent 的底层载体。

关联代码:
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130-138`: `SkillLoader().compile_skill(sub_root)` + `assemble_graph(sub_compiled, ...)` 把子 skill 独立编译成另一个 LangGraph 图
- `packages/graph-agent/src/graph_agent/core/harness.py:777`: subgraph.execute 入口已存在
- `packages/graph-agent/src/graph_agent/core/run_context.py:30`: subgraph nodes 已是 collaborator (RunContext 的一等公民)

## 2. 业界 Subagent 模式扫描

| 模式 | 出处 | 特征 |
|---|---|---|
| **Handoff** | OpenAI Swarm | 极简, agent 之间转移 state, 属于交接模式 (不是嵌套调用) |
| **Task tool** | Claude code / Anthropic Agent SDK | 主 agent 调取一个内置 `Task` 工具派发子目标, 典型 "动态指令委派" |
| **Send API** | LangGraph | 针对一个 state 数组并发拉起多个相同节点 (map-reduce 范式) |
| **SubagentExecutor (ThreadPool)** | DeerFlow | 拉起隔离的沙盒状态机执行任务, 通过 `disallowed_tools` 阻止嵌套 |

User 明确反对 DeerFlow port 路径, 见 §3。

## 3. 为什么拒绝 DeerFlow Port?

a2 此前 (Phase 2 alignment) 推荐完整 port `deerflow/subagents/executor.py`, 但 user 5/18 明确抵制:

> "现在是不用 deerflow 的 subagent 模块, 而是在 agent loop 中自己调用一个 tool, 这个 tool 调用一个 subgraph"

重新审视方案:
1. DeerFlow 采用纯线程池 (ThreadPoolExecutor) 隔离运行, 与基于 asyncio 的 LangGraph 原生异步状态机格格不入, 引入状态写锁问题
2. V2.1 的 `_subgraph_node` 已经将另一张图完美隔离跑起 (`messages: []` 实证)
3. 重新 port 纯 Python executor 纯属重复造轮子

**结论**: 复用现有 subgraph 引擎的内部执行器, 将触发口暴露为给大模型的 tool 即可。

## 4. 动态并发派发的痛点与解法 (Schema Validation)

行业里凡是用到类似 `parallel_map` 工具让 LLM 一次生成 N 个对象的数组时, LLM 极易产生严重的幻觉或字段漏写, 导致执行期崩溃 (典型例: 该传 list of dict 传成单个 dict / key 名错 / list 长度不匹配)。

a2 原方案对此推荐 "手写 Python dispatcher 兜底", 但 user 5/18 push back:

> "我不太建议用自己写的, 这玩意儿是和业务逻辑没关系的, 应该聚合在 engine 里面的"

**最终解法** (跟 user 设计 align): 剥夺 PM 手写 dispatcher 的权限, 由引擎作为**绝对唯一 dispatcher**。

引擎在 `call_subagent` tool 层面截获 LLM 给的 JSON, 用 Pydantic 对照子技能的 input schema 进行强验证。错了直接抛回:

```
ToolMessage(content="Validation Error: Expected {'scene_text': str}. You provided {'text': '...'}. Please retry with correct schema.")
```

进行带指导的纠错循环 (informed retry, 不是 dumb retry), 最大 10 次。

## 5. 并发模型选型

| 选项 | 评估 | 决定 |
|---|---|---|
| `ThreadPoolExecutor` | 与 LangGraph asyncio 死锁隐患 | 淘汰 |
| `asyncio.gather` | 可用, 但在 LangGraph 生态外不便溯源 | 备选 |
| **`langgraph.Send`** | 现有图内动态 spawn 分支, 原生支持 tracing 溯源和并发度管理, 生态内最佳实践 | **中标** |

并发上限默认 = 3 (user 拍, 沿用业界共识)。

## 6. 跟 V2.1 SUBGRAPH 的关系澄清

| | subagent | SUBGRAPH (现有) |
|---|---|---|
| 路由方式 | **动态** (LLM agent loop 决定调不调) | **静态** (编译期拓扑, 执行到必进) |
| 调用入口 | builtin tool `call_subagent` | phase 声明 `subgraph: <ref>` |
| Context 隔离 | 是 (复用 subgraph 机制) | 是 (`messages: []`) |
| 视觉化 | "Toolbox" badge on phase node | drill-down 双击进入 |
| 用途 | 主 agent 自主调度子专家 | 编排好的多步流程 |

二者并列, 不嵌套。subagent 可以视作 "把一个完整 skill 包装成 tool 供上层 runtime 随时取用" 的能力。
