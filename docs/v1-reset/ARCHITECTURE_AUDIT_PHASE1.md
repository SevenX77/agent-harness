---
title: v1-reset 架构溯源报告：从 e2e 失败看框架契约与健壮性设计盲点
作者: a2 (gemini-3.x, 跑在 Gemini CLI yolo 模式)
派任务主控: 主控 Claude (claude-opus-4-7 1M ctx)
派任务 brief: /tmp/a2-architecture-tracing-full-brief.md
ccb job_id: job_fbbfb12616e1
日期: 2026-04-29
类型: agent 架构溯源审计 (Architecture Tracing Audit)
范围: v1-reset Phase 1 = 5decd0a baseline → HEAD 共 49 commits
区别声明:
  - 本文件 a2 (gemini) **架构视角** — 接口契约 + 设计文件溯源 + 设计缺陷 vs 实现缺陷判断
  - MASTER_REVIEW_PHASE1.md 主控 Claude **PM 视角** — 大厂对标 + 工程性能评分
  - RETROSPECTIVE_PHASE1.md a3 (claude) **项目复盘视角** — 时间轴 + 协作模式
---

# v1-reset 架构溯源报告：从 e2e 失败看框架契约与健壮性设计盲点

## 第 1 节: 现状架构层面诊断

通过对 e2e 错误链、`text-segmentation` SKILL 及框架代码的审计，当前的失败并非孤立的逻辑错误，而是“接口契约演进中断”与“LLM 格式容错缺失”叠加导致的架构性断层。

### 1.1 ValidationMiddleware `schema is None` 路径的设计意图溯源

在 Baseline（v1 阶段，commit `5decd0a`），`ValidationMiddleware` 包含以下逻辑：
```python
if schema is None:
    business_errors = self._run_business_validator(self.ctx)
```
**设计意图**：这是一种“黑盒透明转发”策略。当 SKILL 未定义静态 `output_schema` 时，框架认为业务逻辑完全自定义。框架放弃介入，直接将代表整个阶段上下文的字典 `self.ctx` 抛给 `business_validator`。
**契约假设**：框架假设“无 Schema”的校验器拥有全量上下文读写权，自行从中提取数据分析。

### 1.2 Validator 接口契约：基于副作用而非数据流

审计 `text-segmentation` 的校验器 `validate_segmentation_structure` 发现其签名如下：
```python
def validate_segmentation_structure(segments: list[dict]) -> tuple[bool, list[str]]:
```
校验器明确期望接收解析后的段落列表 `list[dict]`，而非包含整个状态的 `ctx`。
**为什么 Baseline 能跑通？**
Baseline 能够跑通，并不是因为接口契约匹配，而是因为 **副作用的时序巧合**。在 Baseline 中，LLM 在调用 `finish_task` 之前，先调用了 `store_segments` 工具，该工具将数据写入了 `context['segments']`。旧的 Validator 在实际执行中，如果依靠某种方式获取到了正确数据（或者之前的实现不同），就能通过。目前的接口要求 `list[dict]`，如果直接把 `ctx` (字典) 传给它，遍历字典拿到的是 `str`，进而调用 `.get()` 必然崩溃。这说明 Baseline 的实现依赖于隐式的全局状态（副作用），而不是清晰的数据流。
**结论**：这是典型的“基于副作用的契约”设计缺陷，极度脆弱。

### 1.3 新旧 Middleware 的职责重叠与“双系统并行”

在 v1-reset MVP-3 中，设计了全新的 `CognitiveFlowMiddleware`，负责拦截 `finish_task`、执行 `SchemaEngine` 校验和 `IOManager` 的搬运。
**现状盲点**：`phase_executor.py` 却依然硬编码调用 legacy `ValidationMiddleware`。
**后果**：新架构（强类型、无副作用）已就绪，但核心执行引擎仍在用旧架构。这导致了“双系统并行”，a3 试图在 legacy 代码里打补丁，但这只是在废弃的系统上徒劳地缝补，完全绕开了新架构的设计。

### 1.4 Bridge JSON Parse Retry 死循环的根因

