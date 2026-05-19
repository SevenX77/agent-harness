# agent-harness v1 reset — 总体方针 (Direction Doc)

**Owner:** SevenX (主控 Claude / Gemini / Codex)
**Date:** 2026-04-28
**Status:** Approved direction; per-MVP specs to follow under `.kiro/specs/v1-reset-mvp-N-*/`

---

## 1. 触发原因

2026-04-28 全库审计：
- **Codex 工程层**: 6.1 / 10
- **Gemini 架构层**: 7 / 10，B 级
- 16 个维度（codex 8 + gemini 8）**没有任何一项真正 clear** — 即便 8 / 9 分维度也都有 must-fix（IOManager OCP / GraphRecursionError 兜底 / 主干代码留 TODO）

按当前架构继续修补会出现"补丁堆积"反模式（参见 `~/.claude/rules/architecture-discipline.md`）。需要 ground-up reset。

## 2. v1 完成定义（不可妥协）

**两条同时满足：**

1. **16 个维度全部 ≥ 8 / 10**
2. **零 must-fix 残留** — 8 分维度里现存 must-fix（IOManager OCP / GraphRecursionError 兜底等）也必须解掉

如果某个维度跟保留某个 feature 本质冲突（例：保留无类型字典透传 + 严苛类型安全 = 数学不可能），则**砍 feature**，不降标准。

## 3. 总体方针

**接受 Gemini v1 reset plan**（`/tmp/gemini-v1-reset-reply.txt`）的全部 10 项接口重画 + 5 项功能砍除 + 4 阶段路径 + 工程门禁基线。

| 类别 | 项数 | 说明 |
|---|---|---|
| 必须重画的接口 (Part A) | 10 | A1 WorkflowState / A2 loader / A3 phase_executor / A4 finish_task / A5 SchemaEngine / A6 异常 / A7 IOManager / A8 ContextBridge / A9 output_schema / A10 harness.run |
| 必须砍的功能 (Part B) | 5 | B1 parallel_delegate+subgraph / B2 multimodal tools / B3 Summarization+LoopDetection / B4 vendored deerflow+双 pyproject / B5 dead code |
| 工程门禁 (Part E) | 5 | mypy strict / ruff / coverage 核心 ≥95% 整体 ≥85% / 单测无网络 / pre-commit |

**估算工作量**：约 50-60% 核心代码变动；2-3 周（按 1 名工程师 + 多 agent 并行）。

## 4. MVP 切分（6 个 MVP，每个 ~2-4 天）

按"自然依赖边界 + 每个 MVP 完成时 4 个核心 SKILL e2e 必须仍能跑"双重约束切。

### MVP-0 — 基石清创
- **范围**: B1 / B2 / B3 / B4 / B5 全部砍除 + A6 异常体系 / A8 ContextBridge 单一来源
- **完成标志**: pyproject 单一 / dead code 清零 / multimodal & parallel & subgraph 删除 / `except Exception: pass` 清零；4 SKILL pytest 全绿
- **特点**: 纯减法 + 收尾，地基扫干净；为后续 MVP 腾干净空间

### MVP-1 — 状态拆解
- **范围**: A1 WorkflowState → `business_data: dict[str, Any]` + `framework_state: FrameworkState`(Pydantic)
- **完成标志**: 所有 `_finish_task_result` / `_retry_feedback` / `_working_memory` 等魔法下划线变量从 user dict 迁出；middleware 用 `Command(update={...})` 返回更新；mypy strict 在 state 模块通过
- **特点**: **基础**，影响所有下游；卡住所有后续 MVP

### MVP-2 — 独立基础设施
- **范围**: A5 SchemaEngine + A7 IOManager StorageAdapter
- **完成标志**: strict_v2 / md_to_json / middlewares 三处校验逻辑收编进 `SchemaEngine`；`IOManager.save_outputs` 改为 `StorageAdapter` 接口；新增 target 类型不需改框架核心
- **特点**: A5 / A7 彼此独立，可并行实现（codex + a3 各拿一个）

