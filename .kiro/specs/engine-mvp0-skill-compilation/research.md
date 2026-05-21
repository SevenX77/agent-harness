# Engine MVP0 — skill-compilation Research

## §1. 现状综述

当前 `skill-compilation` 模块作为纯后端 Python 库，负责将目录型 V2.1 skill 解析为内存可执行的 `CompiledSkill` 对象。主入口点是 `compile_skill()`（`packages/graph-agent/src/graph_agent/core/compiler.py:40`），它背后调用 `SkillLoader.compile_skill()`（`packages/graph-agent/src/graph_agent/core/loader.py:142`）完成所有底层解析工作。

当前的编译流程已能执行拓扑相关的多项基础校验：包括入口目录守卫（`_guard_v21_root`，`loader.py:256`）、读取 `GRAPH.md` 生成 `GraphManifest`，以及校验节点依赖拓扑（环、孤岛等，`loader.py:730`）。对于 IO 方面，目前的编译器只会校验根级 `io/inputs.json` 和 `io/outputs.json` 文件作为 JSON Schema 的合法性（`loader.py:874`）。此外，当前已实现逻辑操作节点 (`LOGIC.md`) 的静态写键扫描，限制返回 key 在输出 schema 范围内（`loader.py:964`）。

然而，当前机制还存在诸多未对齐 MVP0 目标的空白：
1. **缓存快照数据不全**：`_dehydrate_compiled_skill()` 只保存了 `raw`、`manifest` 和 `nodes`（`packages/graph-agent/src/graph_agent/core/cache.py:84-99`），丢失了 subagent 元数据（`subagents_by_phase`）和 `GRAPH.md` token 位置（`phase_tokens`）。
2. **缺乏节点级 IO 与全局数据流校验**：目前的 phase AST 缺乏对输入输出字典的明确定义要求，导致编译器只能验证执行顺序，而无法确保“下游必需的输入由上游产出”的静态数据流正确性。

## §2. MVP0 目标拆分 — 已知 audit ID 一览

### P1-1 cache 元数据补全
- **现状**：`cache.py:84-126` 中的脱水与重水化逻辑仅涵盖核心骨架，导致缓存命中后 `subagents_by_phase` 和 `phase_tokens` 变成空值（利用 dataclass 默认值）。
- **MVP0 目标**：缓存恢复后必须与冷编译等价。序列化方案必须保存子代理的输入和预期 schema，并在反序列化时调用 `build_subagent_input_model` 动态重建 Pydantic 模型。

### P2-2 cache 写失败降级
- **现状**：`save_to_cache()`（`cache.py:45-52`）直接调用 `mkdir` 和 `write_text`，如遇权限问题或目录只读，编译本身虽成功但会因缓存写入异常而中断。
- **MVP0 目标**：将缓存写入转为“性能优化”而非“阻塞节点”。发生 I/O 错误时，只记录 warning 并平滑降级，返回已编译的内存对象。

### A7 SKILL.md frontmatter 必须 io dict
- **现状**：当前的 `SkillNodeAST`（`manifest.py:83-90`）和 `LogicNodeAST` 仅包含 `system_prompt` 等字段，没有 phase-level `io` 字段。
- **MVP0 目标**：在 AST 层面及 frontmatter 解析环节，强制要求所有执行阶段（Skill、Logic）声明各自的 `io` dict，以确立节点级输入输出契约。

### A8 图级 IO 数据流静态校验
- **现状**：当前的 `_validate_graph_topology()`（`loader.py:730-771`）仅验证 ID 是否重复、边是否存在环等拓扑问题，对数据的流向与类型一无所知。
- **MVP0 目标**：在编译期引入静态数据流分析，遍历 `depends_on` 拓扑，证明所有节点的 `required input` 都能通过全局初始化或前置节点的 `outputs` 满足。

### 结构化 CompileIssue
- **现状**：编译期错误仅抛出 `[F-v21-*]` 字符串前缀的 Python Exception（如 `loader.py:232-253`），UI/Canvas 无法利用其对报错位置进行红线高亮。
- **MVP0 目标**：提供结构化的 Issue 载体，携带错误码 (`code`)、严重度 (`severity`)、受影响的阶段 (`phase_id`) 以及精确的源代码坐标 (`path`, `line`)。

## §3. 各 audit ID 设计候选方案

### P1-1 cache 元数据补全
- **候选 A：[NEW] 深层序列化扩展与动态还原（推荐）**
  - **Trade-off**：保留 `CompiledSubagent` 等现有运行时的丰富类型，在 `_dehydrate_compiled_skill` 中保存字典，在 `_rehydrate` 中借助 `build_subagent_input_model` 动态恢复。符合目前架构且语义不流失，但重构后的 cache.py 逻辑较长。
  - **冲击范围**：`packages/graph-agent/src/graph_agent/core/cache.py:84-126`。
  - **兼容性**：完全向后兼容，不改变其他模块的调用行为。
- **候选 B：[BREAKING] 将编译产物降级为纯 Pydantic JSON 模型**
  - **Trade-off**：直接让 `CompiledSkill` 变为 `BaseModel`，利用内置序列化实现。代码精简，但会抛弃动态建立的 Type 型 class，强迫所有下游改为解析字典，重构成本极大。
  - **冲击范围**：`loader.py`（65-89行定义），并波及执行时的全部依赖。
  - **兼容性**：破坏了与当前 Runtime 调用机制的约定。

