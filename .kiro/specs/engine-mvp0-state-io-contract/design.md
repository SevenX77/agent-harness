# Engine MVP0 — state-and-io-contract Design

## §0.5 继承字段表 (round N-1 = main HEAD 现状, MVP0 默认不动)

### BlackboardState (state.py) 与核心模块

| 字段 | 类型 | 含义 | MVP0 是否改 |
|---|---|---|---|
| `BlackboardState.data` | `Annotated[dict, shallow_dict_merge]` | 业务数据黑板 | 不改 (只换 Reducer) |
| `BlackboardState.flow` | `dict` | 框架控制流 | 不改 |
| `BlackboardState.messages` | `Annotated[list, add_messages]` | LLM 对话历史 | 不改 |
| `BlackboardState.run_id` | `str \| None` | 运行 ID | 不改 |
| `shallow_dict_merge` | `function` | 当前并行写冲突红线 | **[BREAKING] 换** |
| `IOManager.load_inputs` | `method` | 历史 2.0 版的 file/runtime 加载器 | 不改 (保留 Legacy 且不进主线) |
| `ContextResolver` | `class` | 历史 2.0 版的依赖取值引擎 | 不改 (保留 Legacy) |

### [NEW] 新增
- `StateMapper` `[NEW]` — 负责依据 `PhaseIOSchema` 从 `inputs` 或上游提取局部的 `phase_input`。
- `phase_outputs` 命名空间 `[NEW]` — 在黑板内部，专门留作节点输出存放区域 (形如 `data["phase_outputs"][phase_id]`)。
- `filter_runtime_inputs()` `[NEW]` — 位于 runner.py 之前的输入过滤函数。
- `BlackboardState.inputs` `[NEW]` — 候选新增字典键，用于存储入场前的纯净、只读输入全集。

### [BREAKING] 修改现有 (必须 PM 拍板)
- `data` 属性的 reducer：`shallow_dict_merge` → `smart_dict_reducer` `[BREAKING]` — 更改了冲突合并语义，允许顺序重写。
- `_run_v21_skill_dict` (runner.py) 入口初始化：直接 `dict(inputs)` → 调用 `filter_runtime_inputs(inputs, schema)` `[BREAKING]` — 强滤所有入参脏数据。
- LOGIC 节点的 `Context` (graph_assembler.py) 包装范围：全量 `state.data` → `phase_input` (仅限 io 声明的 Key) `[BREAKING]`。
- SUBGRAPH 节点的 child data 初始化：全量父图 `state.data` → explicit input only `[BREAKING]`。
- Subagent 调用阶段的 child data：`{**before_data, **input_data}` → explicit input only `[BREAKING]`。

## §1. P0-3 顺序覆盖冲突 修复

### §1.1 候选 A: smart_dict_reducer 替换 shallow_dict_merge
- **描述**：重写状态的合并拦截器。对于相同的 Key，检查它们是否来源于同一个 super-step (也就是 LangGraph 并发扇入点)。如果是并发覆写抛冲突；若是不同 step 的先后时序更新，采用 `dict.update` 合法覆盖。
- **冲击范围**：`packages/graph-agent/src/graph_agent/runtime/state.py:13-32`。
- **兼容性**：完全兼容旧系统但消除了致命的先后覆盖拦截。

### §1.2 候选 B: phase_outputs 命名空间, 顶层不重名
- **描述**：通过隔离根治。将一切节点的数据更新隔离写入以节点ID为键的二级字典里 (如 `data["phase_outputs"]["branch_a"]["foo"]`)。顶层不重合，自然不冲突。
- **冲击范围**：`graph_assembler.py` 几乎所有的逻辑返回值。
- **兼容性**：破坏性较大，所有节点内部取数都需要明确指明来源。

### §1.3 候选 C: A + B 组合
- **描述**：兼收并蓄。用 smart_dict_reducer 解除现有的直接宕机，为框架注入柔性；同时引进 phase_outputs 作为推荐的新式输出靶向，彻底实现黑板分区。

### §1.4 推荐 + 拍板项
- **推荐**：候选 C。同时缓解痛点并建立清晰未来的治理。
- **PM 拍板 Q-S-P0-3**：Reducer 冲突是否直接通过 `smart_dict_reducer` (候选A) 及 `phase_outputs` 组合解决跨步覆盖的问题？

## §2. A1 runtime input funnel

### §2.1 候选 A: 显式 filter_runtime_inputs() with jsonschema strict
- **描述**：依据 Block 1 阶段 `io/inputs.json` 的 JSON Schema 定义，在 `runner.py:471` 创建一套过滤漏斗。拒绝不在属性名单内的所有意外字段，并可实施基本的数据类型强转与缺省值填补。
- **冲击范围**：`packages/graph-agent/src/graph_agent/core/runner.py`。
- **兼容性**：极强。任何从外部传入脏数据或隐式参数的代码将会在一开始就被报错（或拦截）。

### §2.2 候选 B: 复用 legacy IOManager.load_inputs() 接 V2.1
- **描述**：强行将 V2.0 时代的 `IOManager` 从冷宫请回主流程。
- **冲击范围**：整个引擎加载入口的依赖。
- **兼容性**：极差。不仅带有文件存取的重包袱，与目前 V2.1 的干净启动意图相违背。

### §2.3 推荐 + 拍板项
- **推荐**：候选 A。严卡入参，清爽利落。
- **PM 拍板 Q-S-A1**：是否明确采用基于 jsonschema 的 strict `filter_runtime_inputs` 漏斗拒绝一切未在 schema 声明的运行时参数？

## §3. A2 phase-level IO 契约

