# Phase F4 — Studio Frontend 未接 API 集成 — Research (Round 1)

> 起草: 主控派的 fork sub-agent (Claude general-purpose)
> 日期: 2026-05-08
> 范围: 仅 R 调研, 不做 D 也不出 tasks。这两份文档分别由 a2 / a1 接力。

## 0. Scope 框定 + 4 router 真实分类

任务 brief 给定 5 个候选 router (audit / debug / compare / lint / copilot), 其中 copilot 已声明走 SDK 集成另派, 不在本任务范围。**剩余 4 个 router 经过实际代码读后, 真实状态分布跟 brief 假设的"已挂未接"差异显著**, 需要主控决策再切分:

| Router | brief 假设 | 实际状态 (filesystem 实证) | 处置建议 |
|---|---|---|---|
| `lint` | 未接 | **后端已实现 + 前端已接** (`App.tsx:322` POST `/skills/{id}/lint`, `useGoldenDiff.ts` 模式) | 不需主任务; 仅有"`phases_summary` 字段未渲染"小遗珠, 可独立小任务 |
| `compare` | 未接 | **后端已实现, 前端 50% 接** (GET `/diff` 已用, POST `/compare` 未用且语义重叠) | 决定保留 POST 还是删除冗余, 基本无新增工作 |
| `debug` | 未接 | **`include_in_schema=False` 隐藏内部 smoke endpoint** (`debug.py:7`), 不是产品级 feature | 跳过, 不是 frontend 集成对象 |
| `audit` | 未接 | **后端是 stub (501)** + service 层不存在 + 设计文档显式标注 MVP3 deferred (`studio-mvp1/design.md:100`, `studio-mvp1/requirements.md:105`) | **阻塞**: backend stub, frontend 无可接对象 |

**结论**: brief 的"5 个已挂未接 → 写 frontend"前提**不成立**。lint 已接, compare 大部已接, debug 不是产品 feature, audit 是 stub 没东西可接。详见 §6 阻塞问题。

## 1. Backend 现状 (handler 完整签名 + service 层 + 测试)

| Router | URL pattern | Method | Handler 状态 | Request model | Response model | Service 层 | 测试 | file:line |
|---|---|---|---|---|---|---|---|---|
| audit | `/api/skills/{skill_id}/runs/{run_id}/audit` | GET | **Stub** (`raise_not_implemented` → 501) | — | `AuditResult{drift_score: float, violations: list[str]}` | **不存在** (无 drift / plan_checklist 比对逻辑) | 仅 OpenAPI surface 注册测试 (`test_api.py:46`) | `routers/audit.py:14-20` |
| compare (POST) | `/api/skills/{skill_id}/runs/{run_id}/compare` | POST | **已实现** (调 `compare_run_to_golden` 不带 `against`) | — | `CompareResult` (与 `/diff` 同) | `services/golden_diff.py:68-110` (真实差分实现) | OpenAPI surface 注册 (`test_api.py:43`); 实际功能测试只覆盖 `/diff` (`test_api.py:330-382`) | `routers/compare.py:14-20` |
| compare (GET) | `/api/skills/{skill_id}/runs/{run_id}/diff` | GET | **已实现** (调 `compare_run_to_golden` 带可选 `against`) | query `against?: str` | `CompareResult` | 同上 | 已覆盖 (`test_api.py:330-382`) | `routers/compare.py:23-29` |
| lint | `/api/skills/{skill_id}/lint` | POST | **已实现** (调 `lint_skill` → `compile_skill`) | — | `LintResult{status, errors, phases_summary}` | `services/skills.py:98-111` (调 `graph_agent.compile_skill`) | 已覆盖 (`test_api.py:82-100`) + OpenAPI surface | `routers/lint.py:13-15` |
| debug | `/api/_debug/value-error` | GET | **smoke only** (raise `ValueError`), `include_in_schema=False`, 用于测试统一异常处理 | — | — | — | OpenAPI 验证它**不出现**在 schema (`test_api.py:52`) | `routers/debug.py:7-12` |

补充语义观察:

