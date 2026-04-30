# Phase 2 实施级架构重塑设计 (A1/A2/A3)

## 1. 背景与目标

在 v1-reset Phase 1 的工程审计中，多重视角（工程基线、架构治理、架构溯源、PM 对标）达成了一个核心共识：**当前的 49 个 commits 包含阻碍稳定性的架构断层，坚决不能直接进入 1.0.0。**
目前的实现存在三大核心顽疾：
1. **隐式的副作用契约 (A1)**：早期遗留的 `schema is None` 分支允许未定义 `output_schema` 的 Phase 执行业务校验，导致底层 Validator 只能收到无类型的全局字典 `ctx`，进而引发类型错配和崩溃。
2. **双系统并行 (A2)**：MVP-3 已设计了基于数据流的 `CognitiveFlowMiddleware` 和 `ProtocolValidationMiddleware`，但执行引擎 `phase_executor.py` 仍硬编码调用遗留的 `ValidationMiddleware`，导致新基建空转。
3. **零静默失败原则的破坏 (A3)**：code-only phase 遇到返回 `dict` 时，在缺乏 schema 的情况下多余字段会被静默丢弃（Silent Failure），违反框架的 "fail-loud" 铁律。

**阶段 2 目标**：彻底废弃补丁式开发，实施真正的接口重画。实现严格的编译期门禁、替换全新的中间件管道、修复隐式丢弃，为后续全面通过 mypy strict 与真实 LLM e2e 铺平道路。

---

## 2. A1 砍 schema is None 路径详细设计

### 2.1 现状与问题
当前在代码中存在针对 `schema is None` 的 fallback 逻辑。这源于旧版 `deerflow` 允许 "黑盒透明转发" —— 即没有明确输出结构的 SKILL 也能挂载业务 Validator。这导致 Validator 的签名（如期望 `list[dict]`）与实际输入（整个 `ctx` 字典）严重错配，完全依赖运行时的副作用巧合才能跑通。

### 2.2 替代方案与契约
**编译期强阻断 (Failure-Loud)**：
任何声明了 `validation` (业务校验器) 或明确需要结构化解析的 Phase，**必须**在 `SKILL.md` 中定义 `output_schema`。
若编译期发现 `phase.validation` 存在但 `phase.output_schema` 缺失，抛出 `SkillCompileError`。

### 2.3 实施步骤 (a3 Action Items)
1. **修改 Schema/Manifest 验证** (预估位置：`src/core/graph_agent/core/skill_validator.py` 或 `manifest.py`)
   - 在验证 `Phase` 配置时增加断言，并**提供精确的类型签名**（禁止使用 `Any`）：
     ```python
     from .manifest import GraphSkillDef # 请使用相对引入或对应的绝对路径

     def _enforce_validator_requires_output_schema(manifest: GraphSkillDef) -> None:
         # 遍历 manifest.phases, 发现 phase.validation 存在但缺少 schema 时抛出 SkillCompileError
         pass
     ```
2. **清理 Runtime 遗留逻辑 (共 5 处)** 
   - `src/core/graph_agent/middleware/cognitive_flow.py:251`: 彻底删除 fallback，若缺失直接 `raise ValueError` 或移除该分支让上游拦截。
   - `src/core/graph_agent/cognitive/middlewares.py:512`: 彻底删除 `if schema is None:` 相关代码，业务 Validator 输入强类型化。
   - `src/core/graph_agent/tools/md_to_json.py:534`: 移除 fallback 转发，确保只处理带 schema 的结构化转换。
   - `src/core/graph_agent/core/skill_builder.py:273` & `907`: **保持不变**。这里的 `if phase_def.output_schema and dynamic_schema is None` 是正常的“动态 schema 解析失败”的分支，并非由于缺乏静态 schema 导致的遗留 fallback，需要区分清楚。
3. **修复现有 SKILL.md**
   - 检查 `find skills/ -name "SKILL.md"`。若有 Phase 挂载了 Validator 但缺少 schema，为其补齐 Pydantic 等价的 JSON Schema 定义。

