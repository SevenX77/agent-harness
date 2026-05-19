# MVP-3 Research — A2 Loader / A9 hack / B3 Middleware 决策

## 来源资料

- v1-reset direction doc: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` §4 MVP-3 + §A2 / §A9 / §B3 + Appendix B
- MVP-1 spec (已 commit): `.kiro/specs/v1-reset-mvp-1-state-split/{requirements,design,tasks}.md` (BusinessData / FrameworkState / StateManager)
- MVP-2 spec (a3 刚起草, 等主控审 commit): `.kiro/specs/v1-reset-mvp-2-schema-io/{requirements,design,tasks}.md` (SchemaEngine / IOManager / build_business_data_for_skill 工厂)
- Gemini independent design (2026-04-29): job_d22adb45e517 (整合到本 spec design.md)
- 当前 loader / runner / middleware 散布点 (Gemini Part A 现状审计):
  - `src/core/graph_agent/core/loader.py` (~800 行, 上帝类 SkillLoader, 含 `_load_skill_md` / `_parse_manifest` / `_build_graph` / `_setup_namespace` / `_resolve_persona`)
  - `src/core/graph_agent/core/runner.py` (含 `os.environ` / `sys.path.append` 副作用)
  - `src/core/graph_agent/cognitive/middlewares.py` + `cognitive/clarification_middleware.py` (6+ middleware 物理散落)

## Baseline 数据 (待 T0-prep 测)

T0-prep 子任务 (派 a3 在派 T1 前跑) 需要测:
- `loader.py` 当前总行数 (MVP-2 后) + 各方法行数分布
- `runner.py` 内 `os.environ.*` / `sys.path.*` 站点完整清单 (file:line + 上下文)
- `_resolve_output_schema_path` 当前实现位置 + sys.modules 写入站点
- Monkey-patch 散落位置 (grep `setattr.*langchain` / `setattr.*pydantic` / `__patch__` 等模式)
- 当前 middleware 物理清单 (含派生类 + 装饰器版本)
- 启动延迟 baseline (从 `SkillLoader.__init__` 到第一个 phase node 调用的 wall-time)
- 4 SKILL persona 渲染当前输出快照 (作为 regression-by-snapshot 基准)

## 决策记录

### D1 — Loader 三阶段命名: `parse / validate / build`

**选项**:
- A. `parse_skill_md / validate_manifest / build_graph_nodes` (Gemini 推荐, 动词式)
- B. `Parser / ManifestValidator / GraphBuilder` (Class 式, 跟 direction doc §4 MVP-3 描述一致)
- C. `read_skill / compile_manifest / wire_graph` (语义式)

**决策: A (动词式纯函数), 但配套 Class wrapper 用于依赖注入**

**理由**:
- 三阶段是纯转换函数 (没有跨阶段共享状态, 易测), Gemini 推荐的动词式名字符合 Pipeline 模式
- 但 Phase 2 (validate_manifest) 需要注入 SchemaEngine + IOManager 实例 (避免单例污染), 因此实际签名为:
  ```python
  def parse_skill_md(text: str) -> dict
  def validate_manifest(raw_dict: dict, schema_engine: SchemaEngine, io_manager_factory: Callable[[list[IODef]], IOManager]) -> SkillManifest
  def build_graph_nodes(manifest: SkillManifest) -> list[PhaseNode]
  ```
- direction doc §4 MVP-3 描述的 "Parser / ManifestValidator / ModuleSandbox / PhaseBuilder" 是 4 个工件, 但本 MVP 3 阶段对应 Parser / ManifestValidator / PhaseBuilder, ModuleSandbox 单独存在 (见 D2)

### D2 — Gemini A9 误读纠正: 双 A9 都做

**问题**: a2 design 把 §A9 理解为 "启动序列 hack 清理" (os.environ / monkey-patch / sys.modules), 但 v1-reset-direction §4 MVP-3 原义是 **"A9 output_schema hack 剥离"** (`_resolve_output_schema_path` 用 PEP 451 importlib namespace, sys.modules 改写消失)。

**两者都是 "hack 清理" 但目标完全不同**:
- a2 understanding (启动序列 hack): runner.py 内 os.environ / sys.path / monkey-patch 副作用清理
- direction doc §A9 原义: SKILL.md `output_schema_path` 字符串 → 类对象的解析路径不再用 sys.modules 写脏数据

**决策: 两者都纳入 MVP-3 范围, 命名上区分**:
- **A9-original** (direction doc §A9): "output_schema 路径解析 hack 剥离" → 落地为 ModuleSandbox 工件
- **A9-bis** (a2 design 扩展): "startup hack 清理" → 落地为 Bootstrap + Settings 工件

**理由**:
- a2 design 把 A9 误解, 但提议的"启动序列清理"本身是合理且必需的工作 (runner.py 散落 os.environ 副作用确实是 v1-reset 应清的债)
- direction doc §4 MVP-3 列的"A9 output_schema hack"也必须做, 否则 SchemaEngine 集成不彻底 (路径解析仍走旧 sys.modules hack)
- 把两者并入同一 MVP 没有冲突 (A9-bis 改 runner / patches, A9-original 改 _resolve_output_schema_path / 新建 ModuleSandbox), 且互不依赖, 可并行实施

### D3 — Middleware 简化目标: 4 核心 + 顺序契约固化

**当前 middleware 清单** (T0-prep 复核):
- `ValidationMiddleware` (cognitive/middlewares.py:287)
- `ClarificationMiddleware` (cognitive/clarification_middleware.py)
- `UnattendedClarificationMiddleware` (cognitive/middlewares.py:622)
- 可能存在的 RetryMiddleware / LoopDetectionMiddleware (待 T0-prep 测)

**决策: 收拢为 4 核心** (Gemini Part D):
1. `ProtocolValidationMiddleware`: 吸收 ValidationMiddleware 的契约校验职责, 并入 MVP-1 / MVP-2 的 BusinessData / FrameworkState / SchemaEngine 校验
2. `CognitiveFlowMiddleware`: 吸收 finish_task interception + Clarification + UnattendedClarification 三者
3. `ExecutionControlMiddleware`: retry / loop detection / metrics
4. `LoggingMiddleware`: 统一 callback 触发

**顺序契约**: ProtocolValidation → CognitiveFlow → ExecutionControl → Logging。在 `tests/graph_agent/conftest.py` 加固定顺序回归测试。

**理由**:
- 当前 Clarification 跟 UnattendedClarification 职责高度重叠 (Gemini Part A 评估), 整合到 CognitiveFlow 减少代码重复
- LangGraph `update_state` 触发顺序极度敏感 (Gemini Part G), 顺序固化避免后续改 middleware 时不小心变序

### D4 — 实施顺序: 修订 a2 design Part E

**a2 design Part E 给定顺序**: A9 (启动清理) 先行 → A2 (Loader 重画) → B3 (Middleware 简化)

**主控修订**: 
- A9-bis (startup hack 清理) **可独立优先做** (T1: Bootstrap + Settings) — 跟 a2 一致
- A2 (Loader 三阶段) **跟 A9-bis 部分并行** (T2 SkillManifest 模型不依赖 A9-bis)
- A9-original (output_schema 路径 hack) **依赖 A2 Phase 2** 的 ModuleSandbox 出炉 (direction doc 明说"A9 依赖 A2 的 ModuleSandbox, 串行做")
- B3 (Middleware 简化) **依赖 A2 数据流模型** (新 SkillManifest 决定 middleware 的 state 接口)

**修订后顺序**:
```
T1 (A9-bis Bootstrap) ──┐
T2 (SkillManifest 模型) ─┴→ T3 (parse_skill_md) → T4 (validate_manifest 集成 MVP-2) → T5 (build_graph_nodes + ModuleSandbox)
                                                                                    ├→ T6 (废弃旧 SkillLoader, 切三阶段)
                                                                                    ├→ T7 (ProtocolValidationMiddleware)
                                                                                    ├→ T8 (CognitiveFlowMiddleware)
                                                                                    ├→ T9 (ExecutionControlMiddleware)
                                                                                    ├→ T10 (清理 runner.py os.environ)
                                                                                    └→ T11 (单测) → T12 (集成压测)