- `compare.py:14-20` 的 POST `/compare` 跟 `compare.py:23-29` 的 GET `/diff` 都直接调用同一个 service 函数 `compare_run_to_golden(skill_id, run_id, against=...)` (`services/golden_diff.py:68`)。POST 不接 body / 不接 query 参数 / 不能指定 `against`, 而 GET 接 `against`。语义上 POST 是 GET 的弱化版, 没有独立价值。`studio-mvp1/design.md:98` 当初预留 POST `/compare` 是基于"compare = mutation 副作用"的假设, 但实际实现里两者都是 read-only diff, **POST 在当前实现下是死路由**。
- `lint_result.phases_summary` 在 `passed` 状态下返回 `list[dict[str, Any]]` (`models/lint.py:17`), 但 frontend 既不渲染也不消费 (grep 全 `apps/studio/frontend/src/` 仅有 `types.ts:27` 类型定义)。这是已接 lint 后的小遗珠, 不是缺集成。
- audit handler 的 router prefix `/api/skills/{skill_id}/runs/{run_id}` (`routers/audit.py:11`) + path `/audit` 解析为 GET, 没 query / body。如果未来要做, 还要决定是 GET (idempotent 重新计算) 还是 POST (mutation 写持久化结果)。

## 2. Frontend 接入模式范例 (现有 hook / UI / state mgmt)

### 2.1 axios + interceptor 单例 (`api/client.ts`)

`apps/studio/frontend/src/api/client.ts:7-25`:
- 单例 `api = axios.create({ baseURL })`, 默认 `http://localhost:8787/api` (`client.ts:3`)
- request interceptor 统一注入 `X-Studio-User-ID: default` header (`client.ts:20-25`)
- 提供 `fetcher` (`client.ts:27-30`) 给 SWR 用

### 2.2 SWR-based read hook (`hooks/useSkills.ts`, `useTemplates.ts`, `useRunHistory.ts`)

`apps/studio/frontend/src/hooks/useRunHistory.ts:6-44` 是典型范例:
- `useSWR<T>(skillId ? '/skills/${skillId}/runs' : null, fetcher)` — `null` key 代表"还没选 skill, 暂不发请求" 模式
- 返回 `{ data, error, isLoading, mutate }` 解构后包成 hook 自有 API (`refresh`, `deleteRun`, `fetchRunDetail`)
- 突变方法用 `useCallback` 包裹后调 `api.delete/post`, 然后 `mutate(...)` 触发本地 + 服务端重新拉取

### 2.3 Imperative action hook (`hooks/useGoldenDiff.ts`)

`apps/studio/frontend/src/hooks/useGoldenDiff.ts:1-68` 是非 SWR 命令式 hook 的范例 (用于"按按钮才发请求, 不预拉取"):
- 自管 `state = { result, loading, error }` (`useGoldenDiff.ts:7-17`)
- `compare` 方法 setLoading → `api.get` → setState success/fail (`useGoldenDiff.ts:19-37`)
- 错误处理: try/catch + `errorMessage(error)` (`utils/errors.ts:61-67`) 提取 `ErrorResponse.message`
- 提供 `clear()` reset (`useGoldenDiff.ts:58-60`)
- `useCallback` 依赖 `[skillId, runId]`, 防止 re-render 失效

### 2.4 一次性 imperative call (App.tsx 内 inline)

非 reusable 一次调用的模式 (`App.tsx:315-329` `handleLint`):
- 直接 `await api.post<LintResult>(...)` inline 在 `useCallback` 内
- 用 `pushToast` 反馈 (`App.tsx:324, 327`); 用 `lintErrorsFromError` 提取 422 详情错误 (`utils/errors.ts:48-59`)
- 状态写到 `lintOverride` state (`App.tsx:99, 320`)

### 2.5 UI 风格

- **CSS 框架**: TailwindCSS 4.2 (`package.json:18`) + Lucide icons (`package.json:21`)
- **暗黑模式**: `dark:` 前缀 + `useTheme` hook (`hooks/useTheme.ts`)
- **主色**: sky-600/400 (按钮 primary), amber-500/400 (golden 操作), red-* (错误), slate-* (中性)
- **panel 样式**: `flex h-full flex-col bg-slate-50 dark:bg-slate-950` 内层 + `border-b border-slate-200 px-4 py-3` header 区
- **icon-tab 切换**: `RightPanel.tsx:113-135` 6 tab 横排 (Code / Trace / Diff / History / Batch / CLI) — F4 加新 UI 时是否新增 tab 还是嵌入既有 tab 是设计点 (见 §3)

### 2.6 报告 / 错误提取 utilities (`utils/errors.ts`)

`apps/studio/frontend/src/utils/errors.ts`:
- `errorMessage(error)` (61-67): 从 axios `ErrorResponse.message` 取或 fallback 到 `error.message`
- `lintErrorsFromError(error)` (48-59): 从 422 `details.errors` 提 LintError 数组 — 给 lint 失败时 422 反序列化用
- 后端 `ErrorResponse` 结构在 `apps/studio/backend/app/models/errors.py:10-17`: `{error_code, http_status, message, details, retry_strategy}`

