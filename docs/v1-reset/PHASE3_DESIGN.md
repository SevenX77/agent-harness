# Phase 3 实施级架构重塑设计 (M6/M7)

## 1. 背景与目标

在经历 Phase 1 与 Phase 2 实施后，系统虽然排除了大部分契约错配，并且测试集维持了高覆盖与全量通过，但依据大厂双审结论（Commit 1fc52b3），我们依然面临两项阻碍 1.0.0 稳定发布的**硬核架构漏洞 (hard fail)**：
- **M6: `phase_executor.py` 仍为 1182 行的 God Class**，违反单一职责，将不同类型 Phase 的构建和运行揉捏在了一起。
- **M7: 遗留的 `ValidationMiddleware` 仍在双系统并行**，因为现有的 4 个 Live SKILL 的特定 LLM Phase 在没有配置 `output_schema` 的情况下依旧调取了 `finish_task`。

**阶段 3 目标**：彻底肢解 `phase_executor.py`，实现多态节点架构；全面引入 `mode: raw_output` 或 `free_text`，清理不需要 schema 但使用 `finish_task` 的自由文本输出阶段；彻底删除 `ValidationMiddleware`。

---

## 2. M6 phase_executor God Class 拆解 详细设计

### 2.1 现状
当前的 `src/core/graph_agent/core/phase_executor.py` (1182 行) 是整个执行周期的上帝类，包含了模型初始化、中间件组装（包含静态、动态与无 schema 的复杂路由）、代码工具执行、校验状态流转等所有逻辑。它严重违反了单一职责原则，是制约系统拓展和导致回归的核心技术债。

### 2.2 多态节点架构设计
摒弃单个巨大的 `PhaseExecutor`，全面采用面向对象的多态节点架构设计。在执行层解耦不同 Phase 的具体运行逻辑：
- **基类 `PhaseNode`**：
  抽象接口，声明标准签名：
  ```python
  from abc import ABC, abstractmethod
  class PhaseNode(ABC):
      @abstractmethod
      def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
          pass
  ```
  所有子类必须实现此接口，以便上游 LangGraph 在路由时无脑分发。
- **子类 `LLMPhaseNode`**：
  专职负责 `mode: llm`。承接原 `execute_llm_phase` 的核心逻辑。它不再关心代码工具的特殊处理，而是专注组装 LLM 的提示词、配置模型（如 `create_agent`）并发起 LangChain 调用，同时负责中间件（ProtocolValidation 和 CognitiveFlow）的精准挂载。由于我们在 M7 中消除了双系统，这里只挂载一种规范的中间件栈。
- **子类 `CodePhaseNode`**：
  专职负责 `mode: logic`（即不依赖 LLM 的纯代码任务）。承接原 `execute_code_only_phase` 的逻辑。只负责同步地执行 `execute_steps` 注册的 Python 函数，并将结果直接合并到状态的 BusinessData 中。它将包含严谨的保留字检查逻辑，确保不出现越界覆写，绕过不必要的 LLM 中间件，以提升稳定性和性能。
- **子类 `ValidationPhaseNode`**：
  专职负责隔离执行 `validator` 校验节点逻辑。承接原 `execute_validation_phase` 的责任，处理校验失败时的状态切轨（如设置重试计数器，输出校验警告信息），并将 `business_validator` 等函数的调用局限于此。
- **工厂模式 (Factory) 与依赖容器 (`DependencyContainer`)**：
  原 `PhaseExecutor` 承担了存放 `_resolver`, `_callbacks`, `_save_compaction_sidecar`, `_run_context` 的全局职责。在多态节点架构下，我们将引入一个不可变的 `@dataclass` `DependencyContainer` 来封装这些生命周期跨度不同的对象：
  ```python
  @dataclass(frozen=True)
  class DependencyContainer:
      resolver: Any
      callbacks: list[Callback]
      save_compaction_sidecar: Callable[..., None]
      io_manager: IOManager
  ```
  引入 `phase_node_factory.py` 并在内部实现分发工厂：
  ```python
  def build_phase_node(phase: Phase, dependencies: DependencyContainer) -> PhaseNode:
      if phase.mode == "llm":
          return LLMPhaseNode(dependencies)
      elif phase.mode == "logic":
          return CodePhaseNode(dependencies)
      elif phase.mode == "validation":
          return ValidationPhaseNode(dependencies)
      else:
          raise ValueError(f"Unknown phase mode: {phase.mode}")
  ```
  工厂将根据 `phase.mode` 实例化具体的 `PhaseNode` 子类，并将 `dependencies` 安全注入。这避免了直接在 `GraphBuilder` 的闭包中捕获散乱的变量，保障了依赖注入的清晰与严格。

