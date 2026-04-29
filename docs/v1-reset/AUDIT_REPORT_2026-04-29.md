---
title: v1-reset 项目架构溯源与质量重塑审计报告
作者: a2 (gemini-3.x, 跑在 Gemini CLI yolo 模式)
派任务方: 用户 (非主控派)
日期: 2026-04-29 16:03
类型: agent 架构治理审计 (Architecture Governance Audit)
范围: v1-reset Phase 1
区别声明:
  - 本文件 a2 (gemini) **架构治理视角** — 编译期严格契约 + Robust Infrastructure + Rust 式编译器升级
  - ARCHITECTURE_AUDIT_PHASE1.md a2 (gemini, 主控派) **架构溯源视角** — 接口契约 + 设计文件回溯
  - ENGINEERING_AUDIT_CODEX_GPT5_2026-04-29.md a1 (codex) **工程基线视角** — 12 个 P0/P1/P2 issue
  - MASTER_REVIEW_PHASE1.md 主控 Claude **PM 视角** — 大厂对标 + 工程性能评分
---

# v1-reset 项目架构溯源与质量重塑审计报告 (2026-04-29)

## 0. 核心愿景：重塑“Rust 式”严格契约
本报告的核心结论：**e2e 的频繁失败不是实现 bug，而是架构治理的失效。** 
我们必须停止“打补丁”的思路，建立一套像 Rust 语言一样严格的编译与预测机制。**任何不符合标准的 Skill 必须在编译期被拦截，严禁进入运行时。**

---

## 1. 现状诊断：被忽视的“套娃”契约

### 1.1 JSON 信封 vs Markdown 信件
目前的 e2e 失败（尤其是单引号导致的死循环）源于对交互协议层级的误解：
*   **交互协议层（JSON Envelope）**：这是 LangGraph/Tool-calling 的底层物理协议。当 LLM 输出 `{'name': 'finish_task', ...}` 时，信封已经坏了。
*   **业务数据层（Markdown Letter）**：这是 `md2json` 和 `md-patch` 负责的对象，位于 JSON 的 `args` 字段内部。
*   **诊断结论**：目前的死循环是因为 **“信封坏了，却尝试用修信件的方法去补”**。当 JSON 解析在 Middleware 层失败时，`md2json` 甚至还没机会上场。

### 1.2 为什么之前没问题，现在出问题？
1.  **从“正则抠取”到“结构化解析”的阵痛**：旧架构通过正则模糊匹配规避了 JSON 的严格性；新架构为了 Studio 监控和状态流转，强制走标准 JSON 协议，导致隐藏的格式问题暴露。
2.  **契约冲突**：`callback_bridge.py` 采取了宽容策略（Warn but Continue），而 `ValidationMiddleware` 采取了严厉策略（Reject & Retry），这种不一致导致了死循环。

---

## 2. 设计文件回溯 (Specs Retrospective)

### 2.1 MVP 1-3 的遗漏清单
*   **遗漏项 A**：未定义“LLM 物理格式清洗契约”。默认了 LLM 总能输出标准 JSON，缺乏在基础设施层（Infrastructure）的 **Robust JSON Cleaning**。
*   **遗漏项 B**：**Middleware 过渡期断层**。新 Middleware 已就绪，但 `phase_executor` 仍挂载旧版逻辑，导致“双系统并行”。
*   **遗漏项 C**：**Validator 接口契约模糊**。未在设计文件中明确声明 `schema is None` 路径下 Validator 的输入到底应该是 `ctx` 还是 `list[dict]`。

---

## 3. 设计缺陷 vs 实现缺陷判定

### 3.1 架构设计缺陷 (Design Defect)
*   **错误纠偏责任归属错误**：将 JSON 语法错误（底层基建错误）抛给了业务 Agent 修复，而非在框架层自动清洗。
*   **隐式依赖风险**：Baseline 时代的成功依赖于“LLM 必须先调存储工具”这种隐式副作用，而非显式的数据流契约。

### 3.2 治理缺陷 (Governance Defect)
*   **编译门禁过松**：允许没有定义 `output_schema` 的 Phase 挂载需要结构化数据的 Validator。

---

## 4. “Rust 式”严格重塑方案

### 4.1 强健的编译器 (Strict Compiler)
**原则：不符合契约的 Skill 严禁上线。**
1.  **强制 Schema**：如果 Phase 挂载了业务 Validator，则 **必须** 显式声明 `output_schema`。编译期若缺失，报错。
2.  **静态路径检查**：在编译阶段检查所有 `script.*` 路径的合法性，禁止在运行时才抛出 `ModuleNotFoundError`。
3.  **IO 闭环验证**：静态验证 `context_mapping` 里的每一个变量在输入/输出链路中都有归属。

### 4.2 智能预测器 (Robust Predictor)
**原则：在真正运行 e2e 之前，通过 Predict 发现动态风险。**
1.  **格式模拟**：Predict 阶段模拟 LLM 输出各种“口音”的 JSON（单引号、尾随逗号），验证 Middleware 的清洗能力。
2.  **契约压测**：利用推理模型预测当前 Prompt 是否会导致 `SemanticValidationError`，并检查修复 Agent 是否有足够的上下文进行修复。

### 4.3 基础设施层硬核清洗 (Robust Infrastructure)
*   **实现 `robust_json_load`**：在 `ValidationMiddleware` 入口处，对 LLM 输出进行强制正则清洗（单引号转双引号、修复截断、剔除多余逗号）。
*   **职责剥离**：基建层负责把“信封”拆开；`md2json` 负责把“信件”解析；Agent 只负责修“业务内容”。

---

## 5. Phase 1 Ship 准则

1.  **不打补丁**：拒绝任何在 `ValidationMiddleware` 里加 `if-else` 的 PR。
2.  **重画接口**：
    *   立即将 `phase_executor` 切换至 MVP-3 定义的新 Middleware 架构。
    *   废弃 `schema is None` 路径，强制所有业务 Skill 补充 Schema 定义。
3.  **编译器升级**：将上述“Rust 式”规则写入 `scripts/compile_all.py`，作为 CI 阻断标准。

---

## 6. 总结
我们架构的健壮性不应来源于 LLM 的配合，而应来源于框架的“冷酷无情”。只有像 Rust 编译器那样在编译阶段“得罪”开发者，才能换来在运行时的“绝对安全”。