### 2.7 总结: 现有接入 pattern

| 场景 | 推荐 pattern |
|---|---|
| 列表 / 详情 read 类 (有 cache 价值) | SWR hook (`useSkills` / `useRunHistory` 模式) |
| 一次性按钮触发 read (不需 cache, 状态短) | imperative useState hook (`useGoldenDiff` 模式) |
| 一次性 button 一次调用 inline (state 短到不值得抽 hook) | App.tsx 内 `useCallback` + `api.xxx` (`handleLint` 模式) |
| 错误反馈 | `pushToast(errorMessage(error), 'error')` 顶部 toast + 详情错误进 `lintErrors` 之类的 state 区 |
| 列表 panel UI | `flex h-full flex-col bg-slate-50 dark:bg-slate-950` + sticky header `border-b` + 主区 `min-h-0 flex-1 overflow-y-auto` |

## 3. 4 个 API 的 frontend 集成具体形态 (per-router)

### 3.1 audit — **不能集成** (backend 是 stub, MVP3 deferred)

`routers/audit.py:20` 直接 `raise_not_implemented(...)` 永远返回 501。`AuditResult{drift_score, violations}` (`models/audit.py:8-13`) 是占位 schema, 没有 `compute_drift(plan_checklist, trace)` service 层。`studio-mvp1/requirements.md:105` 显式标注 "Deferred (MVP3/P2+)", `studio-mvp1/design.md:100` 标注 "MVP3"。

**唯一可做的事**: frontend 加一个**"Drift Audit (coming in MVP3)" disabled 占位按钮** + 加 `AuditResult` 类型到 `api/types.ts`。但这没业务价值, 反而误导 PM。**建议主控直接 push back: 把 audit 从 F4 范围里删掉, 等 MVP3 一起做**。

### 3.2 compare — **不需新增 frontend 工作, 仅决定 POST 处置**

GET `/diff` 已通过 `useGoldenDiff.compare()` (`hooks/useGoldenDiff.ts:27`) 在 `App.tsx:547` `handleCompareToGolden` + `App.tsx:582` `handleCompareHistoryRun` 完整接入。Diff UI 在 `components/diff/DiffView.tsx` 完整实现 (字段列表 + 选中字段详情 + 总分卡片 + Compare/Promote 按钮)。

POST `/compare` (`compare.py:14-20`) 跟 GET `/diff` 调同一 service 但缺 `against` 参数, 当前 frontend 完全不需要 POST 形式。Backend 处置选项:
- (A) 删除 POST `/compare` 路由 (后端 a1 任务)
- (B) 给 POST 加独特语义 (例如 "create snapshot of comparison report"), 然后 frontend 接入 — 需要 PM 拍要不要这功能
- (C) 保留作 alias, 在 OpenAPI 标 deprecated

**主控分叉点**: 见 §6 Q1。

### 3.3 lint — **已接 95%, 仅 `phases_summary` 渲染遗珠**

`App.tsx:315-329` 完整接入 POST `/skills/{id}/lint`, lint 错误进 MonacoPanel 顶部红条 (`MonacoPanel.tsx:31-61`), success 推 toast。

未利用: `LintResult.phases_summary` (后端 lint passed 时返回 phases 概览 dict 列表, `services/skills.py:110`)。frontend `types.ts:27` 有定义但无任何渲染消费。如果要展示, 自然位置是:
- 选项 A: lint 成功 toast 改成 "Lint passed (X phases validated)" — 微改 (App.tsx:324 一行)
- 选项 B: 在 MonacoPanel 顶部加 success 状态绿条, 列 `phases_summary` 概览 — 中等改, 加一个 component
- 选项 C: 不做, 删除 frontend `phases_summary` 类型定义并归档

**主控分叉点**: 见 §6 Q2。

### 3.4 debug — **不应集成, 不是产品 feature**

`debug.py:7` `include_in_schema=False` + 路由前缀 `/api/_debug` (Studio 全局规约: `_debug` 前缀 = 内部 smoke), 用途是验证 backend 异常处理 middleware 在 ValueError 时也能产出标准 `ErrorResponse` (`backend/tests/test_api.py:52` 验证它**不出现**在 OpenAPI schema 中)。

如果 frontend 接入这个端点, 等于把内部测试钩子暴露给 PM。**建议跳过, 不在 F4 范围**。