### 2.3 实施步骤 (a3 Action Items)
1. **新建目录与文件划分**：
   新建 `src/core/graph_agent/core/phase_nodes/` 目录，并创建以下文件：
   - `__init__.py`: 统一暴露节点类及工厂函数。
   - `base.py`: 定义 ABC `PhaseNode` 以及共享的上下文注入规范（含 `DependencyContainer` 定义）。
   - `llm_phase_node.py`: 从 `phase_executor.py` 抽离 LLM 相关组装执行流，包含工具绑定的所有私有辅助方法。
   - `code_phase_node.py`: 抽离纯代码逻辑执行流 (Code-only)，包含保留字检查，保持代码紧凑。
   - `validation_phase_node.py`: 抽离独立验证节点的流转逻辑。
   - `factory.py`: 包含基于 `mode` 分发依赖注入的 `build_phase_node` 工厂。
2. **抽离代码逻辑**：
   - 彻底将 `phase_executor.py` 中的上千行大函数切割为类的方法。确保 `LLMPhaseNode` 中对 `CognitiveFlowMiddleware` 的依赖装配不再需要 `schema is None` 的冗余检测（由于 M7 实施后所有 LLM Phase 必定拥有 Schema）。需要小心处理原有的 `_apply_io_hoist` 等通用辅助方法，可以将它们重构成各个 Node 基类或是 helper 函数调用。
3. **改造入口与工厂分发**：
   - 重写原有的 `phase_executor.py`，使之成为一个薄壳包装文件，或者直接废弃该文件，将调用图的构建直接指向 `factory.py` 生成的 `PhaseNode.execute`。重构后入口路由应控制在 200 行以内。在 `GraphBuilder` 注入中间件或闭包执行时，只需使用构建好的 `PhaseNode` 实例。

### 2.4 验证标准
- `pytest` 测试集 912+ passed 维持不破（涵盖了原有的 28 个执行器测试与路由测试）。
- `mypy --strict` 0 error。
- `ruff check` 0 error。
- 测试覆盖率 `≥ 73.25%`。
- `phase_executor.py` (或其替代核心路由文件) ≤ 200 行。
- 多态节点子类 `mypy` 签名必须严格，所有注入点不再使用隐式的泛型，杜绝 `Any` 污染。

### 2.5 改造图构建逻辑 (`src/core/graph_agent/core/harness.py` 或 `graph_builder.py`)
原本闭包中直接持有 `_phase_executor`。我们需要修改对应的 `GraphBuilder` 挂载点：
- 在调用层实例化 `DependencyContainer`。
- 修改传入 LangGraph 的 node function。原先的闭包逻辑大约为 `return phase_executor.execute_xxx(phase, state)`。
- 修改后，节点构建闭包应当变为获取工厂方法，并直接委派：
  ```python
  def node_closure(state: WorkflowState) -> WorkflowState:
      dependencies = DependencyContainer(
          resolver=self._resolver,
          callbacks=self._callbacks,
          save_compaction_sidecar=self._save_compaction_sidecar,
          io_manager=io_manager
      )
      phase_node = build_phase_node(phase, dependencies)
      return phase_node.execute(phase, state)
  ```
- 将 `phase_executor.py` 彻底改造为薄壳，或废弃该文件，将调用图的构建逻辑统一放在 `factory.py` 附近管理。在改造时建议 a3 采取“抽取接口 -> 改写 Builder 挂载 -> 替换废弃原逻辑”的三步走节奏。

### 2.6 风险点
- **生命周期时序与依赖 (Lifecycle & Dependency Injection)**：
  确保在工厂分发时安全准确地传递到不同 `PhaseNode` 的构造函数中。尤其是 `run_context` 和 `heartbeat` 等 per-invocation 状态，需要确认它们是在 `execute()` 入参传递，还是封装在 `DependencyContainer` 内（推荐前者，保持 container 的无状态性）。

---

## 3. M7 终结 ValidationMiddleware 双系统 详细设计

### 3.1 现状
根据 A2 v5 的 `Legacy Fallback` 路由策略，那些没有配置 `output_schema` 的 LLM Phase 走回了 `ValidationMiddleware`。实证发现 `event-extraction` (aggregate, review), `batch-analysis`, `global-synthesis` 等中的聚合阶段因为只是为了获得 LLM 的总结文本，所以并没有结构化需求。

### 3.2 方案选型 (放弃 raw_output，直接补 Schema)
**决断：采用策略 C，即为所有使用 `finish_task` 的 schema-less phase 直接补充对应的 `output_schema`。这避免了发明新的 phase type 的复杂性，能够维持单一执行管道的优雅。**