### 2.4 Validator 输入契约 (Runtime Data Shape)
在旧的 `schema is None` fallback 路径下，Validator 接收的是包含所有上下文的完整字典 (`ctx: dict[str, Any]`)。在 A1 废弃 fallback 后，我们需要建立基于数据流的严格运行时契约：

1. **当 phase (如 LLMPhase) 配置了 `output_schema` 时**：
   - **强制契约 (选项 A 变体)**：Validator **只接收解析后的结构化数据列表**，即 `list[dict[str, Any]]`（当前中间件中提取出的 `raw_items`，或与之等价的 Pydantic 模型实例列表 `list[T]`），**坚决不传全局 `ctx`**。
   - **理由**：符合 "Rust 式严格契约"。Validator 作为纯函数，只需也只能看到该 Phase 自己声明的输出结构。传入全局 `ctx` 是一种极易被滥用的隐式依赖（副作用），会导致类型签名模糊不清。
2. **当 phase 不配 `output_schema` 时** (如 `LogicPhase` / `AgentPhase` / `PersonaPhase`)：
   - **强制契约**：对于 `LLMPhase`，如果在没有 schema 的情况下挂载 Validator，走 `SkillCompileError` 阻断。
   - **豁免情况**：仅对非 `LLMPhase` (如执行确定性 Python 逻辑的 `LogicPhase`) 豁免。这部分已在 `_enforce_validator_requires_output_schema` 逻辑中通过 `isinstance(phase, LLMPhase)` 进行精准过滤。
3. **接口契约与现存代码重写**：
   - Validator 的标准函数签名应统一为：`def validator(payload: list[dict[str, Any]]) -> tuple[bool, list[str]]:` （注意 payload 必须是一个结构化的列表，而不是全局字典 `context`）。
   - **现存代码重写**：当前的 `validate_event_extraction`（位于 `skills/event-extraction/script/validators.py:14`）等仍按接收 `context: dict` 编写，执行 `context.get(...)` 获取数据。这与新的强类型契约**严重错配**。必须在实施 A1 时**一并重写这些 Validator**，修改其函数签名接收 `payload: list[dict[str, Any]]`，并调整内部的数据处理逻辑。
   - **责任划分**：由 **a3** 在实施 A1 时一并重写所有的 live SKILL validator（如有），**a1** 在 review 时验证签名是否匹配。

### 2.5 风险点
此举会破坏不合规的存量 `SKILL.md`，并打破现存 Validator 的函数签名预期。但这是预期的（我们宁愿在加载时崩溃，也不要在 LLM 对话中死循环）。由 a3 顺手修复存量 validator 即可。

---

## 3. A2 phase_executor 切轨到新 middleware 详细设计

### 3.1 现状与问题
当前的 `src/core/graph_agent/core/phase_executor.py` 是一个包含约 **964 行**的巨大上帝类 (god execution flow)，并且仍在硬编码使用旧版的 `ValidationMiddleware`。这个遗留类把协议层 JSON 解析、业务 Validator 调度、上下文合并全揉在了一起，导致极高的重构风险。
更严重的是，MVP-3 已经实现了新的基于数据流的 `CognitiveFlowMiddleware`（已经内置了 Markdown 解析、Schema Validation 和解析后对象的组装），而 `phase_executor` 却处于双系统并行的“空转”状态。

### 3.2 接口契约重构 (切轨至 CognitiveFlowMiddleware)

**决断：放弃新建 `SchemaHoistingMiddleware`，直接切轨至 `CognitiveFlowMiddleware`，并通过扩展 `current_phase_schema` 联合类型（方向 2）解决类型错配和动态加载问题。**

实证发现，`CognitiveFlowMiddleware._validate_finish_args` 已经完整实现了 Schema 解析和数据对象化（Hoisting）的职责。但是，当前 A1 `CognitiveFlowMiddleware` 的签名期望 `current_phase_schema: SchemaObject | None`，而 `phase.output_schema` 在运行时承载的是 `type[BaseModel]` (对于使用 dotted Pydantic 路径的 SKILL，如 `text-segmentation`) 或 `DynamicSchemaDef`，导致运行时的强硬崩溃。

同时，由于 `compiled_schemas` 仅在编译期填充了使用内联 markdown 的 Phase，直接切轨会导致 live SKILL（使用了 dotted path Pydantic Schema）拿不到 schema 并引发 `CognitiveFlowError`。

