# Design: Contract Docs Baseline Freeze

## §0 审计驱动的 Scope 修正
最初的契约设计仅将 `graph_agent.__all__` 导出的 18 个符号作为防漂移防线。在随后的 `CONSUMER-API-INVENTORY` 审计中发现，下游宿主（特别是 Studio Backend 与 Predict V2）实际上强依赖了 **61 个符号**，其中包含 11 个 `_predict_internal` 私有模块的符号以及大量 Callback Events、AST 等深层对象。
**设计修正判据：“被消费的即是契约 (What is consumed is the contract)”**。如果我们只冻结 18 个符号，在未来的重构中修改了其余 43 个符号会导致测试放行但生产环境崩溃，这直接违背了 PM 的 Golden Principle。因此，本次冻结设计全面转向**“真实 61 符号表面”**，并引入更强硬的哈希锁、字段级断言和测试绑定矩阵机制。

## 1. 契约边界设计与 `_predict_internal` 处理方案

### 1.1 真实的契约 Scope：冻结 61 表面
- **定义**：API 漂移防御必须覆盖完整的 61 个已被消费的符号。
- **判据**：凡是目前存在于 `CONSUMER-API-INVENTORY.md` 中的符号，无论是否在 `__all__` 中，无论是否带有 `_` 私有前缀，均认定为当前架构的**既定事实契约 (De Facto Contract)**，纳入 CI 冻结与 API 文档。

### 1.2 `_predict_internal` 的技术债处理
- **推荐方案：【冻结现状 + 标记为已知债务 + 单开边界清理 PR】**
- **理由**：
  1. 本次 `contract-docs` PR 的核心目的是“拉起防线并暴露真相”，决不能与业务代码的重构混在一起（违背 Additive-only 原则与 Non-Goal）。
  2. 把内部模块暴露为 Public API 需要仔细设计接口，强行在冻结动作中提权会导致 API 设计草率。
  3. 先通过本 PR 把 `_predict_internal` 的依赖现状写进防漂移测试（即使它很丑陋），让它暴露在阳光下，接下来的第一个重构 PR 就可以名正言顺地针对它进行清理解耦，届时通过“显式豁免”来合法修改防线。

## 2. 核心架构设计：三类契约的强制守门机制 (True Enforcement)

为了闭合所有“纸老虎”漏洞，三类契约必须拥有工程化强制手段。

### 2.1 引擎功能合规清单 (Feature Traceability Matrix)
- **强制机制**：纯 Markdown 清单无法防止功能被删。我们将清单升级为**可追溯性矩阵**。
- **落地**：每一项功能清单的条目后面，必须通过标签绑定现存的测试用例（例如 `[Covered By: tests/test_parser.py::test_basic_parse]`）。
- **CI 检查**：防漂移测试套件将包含一个脚本，解析该 Markdown 文件，校验每个 `[Covered By: ...]` 的测试不仅在代码库中存在，而且必须在 CI 中是 PASS 状态。一旦测试被误删，Markdown 也会立刻报错。

### 2.2 公开 API 契约与字段级漂移防御 (Field-level Drift Prevention)
- **强制机制**：只检查符号是否存在是不够的，如果 Dataclass 删除了一个字段，同样是致命漂移。
- **落地**：防漂移测试 `test_public_api_contract.py` 必须使用 AST 或 `inspect` 锁定完整的 61 符号表面，并且对所有的对象执行**签名与字段级断言**。对于 Dataclass 或 Pydantic Model（如各种 Event 和 AST），需提取其属性名和类型进行硬编码断言（如确保 `PathDiff` 依然包含 `added`, `removed`）。

### 2.3 文件标准冻结 (skill-spec Hash Lock)
- **强制机制**：为了防止在不经意间绕过 `status: FROZEN` 修改正文（内容守门）。
- **落地**：防漂移测试中必须计算这 14 份文档的内容哈希（SHA-256 Snapshot）。任何哪怕多了一个空格的修改，都会导致哈希变动从而 CI 失败。这彻底剥夺了“悄悄改字眼”的可能性。

### 2.4 豁免机制与批准记录 (Approval Gate)
- **强制机制**：如何定义 PM 说的 "unless explicitly approved"？
- **落地**：在代码库根目录或测试目录下引入显式的文件 `contract-exemptions.yaml`。若必须破坏契约（如后续清理 _predict_internal），必须在该文件中记录 PR 号、PM 批准说明、以及被豁免修改的具体符号/哈希。防漂移测试读取该 YAML 放行，由此留下永久的可审计痕迹。

### 2.5 排除非契约目录 (Sibling Exclusion)
- 明确声明：`docs/engine/` 下的其余 7 个子目录（如 `error-handling`, `execution-runtime` 等）属于内部逻辑讲解（Logic-Explained Docs），**不属于**不可动摇的契约基线。只有 `skill-spec` 目录属于此列。

## 3. PR 拆分计划
基于上述架构，我们强烈建议将该工作流拆分为两个 PR：
- **PR 1: 本次 PR (The Gatekeeper PR)**
  - 交付：完整的 61 符号 API 文档、带测试绑定的功能清单矩阵、skill-spec 文档打上 FROZEN。
  - 防线：建立基于哈希的文档防线、基于签名字段的 API 防线、特征追踪矩阵验证脚本文本。
  - 性质：纯 Additive，不改一行 src 业务代码。
- **PR 2: 边界解耦 PR (The Boundary Cleanup PR)**
  - 动作：专为解决 `_predict_internal` 泄露和深层耦合的技术债，设计专门的公开接口并在内部重构，利用 `contract-exemptions.yaml` 合法更新契约。