起初考虑过增加 `mode: raw_output` / `free_text`，但是：
1. `raw_output` 会产生全新的中间件挂载路径，它可能绕过 `CognitiveFlowMiddleware`，这反而增加了一个新的"特权路径"，导致中间件链条的断层（比如，如果自由输出阶段仍然需要 Protocol Validation 检查其输出字段呢？）。
2. 在原有的交互契约下，`finish_task` 是由 LLM 显式调用的工具。只要调用了该工具，系统就默认它是为了传递某种格式化数据（哪怕只有一段总结字符串）。
3. 补充 Schema 并不是多此一举：我们只用为那些 Phase 增加最简单的 `{ "summary": "string" }` 字典，就能让这些阶段在新的强类型管道中正常解析，且不需要对现有框架（如 `CognitiveFlowMiddleware._validate_finish_args`）做任何修改，大大降低了风险。这是典型的数据契约显式化的体现。

### 3.3 4 个 live SKILL 迁移 Plan
在 `skills/*/SKILL.md` 中为对应 Phase 补充最简的 markdown 字典或 schema。补充 Schema 不仅仅是简单的填补字段，更是对这些自由输出阶段进行契约化的重塑。必须同步修改这 4 个 SKILL 内 LLM Phase 的 `prompt`，教导大模型输出与新添加 Schema 对应的结构。如果修改不到位，大模型可能会陷入频繁地重复发送纯文本，而始终过不了 Schema 验证器的死循环中。
1. **`event-extraction`**：
   - Phase `aggregate`: 补 `output_schema_md: | { "summary": "string" }`。同时在 prompt 中加入指导说明：“请在 `<business_data>` 块中输出满足上述 JSON 格式的字典，将你的分析内容放在 `summary` 字段下。所有的推断与归纳过程请作为 summary 字段的值，不要使用任何多余的外层包裹或是输出单纯的代码片段”。
   - Phase `review`: 补 `output_schema_md: | { "summary": "string" }`。同步更新其内部 prompt，指示大模型必须遵循新的格式化输出规范，而不再仅仅返回纯文本评论。
2. **`batch-analysis`**：
   - 为所有调用 `finish_task` 的阶段补充包含关键 `summary/output` 字段的 schema，包括 `entity_and_characters`, `parallel_analysis`, `continuity`。由于批次分析往往涉及大量角色的提取或连续性检验，这里的 schema 可以更加贴合场景。
     例如：
     ```yaml
     output_schema_md: |
       {
         "analysis_summary": "string",
         "identified_issues": ["string"],
         "status": "string"
       }
     ```
     在 `user_prompt_template` 或 system prompt 中，需显式声明：“在调用 `finish_task` 时，你必须在 `business_data_md` 中提供形如上述字段结构的 JSON 或是等价 Markdown。必须通过指定的结构化方式汇报你识别出的核心事件状态 (status) 和潜在问题 (identified_issues)，任何多余的废话都将被视为不合规并遭受打回。”
3. **`global-synthesis`**：
   - 为 `global_analysis`, `retroactive` 等补充 Schema。全局综合通常需要回顾前面的分析结果并做最后归总，例如：
     ```yaml
     output_schema_md: |
       {
         "global_insights": "string",
         "retroactive_corrections_applied": "int"
       }
     ```
     修改对应的 prompt，特别是在结尾部分加上：“最后，调用 `finish_task` 传递结构化的分析报告，包含 `global_insights` 字段以陈述你的全盘观察，以及使用 `retroactive_corrections_applied` 标记你实施的回溯修正次数。确保模型生成的结尾能够通过 CognitiveFlow 的 `SchemaEngine.validate` 严格校验。”

### 3.4 ValidationMiddleware 删除步骤
由于我们采用策略 C（给所有缺失 Schema 的 LLM Phase 补充 Schema），此时双系统的 Legacy Fallback 路线将永远不会被触发，它变成了纯粹的死代码 (Dead Code)。
1. **迁移验证阶段**：
   完成 `SKILL.md` 的迁移后，必须确保 `pytest` 跑过现存的 e2e 验证逻辑。如果 e2e 测试因为 LLM 模型的不可预知行为而发生 Schema 解析错误，我们需要在 CI/CD 流中捕获并分析这些错误，这证明新管道已经在发挥拦截作用。
2. **代码物理删除阶段**：
   - 删除 `src/core/graph_agent/cognitive/middlewares.py` 中的 `ValidationMiddleware` 整个类。这大约能精简出数百行的遗留逻辑。
   - 删除所有曾经为了支撑 `ValidationMiddleware` 工作而存在的独立辅助函数（如在 `middlewares.py` 中独占的 `_legacy_finish_result_key` 等）。
