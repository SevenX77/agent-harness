# Design: Contract Docs Baseline Freeze

## 1. 核心架构设计与产出物定义

本次 PR 的交付件设计分为两类：文档级防线（面向人与 LLM）与 工程级防线（面向 CI/CD）。

### 1.1 新增：引擎功能合规清单 (Feature Compliance Checklist)
- **定位**：“功能一个都不能少”的可执行核对表。
- **颗粒度**：必须具体到“核心行为 + 边界能力”，避免模糊表达。例如：“必须支持以 `<instruction>` 块提取 System Prompt 并映射给 LLM”，而非“支持 Markdown Prompt”。
- **分类组织**：
  1. 技能加载与解析 (Loading & Parsing)
  2. 静态编译与校验 (Compilation)
  3. 运行时调度与路由 (Execution & Routing)
  4. 状态与黑板机制 (State & Blackboard)
  5. 可观测性与异常处理 (Observability & Errors)
- **后续规范**：未来重构 PR 的描述中，强制要求 Checklist 核对。

### 1.2 新增：公开 API 契约文档 (Public API Reference)
- **定位**：宿主集成方（Studio/CLI）以 Python 调度引擎的绝对编程接口契约，与 `skill-spec` (描述 MD 格式) 严格区分。
- **覆盖范围**：精准对应 `graph_agent/__init__.py` 中的 18 个符号。
- **文档要素**：
  - 核心签名 (Signature): 参数与类型。
  - 语义契约 (Contract): 前置条件与后置条件。
  - 稳定性标识: 明确标记 `@stable`。

### 1.3 改造：文件标准冻结 (skill-spec Freeze)
- **策略**：**Additive-Only（只增不改）**。
- **落地手段**：对 `docs/engine/skill-spec/` 下的所有规范文件（含 README）注入“双重封印”：
  1. YAML Frontmatter: 注入 `status: FROZEN` 标识。
  2. 顶部注释指令: 追加 `<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->`。
- **纪律约束**：严禁借此机会修改规范的已有正文。

## 2. 工程化落地：API 漂移防御 (API Drift Prevention)
为保证 18 个公开 API 真正不可动摇，需从工程层面实施“双重锁定”。
- **测试名**：新增 `test_public_api_contract.py`
- **断言逻辑**：
  - **符号一致性**：使用 Python `inspect` 模块加载 `graph_agent/__init__.py`，断言其暴露的符号名称与数量必须永远等于 18（并逐一比对名称）。
  - **核心签名一致性**：提取并断言核心方法（如 `run_skill`, `compile_skill`）的参数名、必要类型注解未发生破坏性（Breaking）更改。
- **机制**：一旦在任何重构 PR 中意外改动了公开签名，CI 必须立即报错阻断。

## 3. 分工计划
- **Spec Authoring**：完成 Requirements, Research, Design（已由主控与架构师完成）。
- **Execution Agent (a1)**：负责编写 Tasks，并利用 AST 分析穷尽生成 API 契约文档与功能合规清单，编写防漂移测试。
- **Audit Agent (a3)**：交叉验证生成的 API 契约和功能清单，确保与代码库事实 100% 对齐。