错误日志显示 `GraphRecursionError`，源于 `callback_bridge.py` 与 `ValidationMiddleware` 对 LLM 输出容错的不一致。
1. LLM 输出了带单引号的 Python 字典字面量。
2. `callback_bridge.py` 中的 `on_tool_start` 尝试 `json.loads` 失败，退化为包裹成字符串 `{"input": raw_str}` 传给下游。
3. `ValidationMiddleware._args_dict` 再次尝试 `json.loads`（因为期望 dict），失败后触发 `_json_parse_retry`。
4. `_json_parse_retry` 返回 `Command(goto="model")`，要求 LLM 重试。
5. LLM 不具备自修正单引号到双引号的能力，再次输出同样的错误格式，触发 30 次重试熔断。
**结论**：这是严重的“健壮性盲点”，设计上未定义“LLM 输出非标 JSON 时，在框架的哪一层负责清洗或熔断”。

---

## 第 2 节: 设计文件回溯（遗漏的 case 清单）

回溯 v1-reset 的 Specs，我们发现在 MVP 演进中存在明显的场景遗漏。

### MVP-1 design.md (状态拆分与 finish_task 路由)
- **考虑了**：将 `_finish_task_result` 隔离到 `FrameworkState`，并设计了 `route_finish_task`。
- **未考虑**：没有显式梳理和定义 `schema is None` 这一遗留分支的去留。设计文件默认了所有新 SKILL 都是基于 Schema 的，忽略了存量无 Schema 技能（如 `text-segmentation`）的迁移路径。
- **未考虑**：没有声明业务 Validator 的强类型接口契约。

### MVP-2 design.md (SchemaEngine 与 IOManager)
- **考虑了**：将 Markdown 解析和 Pydantic 强类型校验封装。
- **未考虑**：并未在设计层面声明 `ValidationMiddleware` 如何与 `SchemaEngine` 桥接，特别是当 LLM 连基本的 Markdown 外壳或 JSON 格式都拼错时的健壮性策略。

### MVP-3 design.md (新 Loader 与 Middleware)
- **考虑了**：设计了全新的四大核心 Middleware（包括接管 `finish_task` 的 `CognitiveFlowMiddleware`）。
- **未考虑**：没有明确声明从 Legacy `ValidationMiddleware` 到新 Middleware 的**过渡期对接协议**。
- **遗漏 Case**：设计文件未指明 `phase_executor.py` 应该何时切入新 Middleware。这直接导致了实现期的“双系统并行”。

### MVP-4 design.md (Executor 重画)
- **考虑了**：废弃 `phase_executor.py`，拆分为 `LLMPhaseNode` 等多态节点；重画了 `finish_task` 数据通道。
- **未考虑（之前修订的盲区）**：未声明“LLM tool format 健壮性” Invariant。即使图重画了，如果 LLM 持续输出单引号 Dict，Parse Retry 死循环依然存在。

---

## 第 3 节: 设计缺陷 vs 实现缺陷判断

按照 `architecture-discipline.md` 的定义，明确界定缺陷性质：

### 1. 设计缺陷 (Design Defects)
- **Validator 接口契约错配**：Baseline 时代 `schema is None` 传 `ctx`，而实际 Validator 期望 `list[dict]`。这是最初未明确接口签名导致的设计缺陷。
- **框架健壮性盲点 (Bridge JSON Parse 死循环)**：整个框架设计时，未对“LLM 输出包含语法错误的 JSON/Markdown 时，何处进行容忍/清洗/熔断”做出架构层面的契约规定。这是跨越 Baseline 和 v1-reset 的严重设计盲点。

### 2. 过渡期架构断层 (Architectural Disconnect)
- **Middleware 双系统并行**：MVP-3 新 Middleware 已就绪，但 `phase_executor.py` 仍用旧版。这是 v1-reset 演进路线规划遗漏导致的实现断层。

### 3. 实现缺陷 (Implementation Defects)
- a3 的修复尝试（方向 A/B/C）：仅仅是在 Legacy 代码中打 `if-else` 的补丁，未能触及接口重画的本质。对设计缺陷使用了修补实现的错误方式。