3. **清理遗留挂载点**：
   清理新拆分的 `llm_phase_node.py`（或尚未拆分的 `phase_executor.py`）中的 `ValidationMiddleware` Legacy Fallback 引入与实例挂载。
   ```python
   # 删除以下曾经用于兜底的旧有防线代码：
   from ..cognitive.middlewares import ValidationMiddleware
   
   if phase.output_schema is None or isinstance(phase.output_schema, DynamicSchemaDef):
       phase_middlewares.append(ValidationMiddleware(...))
   ```
4. **终极确认阶段**：
   全库 `grep "ValidationMiddleware"` 确保 0 hit (除历史审计文档、Markdown 说明等静态文本外)，确认双系统的物理实体彻底消亡。

### 3.5 实施步骤 (a3 Action Items)
1. **修 4 SKILL.md**：按照 3.3 为 `event-extraction` 的 aggregate / review，`batch-analysis` 的各个 LLM phase 以及 `global-synthesis` 的 LLM Phase 补充最简 Schema。必须同步修改这 4 个 SKILL 内 LLM Phase 的 `prompt`，教导大模型输出与新添加 Schema 对应的结构。
2. **清理 Fallback 路由**：在 `llm_phase_node.py` 挂载中间件时，移除 `if phase.output_schema is None:` 和 `DynamicSchemaDef` fallback 相关的 `ValidationMiddleware` 逻辑，强制全部使用 `CognitiveFlowMiddleware` 和 `ProtocolValidationMiddleware`。由于现在所有 LLM Phase 都有了明确的 Schema，所有的分支逻辑都可以精简成唯一的强类型静态 Schema 管道。
3. **终极清理**：
   - 从 `src/core/graph_agent/cognitive/middlewares.py` 删除 `ValidationMiddleware` 整个类定义（及其依赖的 `_legacy_finish_result_key` 等辅助方法）。
   - 全库检索 `ValidationMiddleware`，确保没有任何挂载引用，同时删除所有过时的 import 声明。
   - 检索 `tests/` 目录，特别是 `tests/graph_agent/cognitive/test_middlewares.py` 中涉及旧版 ValidationMiddleware 的数百行单测，因为新架构已经通过 CognitiveFlowMiddleware 的对应单元测试进行了覆盖，直接将被废弃的方法的测试用例全量删除。这不仅可以加快测试的执行速度，更标志着双系统技术债的彻底偿还。

### 3.6 验证标准
- 全库搜索 `ValidationMiddleware` 命中数为 0。
- pytest 912+ (新增针对 raw_output 或是兜底 Schema 行为逻辑测试用例必须覆盖新的执行流)。
- 4 个 live SKILL 真跑 e2e 仍工作。在修改 prompt 与 schema 之后，需要确保实际的 LLM (如 GPT-4, Claude) 能够顺利地输出所要求的简单 JSON，没有发生大范围的重试与死循环。
- mypy 与 ruff 的 0 error 基线不动摇。

### 3.7 风险点
为已有的自由文本生成添加 schema 可能会改变 LLM 返回的数据格式，这需要严格地验证在 prompt 中对应的 user example 和 schema 结构是否对齐。如果 LLM 持续返回原本的自由文本而忽略 Schema，将会触发 CognitiveFlow 的 Schema Validation Error。这要求在实施 3.3 迁移方案时，同步审视对应 Prompt，确保包含 `output_schema_md` 中定义的字段结构指引。这也可能对原有的 Token 开销造成不可避免的少量上升。
同时注意 `tests/skills/event_extraction/test_cognitive_flow_smoke.py` 等 e2e smoke 测试文件，它们直接依赖于当前输出数据的形状（如对 `_finish_task_result` 字典结构的断言），迁移 Schema 后必须同步更新这些断言，否则 CI 将被直接阻断。

### 3.8 应对 LLM 输出漂移的 Prompt 设计最佳实践
由于我们将原有的自由文本输出强制通过增加 Schema 转换成了格式化输出，一个常见的模型退化模式是：LLM 只输出了纯 JSON，但忘记将其包裹在 `<business_data>...</business_data>` 的 Markdown Code Block 中。
在实施时：
- 对 4 个 SKILL 中的系统 Prompt 进行调整，必须包含如下类似语句：“你的最终输出必须并且仅仅包含一个被 `<business_data>` 标签包裹的有效 JSON 结构，结构如下：{ ... }。”
- 对于更智能的模型 (如 GPT-4, Claude 3.5 Sonnet) 这通常不是问题，但如果是用于较小规模模型 (如 Gemini-Flash 或开源的 8B 模型) 的测试，它们可能会因为这个格式约束而频繁触发 `CognitiveFlowError`。
- 我们需要在 smoke test 中考虑到这种可能性，甚至在测试时显式引入 `output_example` 来帮助小模型进行 Few-shot 学习，确保在 A3 实施 M7 之后系统的健壮性。

---