### MVP-3 — 模块边界对齐
- **范围**: A2 loader.py 拆解 + A9 output_schema hack 剥离
- **完成标志**: `loader.py` 拆为 `Parser` / `ManifestValidator` / `ModuleSandbox` / `PhaseBuilder`；`_resolve_output_schema_path` 改用 PEP 451 importlib namespace，`sys.modules` 改写消失；幽灵模块名调试问题消失
- **特点**: A9 依赖 A2 的 `ModuleSandbox`，串行做

### MVP-4 — 执行核心拆分
- **范围**: A3 phase_executor 拆 + A4 finish_task 控制流原语化
- **完成标志**: `execute_llm_phase` 532 行拆为 `PromptRenderer` / `AgentLoopDriver` / `LifecycleEmitter` / `StateTransformer`；`finish_task` 不再是 LangChain Tool，改为 LangGraph Node/Edge 路由 或 LLM `response_format`
- **特点**: 这两个绑死，一起改；MVP-1 (state 拆) 是前置

### MVP-5 — 装配 + 工程门禁
- **范围**: A10 harness.run 拆解 + Part E 全部门禁落地 + 4 SKILL CI 全绿
- **完成标志**: `harness.run()` 拆为 `.compile()` / `.prepare_state()` / `.invoke_graph()` / `.persist_outputs()`；mypy strict + ruff + coverage 核心 ≥95% 整体 ≥85% + pre-commit + 单测无网络全部 CI 锁死；4 SKILL e2e + pytest 全绿
- **特点**: 收口，v1 ship gate

### 不变量（每个 MVP 的红线）

每个 MVP 完成时必须仍然满足：

1. **4 个核心 SKILL e2e 能跑通**（text-segmentation / event-extraction / batch-analysis / global-synthesis）
2. **pytest 不退步**（不允许任何已绿测试变红）
3. **新代码 mypy strict 通过**（旧代码逐 MVP 收）
4. **新代码 ruff 通过 + coverage ≥ 85%**

**MVP-1 / MVP-4 高破坏期间的额外约束**（Gemini sanity check 提醒）：
- 这两个 MVP 改动的是 v1 框架核心结构（state 重画 / finish_task 重画），中间态可能数小时 e2e 跑不通
- 必须在 spec 中追加 `migration-guide.md` 章节：设计**过渡适配器**让"半新半旧"底座仍能跑通 4 SKILL e2e
- 拆分子任务时**先实施过渡适配器、再实施真改造**，确保任一子任务完成时 e2e 可跑

任一不变量破坏 = MVP 不能 ship，回滚到上一个 MVP head 重做。

## 5. 角色 + 协作 pipeline

### 角色

| Agent | 主职 | 任务类型 |
|---|---|---|
| **主控 Claude (PM)** | 项目经理 + 监工 | 切 MVP / 写 spec / dispatch / verify;**不写代码不亲自做领域分析** |
| **a1 codex (executor)** | 主力编码 | 重型独立块（loader / executor 拆解、大重构） |
| **a2 gemini (analyst + reviewer)** | 设计审 + 偏离审 + 战术决策辩论 | 每 MVP design 审 / 实施完偏离审 / Claude vs Gemini 分歧时辩论收敛对手;**不写代码** |
| **a3 claude (executor 副)** | 副编码（短链独立块）+ 审查 | 短链 / 独立 / 增量任务（IOManager StorageAdapter / dead code 删除等）;**a3 编码必须 codex 审一遍** |

### 每个 MVP 的 spec-driven pipeline