**实施方向 (选定方向 2)**：
1. **修改 A1 中间件接口（显式授权）**：为了兼容使用 dotted path `type[BaseModel]` 的 `output_schema`，正式授权 A2 阶段可以修改 `protocol_validation.py` 和 `cognitive_flow.py` 中 `current_phase_schema` 的类型签名，从 `SchemaObject | None` 扩展为 `type[BaseModel] | SchemaObject | None`。
2. **内部分派校验逻辑**：在 `CognitiveFlowMiddleware` 内部校验时进行分派：
   - 如果是 `SchemaObject`，继续走 `SchemaEngine.get_pydantic_model()` 及后续逻辑。
   - 如果是 `type[BaseModel]`，则无需通过 `SchemaEngine` 转换，直接利用该 Pydantic Class 进行 JSON/Markdown 解析和 validate。
3. **彻底接管旧 ValidationMiddleware 职责**：新的单一职责管道由以下中间件组装（均继承自 `AgentMiddleware[AgentState[Any]]`）：
   - `ProtocolValidationMiddleware`：负责状态完整性边界断言。
   - `CognitiveFlowMiddleware`：独占接管 `finish_task`。

### 3.3 旧版 ValidationMiddleware 独占能力的迁移路径
旧版 `ValidationMiddleware` 承载了历史能力，它们将被按以下契约迁移：

1. **dotted output_schema_path (静态 Pydantic 路径)**：
   - **决策与迁移**：通过修改 `CognitiveFlowMiddleware` 的入参联合类型（见 3.2），直接原生支持 `type[BaseModel]` 的运行时注入。这就完全覆盖了旧版的 `_resolve_output_schema` 后加载行为。
2. **output_example (Dynamic Schema)**：
   - **决策**：**临时保留旧版 ValidationMiddleware 的 fallback 调用**。
   - **迁移路径**：在装配时，通过判断 `phase.output_schema` 的实际承载类型（`DynamicSchemaDef`）来决定路由。如果是动态 Schema，就继续使用遗留的 `ValidationMiddleware`。`CognitiveFlowMiddleware` 仅服务于强类型（`type[BaseModel]` 或 `SchemaObject`）。
3. **ctx-based Legacy 字典传递**：
   - **决策**：**废弃**。在 A1 契约下，`business_validator` 的输入必须是强类型的结构化数据 `list[dict]`。

### 3.4 实施步骤 (a3 Action Items)

**授权声明：A2 实施阶段允许安全地修改 `protocol_validation.py` 和 `cognitive_flow.py` 以扩展 Union 类型，打破了之前不可触碰 A1 的假设。**

1. **扩宽 Schema 参数类型**：
   修改 `src/core/graph_agent/middleware/protocol_validation.py` (约 82 行) 和 `src/core/graph_agent/middleware/cognitive_flow.py` (约 67 行) 的构造函数：
   ```python
   from pydantic import BaseModel
   from ..core.schema_engine import SchemaObject
   # 修改为:
   current_phase_schema: type[BaseModel] | SchemaObject | None = None
   ```
2. **CognitiveFlow 内部分派** (`src/core/graph_agent/middleware/cognitive_flow.py:280` 附近)：
   ```python
   # 改造 _validate_finish_args 中获取 model 和校验的过程
   if isinstance(schema, SchemaObject):
       model = self._schema_engine.get_pydantic_model(schema)
       blocks = parse_md(business_data_md, model)
       # 循环校验使用 self._schema_engine.validate(block.data, schema)
   else: # type[BaseModel]
       model = schema
       blocks = parse_md(business_data_md, model)
       # 循环校验直接使用 model.model_validate(block.data)
   ```