### §3.1 候选 A: phase wrapper sandbox + 限 io.inputs 字段
- **描述**：依赖于 Block 1 编译期构建的 `PhaseIOSchema`。在所有任务启动前截取 `BlackboardState`。只有被标定为 `required` 的变量才会构成精简的 `phase_input` 进入计算流。
- **冲击范围**：`graph_assembler.py` 的构建包裹函数中。
- **兼容性**：极具破坏性。这代表所有过往没有显式声明需要的脚本，在读参数时全部崩溃。

### §3.2 候选 B: warning-only, 不 sandbox
- **描述**：依旧下放全量的 `state.data`，但利用 Trace 层去检测是否读取了不属于它声明的数据并抛出警告。
- **冲击范围**：较小。
- **兼容性**：完全兼容。但放弃了 A2 安全治理。

### §3.3 候选 C: 跟 pending-questions §3 context_mapping 调和
- **描述**：使用与 PM 在 pending-questions §3 中讨论一致的双模方案。如果没有写出显式的 map，默认按 `phase_outputs` 加名字匹配执行沙箱。如果显式书写，调用轻量级的 `{dot.path}` 工具精确定向传递参数。
- **冲击范围**：中等，建立统一 Mapper 即可。

### §3.4 推荐 + 拍板项
- **推荐**：候选 C。它是向未来演进的中间解，即享受了隔离又具有可定制映射。
- **PM 拍板 Q-S-A2**：当前节点的输入上下文，是否进行强制沙箱劫持？(或者仅提供 Warning) 并且是否同意采纳 PM §3 的 mapper 思想融合入参？

## §4. A3 + A6 子图隔离 (合并)

### §4.1 候选 A: 全隔离 (subagent + SUBGRAPH 都按 explicit input)
- **描述**：不再继承环境。无论是 Subagent 工具调用还是 SUBGRAPH 分支，传入的字典彻底阻断父级的 `{**before_data}`，必须依据 explicit mapping 和 config 所选定的内容干干净净地初始化图实例。
- **冲击范围**：`graph_assembler.py:155-164` 和 `graph_assembler.py:398-403`。
- **兼容性**：破坏性改变。所有习惯于偷懒取父级变量的子图将立即报错。

### §4.2 候选 B: 仅 subagent 隔离, SUBGRAPH 保留全量
- **描述**：工具隔离，逻辑子图不隔离。
- **冲击范围**：较小。
- **兼容性**：一定程度上维护了子图。但隐患残留。

### §4.3 候选 C: 显式 input/output mapping 字段
- **描述**：为 AST 和 SubagentConfig 加入明确映射表字典（`inputs: {}, outputs: {}`），在跨越主辅边境时依据表项转移值。这能够保证安全还能按需跨边界通信。

### §4.4 推荐 + 拍板项
- **推荐**：候选 C 搭配 候选 A。强制切断隐式依赖，仅通过明确的跨界字典转移状态。
- **PM 拍板 Q-S-A3-A6**：面对子图（Subagent 及 SUBGRAPH），是否同意彻底掐断全集继承，转换为只凭明确映射的 Explicit Input 初始化？

## §5. StateMapper

### §5.1 候选 A: 独立类 build_phase_input / wrap_phase_output
- **描述**：设立一个功能类承担切片、打包、检查缺失等所有行为。这便于外部在运行前的 Trace 工具与调试端复用逻辑。

### §5.2 候选 B: 直接在 phase wrapper 函数实现
- **描述**：以匿名闭包完成散列拦截。
- **兼容性**：实现最轻量，但不具备后续观测面板 (Studio) 在前端重演输入漏斗的要求。

### §5.3 推荐 + 拍板项
- **推荐**：候选 A。独立封装有利于单元测试覆盖边界条件。
- **PM 拍板 Q-S-StateMapper**：装载器是由独立功能类（StateMapper）承担，还是直接融入汇编器的 Wrapper 函数中？

## §6. 测试策略
- **P0-3 并行与顺序验证**：
  在 `test_v21_graph_assembler.py` 内部增设并断言两组案例。Case 1: 一个逻辑相在不同环节覆写同一 Key (必须成功)；Case 2: 扇入节点的并发侧同时写回相同 Key (引发 Error)。Mock-only。
- **A1 Input Funnel 边界断言**：
  编写针对 `filter_runtime_inputs` 的纯单元测试，利用含冗余或类型偏离的数据集合注入漏斗，校验是否过滤/强制返回合法值。Mock-only。
- **A2 & A3 & A6 沙箱隔离**：
  对现存的 fixture 发送模拟的父层上下文以及 Subagent 响应。判定在子节点内部及工具的内部所截取到的字典状态 `dict`，绝对不包含父层冗余 Key。Mock-only。

## §7. 实施顺序
1. PM 针对上述列出的 Q-S-* 进行所有 [BREAKING] 选项的拍板。
2. 指派 a1 / a3 进行 `smart_dict_reducer` 的热替换和缓存降级。
3. 创建漏斗模块并在 runner 中切入 (A1)。
4. 结合已落地的 A7 (`PhaseIOSchema`) 开发 `StateMapper` 以及实现 A2 沙箱过滤和 A3/A6 阻断。
5. 集成所有报错以抛出可溯源结构的 issue 对象。

## §8. 跟 Block 1 (skill-compilation) 的耦合
本设计中的 A2（节点输入输出契约）、A3 和 A6（严格拦截参数隐式下发）**极其依赖** Block 1 产生的 `PhaseIOSchema` 对象作为核心数据流的权威标尺和执法依据。
如果 Block 1 中 PM 选择拒绝 A7 强制写入 io dict (例如选择了不实施或完全放行空字典的候选 B/C)，那么本 Block 的 StateMapper 及沙箱提取将因为没有合法范围参考而陷入停滞。**在未获得 Block 1 的 A7 拍板项并实现前，此 Block 2 方案不应进场强干。**