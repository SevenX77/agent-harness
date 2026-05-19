---
status: Living
target_goal: "阐述 Engine 暴露的核心接口，以及图执行过程中的上下文流转和状态校验规则"
linked_code_paths:
  - packages/graph-agent/src/graph_agent/api.py
  - apps/studio/backend/app/services/run_manager.py
linked_specs:
  - .kiro/specs/predict-v2/
last_updated: 2026-05-19
---

# 图执行与数据模型 (Graph Execution Model)

## 1. 核心暴露 API 与使用场景
Engine SDK (`packages/graph-agent`) 对外保持极度克制的 API 面积，核心接口包括：
- `compile_skill(path)`: 解析并深度校验 `SKILL.md`，生成可执行的计算图对象。
- `predict(compiled_graph, inputs)`: （空转模式）验证数据绑定和纯代码逻辑，返回 Mock 的占位结果。
- `run(compiled_graph, inputs)`: （真实运行模式）连接真实 LLM，烧入 Token，执行完整业务逻辑。
- `resume(thread_id, state)`: 基于指定的 Checkpoint，从中断处接续运行。

## 2. Graph 拓扑流转规则与上下文大黑板
- **Context 字典 (The Blackboard)**: 各节点共享的全局状态。
- 每个节点通过 `inputs` 声明它需要从大黑板上拿走什么，通过 `outputs` 声明它将向大黑板写回什么。
- Engine 内部的 `DataMapper` 在节点进入前，会自动进行严格的类型断言和变量注入。

## 3. 空转 (Predict) 与真实执行 (Run) 的状态差异
- **Predict**: 针对开发阶段 (Studio)。屏蔽真实的 LLM API 请求，所有 LLM 返回均被替换为 `Mock Response`，极速跑完整个流程，旨在验证 Python 侧工具逻辑不崩溃。
- **Run**: 针对真实调度 (Studio & Cloud)。进行全量真实请求，收集所有的 API 耗时、Token 统计等 Trace 数据。

## 4. Checkpoint 与断点恢复机制
Engine 基于 `LangGraph` 的 Checkpointer 实现了完美的快照机制。
当节点由于 Validator 多次纠偏失败而抛出异常时，流程挂起，当前黑板状态保存。
外部（如 Studio 界面上的 PM）可以强行修正黑板中的非法数据或手工回答问题，随后调用 `resume`，图将毫发无损地继续向下执行。

## 相关 Spec
- [predict-v2](../../.kiro/specs/_archive/predict-v2/)