3. **修改执行引擎** (`src/core/graph_agent/core/phase_executor.py` 的 `execute_llm_phase` 约 783 行附近) 增加联合路由策略 (详见 3.6)：
   ```python
   from ..tools.dynamic_schema import DynamicSchemaDef
   if isinstance(phase.output_schema, DynamicSchemaDef):
       # 走旧的 ValidationMiddleware fallback，可加 warning 日志
       phase_middlewares.append(ValidationMiddleware(...))
   elif phase.output_schema is None:
       # Schema-less fallback
       phase_middlewares.append(ValidationMiddleware(...))
   else:
       # 走新的静态 Schema 管道
       phase_middlewares.extend([
           ProtocolValidationMiddleware(
               schema_engine=resolver,
               current_phase_schema=phase.output_schema,
               phase_name=phase.name
           ),
           CognitiveFlowMiddleware(
               io_manager=io_manager,
               schema_engine=resolver,
               current_phase_schema=phase.output_schema,
               phase_name=phase.name
           )
       ])
   ```
4. **清理遗留基建**：在上述切轨稳定后，从 `middlewares.py` 中将 `ValidationMiddleware` 标记为 `@deprecated("保留仅供 dynamic schema 和 schema-less fallback 使用")`。

### 3.5 风险点
- **重构范围**：`phase_executor.py` 具有 964 行。尽管本方案没有引入新类，但修改 A1 中间件的签名，并在内部实现 Pydantic `BaseModel` 的原生支持仍然有一定风险。不过这种方案将 Pydantic 类的支持彻底下沉到了 Middleware 中，解决了编译与运行时契约不对齐的根本问题，一次合并是合理的。

### 3.6 Schema-less LLM finish_task 路由策略 (v5 新增)
**决断：策略 A (Legacy Fallback)。** 
当前 live SKILLs (`event-extraction`, `batch-analysis`, `global-synthesis`) 中存在多个 LLM Phase 未声明 `output_schema` 但仍调用了 `finish_task`。如果在编译期或运行时强制拦截（策略 B），将导致大量现存 SKILL 直接不可用，爆炸半径过大。因此：
- **短期 (Phase 2)**：当 `phase.output_schema is None` 时，执行遗留的 `ValidationMiddleware` Fallback，保证旧业务的存活。
- **长期 (v1.1+)**：推行**策略 C** 重构，强制为这些输出自由文本但借用 `finish_task` 中断逻辑的 Phase 添加专门的类型（如 raw_output phase），最终彻底移除 `ValidationMiddleware` 的双系统并行问题。

---

## 4. A3 code-only phase dict 静默丢弃修详细设计


### 4.1 现状与问题
如果一个 `type: code` 的 Phase 返回了一个 `dict`，而它没有明确定义 `output_schema`，底层的合并逻辑（位于 `phase_executor.py` **第 255 行** `execute_code_only_phase` 附近）可能只会捕获特定字段，而将 `dict` 的其他业务字段静默丢弃。这违反了 "零静默失败" 铁律。

### 4.2 修复契约
**显式合并与越界拒绝**：
- 如果 code-only phase 返回的 `dict` 包含框架保留字（如以 `_` 开头），这代表尝试越界覆写框架状态，必须抛出 `RuntimeError`，决不能直接 `pass` 或仅仅 `logger.debug`。
- 如果配置了 `output_schema`，返回的 `dict` 还需通过 Pydantic Validate 强校验。

### 4.3 实施步骤 (a3 Action Items)
1. **修改 Code Phase 处理** (`phase_executor.py` -> `execute_code_only_phase`)
   必须严格遵循 §4.4 定义的检查顺序，确保保留字检查发生在 validate 之前。
   ```python
   result = code_func(ctx)
   if isinstance(result, dict):
       # 1. 先检查 reserved key (必须在 validate 之前！)
       invalid_keys = [k for k in result.keys() if k.startswith('_')]
       if invalid_keys:
           raise RuntimeError(f"Code phase '{phase.name}' returned reserved keys: {invalid_keys}")
       
       # 2. 再走 schema validate (Pydantic 默认 extra=ignore 不影响，因为 reserved 已 raise)
       if phase.output_schema:
           result = SchemaEngine.validate(result, phase.output_schema)
           
       # 3. 合并到 State
       next_state = StateManager.update_business(state, **result)
   ```

### 4.4 检查顺序契约 (Runtime Check Ordering)
**强制契约**：对于 code-only phase 返回结果的校验，**保留字检查必须发生在 Pydantic schema validation 之前**。

