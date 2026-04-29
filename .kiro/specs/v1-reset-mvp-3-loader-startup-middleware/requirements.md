# MVP-3 Requirements — A2 Loader 重画 + A9 hack 剥离 + B3 Middleware 简化

## 背景

graph_agent v1-reset 序列 MVP-3。MVP-1 (state 物理拆分) + MVP-2 (SchemaEngine + IOManager 抽出) 已为运行时打好基础设施。MVP-3 进入"逻辑清创"阶段——对当前 framework 启动期 + 编译期 + 拦截期 三条主线做三件事:

- **A2**: 把 `loader.py` (~800 行上帝类 SkillLoader, MVP-2 卸载后 ~500 行仍交织) 拆为三阶段 Pipeline
- **A9**: 剥离 startup hack (a2 design 的扩展义) + 剥离 `output_schema` 路径解析 hack (`_resolve_output_schema_path` 用 PEP 451 importlib namespace 改写, sys.modules 污染消失)
- **B3**: middleware 简化 (从当前 6+ middleware 收拢为 4 核心)

## 业务目标

让 framework 生命周期 (启动 → 编译 → 运行 → 拦截) 各阶段职责单一可测。loader.py 瘦身至 ≤ 200 行 (仅做编排), 启动序列不再含散落 `os.environ` / monkey-patch / `sys.path.append` 副作用, middleware 物理文件数降至 4 个核心类, 启动延迟下降 ≥ 20%。为 MVP-4 phase_executor 拆分 + finish_task 控制流原语化扫清结构性障碍。

## EARS 需求

### Req 1 — Loader 三阶段 Pipeline

**WHEN** framework 编译 SKILL.md，**THE SYSTEM SHALL** 经过三个纯净的转换函数:
- `parse_skill_md(text: str) -> dict` (Phase 1: 仅 markdown 块结构化分割 + 基础正则提取, 无对象引用)
- `validate_manifest(raw_dict: dict) -> SkillManifest` (Phase 2: Pydantic 强校验, 调用 MVP-2 SchemaEngine 校验 output_schema, 调用 IOManager 校验 hoist_to 路径)
- `build_graph_nodes(manifest: SkillManifest) -> list[PhaseNode]` (Phase 3: SkillManifest → LangGraph 节点, 不再理解 markdown)

三阶段之间通过明确类型边界传递 (raw_dict / SkillManifest / list[PhaseNode]), 不共享内部状态。

### Req 2 — SkillManifest Pydantic 全量模型

**WHEN** Phase 2 校验完成，**THE SYSTEM SHALL** 输出 `core/manifest.py:SkillManifest` 完整 Pydantic 模型, 含:
- 所有 phase 定义 (PhaseDef discriminated union, MVP-0 已有)
- 所有 io 字段 (IODef, MVP-0 已有)
- ContextBridge (MVP-2 已演化)
- output_schema 字段 (类型 = SchemaObject, 由 SchemaEngine 解析填充)
- 所有顶层元数据 (skill_name / description / 等)

`extra="forbid"`, mypy strict 通过, model_validate round-trip 通过。

### Req 3 — Bootstrap + Settings 启动序列

**WHEN** framework 进程启动，**THE SYSTEM SHALL** 按固定顺序执行启动序列:
1. `Bootstrap.apply_patches()` 把所有 monkey-patch 集中调用 (从 `src/core/graph_agent/patches/` 模块加载)
2. `Settings.load()` 显式构造 Settings 对象 (从 env / 配置文件读), 不再 `os.environ.set` 在运行时
3. `SchemaEngine()` 实例化 (MVP-2 模块)
4. `SkillLoader.compile_skill()` 调用三阶段 Pipeline
5. `Harness.run()` 启动执行

### Req 4 — output_schema 路径解析 hack 剥离 (direction doc §A9 原义)

**WHEN** SKILL.md 引用 `output_schema_path: "module.path.ClassName"`，**THE SYSTEM SHALL** 通过 PEP 451 importlib namespace 解析路径, 不再:
- 写入 `sys.modules[<幽灵模块名>]`
- 在 `_resolve_output_schema_path` 内做 `importlib.import_module` 后 fallback 到 `sys.modules` 的现有 hack
- 产生 "幽灵模块名" 调试问题

### Req 5 — startup hack 清理 (a2 design 扩展义)