```
1. PM 写 .kiro/specs/v1-reset-mvp-N-<topic>/ 4 doc：
   - requirements.md (EARS 风格 acceptance criteria)
   - research.md (设计意图 + 选型 + 参考)
   - design.md (具体接口形态 + 数据结构 + 生命周期)
   - tasks.md (按 a1 / a3 分派的子任务)

2. PM 把 design.md 派给 a2 Gemini 审（30-60 min）
   - Gemini 给"是否对齐 reset plan + 是否有遗漏 + 是否引入新缺陷"评审
   - 分歧时 PM vs Gemini 辩论 3 轮，收敛后再进入下一步

3. PM 派 tasks.md 子任务给 a1 codex / a3 claude
   - codex 拿重型独立块（heavy refactor）
   - a3 拿短链独立块（small surface area）
   - 两线交叉验证 (a3 编码 → codex 审 → 双盲对齐)

4. coding 阶段 PM 监督：
   - 每 60-120s capture pane 验证 agent 真在工作
   - 每 30 min 拉 git status fork verify filesystem 实证
   - codex pane 每 ≥ 15 个 commit 做一次 /clear 防 context 撑爆
   - 越界（改了不该改的文件 / 派任务给其他 agent）立即 escape + 回滚

5. coding 完成后 PM 触发：
   - 单测：codex / a3 自验
   - smoke 测：4 SKILL e2e（PM 跑或派 a3 跑）
   - 偏离审：把 git diff 派给 a2 Gemini 审 "是否按 design.md 实现 / 是否引入 must-fix"
   - 偏离审通过 → MVP 收尾 commit + push

6. MVP 之间：
   - PM 把 MVP 完成结论 + 学习写入 memory
   - 给 codex / gemini 做一次 /clear 或 /compact 释放 context
   - 关闭当前 MVP scope，开下一个 MVP scope
```

### scope 与 context 管理纪律

- **每个 MVP 一个独立 orchestrator scope**（`v1-reset-mvp-N-<topic>`），完成立刻 `stop-task-scope`
- **不在 daily ccb 跑 MVP 编码**（codex pytest 全跑会撑爆 daily 的 systemd quota）
- **codex / gemini 上下文阶段性清理**：每 MVP 之间至少做一次 `/clear`（codex）或 `/compact`（gemini）；2 个 MVP 之间累计 token 用量 > 50% 强制清
- **派 ccb agent = 主控任务开始**（按 ccb-collaboration 6.0bis），in-loop 接力到产出 filesystem 实证为止
- **任何派任务 prompt 必须含边界**：只读 / 不派任务 / 不 commit / 不创 PR / 不跑非必要 git

## 6. 演进路线

### v2 — 能力回血期

在 v1 基底强类型稳固后引入：
- B1 重做：`parallel_delegate` / `subgraph` 用 LangGraph `Send` API 重新设计
- B3 重做：建立标准 middleware 插件协议（Summarization / LoopDetection 跑稳后回归）
- 引入 `dry_run()` / `predict()` 工具层（之前 user 提的 predict feature 在 v2 重新做）

### v3 — 生态与协作期

- 动态 Schema 进化支持
- 跨 Agent 复杂协作 / 对话流
- Studio 可视化看板
- Async streaming 深度支持

### 永远不回归

- B5 dead code (`_phase_string` / `_phase_int` / 冗余 parser) — 永久抛弃

## 7. v1 工程门禁基线（不可妥协，CI 锁死）

```yaml
mypy:
  strict: true
  禁止: Any
  强制: def 全部带类型签名
  禁止: 第三方库的隐式 Any 推断回退（`disallow_any_generics`、`warn_return_any` 强开）
  策略: 上游 stubs 不全时，要么自写 `stubs/` 模块，要么 inline `# type: ignore[attr-defined]` + 注释；禁止 file-level / module-level ignore

ruff:
  rules: [E, F, B, I, UP, SIM, N]
  formatter: ruff format
  pre-commit hook: blocking

coverage:
  core (core/, io/, cognitive/): >= 95%
  total: >= 85%

unit_tests:
  network_isolation: 严禁向外发真实 LLM 请求

pre-commit:
  hooks: [check-yaml, ruff format, mypy, ruff check]

ci_pipeline:
  # pre-commit 只约束本地，CI 是合入硬门禁（不能仅靠本地）
  platform: GitHub Actions
  triggers: [pull_request, push to main]
  jobs:
    - name: lint
      run: ruff check + ruff format --check
    - name: type
      run: mypy --strict src/
    - name: test
      run: pytest tests/ --cov=src/core/graph_agent --cov-report=xml
    - name: coverage_gate
      run: 核心 ≥ 95% / 总体 ≥ 85% (硬卡，未达不允许 merge)