## 4. 实施依赖与顺序
- **并行解耦**：M7 和 M6 可以切分成两个阶段，但推荐 **M7 在前，M6 在后**。
- **先做 M7**：先给 4 个 SKILL 补充 schema，并在当前的 `phase_executor.py` 内部摘掉 `ValidationMiddleware`，此时双系统已被消灭。
- **再做 M6**：在完全干净没有双系统 fallback 的 `phase_executor.py` 基础上进行 `PhaseNode` 子类的拆解，难度与引发状态漂移的风险会成倍下降。

---

## 5. 整体阶段 3 Ship 标准
- Pytest 测试集 912+ passed 维持不破（涵盖新增加的多态节点分发测试与旧路由路径对齐）。
- `mypy --strict` 0 error 不破。
- `ruff check` 0 error 不破。
- 测试覆盖率 `≥ 73.25%`（期望伴随单元测试增加进一步提升）。
- `phase_executor.py` (或其直接替代的核心分发路由) ≤ 200 行，结束 God Class 时代。
- 彻底清理双系统：全库 `grep "ValidationMiddleware"` 返回 0。

---

## 6. Out-of-scope (推 v1.1+)
- 彻底的插件化解耦以及 IoC 容器化改造（例如允许外部第三方动态注册新的 PhaseNode 类型或让 `SchemaEngine` 能够由不同实现的后端插件接管）。
- OpenTelemetry (OTel) 链路跟踪标准的 context propagation 改造。
- `business_data` 完全基于编译期的静态流依赖检查器。), `batch-analysis`, `global-synthesis` 等中的聚合阶段因为只是为了获得 LLM 的总结文本，所以并没有结构化需求。

### 3.2 方案选型 (放弃 raw_output，直接补 Schema)
**决断：采用策略 C，即为所有使用 `finish_task` 的 schema-less phase 直接补充对应的 `output_schema`。这避免了发明新的 phase type 的复杂性，能够维持单一执行管道的优雅。**

起初考虑过增加 `mode: raw_output` / `free_text`，但是：
1. `raw_output` 会产生全新的中间件挂载路径，它可能绕过 `CognitiveFlowMiddleware`，这反而增加了一个新的"特权路径"，导致中间件链条的断层（比如，如果自由输出阶段仍然需要 Protocol Validation 检查其输出字段呢？）。
2. 在原有的交互契约下，`finish_task` 是由 LLM 显式调用的工具。只要调用了该工具，系统就默认它是为了传递某种格式化数据（哪怕只有一段总结字符串）。
3. 补充 Schema 并不是多此一举：我们只用为那些 Phase 增加最简单的 `{ "summary": "string" }` 字典，就能让这些阶段在新的强类型管道中正常解析，且不需要对现有框架（如 `CognitiveFlowMiddleware._validate_finish_args`）做任何修改，大大降低了风险。这是典型的数据契约显式化的体现。

### 3.3 4 个 live SKILL 迁移 Plan
在 `skills/*/SKILL.md` 中为对应 Phase 补充最简的 markdown 字典或 schema。补充 Schema 不仅仅是简单的填补字段，更是对这些自由输出阶段进行契约化的重塑。必须同步修改这 4 个 SKILL 内 LLM Phase 的 `prompt`，教导大模型输出与新添加 Schema 对应的结构。
1. **`event-extraction`**：
   - Phase `aggregate`: 补 `output_schema_md: | { "summary": "string" }`。同时在 prompt 中加入指导说明：“请在 `<business_data>` 块中输出满足上述 JSON 格式的字典，将你的分析内容放在 `summary` 字段下”。
   - Phase `review`: 补 `output_schema_md: | { "summary": "string" }`。同步更新其内部 prompt。
2. **`batch-analysis`**：
   - 为所有调用 `finish_task` 的阶段补充包含关键 `summary/output` 字段的 schema，包括 `entity_and_characters`, `parallel_analysis`, `continuity`。
     例如：
     ```yaml
     output_schema_md: |
       {
         "analysis_summary": "string",
         "identified_issues": ["string"],
         "status": "string"
       }
     ```
     在 `user_prompt_template` 或 system prompt 中，需显式声明模型在调用 `finish_task` 时必须附带符合上述结构的 JSON 数据。
3. **`global-synthesis`**：
   - 为 `global_analysis`, `retroactive` 等补充 Schema，例如：
     ```yaml
     output_schema_md: |
       {
         "global_insights": "string",
         "retroactive_corrections_applied": "int"
       }
     ```
     修改对应的 prompt，确保模型生成的结尾能够通过 CognitiveFlow 的 `SchemaEngine.validate` 严格校验。