## 4. 实施 sub-task 拆分 (待主控解锁分叉点后由 a1 接力)

> 注意: 以下 task 以"如果 §6 分叉点全选最小路径"为前提。每个 task 都假设是 a1 实施, 主控派 + a2 review。

| Task | 输入 | 输出 | 估时 | 依赖 |
|---|---|---|---|---|
| T1 (可选) Lint phases_summary 微改 | App.tsx:324 toast 文案 | "Lint passed (N phases)" | 30 min | 主控选 §6 Q2 选项 A |
| T2 (可选) Lint phases_summary 完整 panel | MonacoPanel 加 success 状态 component + phase summary 列表渲染 | 新 file: `MonacoPanel/LintSuccessBanner.tsx` (~50 行); `MonacoPanel.tsx` 接入 | 1.5 hr | 主控选 §6 Q2 选项 B |
| T3 (可选) 删除 POST `/compare` 死路由 | `routers/compare.py:14-20` + `main.py` import | 删除路由 + 更新 `test_api.py:43` expected_paths | 45 min | 后端 a1 任务; 主控选 §6 Q1 选项 A |
| T4 (条件) audit MVP3 占位 UI | 加 `AuditResult` 到 `types.ts`; `TracePanel` 加 disabled "Audit" 按钮 (tooltip: "Available in MVP3") | 改 `types.ts` + `TracePanel.tsx` | 1 hr | 主控明确说"先建占位"; 否则砍掉 |

**重要**: 没有任何 task 是 brief 隐含的"5 router frontend 集成"。在主控解锁分叉点之前, F4 这个 spec 实质工作量是 0-3 hr (远低于 brief 估的"并行流"工作量), **极可能应被砍并合并到其他 spec**。

## 5. 风险 / 阻塞 / 不确定 (每条标证据 × 影响 × 置信度)

### R1: brief 的"5 router 已挂未接"前提不准确 (证据=High, 影响=High, 置信度=A)

- 证据: 全部 5 router 的 file:line 已逐条验证 (§1)。lint 已接 (`App.tsx:322`), compare GET 已接 (`useGoldenDiff.ts:27`), audit 是 stub, debug 不是产品。
- 影响: 直接决定 F4 spec 是否成立。如果按 brief 字面派 a1 写"5 router frontend hooks", 会做出大量重复 / 错误工作 (例如 lint 已接还派人写 useLint hook)。
- 应对: 主控先看 §6 决定 F4 spec 是真存在还是合并到其他 spec / 砍掉。

### R2: audit MVP3 deferred, F4 不该包含 (证据=High, 影响=Medium, 置信度=A)

- 证据: `studio-mvp1/requirements.md:105` "Deferred", `studio-mvp1/design.md:100` "MVP3"; service 层 grep 全 repo 不存在 drift / plan_checklist 比对逻辑。
- 影响: 主控如果按 brief 派 a1 接 audit, a1 找不到 service 会卡住或写假实现。
- 应对: F4 范围内删 audit, 其他 phase 一起做。

### R3: POST `/compare` vs GET `/diff` 语义重叠未决 (证据=High, 影响=Low, 置信度=B)

- 证据: `routers/compare.py:14, 23` 两个 handler 都调 `compare_run_to_golden`, POST 是 GET 的弱化版。
- 影响: 死路由不影响生产 (POST 不被调用 = 不报错), 但增加认知负担 + OpenAPI 表面冗余。
- 应对: 主控决定删 / 加语义 / 标 deprecated, 然后派 a1。**这是 backend 工作不是 frontend**, 强行塞进 F4 frontend spec 是 scope drift。

### R4: phases_summary 死代码 (证据=High, 影响=Low, 置信度=A)

- 证据: backend lint passed 时返回 `phases_summary` (`services/skills.py:110`); frontend `types.ts:27` 有类型但全 `apps/studio/frontend/src/` 无消费。
- 影响: 死字段, 维护负担。
- 应对: 主控选 A/B/C 中之一 (§6 Q2)。如选"不做", 应在 backend 删 + frontend types 删。

### R5: copilot SDK 集成另派, 跟 F4 协调时序 (证据=Medium, 影响=Medium, 置信度=B)

- 证据: brief 显式说 copilot 走 SDK 集成另派, 跳过本任务。
- 影响: 如果两条流并行进行而 spec 边界不清, 可能两边都改 `App.tsx` 的某个区域产生 conflict。
- 应对: 这条 R 不是阻塞当前 research, 但 design.md 阶段需要明确 F4 不动 copilot 相关 component。

