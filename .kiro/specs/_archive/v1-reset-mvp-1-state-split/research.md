# MVP-1 Research — A1 WorkflowState 拆分决策

## 来源资料

- v1-reset direction doc: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` §A1
- MVP-0 CHANGELOG: `docs/v1-reset/CHANGELOG_MVP0.md`
- Gemini independent design (2026-04-29): job_543e6152ff10 reply (整合到 design.md)
- 16-dim audit A1 维度
- 当前 state.py: `src/core/graph_agent/core/state.py:15` (TypedDict 5 字段)

## Baseline 数据

见 `docs/v1-reset/mvp-1-baseline-snapshot.md`（grep 出的 17 个 `_underscore` 框架字段 + 26 个 `state["context"]` 站点 + 47 个 `state[]` 总站点 + 5 受影响测试文件）。

## 决策记录

### D1 — 拆分形态: 内部 Pydantic + 外壳 TypedDict

**选项**:
- A. 全 TypedDict（兼容 LangGraph，但弱校验）
- B. 全 Pydantic BaseModel（强校验，但需自定义 reducer + LangGraph 兼容性额外功夫）
- C. **TypedDict 外壳 + Pydantic 子结构**（推荐，Gemini 给出）

**决策: C**

**理由**:
- LangGraph `StateGraph` 用 TypedDict 是标准用法（reducer + add_messages 等都假设 TypedDict 顶层）
- Pydantic 子结构 (`BusinessData` / `FrameworkState`) 提供强校验 + 序列化 + immutable update
- 业务字段需 `extra="allow"`（用户 SKILL 的 schema 字段是动态的），框架字段需 `extra="forbid"`（防业务污染）
- 序列化用 Pydantic v2 `model_dump(mode="json")` 天然兼容 LangGraph checkpointer

### D2 — 不提供旧 checkpoint migration

**选项**:
- A. 写 migration script 把旧 checkpoint 数据迁到新 schema
- B. **放弃旧 checkpoint 兼容**，框架版本号升级，旧 run 不可恢复

**决策: B**

**理由**:
- MVP-1 是 A 维度破坏性架构调整，按 v1-reset 总方向"接口重画"
- 旧 checkpoint 数据混 `_underscore` 字段在 context dict 里，正确 migrate 需要识别 17 个不同字段+各自的归宿，复杂度高且易错
- v1-reset 期间用户已接受"不保留旧运行状态"的约定（MVP-0 CHANGELOG L7）
- 简化 = 框架更可维护

### D3 — Reducer 行为按字段分

**选项**:
- A. 全 replace（每次状态合并完整覆盖）
- B. 全 update（字段级累积）
- C. **按字段分**（Gemini 推荐）

**决策: C**

**理由**:
- `messages`: LangGraph 标准 `add_messages` reducer（追加，不替换）
- `data` (BusinessData): replace 模式 — 业务数据每次 phase 交付完整快照，避免脏累积
- `flow` (FrameworkState): 字段级 — `metrics`/`retry_counts` 累积，`finish_task_result`/`hop_count` 覆盖

实施细节: `Annotated[T, reducer_fn]` 在 TypedDict 字段标注，或自定义 reducer dispatcher。

### D4 — finish_task 改造的最小切入点 = phase_executor.py + 新 StateManager 辅助类

**选项**:
- A. 直接在 finish.py 改写返回路径
- B. **在 phase_executor.py 新加 StateManager 辅助类**做 LLM-output → BusinessData / Interceptor → FrameworkState 的路由（Gemini 推荐）
- C. 等 MVP-4 完整重画 finish_task 数据通道

**决策: B**

**理由**:
- A 改 finish.py 内部，但调用方 phase_executor 仍然用 dict 接收，最终还是要在 phase_executor 处理路由 → 不如直接在 phase_executor 做
- C 把 finish_task 完整重画推到 MVP-4，MVP-1 期间需要一个过渡形态——StateManager 辅助类正好担任过渡责任，MVP-4 重画时可以替换或吸收
- StateManager 是单文件 + 短链接口，复杂度可控

### D5 — ContextBridge 演化为 BusinessData 工厂类

**当前**: `core/manifest.py` 的 ContextBridge (Pydantic 版，T10 单一来源化) 解析 SKILL.md 的 context 字段定义。

**MVP-1 后**: ContextBridge 输入 SKILL.md 字段定义 → 输出 `BusinessData` 的字段 schema（喂给 `BusinessData(extra="allow")` 的动态字段定义）。**ContextBridge 不再触碰框架元数据**（MVP-0 已部分处理，MVP-1 彻底完成）。

### D6 — 隐藏耦合排查必跑

`grep -rn "\*\*state" src/core/graph_agent/ --include="*.py"` 必跑，找出所有解包式状态读取的位置，按拆分后改造或删除。

### D7 — 子任务并行度优化

Gemini 出 8 子任务（T1-T8），最长依赖链 = T1→T2→T4→T5→T7→T8 = 1+2+3+2+4+2 = 14h（实际更短，因为 T3+T4 / T5+T6 可并行）。

**主控调度**:
- a1 codex 主线: T1 → T2 → T4 → T6（核心枢纽 + 工具改造）
- a3 claude 副线: 等 T2 done 后接 T3，T4 done 后接 T5，T5+T6 done 后 T7 → T8（runner 调整 + middleware + 测试 + smoke）
- a1 期间空闲做 cumulative review；MVP-1 done 后 a1 整体 review
- 调度细节见 tasks.md

### D8 — 受影响测试 5 文件 ≠ 实际改动量

baseline grep 出 5 个 tests 文件含 `WorkflowState` / `state[`。但**子任务 T7 估时 4h 反映的是更广泛的影响**：所有 mock state 用 `{"context": {...}}` 形式的测试都要改成 `{"data": ..., "flow": ..., "messages": ...}`，预计 30-50 个测试需要 mock 更新。a3 应该用 grep + sed 批量处理共性 mock，剩余手工。

## 不在 MVP-1 处理的相关问题（明确 defer）

- `tool_wrapper.py:138` silent fallback (defer 到 MVP-4，跟 finish_task 完整重画绑定)
- mypy strict / ruff / coverage 全库收敛 (defer 到 MVP-5)
- e2e smoke 全章节断言 (defer 到 MVP-5)
- Phase Executor 整体重画 (defer 到 MVP-4)