**WHEN** MVP-3 收尾，**THE SYSTEM SHALL** 满足:
- `runner.py` 内 `os.environ.set` / `os.environ[...] = ...` 站点数 = 0 (除显式 Settings.apply 内部)
- `sys.path.append` 在 `runner.py` `__main__` 段内 = 0 (移到专用工具类)
- monkey-patch 物理位置统一在 `src/core/graph_agent/patches/`, 启动序列只调用一次 `Bootstrap.apply_patches()`

### Req 6 — Middleware 简化为 4 核心

**WHEN** LangGraph 触发 middleware 链，**THE SYSTEM SHALL** 仅含以下 4 个核心 middleware (按拓扑序):
1. `ProtocolValidationMiddleware`: 唯一负责 BusinessData / FrameworkState 契约校验
2. `CognitiveFlowMiddleware`: 整合 finish_task interception + clarification (LLM 澄清请求)
3. `ExecutionControlMiddleware`: retry / loop detection / metrics 等运维逻辑
4. `LoggingMiddleware`: 统一 callback 触发点

旧 middleware (`ValidationMiddleware` / `ClarificationMiddleware` / `UnattendedClarificationMiddleware` / `RetryMiddleware` 等) 全部并入或删除。

### Req 7 — Middleware 顺序契约 + 拓扑序测试

**WHEN** middleware 链在 LangGraph `update_state` 触发，**THE SYSTEM SHALL** 满足固定顺序: ProtocolValidation → CognitiveFlow → ExecutionControl → Logging。`tests/graph_agent/conftest.py` 必须含拓扑序回归测试。

### Req 8 — PhaseNode 跟 MVP-4 接口契约

**WHEN** Phase 3 输出 PhaseNode 对象，**THE SYSTEM SHALL** 满足 MVP-4 phase_executor 重画的契约: PhaseNode 暴露统一的 `.execute(state: WorkflowState) -> WorkflowState` 同步方法 (MVP-4 改异步)。MVP-3 阶段先用同步签名, MVP-4 时把签名升级为 async (改动局限在 PhaseNode 实现内, 不破坏调用方)。

### Req 9 — Baseline diff 验证

**WHEN** MVP-3 收尾，**THE SYSTEM SHALL** 满足下列 baseline diff 指标:
- `loader.py` 逻辑行数 (SLOC) ≤ 200 行 (MVP-2 后约 500 → ≤ 200)
- middleware 物理文件数 ≤ 4 (当前 6+ → 4)
- `runner.py` 内 `sys.path.append` / `os.environ.set` 站点数 = 0
- `_resolve_output_schema_path` 内 `sys.modules[...] = ...` 写入 = 0
- 启动延迟 (从 SkillLoader 实例化到第一个 phase 开始) 下降 ≥ 20% (T0-prep 测 baseline)
- pytest 全过 (--ignore test_strict_v2), test_strict_v2 14 pre-existing failures 仍 isolated
- 4 SKILL compile 状态不变, e2e smoke 跑 1 chapter 不破裂
- 4 SKILL persona 渲染输出文本完全一致 (regression-by-snapshot)

### Req 10 — 测试覆盖

**WHEN** 新模块上线，**THE SYSTEM SHALL** 满足:
- `parse_skill_md` / `validate_manifest` / `build_graph_nodes` 单元测试覆盖率 ≥ 95%
- `Bootstrap` / `Settings` 单元测试覆盖率 ≥ 95%
- 4 核心 middleware 单元测试覆盖率 ≥ 95%
- LoopDetection 集成压力测试 (在新 ExecutionControlMiddleware 下行为不变)

## Out of scope（MVP-3 不做）

- A3 phase_executor 拆解 → MVP-4
- A4 finish_task 控制流原语化 (从 LangChain Tool → LangGraph Node/Edge) → MVP-4
- A10 harness.run 拆解 → MVP-5
- 全库 mypy strict / ruff strict / coverage ≥ 85% 整体收紧 → MVP-5
- 4 SKILL e2e 全部断言 → MVP-5
- B3 重做的"标准 middleware 插件协议" (允许第三方 middleware 注册的 plugin 系统) → V2 / MVP-6+
- LoopDetection / Summarization 算法重写 → V2 (MVP-0 已砍, MVP-3 仅复活精简版于 ExecutionControlMiddleware)
