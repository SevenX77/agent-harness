# Studio MVP1 集成路线（修正版，以 main 为基）— 2026-06-13

> **状态**：Claude 审计后给出的修正路线，供 PM 决策参考。
> **关系**：本文**不替换**原方案 `temp/`（PM 的 7 步整合方案）。原方案的「卫生原则 / 阶段 2 / 重新实现 7 项」我认同并保留；本文只修正它的**地基设定与阶段 0/1**。
> **核心修正一句话**：`main` 已经是三模块集成（#139），且接口层是设计对齐的真功能；不该从 pre-#139 旧 baseline 重建，而应以 main 为基、嫁接前端增量、再补前向功能。

---

## 0. 为什么改地基（已核实的事实，附证据）

> 全部用 `git` 在仓库实测，不是转述。`R = /Users/sevenx/Documents/coding/agent-harness`。

### 0.1 main 就是三模块集成本身，且后端是真功能

- `main` HEAD = `9f53d6f4 feat: MVP1 three-module integration + functional completion (#139)`。
- main 已有完整三模块 owner 代码（`apps/studio/backend/app/core/adapters/` 整目录）：`engine.py`（EngineAdapter，Studio 调引擎原语的适配器）、`gateway.py`（GatewayAdapter，调网关的适配器）、`gateway_config_store_local.py`（配置真相本地存储）、`run_artifact_store_local.py`（运行产物存储）、`runtime_state_store_local.py`（运行态存储）、`product_store_local.py`（成品库）、`storage_local.py`、`metadata_local.py`、`http_transport.py`、`eventbus_memory.py`、`auth_local.py`。
- `ConfigTruthStore`（网关配置真相接口）命中 **21** 文件；`run_artifact`（按 artifact 跑的引擎入口）命中 **20** 文件。
- 后端能力是**真实现，非桩**（行数为证）：`run_manager.py`（运行管理器）**622 行**、`golden_headless.py`（golden 无头评估）**243 行**、`predictor.py`（predict 链路）**149 行**、`run_artifact_flow.py` **69 行**、`publish_pipeline.py`（发布流水线）**60 行**。
- owner 边界已落地：copilot 把 `decide_fallback`（路线降级决策）+ `project_route_state`（6 态投影）**委派给 gateway**（命中 `gateway.py` + `copilot.py` / `llm.py`），不是 Studio 自算。

**含义**：接口层（adapter / owner 边界）是 #139 最难、已做完、已验绿的部分（上一轮独立跑过 Engine 1297 / Gateway 198 / Studio 479 全绿；main HEAD 至今未动，绿色仍成立）。所有 studio-only 分支都**没有**这一层。

### 0.2 六个候选分支全部不含 #139，都 root 在旧点

| 分支 | 是否含 #139 | 与 main 分叉点 |
|---|---|---|
| `codex/studio-mvp1-clean-baseline-reconcile-2026-06-13` | ❌ 缺 | `a1ca363c`（旧） |
| `codex/studio-mvp1-wave3-studio-only` | ❌ 缺 | `92d33c34`（pre-#139） |
| `codex/studio-mvp1-wave2` / `-wave2-safety-2026-06-13` | ❌ 缺 | pre-#139 |
| `feat/studio-mvp1-integration` | ❌ 缺 | `02aa4dc5`（#139 下面一格，是 #139 的前身/兄弟尝试，已被 #139 取代） |
| `llm-provider-intelligence-v2-phase1` | ❌ 缺 | pre-#139 |
| `codex/llm-platform-main-reconcile` | ❌ 缺 | pre-#139 |

- `codex/mvp1-three-module-integration-2026-06-11`（#139 的 squash 源）非 main 祖先，是 squash 合并丢历史所致，内容已在 main——**再合它 = 把 #139 重做一遍**。
- `clean-baseline-reconcile` 的 `c894f311` 实测只改 **5 个测试文件、18 增 18 删**（对称=空白），近乎空操作——确认它不是一个可用基线。

### 0.3 main 真正落后的只有「前端设置 UI + i18n」

前端 `.ts/.tsx` 文件量：main **318**、wave3 **334**、wave2 **339**——三者只差 ~6%，**studio-only 不是"功能大幅更全"的 Studio**。

- 真 `wave2` vs main（前端 src）：**25 增 / 3 删 / 75 改**；`wave3` vs main：**23 增 / 3 删 / 66 改**。
- main 缺、两条 wave 都有的新增文件（两边**完全相同**）：`i18n.ts`、`locales/{en,zh-CN}/{errors,settings}.json`、`@types/react-i18next.d.ts`、`components/studio/settings/copilot/copilot-role-derivation.ts`、`components/studio/workspace-identity.ts`、`components/ui/save-status-badge.tsx`。
- 那 ~70 个「改」集中在 `settings/llm-roles/*`（角色卡 / 模型组 / provider 状态徽章）、`settings/copilot/*`、`settings/api-keys/*`——即 **LLM 设置 UI 精修**。但这块正是 owner 边界债最重的区（Studio 自算 state / mock-copilot / roleTestStates 当真状态），**不能整段照搬**。