### 3.4 ValidationMiddleware 删除步骤
由于我们采用策略 C（给所有缺失 Schema 的 LLM Phase 补充 Schema），此时双系统的 Legacy Fallback 路线将永远不会被触发，它变成了纯粹的死代码 (Dead Code)。
1. **迁移验证阶段**：
   完成 `SKILL.md` 的迁移后，必须确保 `pytest` 跑过现存的 e2e 验证逻辑。如果 e2e 测试因为 LLM 模型的不可预知行为而发生 Schema 解析错误，我们需要在 CI/CD 流中捕获并分析这些错误，这证明新管道已经在发挥拦截作用。
2. **代码物理删除阶段**：
   - 删除 `src/core/graph_agent/cognitive/middlewares.py` 中的 `ValidationMiddleware` 整个类。这大约能精简出数百行的遗留逻辑。
   - 删除所有曾经为了支撑 `ValidationMiddleware` 工作而存在的独立辅助函数（如在 `middlewares.py` 中独占的 `_legacy_finish_result_key` 等）。
3. **清理遗留挂载点**：
   清理新拆分的 `llm_phase_node.py`（或尚未拆分的 `phase_executor.py`）中的 `ValidationMiddleware` Legacy Fallback 引入与实例挂载。
   ```python
   # 删除以下曾经用于兜底的旧有防线代码：
   from ..cognitive.middlewares import ValidationMiddleware
   
   if phase.output_schema is None or isinstance(phase.output_schema, DynamicSchemaDef):
       phase_middlewares.append(ValidationMiddleware(...))
   ```
4. **终极确认阶段**：
   全库 `grep "ValidationMiddleware"` 确保 0 hit (除历史审计文档、Markdown 说明等静态文本外)，确认双系统的物理实体彻底消亡。

### 3.5 实施步骤 (a3 Action Items)
1. **修 4 SKILL.md**：按照 3.3 为 `event-extraction` 的 aggregate / review，`batch-analysis` 的各个 LLM phase 以及 `global-synthesis` 的 LLM Phase 补充最简 Schema。必须同步修改这 4 个 SKILL 内 LLM Phase 的 `prompt`，教导大模型输出与新添加 Schema 对应的结构。
2. **测试覆盖补全 (must-fix #1)**：由于 `src/core/graph_agent` 的覆盖率跌至 72.47%，要求补齐因删除 `ValidationMiddleware` 和修改 `phase_executor` 路由导致的覆盖率盲区。特别是针对新抽离的 `LLMPhaseNode` 和 `CodePhaseNode` 等执行路径，编写对应的单元测试，确保覆盖率回升至 73.25% 门槛之上。
   - 运行 `pytest --cov=src/core/graph_agent --cov-report=term-missing`，定位所有 coverage 缺失的代码行。
   - 为缺乏测试的特定分支（如 dynamic schema fallback 以外的其他异常路径）补充单元测试。
   - 为代码拆分后的每个 Node 类（`LLMPhaseNode`, `CodePhaseNode`, `ValidationPhaseNode`）编写针对性的测试。
   - 注意 `phase_executor.py` 内部对于状态更新逻辑的单元测试转移。原来位于 `tests/graph_agent/core/test_phase_executor.py` 中的测试，如果已经因为代码搬迁而失败，需要迁移到对应的 `test_llm_phase_node.py` 和 `test_code_phase_node.py` 等测试文件中。
   - 保证至少新增 3 到 5 个高价值的单测用例，验证在缺失 Schema (被编译期阻断) 和带有正常 schema 的两种不同路线的组合覆盖。
3. **修复 ModuleSandbox Pydantic Forward-Ref 缺陷 (must-fix #2)**：
   在 `src/core/graph_agent/core/module_sandbox.py` (如 `_load_module` 或 `_load_from_file` 处执行完 `exec_module` 之后，或者更好在执行前)，必须执行以下两步契约：
   - 1) 强制将模块注册到全局命名空间：`sys.modules[module_path] = module`，以便 forward-ref 解析时能从系统中命中。
   - 2) 遍历模块中所有继承自 `BaseModel` 的类，调用 `cls.model_rebuild()`：
     ```python
     import sys
     from pydantic import BaseModel
     
     # 在 exec_module 前或后（根据内部实现调整时机）：
     sys.modules[module_path] = module
     spec.loader.exec_module(module)
     
     for obj in vars(module).values():
         if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
             obj.model_rebuild()
     ```
4. **清理 Fallback 路由**：在 `llm_phase_node.py` 挂载中间件时，移除 `if phase.output_schema is None:` 和 `DynamicSchemaDef` fallback 相关的 `ValidationMiddleware` 逻辑，强制全部使用 `CognitiveFlowMiddleware` 和 `ProtocolValidationMiddleware`。
5. **终极清理**：
   - 从 `src/core/graph_agent/cognitive/middlewares.py` 删除 `ValidationMiddleware` 整个类定义。
   - 检索 `tests/` 目录，删除所有直接实例化或测试 `ValidationMiddleware` 相关方法（如 `_validate_finish_task` 且未使用 CognitiveFlow 等价逻辑）的废弃测试。由于我们放弃了旧系统的向下兼容，任何针对旧系统的单测也应当随着功能代码一并废弃。
   - 全库检索 `ValidationMiddleware`，确保没有任何挂载引用。