```

### D5 — 跟 MVP-2 SchemaEngine / IOManager 接口契约

**MVP-2 已就位**:
- `core/schema_engine.py:SchemaEngine` 含 `parse_from_md / get_pydantic_model / validate / get_json_schema`
- `core/io_manager.py:IOManager` 含 `__init__(io_specs, schema_engine) / resolve_hoist / validate_spec`
- `core/state.py:build_business_data_for_skill` 工厂

**MVP-3 集成点**:
1. **Phase 2 (validate_manifest)**: 调用 `SchemaEngine.validate_spec_dict` 校验每个 phase 的 output_schema 字段格式合法; 调用 `SchemaEngine.parse_from_md` 把 output_schema 字段解析为 SchemaObject 存入 SkillManifest
2. **Phase 2 (validate_manifest)**: 调用 `IOManager.validate_spec` 校验 io.outputs / hoist_to 路径合法
3. **Phase 3 (build_graph_nodes)**: 调用 `build_business_data_for_skill(manifest, schema_engine)` 生成 BusinessData 子类, 写入 PhaseNode 的 initial_state 工厂
4. **新 Bootstrap**: 启动序列里 `SchemaEngine()` 实例化必须在 `SkillLoader.compile_skill()` 之前

**关键不变量**: MVP-3 期间 SchemaEngine / IOManager 的对外接口签名不能改 (MVP-2 已定型), 只能扩展。

### D6 — 跟 MVP-4 phase executor 重画的接口约定

**MVP-4 范围** (direction doc §4): A3 phase_executor 拆为 PromptRenderer / AgentLoopDriver / LifecycleEmitter / StateTransformer, 同时 A4 finish_task 不再是 LangChain Tool。

**MVP-3 给 MVP-4 的契约**:
1. **PhaseNode 接口**: `class PhaseNode: def execute(self, state: WorkflowState) -> WorkflowState` (MVP-3 同步签名, MVP-4 改 async)。MVP-4 拆解时必须通过 PhaseNode.execute 入口路由到 PromptRenderer / AgentLoopDriver / 等子组件
2. **finish_task 截获位置**: MVP-3 把 finish_task interception 放到 CognitiveFlowMiddleware (Tool Call 拦截), MVP-4 把 finish_task 改成 LangGraph Node 时, CognitiveFlowMiddleware 的拦截逻辑被吸收/替换
3. **Middleware 链跟 phase_executor 的接缝**: MVP-3 的 4 middleware 通过 LangGraph `update_state` hook 触发, MVP-4 重画 phase_executor 时不能破坏这套 hook 协议 (否则 middleware 全部失效)

**关键不变量**: MVP-3 的 PhaseNode 接口 + middleware 顺序契约是 MVP-4 的输入边界, MVP-4 重画时只能内部拆, 不能改这两个接口。

## 不在 MVP-3 处理的相关问题（明确 defer）

- phase_executor 整体拆解 (532 行 → 4 子组件) → MVP-4
- finish_task 不再是 LangChain Tool (改 LangGraph Node 或 LLM response_format) → MVP-4
- harness.run 拆解为 .compile/.prepare_state/.invoke_graph/.persist_outputs → MVP-5
- 全库工程门禁 (mypy strict / ruff / coverage) 整体收紧 → MVP-5
- 4 SKILL e2e 全部断言 → MVP-5
- 第三方 middleware 注册插件协议 (B3 重做远期目标, direction doc line 150) → V2 / MVP-6+
- LoopDetection / Summarization 算法重写 → V2