docstring:
  scope: 核心公开 API (harness.run, Phase, WorkflowState, IOManager, SchemaEngine 等所有暴露给 SKILL 作者的类/函数)
  style: Google 或 NumPy 风格
  enforcement: ruff D100/D101/D102/D103 + Sphinx build 不报 missing
  range: v1 必达；非公开 internal 可豁免
```

## 8. 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| story-deconstruction 依赖 parallel_delegate (被砍) | 第 5 SKILL v1 期间不可用 | 接受；v2 用 LangGraph Send API 重做 |
| LangGraph API 变化破坏 finish_task 重画 | A4 重画方案失效 | A4 设计前先去 LangGraph 上游确认稳定 API（`response_format` / `Command`） |
| codex 长任务挂 / 上下文爆 | MVP 进度受阻 | 每 MVP 一个 scope；每 MVP 之间强制 `/clear`；派任务用文件投递 + 边界声明 |
| a3 编码质量与 codex 不一致 | 交叉验证不收敛 | 严格按 ccb-collaboration: a3 编码必须 codex 审；3 轮 review 不过升级 PM |
| Gemini 在 design 审里 hallucinate | 偏离审失效 | 每次 design 审给完整文件路径 + 行号 + 具体接口形态；不要让 Gemini 凭印象审 |
| daily ccb scope 同时跑 2+ MVP 撑爆 | 整库锁死 | 严格 1 MVP 1 scope；MVP 之间 `stop-task-scope` |
| **上游 LangGraph / LangChain 类型 stubs 不全** | mypy strict 在 import 链上深层报错 | 三道防御：(1) 在 `stubs/` 自写 LangGraph subset stubs；(2) 必要处 inline `# type: ignore[attr-defined]` + 单行注释（禁止 file-level）；(3) `mypy.overrides` 块只在确认上游不可救时使用 |
| **过度激进清理 + 向前兼容崩塌** | MVP-0 删 dead code / 砍 vendored deerflow 时打死 4 SKILL 之外的隐藏用例 | (1) MVP-0 删除前 snapshot diff（4 SKILL.md 解析结果 + pytest 输出）+ MVP-0 完成后比对一致；(2) 仓库里所有 SKILL.md（不只 4 个核心）每个都跑 `compile_skill()` 一遍，新 / 老结果对比；(3) 任何 SKILL.md 配置项被砍前必须 grep 确认无引用 |
| **MVP-1 / MVP-4 是 e2e 高破坏 MVP** | state 重画 / finish_task 重画期间几个小时 e2e 跑不通 | 在 MVP-1 / MVP-4 spec 中**必须**追加 `migration-guide.md` 章节，设计过渡适配器（让半新半旧底座能跑），保住"每时每刻都能跑"铁律 |

## 9. 当前状态 / next step

- 顶层 direction doc 落盘 (本文件)
- 下一步：写 MVP-0 spec (`.kiro/specs/v1-reset-mvp-0-baseline-cleanup/`)
- MVP-0 spec 写完后派 Gemini 审 design + 派 codex / a3 编码

---

## Appendix A — 来源资料索引

| 文件 | 说明 |
|---|---|
| `/tmp/codex-audit-pane-full.txt` | 2026-04-28 codex 工程层全库审计原文 |
| `/tmp/gemini-audit-full.txt` | 2026-04-28 Gemini 架构层全库审计原文 |
| `/tmp/gemini-v1-reset-reply.txt` | 2026-04-28 Gemini v1 reset plan 原文（10 重画 + 5 砍 + 4 阶段 + 门禁） |
| `~/.claude/rules/architecture-discipline.md` | 架构纪律规则（设计缺陷 vs 实现缺陷判断） |
| `~/.claude/rules/ccb-collaboration.md` | ccb 协作规则（角色铁律 + scope 纪律） |
| `docs/compiler/strict-compile-rules-v2.md` | strict_v2 设计文档（被 A5 SchemaEngine 收编） |
| `docs/compiler/skill-health-2026-04-28.md` | 4 SKILL 迁移到 v3 后健康报告 |