### 3.6 验证标准
- 全库搜索 `ValidationMiddleware` 命中数为 0。
- pytest 912+ (新增针对 raw_output 或是兜底 Schema 行为逻辑测试用例必须覆盖新的执行流)。
- 4 个 live SKILL 真跑 e2e 仍工作。在修改 prompt 与 schema 之后，需要确保实际的 LLM (如 GPT-4, Claude) 能够顺利地输出所要求的简单 JSON，没有发生大范围的重试与死循环。
- mypy 与 ruff 的 0 error 基线不动摇。

### 3.7 风险点
为已有的自由文本生成添加 schema 可能会改变 LLM 返回的数据格式，这需要严格地验证在 prompt 中对应的 user example 和 schema 结构是否对齐。如果 LLM 持续返回原本的自由文本而忽略 Schema，将会触发 CognitiveFlow 的 Schema Validation Error。这要求在实施 3.3 迁移方案时，同步审视对应 Prompt，确保包含 `output_schema_md` 中定义的字段结构指引。这也可能对原有的 Token 开销造成不可避免的少量上升。
同时注意 `tests/skills/event_extraction/test_cognitive_flow_smoke.py` 等 e2e smoke 测试文件，它们直接依赖于当前输出数据的形状（如对 `_finish_task_result` 字典结构的断言），迁移 Schema 后必须同步更新这些断言，否则 CI 将被直接阻断。

### 3.8 PydanticUserError Forward-Ref 防退化 Regression (新加)
a3 在实施完成后，必须验证 Pydantic Forward-Ref 不再崩溃。我们要求增加一个 `loader → schema → CognitiveFlow.model_validate → NO_RAISE` 的组合 case，通过 `ModuleSandbox` 加载一个带前向引用的 Pydantic schema，并确保它能无缝通过后续的管道验证，从而防御此类隐式 Forward-Ref 失败的幽灵 Bug 再次复活。
具体的做法是，在测试目录下（例如 `tests/graph_agent/core/test_module_sandbox.py` 或者 `test_cognitive_flow_smoke.py` 中），编写一个微型的 Pydantic class，该类包含类似 `Literal["A", "B"]` 等 forward reference 声明。
- 使用 `SkillLoader.compile_skill` 模拟读取并在 `ModuleSandbox` 中加载这个类。
- 发送一个合理的字典格式 Mock 响应，让其流入 `CognitiveFlowMiddleware._validate_finish_args` 并触发 `model_rebuild` 和验证逻辑。
- 只有这个断言在未来任何重构中始终成功时，我们的 `sys.modules` 以及 `model_rebuild` 的 workaround 才算是稳固合规的。
- 请注意 `model_rebuild` 可能会触发更深层的 ImportError 或 TypeError，这必须在加载阶段 fail-loud 暴露，而不是等到运行时 CognitiveFlowMiddleware 调用 validate 时。因此 `sys.modules` 的写入和 `model_rebuild` 必须保持强原子性。

---

## 4. 实施依赖与顺序
- **并行解耦**：M7 和 M6 可以切分成两个阶段，但推荐 **M7 在前，M6 在后**。
- **先做 M7**：先给 4 个 SKILL 补充 schema，并在当前的 `phase_executor.py` 内部摘掉 `ValidationMiddleware`，此时双系统已被消灭。
- **再做 M6**：在完全干净没有双系统 fallback 的 `phase_executor.py` 基础上进行 `PhaseNode` 子类的拆解，难度与引发状态漂移的风险会成倍下降。

---

