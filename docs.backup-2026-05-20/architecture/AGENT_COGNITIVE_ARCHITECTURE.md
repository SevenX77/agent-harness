---
status: Living
target_goal: "定义 Graph Agent 独有的声明式工作流理念，以及三层控制/双层循环的内部认知机制"
linked_code_paths:
  - packages/graph-agent/src/graph_agent/core/
  - apps/studio/backend/app/services/copilot.py
linked_specs:
  - .kiro/specs/predict-v2/
last_updated: 2026-05-19
---

# Agent 认知与控制架构 (Cognitive Architecture)

## 1. 框架核心理念 (声明式工作流)
与市面上允许大模型自由发散的框架不同，Graph Agent 采用**强编排的声明式拓扑** (`SKILL.md`)。
大模型仅在由 PM 预先划定好的沙盒 (Phase) 内进行局部推理，而整体状态机的流转、前置后置校验，均由严谨的代码逻辑掌控，从而兼顾 LLM 的泛化能力与企业级的可靠性。

## 2. Agent Loop 双层控制机制内幕
当一个节点被赋予 Agent 权力时，它内部并非只是一次简单的 API 调用，而是执行一个被称为 `Agent Loop` 的复杂双层循环：
1. **外层 (Plan & Reflection)**: 
   - 每次循环开始前更新工作记忆 (Working Memory)。
   - 评估当前距离目标还差什么，生成执行计划。
2. **内层 (Action & Validation)**: 
   - 执行选定的 Tool 动作。
   - 获取外部数据。
   - 若出现格式或意图错误，底层触发 `Validator` 强制纠偏 (`Nudge`)。

## 3. Phase 的三种互斥模型深度解析
在一个 SKILL 拓扑中，每一个 `Phase` 节点必须严格归属于以下三种类型之一：
- **Code-only (确定性执行)**: 纯 Python 代码流水线，不消耗任何 LLM Token，执行速度极快，用于前置数据处理或组装。
- **Agent-Loop (智能推理)**: 挂载了角色和工具的 LLM 节点，能在限定约束内自行探索。
- **Subgraph (图嵌套)**: 作为一个黑盒，完整委派给另一份 `.SKILL.md`，实现多层复合 Agent 协同。

## 4. 框架的硬性开发红线
- **禁止状态穿透**: 一个 Phase 无法直接读取另一个 Phase 的内部临时变量，一切必须通过显式的 Context 大黑板 (Context Bridge) 传递。
- **不可突变的系统 Prompt**: 运行时的 Tool 异常反馈只附加在 User Message 或 Tool Message 里，绝不允许动态修改 System Prompt 本身。

## 5. Studio Copilot 上下文组装与 Claude Agent SDK 注入
为了让 Studio 右侧陪伴的 Copilot 能“读懂”整个 Agent Harness 仓库的框架知识，必须执行严格的 Context 注入流程（对应 MVP0 模块 3 的核心诉求）。

### 读取规则与组装管道
Copilot 不应该每次向大模型全量传输仓库源码，而是按需组装知识段。
1. **知识基底**: 提取核心架构文件：
   - `docs/engine/WORKSPACE_AND_FILE_SPEC.md`
   - `docs/engine/LLM_ROUTING_AND_FALLBACK.md`
2. **当前工作区状态**: 抓取当前用户正处于哪个 Skill 目录下，并提取该 `SKILL.md` 源码及出错日志。
3. **去重与 Chunking**: 后端接收到这些数据后，进行 Deduplication 处理，剔除重复概念。

### 注入与 SDK 调用链路
后端接口 `apps/studio/backend/app/services/copilot.py` 中，使用 Claude Agent SDK 组装系统级提示词：
```python
# 伪代码：Copilot 注入点
async def build_copilot_session(skill_id: str, error_log: Optional[str] = None):
    # 加载系统基底知识
    base_knowledge = load_docs_as_string(["WORKSPACE_AND_FILE_SPEC.md"])
    # 获取当前用户正操作的代码
    current_skill_content = get_skill_content(skill_id)
    
    system_prompt = f"""
    You are an expert GraphAgent builder.
    ## Core Architecture Rules:
    {base_knowledge}
    
    ## Current Workspace Context:
    {current_skill_content}
    """
    
    # 将系统知识与当前提问传入 SDK
    async for chunk in claude_agent_sdk.stream(
        system=system_prompt,
        messages=[...],
        tools=available_actions
    ):
        # 通过 WebSocket 流式推给前端 UI 渲染
        yield build_websocket_payload(chunk)
```
这段实现入口保障了 Copilot 绝非在真空中聊天，而是时刻清楚当前的框架约束和上下文状态。

## 相关 Spec
- [predict-v2](../../.kiro/specs/_archive/predict-v2/)