---

## 1. 三模块偏离台账（回答「偏离多少」，按性质分三桶）

> 全部直接看 main 代码核验，不信可能过时的 frozen 文档。

### 桶 A — 接口/owner 层：不偏离，真功能（保住）
run/predict/publish/golden 后端真实现 + adapter + gateway 委派（见 §0.1）。**这是 studio-only 分支完全没有的，必须以 main 保住。**

### 桶 B — 真偏离，但每条分支都缺 = 前向 MVP1 工作（base 无关，向前做）
| 能力 | main 实际状态（已验证） |
|---|---|
| debug-resume（D10 节点级恢复） | `runs.py:66` resume 路由 **501**，主路径不存在 |
| D10/D12 Rust 唯一写者 | main tauri 只有 `lib.rs`/`main.rs`/`sidecar.rs`，**无 `native_fs.rs`**；文件仍由 Python(FastAPI) 写 = 架构级偏离 |
| copilot 安全写 | `copilot.py` 仍 `acceptEdits`，**无 `patch_proposed`**（无 diff/确认/落盘） |
| copilot dispatch | `routers/copilot.py:31` `raise_not_implemented` = **501** |
| copilot @mention | 仅 placeholder |
| trace-observability | `TracePanel.tsx` 存在但**孤儿**（未挂主流程，edge dot 假黑板 JSON） |
| run-execution 前端 | Run handler 仍桩，predict-pass 不置闸 |
| phase-editing / graph-authoring | 读写旧字段；inline subgraph = mock |

→ 对应原方案「重新实现 7 项」，**全部前向工作，换基解决不了**。

### 桶 C — main 落后、可嫁接：前端设置 UI + i18n（见 §0.3）
唯一「main 比 wave 旧」的真偏离。**可嫁接，但须按 owner 边界改造**（Studio 只渲染 gateway 事实、删 mock）。

**结论**：#139 的偏离 = 桶 B（前向未做，全分支皆缺）+ 桶 C（前端 UI/i18n 落后，可嫁接）；接口层（桶 A）设计对齐且真实，**没有"接在假功能上"**。故不推倒重建。

---

## 2. 指导原则（沿用原方案，认同）

1. **owner 边界优先**：Engine/Gateway owner 逻辑以三模块设计为准；Studio 只渲染 gateway 返回的事实，不自算 fallback/materialize/6 态。
2. **只捞正向材料**：凡主体仍走旧路、fake、Studio 代 Gateway 决策的，不合实现，只捞测试意图或重新实现。
3. **拒绝带回旧路**：不把 `registry_snapshot`（旧配置快照接口）owner path、`run_skill/predict_skill` 隐藏路径、Studio 自算状态合回来。
4. **前向缺口靠 RED→GREEN 重做，不靠 merge 解决**（桶 B）。

---

## 3. 修正后的阶段计划

### 阶段 0：以 main 为基建集成分支
- 从 `main`（=#139）切 `feat/studio-mvp1-mainbased-integration`（命名待定）。
- **不重建、不合 three-module 分支**（已在 main）。
- 门禁（确认基线绿）：三模块分进程 pytest（Engine / Gateway / Studio 各自；**必须分进程**，合一会 `Plugin already registered` 撞 conftest）+ Studio 前端 `tsc -b --noEmit`。

### 阶段 1：嫁接 wave3 前端增量 + i18n（路径限定 + owner 改造）
- **来源**：`codex/studio-mvp1-wave3-studio-only`（比 wave2 干净，差异略小；i18n 两边相同，无不可替代项）。
- **直接取**：`apps/studio/frontend/src/i18n.ts` + `locales/**` + `@types/react-i18next.d.ts` + `save-status-badge.tsx` + `workspace-identity.ts`（纯增量，低风险）。
- **改造取**：`settings/llm-roles/*` / `settings/copilot/*` / `settings/api-keys/*` 的 UI 精修——逐文件对照，**只要展示层改进，剥掉 Studio 自算/mock**（删 `mock-copilot-data`、不保留 `roleTestStates`/`routeStatusOverrides` 当真状态、API 走 `GatewayAdapter` 或新 DTO）。
- **禁止取**：`apps/studio/backend/**`、`apps/studio/tauri/**`、`packages/graph-agent/**`、`packages/graph-agent-gateway/**`（否则回退 main 的三模块后端 / Rust）。
- **门禁**：Studio 前端 `npm test -- --run` + `npm run typecheck` + `npm run lint`；后端无回归（分进程 pytest）；static guard：无新 `registry_snapshot` owner path、无 `mock-copilot-data`。