### P2-2 cache 写失败降级
- **候选 A：[NEW] 基础 Try-Except 降级**
  - **Trade-off**：在 `cache.py:45-52` 包一层捕获 `OSError`。实现极简，代价是错误仅仅被 log，如需在界面显示“磁盘已满”，Studio 将收不到此信号。
  - **冲击范围**：仅 `packages/graph-agent/src/graph_agent/core/cache.py:45-52`。
  - **兼容性**：完全兼容。
- **候选 B：[NEW] 带 Diagnostics 收集的降级**
  - **Trade-off**：不仅拦截，还将 warning append 进新设计的 `CompileResult.diagnostics`，上报前端。功能完备但需要 Studio 层面一同重构。
  - **冲击范围**：缓存写入与返回结构全体。

### A7 SKILL.md frontmatter 必须 io dict
- **候选 A：[BREAKING] 强制 AST 校验 (Pydantic Field(..., min_items=1))**
  - **Trade-off**：严格控制，不包含 io 直接报 `ValidationError`。会导致当前的旧 V2.1 Fixture 瞬间全部崩盘，需要全量修缮测试数据。
  - **冲击范围**：`packages/graph-agent/src/graph_agent/core/manifest.py:59-90` 以及所有测试 fixture 目录。
  - **兼容性**：破坏旧版 Schema 测试。
- **候选 B：[BREAKING/Soft] io 选填，提供默认空值并下发 Compile Warning**
  - **Trade-off**：减少测试炸毁范围，但会导致 A8 无法信赖契约。违反了强数据流约束。
  - **冲击范围**：同样涉及 AST，但允许兼容旧文件。

### A8 图级 IO 数据流静态校验
- **候选 A：[NEW] 仅进行 Key 可见性检查**
  - **Trade-off**：按拓扑顺序累加上游产出的 Key 集合，对下游必填 Key 查交集。轻量级，运算快，可拦截 90% 数据断层，但不处理 Schema 类型兼容性问题（比如上游是 str，下游要求 int）。
  - **冲击范围**：在 `loader.py` 中的主循环末尾新增 `_validate_phase_io_dataflow`。
  - **兼容性**：依赖 A7 机制实装。
- **候选 B：[NEW] 全面的 JSON Schema 类型交集校验**
  - **Trade-off**：能拦截 Type 错误，但需要引入重量级的 Schema 推导库（或者手写复杂判断），开发成本高且易生误报。

### 结构化 CompileIssue
- **候选 A：[BREAKING] `compile_skill` 返回 `CompileResult`**
  - **Trade-off**：返回 `(CompiledSkill | None, List[CompileIssue])`，最标准的静态分析器接口。但所有引用编译的下游全部需修改提取模式。
  - **冲击范围**：`packages/graph-agent/src/graph_agent/core/compiler.py:40-45` 及依赖此 API 的 runner 和测试。
- **候选 B：[NEW] 保持抛出 `SkillCompileError`，内部附带 `issues: list[dict]`**
  - **Trade-off**：改动小，主流程不需要将警告视作正常返回。后端统一将异常映射为 HTTP 422 附带 JSON 问题列表即可。
  - **冲击范围**：`packages/graph-agent/src/graph_agent/core/loader.py:232-253` 的 Error helper 改造。

## §4. 不依赖 PM 拍板可独立推进的工作清单

1. **P2-2 (cache 写失败降级)**：纯 Bug fix，今晚可直接在 `save_to_cache` 中追加 `try...except OSError`。
2. **P1-1 (cache 丢 subagents/phase_tokens)**：纯实现 Bug，补充缓存的 Dehydrate/Rehydrate 中被漏掉的字典存储并调用 `build_subagent_input_model`。不影响核心 API 签名。

## §5. 必须 PM 拍板才能进 task 阶段的清单

- **Q-COMP-A7：是否强制所有 phase 具有 `io` (BREAKING)**
  - 如果采取候选 A，必须同步修改所有现存的 V2.1 Fixture 和内部业务脚本的 frontmatter。不拍板无法执行。
- **Q-COMP-A8：数据流校验的严格度边界**
  - 仅查 Key Missing 还是执行深度的类型比对？（建议先拍板轻量级的候选 A）。
- **Q-COMP-ISSUE：结构化错误的传递方式 (BREAKING)**
  - 是选择更改全局签名为 `CompileResult`，还是保留异常抛出模式在 Exception 内部结构化数据？

## §6. 跟 pending-questions §1-§3 的关系

- **§1 真相来源确认**：本报告仅参考 `fixtures/` 和 `loader.py`/`manifest.py`，未包含任何已被推翻的 `workspaces/default/skills/` 2.0 遗留代码设计。
- **§2 标签 Cutover**：若 A7 引入了强制的 `io` dict，前端标签流切换时依赖的可视化输入输出将有稳定数据源支撑，相互呼应。
- **§3 Context Mapping**：本模块只做静态校验（A8），证明所需数据存在。而具体如何在运行时映射 `context_mapping`（§3 中的双模设计）那是 execution-runtime 的责任。本设计扩展了拓扑的基础保障，未越权介入。

## §7. 跟其他 3 个 engine feature 的耦合点

- **execution-runtime**：若结构化 CompileIssue 采用更改函数签名的候选方案 A，运行时中的 `run_skill()` 的调用与捕获逻辑必须立刻配合重构。
- **state-and-io-contract**：编译阶段必须完成 A7（解析 io 字段）后，运行时的 Blackboard 输入漏斗与重试隔离（A1/A2/A6）才能有据可依。本 feature 为该 feature 提供强制结构化输入。
- **tracing-and-observability**：追踪系统对代码行号的精准标记强依赖本阶段 `phase_tokens` 能够在缓存中存活（解决 P1-1），二者为提供高精度 Studio 遥测数据而相互咬合。