## 5. 整体阶段 3 Ship 标准
- Pytest 测试集 912+ passed 维持不破（涵盖新增加的多态节点分发测试与旧路由路径对齐）。
- `mypy --strict` 0 error 不破。
- `ruff check` 0 error 不破。
- 测试覆盖率 `≥ 73.25%`（必须补齐全覆盖率盲区，消除跌至 72.47% 的退步）。
- `phase_executor.py` (或其直接替代的核心分发路由) ≤ 200 行，结束 God Class 时代。
- 彻底清理双系统：全库 `grep "ValidationMiddleware"` 返回 0。
- **Loader-based Smoke 覆盖 4 个 live SKILL (must-fix #3)**：不再仅仅依赖 `importlib.util` 的孤立 workaround。必须使用 `SkillLoader.compile_skill(...)` 真实加载 `batch-analysis` / `global-synthesis` / `event-extraction` / `text-segmentation`，并穿透整个 `CognitiveFlowMiddleware`，确保能够真实捕获运行时在生产路径下的模型反射崩溃与契约解析问题。这要求 a3 编写专门的 `test_loader_based_smoke.py` 测试文件，在测试中遍历上述四个 SKILL，执行模拟的完成动作并断言解析管道正常无异常。

---

## 6. M9 Mirror Refactor (收窄 Lift-and-Shift 偏离)

### 6.1 当前 mirror 清单
在 M6 的早期 lift-and-shift 实施中，为了保证所有的 executor 测试无缝迁移并维持 0 回归的基线，`PhaseNode` 的几个核心子类在基类 `__init__` 中 verbatim 复制了老 `PhaseExecutor` 的属性名。通过检索 `self._\w+`，我们识别出以下几个主要 mirror 候选：
- `self._callbacks`
- `self._resolver`
- `self._save_compaction_sidecar`
- `self._run_context`
- `self._heartbeat`

基于架构设计原则，`_run_context` 和 `_heartbeat` 作为 per-invocation 的调用期状态不需要纳入容器。但前 3 个属性是伴随 Harness 生命周期的依赖，这种 mirror 模式虽然降低了短期重构摩擦，但违背了面向对象设计中依赖应该通过明确的数据容器传递或直接委托的原则。

### 6.2 收窄方案 — 通过 DependencyContainer
为了收拢这层设计偏离，我们将完全依赖 `src/core/graph_agent/core/phase_nodes/base.py` 中定义的 `DependencyContainer` 数据类。
- **字段映射 (Mapping)**：
  - `self._callbacks` → 彻底废弃，统一使用 `self.container.callbacks`
  - `self._resolver` → 彻底废弃，统一使用 `self.container.resolver`
  - `self._save_compaction_sidecar` → 彻底废弃，统一使用 `self.container.save_compaction_sidecar`
- **补全缺失的 IO 依赖**：
  检查发现当前的 `DependencyContainer` 遗漏了 `io_manager` 字段。为了支持基类中的 `_apply_io_hoist` 等需要 IO 操作的方法，必须在 `DependencyContainer` 中新增 `io_manager: IOManager`。
- **基类管理容器**：
  基类 `PhaseNode` 只需维护单一的 `self.container = dependencies` 引用，而不再逐一拆解装载。

### 6.3 实施步骤 (给 a3)
为保证平滑迁移，要求 a3 按以下步骤执行：
1. **扩充 DependencyContainer**：
   打开 `base.py`，向 `DependencyContainer` `@dataclass` 中增加 `io_manager: IOManager` 字段，并在所有实例化容器的入口点（如 `factory.py` 或 builder 挂载点）补齐该入参。
2. **清理基类与挂载容器**：
   在 `PhaseNode.__init__` 中删除针对上述三个 harness-lifetime mirror 属性的逐一赋值（`self._callbacks = ...` 等），增加并只保留单一的 `self.container = dependencies` 赋值。
3. **消除子类 Mirror 调用**：
   全量替换 `LLMPhaseNode`、`CodePhaseNode`、`ValidationPhaseNode` 以及基类（如 `_apply_io_hoist`）中对老式 `self._\w+` 属性的引用。将例如 `self._callbacks` 统一修改为 `self.container.callbacks`。
4. **验证正确性与回归基线**：
   在修改完成后，运行 `pytest` 以验证所有测试用例继续保持全量通过（930+ case，0 回归）。
5. **类型与风格严控**：
   运行 `mypy --strict` 和 `ruff check` 确保新的属性委派没有引发意外的 Any 污染。然后可独立 commit。

### 6.4 验证标准
- **测试通过率**：`pytest` 维持 930+ passing，实现 0 回归。
- **Mirror 彻底根除**：整个 `src/core/graph_agent/core/phase_nodes/` 目录下，子类无任何 `self._callbacks`, `self._resolver`, `self._save_compaction_sidecar` 等 mirror 老 `phase_executor` 的生命周期级属性遗留，对这些特定属性的全量 grep 命中数必须为 0。
- **容器体量控制**：`DependencyContainer` 中的字段必须严格小于 10 个（包含新增的 `io_manager`），以防其过度膨胀为上帝对象 (God Container)。
- **静态检查**：`mypy --strict` 0 error，`ruff check` 0 error。

---

## 7. Out-of-scope (推 v1.1+)
- 彻底的插件化解耦以及 IoC 容器化改造（例如允许外部第三方动态注册新的 PhaseNode 类型或让 `SchemaEngine` 能够由不同实现的后端插件接管）。
- OpenTelemetry (OTel) 链路跟踪标准的 context propagation 改造。
