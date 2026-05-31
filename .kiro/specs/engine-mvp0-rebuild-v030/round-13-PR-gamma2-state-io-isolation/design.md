---
spec: engine-mvp0-rebuild-v030/round-13-PR-gamma2-state-io-isolation
phase: PR γ2 (State/IO Isolation)
owner: a2 主笔 / a1 audit
工程量: 35-45h
---

# PR γ2: State/IO Isolation Design

## §0 继承字段表 (Round 9/10/11/12 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。
- **SkillResolverProtocol**: 寻址闭环，入口必需 `skill_resolver` 不动。

## §1 字段表与变更清单

| 实体 | 现状态 | 目标状态 | 标记 | 迁移路径 (SOP-06) |
|---|---|---|---|---|
| `BlackboardData.inputs` | 不存在 | 仅存放经过 Funnel 的初始入参 | **[NEW]** | `state_mapper.py:build_phase_input` 中构建，作为执行期的只读数据区。 |
| `BlackboardData.phase_outputs` | 不存在 | 存放各 Phase 结构化产出 | **[NEW]** | 代替原扁平 `data` 中的顶层 key 写回。 |
| `BlackboardData.scratch` | 不存在 | 草稿本 | **[NEW]** | 允许插件/工具写出的中间态。 |
| `BlackboardState.data` | `dict[str, Any]` (扁平) | 嵌套三区字典 | **[BREAKING]** | 迁移：清理所有直接断言/写入 `state["data"][key]` 的测试和业务代码。受影响点包括 `_dict_delta`, Beta 的 `finish_task` 等。 |
| `BlackboardState.flow` | 任意读写 | deep-copy allowlist | **[MODIFIED]** | 在传递给子图/Phase前严格按白名单克隆，防止跨阶段意外共享引用。 |
| `BlackboardState.messages` | 继承传递 | `[]` (针对隔离子图) | **[MODIFIED]** | 隔离模式下的初始状态应重置为空列表。 |
| `ReaderSandboxState` (`.data` / `.flow` / `.messages` / `.run_id`) | 仅为 stub | 实际沙盒状态 | **[NEW]** | 创建完整的属性隔离壳。 |
| child result 回写区域 | 原地 merge | 走 `phase_outputs[phase_id]` | **[MODIFIED]** | 任何子图/子阶段的正确产出必须归档到输出区。 |
| `_invoke_subagent_once_t23` | `child_data = {**before, **input}` | 仅从显式 input 初始化 | **[MODIFIED]** | 迁移：删除父 `before_data` 暴力合并。`graph_assembler.py` / `test_v21_subagent_executor.py` 必须体现此行为断层。 |
| `_build_subgraph_node` | 传递整包 `before_data` | 只传已构造的显式 Input | **[MODIFIED]** | 迁移：子图输入必须经过 `PhaseWrapper` 构造，不扫父级 state。 |

## §2 跨 Round 影响链 (Cascading Impact on Round-12)

State shape 的**三区化 (Inputs, Phase Outputs, Scratch)** 是一项底层建筑重构。它直接冲击了 Round-11 和 Round-12 已 Ship 的代码：
- **CognitiveFlow / `finish_task` 写回**: Round-11/12 中 `handle_finish_task_tool_result` 将任务完成的结果返回为 `data={phase_name: final_write}` 试图写在扁平字典的顶层。这是**违反新三区**约定的行为，必须强制修正为写入 `data.phase_outputs[phase_id]`。
- **`wrap_phase_output` / `_dict_delta`**: 现有的 Delta 检测和单 key nested dict 放行规则也依赖于扁平层结构，必须同步重构以理解三区映射。

## §3 API 形态与核心机制

### 3.1 State Shape 规范化三区结构
`packages/graph-agent/src/graph_agent/runtime/state.py` 中的 `BlackboardState` 定义的 `data` 需变更为结构化的容器：
```python
class BlackboardData(TypedDict, total=False):
    inputs: dict[str, Any]         # 100% 只读，仅存放入参
    phase_outputs: dict[str, Any]  # 严格按 Phase 写入的结构化产出
    scratch: dict[str, Any]        # 自由读写的草稿本
```

### 3.2 Phase Wrapper 全节点接入点
`PhaseWrapper.wrap` 必须明确覆盖以下 **4 类节点**的接入点 (`graph_assembler.py`)：
1. **Agent Node**: 执行 `SKILL.md` 的常规循环。
2. **Logic Node**: 执行 `LOGIC.md` 的 Python 行列。
3. **Subgraph Node**: 代理调用外部 `SUBGRAPH.md` 图。
4. **Builtin Reference Reader**: 代理执行长文本阅读。
> **Double-wrap 风险声明**: 必须在装配期确保 `PhaseWrapper` **不可嵌套自己**，也不得在 Child Graph 的顶层被外部 Parent 的 Wrapper 进行二次包裹。每层图仅有一层输入/输出漏斗。

### 3.3 SUBGRAPH & Subagent 隔离输入语义 (Parent Leak Prevention)
子图 / Subagent 的 Child Funnel **绝对不扫描**父黑板的顶层键：
- 它们的输入只能通过外部（即 `SUBGRAPH` node 本身执行完毕准备调起子流程前，或显式的 Tool Argument）显式传入。
- 这个入参会直接作为 Child 环境的 `data.inputs` 初始值，并伴随一个空的 `messages = []` 进入子图。
- 这确保了完全切断父环境数据的泄漏路径。

### 3.4 D3 Reference Reader 新建与激活
针对 Reference Reader 沙盒：
- 不仅是激活 `runtime/state_mapper.py:95` 中的 `ReaderSandboxState` stub。
- **必须新建** `core/builtin_subagents/reference_reader.py` 作为其运行时实体，使其真正生效，并强制注入 `flow.timeout_s = 60`。

## §4 测试验收与迁移范围 (D5)

必须在同 PR 交付具备以下红灯断言的隔离测试 (`test_isolation.py` 及迁移原有测试)：
- **Parent Leak Prevention**: 断言子图运行时，无法在自身 `data` 中找到父图的 `scratch` 变量和 `messages` 历史。
- **Input Funnel Drop**: 断言输入了未在 `io.inputs` 声明的字段时，该字段会被静默丢弃，不会进入子图。
- **Inputs Read-only**: 任何节点或插件试图在运行中写入/修改 `data.inputs` 会抛出 Fatal 异常。
- **迁移范围**:
  - `graph-agent/tests/runtime/test_state_mapper.py` (验证三区构建)
  - `graph-agent/tests/core/test_v21_subagent_executor.py` (验证隔离与入参限制)
  - 现有依赖 flat `state["data"]` 断言的各项测试必须改为断言 `phase_outputs` 或 `scratch`。

## §5 工时拆分 (D1-D5: 35-45h)

| Task | 说明 | 预估工时 |
|---|---|---:|
| **D1** | Input Funnel + 规范化 state shape 三区 (含受影响的 `_dict_delta` 改造) | 8h |
| **D2** | Phase Wrapper 真覆盖 4 类节点及 double-wrap 保护 | 8h |
| **D3** | 新建 builtin reference reader runtime 并激活沙盒与超时限制 | 7h |
| **D4** | SUBGRAPH/subagent child 隔离执行改造，禁 parent leak，修复 `finish_task` 写回冲突 | 10h |
| **D5** | Isolation Tests 落地与现有 Flat Test 大规模迁移 | 12h |
| **合计** | (考虑到联合调试与 CI 冒烟) | **~45h** |