### R6: F4 spec name 跟实际工作不匹配 (证据=Medium, 影响=Low, 置信度=B)

- 证据: spec dir 名是 `studio-frontend-f4-api`, 暗示"frontend 接入若干新 API"; 实际剩余工作是 1-2 个微改 + 1 个 backend 删除 + 1 个 spec 砍。
- 影响: 后续 a2/a1 看 spec name 时会带"接 API" 预期, 写出来的 design 跟实际工作不匹配。
- 应对: 主控可能要重命名 spec (建议 `studio-router-cleanup` 之类) 或者 abandon 这个 spec 把残余工作分摊到 lint/compare 各自现有 spec。

## 6. 需 PM 拍板的分叉点

### Q1: POST `/api/skills/{skill_id}/runs/{run_id}/compare` 怎么处置?

- **A. 删除路由** (推荐, 最干净) — backend a1 删 `routers/compare.py:14-20` + `main.py` import + 更新 `test_api.py:43` expected_paths。frontend 无变化。
- **B. 给 POST 一个独特语义** (例如 "snapshot 当前 diff 报告并持久化"), 然后 frontend 接入 — 要 PM 决定要不要这功能 + 后端要新 service 层。
- **C. 保留 + 在 OpenAPI 标 deprecated** — backend a1 加 `deprecated=True` kwarg 到 router 装饰器, 不动 frontend。

### Q2: lint `phases_summary` 字段怎么处置?

- **A. toast 文案微调** ("Lint passed (N phases)") — 30 min, 不增组件。
- **B. 加 success banner panel 列 phases summary** — 1.5 hr, 加一个新组件。
- **C. 删字段** — backend a1 删 `services/skills.py:110` + `models/lint.py:17` + frontend `types.ts:27`。

### Q3: F4 spec 本身要不要存在? 还是合并到既有 spec / 砍掉?

如 R1/R6 指出, F4 实际工作量 0-3 hr。三个选项:

- **A. 保留 F4, 范围限定 Q1+Q2 微改** — 但 spec 名 `studio-frontend-f4-api` 误导, 建议改名 (例如 `studio-router-cleanup`)。
- **B. abandon F4, 把 Q1 (compare 死路由) 并入 backend cleanup spec, Q2 (phases_summary) 加进 lint 后续 small task** — 不留 F4 dir。
- **C. 重新定义 F4 范围** — 如果主控有别的"frontend 没接"的 backend feature 想塞进 F4 (不在原 5-router 假设里), 可以扩 scope, 但需要新一轮 R 调研。

### Q4: audit MVP3 是否提前做 placeholder (R2 关联)?

- **A. 跳过, 等 MVP3 一起做** (推荐) — 不浪费 token 做不能用的 UI。
- **B. 现在加 disabled "Audit" 占位按钮** (`TracePanel` 加按钮 + `types.ts` 加 AuditResult) — 1 hr, 帮 PM 看到 roadmap 但暂不可用。

### Q5: debug router 是否应该从 frontend "可见" 的角度做处理?

R 验证: `debug.py` 已经 `include_in_schema=False` + 测试断言它不在 OpenAPI 输出里 (`test_api.py:52`)。frontend 完全不该接入这个端点, **此项不需要任何决策**, brief 里把它列入 5 个候选是误判。

---

## 7. Self-Review

完成度自检:

- [x] 所有 file:line 引用都精确到行号 (router 文件 / service 文件 / model 文件 / frontend hooks / App.tsx)
- [x] 没有 placeholder / TBD
- [x] 4 router 实际状态都跟 brief 假设作了交叉验证 (Phase 0 §C 验证)
- [x] 风险 R1-R6 每条标三轴
- [x] 分叉点 Q1-Q5 给出具体选项 + 推荐
- [x] sub-task 估时按"a1 1-3 hr 粒度"

预期主控接下来动作:

1. 读 §6 五个分叉点, 决定 F4 spec 边界
2. 如果 Q3 选 A (保留 F4), 派 a2 写 design.md (基于 Q1+Q2 决策)
3. 如果 Q3 选 B (abandon F4), 不需要 design.md, 直接派 a1 在其他 spec 下做 micro-tasks
4. audit/debug 一律不在 F4 范围 — R 阶段已经物理验证它们不能 / 不该接

如果主控对 Q1-Q5 的某个分叉点觉得不该自己拍 (比如 Q2 B 选项的 UI 设计偏 product 决策), 应升给 user 拍一遍。