### 阶段 2：LLM 能力模型 + 设置页小批次（从 phase1/reconcile 提炼）
- **Gateway 能力模型**（来源 `llm-provider-intelligence-v2-phase1/2`）：`registry/capabilities.py`（能力归一化）思路、runtime settings descriptor、fallback event/error 分类、route capabilities / verified profiles 的**测试意图**——合入 **Gateway owner 层**，适配三模块 `ConfigTruthStore` / `ModelResolver(config_store, user_id)`，不带回 `registry_snapshot`。
- **LLM 设置页 UI**（来源优先 `codex/llm-platform-main-reconcile`，其次 phase1）：model/role/provider 卡交互、provider chain 展示、role/model 设置弹窗、state badge——**Studio 只渲染 gateway 事实**，删 mock，API 走 GatewayAdapter。
- 每项**独立小批次** PR（原方案 ~400 行上限）。
- **门禁**：Gateway / Studio 分进程 pytest + 前端三连（test/typecheck/lint）。

### 阶段 3：前向 MVP1 功能（桶 B，RED→GREEN 重新实现）
按依赖排序，每项独立任务、先写失败测试：
1. **D10/D12 Rust native-fs 唯一写者** + RuntimeGate 降级启动（sidecar 失败时 shell 仍渲染、功能区显示 degraded）。这是 Tauri sidecar 那条的根（locked 但未实现）。
2. **D10 resume + RuntimeStateStore**（lease + heartbeat + fencing；engine 侧契约 + Studio resume 去 501）。
3. **Copilot 安全写**（`patch_proposed` / 用户确认 / 落盘，替 `acceptEdits`）+ **dispatch**（决定废旧 endpoint 还是接 WS/SDK）+ **@mention**（payload/menu/backend contract）+ **冷启动恢复**（native read/list + store restore）。
4. **TracePanel 挂载 + edge blackboard**（基于三模块 run events / source map）。
5. **`llm_state_projection` / `llm_role_materializer` / `llm_import_drafts` 下沉 Gateway**（Studio 只消费结果；这是 gateway 设计登记的「待下沉 ③b」）。
- **门禁**：每项对应模块 pytest 全绿 + 端到端真跑一条 skill（不止 module 级）。

### 阶段 4：终态全绿 + Tauri
- 三模块分进程 pytest + Studio 前端 test/typecheck/lint + `cargo test --manifest-path apps/studio/tauri/Cargo.toml`（Rust 写者落地后这条才成硬门禁）。
- static guard：无 `registry_snapshot` owner path、无 `run_skill/predict_skill` hidden runtime、无 FROZEN docs / `uv.lock` 越权 diff。

---

## 4. 拒绝清单（不做）

- ❌ 从 pre-#139 baseline 重建 Studio（丢桶 A，再花一圈重造 #139，纯亏）。
- ❌ 阶段 1 整取 wave3 的 `apps/studio/**`（会回退 main 三模块后端）。
- ❌ `feat/studio-mvp1-integration` 整体合入（主体不干净：`registry_snapshot` 在 owner path `routers/llm.py`/`services/copilot.py`/`services/gateway_resolver.py`；127 文件差异）。只捞少量测试/UI 意图。
- ❌ `llm-provider-intelligence-v2-phase2` 直接 cherry-pick 大块（删改过猛，只提炼设计）。
- ❌ 把 `registry_snapshot`、Studio 自算 6 态/fallback/materialize、`getMockEdgeContext`、`acceptEdits` 合回来。

---

## 5. 已自答的细节（不再问 PM）

1. **前端取 wave2 还是 wave3** → **wave3**。两者近乎等价（wave2:25/3/75，wave3:23/3/66），i18n 文件相同，wave3 更干净、差异略小，无不可替代项。
2. **i18n 来源** → wave2/wave3 带同一套，跟前端源走（wave3）。
3. **main 是否可信为基** → 可信。#139 已验绿、copilot 已委派 gateway、后端真实现；残留 `llm_*` 三服务是 gateway 设计登记的「待下沉」延期重构，非 bug。

---

## 6. 与原方案逐条对照

| 原方案 | 本文处理 |
|---|---|
| 总原则 1/2/3（卫生原则） | ✅ 保留（=§2） |
| 阶段 0：重建 Studio baseline（pre-#139） | ❌ 改为「以 main 为基」（§3 阶段 0） |
| 阶段 1：合 three-module | ❌ 删除（已在 main） |
| 阶段 2：四分支只捞正向材料 | ✅ 保留（=§3 阶段 2 + §4） |
| 重新实现 7 项 | ✅ 保留（=§3 阶段 3） |
| 执行顺序 1-7 | 重排为 §3 阶段 0-4 |

---

## 7. 证据出处（可复核）

本文所有「现状」判断的 git 实测命令与结果，见本会话审计记录；关键锚点：
- main = `9f53d6f4`；adapters 目录 / ConfigTruthStore(21) / run_artifact(20)；后端行数 run_manager 622 等。
- 6 分支 merge-base：clean-baseline `a1ca363c`、wave3 `92d33c34`、feat/integration `02aa4dc5`。
- 前端 diff：wave2 25/3/75、wave3 23/3/66 vs main；文件量 318/334/339。
- main 缺口：`runs.py:66` 501、tauri 无 `native_fs.rs`、`copilot.py` `acceptEdits` 无 `patch_proposed`、`routers/copilot.py:31` dispatch 501、`TracePanel.tsx` 孤儿。