*   **理由**：Pydantic 的默认行为是 `extra='ignore'`。如果先执行 validate，所有不在 schema 定义中的字段（包括以 `_` 开头的非法越界字段如 `_metrics`）都会被 Pydantic 静默丢弃，导致后续的 reserved key 检查落空。这种 silent failure 严重违反了框架的 "fail-loud" 铁律。
*   **保留字定义**：任何以单下划线 `_` 开头的 key（包括 dunder methods 如 `__xxx__`）均视为框架保留字，业务逻辑无权通过直接返回的方式覆盖它们。
*   **Helper 入参签名**：处理提取和验证的辅助函数，其入参的类型提示必须使用精确签名如 `result: object` 或 `Callable[..., object]`，**严禁使用 `Any`**。

---

## 5. A1+A2+A3 实施依赖与顺序

本阶段必须遵循以下串行实施顺序，防止引入中间态破坏：
- **步骤 1：A1 (强制 Schema) 实施**。这是最基础的契约前提。做完 A1，A2 就不需要再考虑 `schema is None` 的包袱。
- **步骤 2：A3 (Code-only 修复) 实施**。相对独立，主要修改 `phase_executor` 中 Python Node 的处理。
- **步骤 3：A2 (中间件换轨) 实施**。涉及核心数据流，需在 A1 的契约保护下完成新管道的组装。

**协作切割**：
a3 在同一工作区中**依次完成**以上 3 步，并在本地确保 `pytest` 全过。全部完成后呼叫 a1 进行 Code Review。

---

## 6. 验证标准 (a1 Review Checklist)

a1 进行验收时，需严格比对以下指标：
1. **Mypy Strict 增量覆盖**：新引入及修改的 `phase_executor.py`、`schema_hoisting.py` 和相关中间件必须包含完整类型签名，不可新增 `Any` 或 `type: ignore`。
2. **测试水位防退步 + runtime 签名验证**：
   - `pytest` 维持 baseline 全过 (870+，A1 v2 引入新 case 后期望 875+)。对于因 `SkillCompileError` (由于缺乏 Schema) 导致的不合规 SKILL 编译失败，视为**预期的正常阻断**，不计入 baseline 退步。
   - **每个 live SKILL 的 validator 必须有 runtime smoke test** (不止 compile gate)。a3 实施时必须为涉及的每个 live SKILL 写对应的 runtime smoke test。
   - smoke test 必须模拟 `ValidationMiddleware` schema 分支真实数据流，验证 validator 接到的 payload 形状跟 `SKILL.md` 声明的 `output_schema` 类型完全一致。
   - **强制 A3 验证用例 1**：必须验证 **dict + output_schema + _reserved_key** 的组合 case。确保在存在 schema 的分支下，即使 Pydantic 的 extra=ignore 机制存在，非法注入 `_metrics` 等保留字的行为也必须 raise `RuntimeError`，决不能被静默丢弃。
   - **强制 A3 验证用例 2 (v5 新增)**：必须增加 schema-less LLM finish_task 的 routing test，确保未声明 schema 但使用 finish_task 的 Phase 能够被正确路由至遗留的 `ValidationMiddleware` fallback，保证 live SKILL 不会挂掉。
   - 覆盖率 `pytest --cov` 不能低于 71.25%。
3. **消除静默失败代码**：检索 `phase_executor.py`，不得存在任何空 `except:`。
4. **无旧中间件残留**：`phase_executor.py` 执行流中不再出现遗留的 `ValidationMiddleware`。

---

## 7. 风险与回退方案

- **阻碍点**：A2 切轨新中间件时，如果发现接口参数无法适配真实的 LangGraph 调用流。
- **回退方案**：立即停止 A2 修改，将 Trace 汇总报告给主控，并申请在 `middlewares` 层重审接口签名。无特殊情况不开启 Feature Flag。

---

## 8. Out-of-Scope (不在本设计范围)

- **A4 (Python 包命名阻塞 mypy strict)**：由 a1 另行实施隔离。
- **A5 (Robust JSON Load 单引号清洗)**：将在中间件换轨 (A2) 稳定后的 MVP-4 中单独引入。
- **v2 Rust 式编译器增强**：全链路 IO 闭环推导属 v1.1 路线。