---

## 第 4 节: 重画接口方案 (真重画方向)

针对上述设计缺陷，提出以下**非补丁式**的重画方向：

### 方向 A：强制 Schema 契约（废弃 `schema is None` 路径）
- **描述**：彻底从框架中移除 `schema is None` 的 Fallback 分支。明确规定：任何需要业务校验的 SKILL Phase，必须在 `SKILL.md` 中显式声明 `output_schema`（静态或动态）。框架在 Compile 阶段若发现无 Schema 但有 Validator，直接报错。
- **工作量**：4h（修改 Loader 逻辑，清理 Legacy Middleware，为相关 SKILL 补充 Schema）。
- **风险点**：需修改存量 SKILL 定义。
- **阻塞 Phase 1 ship 吗**：阻塞。这是核心数据流契约的改变。
- **与 MVP-4 衔接**：高度契合，为 MVP-4 的实施铺平道路。

### 方向 B：立即完成 Middleware 换轨（消除断层）
- **描述**：不等 MVP-4 的完整排期，立即修改 `phase_executor.py`，移除旧 `ValidationMiddleware`，接入已在 MVP-3 就绪的 `ProtocolValidationMiddleware` 和 `CognitiveFlowMiddleware`。
- **工作量**：8h。
- **风险点**：旧的 `while True` 循环与新 Middleware 的 Command 控制流可能存在一定集成风险。
- **阻塞 Phase 1 ship 吗**：阻塞。不换轨的话，新架构形同虚设。

### 方向 C：确立 LLM Tool Payload 健壮性契约
- **描述**：在框架层定义清洗契约。LLM 输出到达 Middleware 之前，必须经过统一的清洗层（如替换单引号）。若仍无法恢复，不再允许无意义的 `goto="model"` 无限重试，而是包装为 `LLMFormatError` 交由 `ExecutionControlMiddleware` 截断或回退。
- **工作量**：4h。
- **风险点**：清洗策略可能误伤正常的业务文本。
- **阻塞 Phase 1 ship 吗**：不阻塞，可作为 MVP-4 或后续增强，但需在当前 Release Notes 声明。

**推荐方案**：**方向 A + 方向 B**，并在后续推进 **方向 C**。

---

## 第 5 节: 对 Phase 1 ship 的影响

### 结论：当前状态 **坚决不能 Ship**。

**阻塞 Ship 的 Hazard**：
1. 核心用例 e2e 测试失败，暴露底层数据流向断裂。
2. 架构处于“双系统并行”状态，新代码未真正运转，旧代码补丁越打越乱。

**Release Notes (Known Limitations) 诚实写法**：
若必须提及：
- "框架对未声明 Schema 的 SKILL 校验器支持存在接口签名错配，无 Schema 模式暂不可用。"
- "面对 LLM 持续输出单引号等非标 JSON 时，框架可能陷入 Parse Retry 死循环熔断。"

**推荐回退计划**：
不应直接 Ship 这 48 个 commits。必须将 **方向 A（强制 Schema 契约）** 和 **方向 B（完成 Middleware 换轨）** 纳入 Phase 1 的最终重构中。使用 `refactor(...)` 明确声明接口契约的变更。

---

## 第 6 节: 对主控 / 用户的总结

**对用户的诚实评估**：
“我们架构不是已经很健壮了吗？” —— **实际上，当前的架构处于危险的过渡期，并不健壮。**
Baseline 时代的运行通过依赖隐式状态和副作用。v1-reset 确实设计了健壮的新架构，但我们在实施时妥协了——旧的执行引擎（`phase_executor`）还在运行废弃的逻辑，导致新系统处于“空转”状态。此外，系统对 LLM 的格式异常缺乏底层的防御纵深。

**推荐下一步 Action**：
**拒绝 a3 的 v3 补丁。开启 `refactor(cognitive)`：实施方向 A（废弃 `schema is None` 路径，强制所有 SKILL 配置 Schema）并在 Compile 时阻断。随后推动 `phase_executor` 切换至 MVP-3 就绪的新 Middleware，彻底拔除旧契约。**