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

### 3.2 接口契约重构
引入单一职责 Middleware 栈。其中 2 个 MVP-3 中间件已就绪，第 3 个需要新建：
- `ProtocolValidationMiddleware` (已就绪)：只负责拦截 LLM Payload，进行基础的格式清洗与 JSON Load 验证。
- `CognitiveFlowMiddleware` (已就绪)：负责业务 Validator 调度以及最终的 `StateMerge`（将结果合并至 `WorkflowState`）。
- **`SchemaHoistingMiddleware` (需新建)**：负责基于 `output_schema` 解析并结构化 Payload。
  - **接口契约**：
    ```python
    class SchemaHoistingMiddleware(BaseMiddleware):
        def __init__(self, schema: type[BaseModel]):
            self.schema = schema

        def __call__(self, state: WorkflowState, tool_call: dict[str, Any]) -> dict[str, Any]:
            # 接收解析好的 raw JSON
            # 走 SchemaEngine 校验与结构化
            # 返回结构化的 dict 供下游 CognitiveFlow 使用
            pass
    ```

### 3.3 实施步骤 (a3 Action Items)
1. **新建 Hoisting 中间件**：
   - 新建 `src/core/graph_agent/middleware/schema_hoisting.py`，实现 `SchemaHoistingMiddleware` 接口。
2. **修改执行引擎** (`src/core/graph_agent/core/phase_executor.py`)
   - 引入并组装新的中间件管道：
     ```python
     middlewares = [
         ProtocolValidationMiddleware(),
         SchemaHoistingMiddleware(schema=phase.output_schema),
         CognitiveFlowMiddleware(business_validator=...)
     ]
     ```
3. **清理遗留基建**
   - 从 `middlewares.py` 中标记 `ValidationMiddleware` 为 `@deprecated` 或在测试过关后删除。

### 3.4 风险点
- **重构范围大**：`phase_executor.py` 有 964 行，一次切轨风险极高，评估是否需要分两个子 PR（前置拆分解耦准备 + 最终切轨）。
- 需确保 `WorkflowState` 在各层中间件中的不可变性（Immutable 更新），避免副作用覆盖。

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
   - **强制 A3 验证用例**：必须验证 **dict + output_schema + _reserved_key** 的组合 case。确保在存在 schema 的分支下，即使 Pydantic 的 extra=ignore 机制存在，非法注入 `_metrics` 等保留字的行为也必须 raise `RuntimeError`，决不能被静默丢弃。
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