## Appendix B — 16 维度当前评分 + v1 目标

每个 MVP 完成时必须验证：受影响维度评分 ≥ 8 + 该维度 must-fix 项全部清零。

### Codex 工程层 8 维度（当前 6.1 / 10）

| # | 维度 | 当前 | 目标 | 主要 must-fix（v1 必清）| 哪个 MVP 解 |
|---|---|---|---|---|---|
| E1 | 文件 / 模块组织 | 4.5 | ≥ 8 | God Module 5 个（harness 1154 / loader 1013 / middlewares 805 / phase_executor 777 / md_to_json 722）必须拆 | MVP-3 / MVP-4 / MVP-5 |
| E2 | 类型安全 | 5 | ≥ 8 | mypy strict 门禁 / 消除 Any / state 类型化 / `assert` 改异常 | MVP-1 / MVP-5 |
| E3 | 错误处理 | 5 | ≥ 8 | `except Exception: pass` 清零 / tool 异常非字符串化 / deepcopy 不浅拷降级 / checkpointer 不静默降级 | MVP-0 / MVP-2 / MVP-4 |
| E4 | 日志 | 5.5 | ≥ 8 | side-effect before/after log / 结构化 key=value / run_id+thread_id 关联 | MVP-2 / MVP-5 |
| E5 | 测试 | 6.5 | ≥ 8 | run_skill 公共入口真实测试 / pytest 内 LLM mock / parallel/subgraph 集成测试（B 项砍后 obsolete） | MVP-5 |
| E6 | 接口契约一致性 | 5.5 | ≥ 8 | ContextBridge 单一来源 / parser 单一实现 / 取消魔法下划线变量 | MVP-0 / MVP-1 / MVP-3 |
| E7 | 代码风格 | 4.5 | ≥ 8 | 函数长度 ≤ 40 行 / 参数 ≤ 3 / 嵌套深度 ≤ 4 | MVP-3 / MVP-4 / MVP-5 |
| E8 | 依赖与构建 | 5.5 | ≥ 8 | 单 pyproject / mypy+ruff+pre-commit+coverage 门禁 / 依赖一致 | MVP-0 / MVP-5 |

### Gemini 架构层 8 维度（当前 7 / 10，B 级）

| # | 维度 | 当前 | 目标 | 主要 must-fix（v1 必清）| 哪个 MVP 解 |
|---|---|---|---|---|---|
| A1 | 整体架构合理性 | 6 | ≥ 8 | loader 上帝模块拆 / 校验逻辑收编 / `_resolve_output_schema_path` hack 剥离 | MVP-2 / MVP-3 |
| A2 | 接口契约设计 | 5 | ≥ 8 | 魔法下划线变量根除 / `output_example` vs `output_schema` 双契约统一 | MVP-1 / MVP-2 |
| A3 | 抽象层级与命名 | 7 | ≥ 8 | finish_task 控制流原语化 / 取消幽灵模块名 | MVP-3 / MVP-4 |
| A4 | 数据流与状态管理 | 5 | ≥ 8 | WorkflowState 强类型化 / 数据流断层运行时 transformer 保护 | MVP-1 / MVP-2 |
| A5 | 可扩展性 | 8 | ≥ 8 | IOManager target 硬编码 → StorageAdapter 接口 | MVP-2 |
| A6 | 错误传播 / 弹性 | 8 | ≥ 8 | GraphRecursionError 兜底 → 优雅 Result 对象 | MVP-4 |
| A7 | 测试架构 | 7 | ≥ 8 | E2E 跟 pytest 体系融合 / LLM mock 层 | MVP-5 |
| A8 | 工程文化与可维护性 | 9 | ≥ 8 ✅ | 主干代码 TODO 历史包袱清理 | MVP-0 / 各 MVP 收尾 |

**最低维度**：当前最低 4.5（E1 / E7），距离 8 差 3.5；最高 9（A8）已达标。

**整体差距**：13 / 16 维度有结构性 must-fix；纯打补丁不可达。
