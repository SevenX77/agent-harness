# Studio MVP1 集成基线（Integration Baseline）

> **日期**: 2026-06-11
> **性质**: 收敛计划 / 跨 session 续作锚点。本文件是「把零散 studio 分支汇成一条集成分支、修完 API 再一次性合 main」这条路线的权威起点。
> **状态**: 基线已锁定；集成分支已建空壳；**带冲突解决的内容构造 + 红→绿留待下一轮**。
> **真理来源**: `docs/studio/mvp1/`（设计文档，FROZEN 冻结 + 哈希锁保护）。本文件只定收敛工程路径，不改设计。

---

## 0. 背景（为什么有这份文件）

三个模块（engine 运行时 / gateway LLM 网关 / studio 工作台）的 MVP1 收敛中，**engine 与 gateway 的 MVP1 已经在 `origin/main` 上了**：

- gateway MVP1 优化经提交 `34ee40f1`（"feat(gateway): merge mvp1 updates into main"，无 PR 直接落 main）+ `fa62b8c7`（PR #127 清理重复测试）落地，且比旧 PR #112/#115 更新。
- engine 的 WS-E1~E8 九条工作流全部在 main（E2/E5/E8 是无 PR 号的直接 merge，易被漏看）。

**唯一剩下的是 studio**：main 上的 `apps/studio` 还是 MVP0 基线，MVP1 的 WS-0~WS-8 增量基本都在分支里没合。studio 还差「API 对接」（前端/后端接通真 gateway + 运行事件流），这部分工作量大、会有很多问题，所以不直接合 main，而是先在一条集成分支上修完、CI 全绿，再一次性合。

---

## 1. 已锁定的三个决策（用户 2026-06-11 拍板）

1. **干净分支**：从 `origin/main` 当前 tip 新拉集成分支，**不复用** `codex/studio-mvp1-wave3-studio-only`（基底旧、名字误导）。后者只当素材源。
2. **WS-6 现在并入**：集成分支一开始就是完整图（WS-0~7 全在），不分两批。
3. **strategy 文档保留**：`investor-pitch-positioning.md`（投资人定位话术）、`kb-closed-loop-worked-example.md`（知识库当裁判的闭环样例）、`walkthrough.md`（WS-1 走查纪要）都收进 main，但**单独走 `docs/strategy/` 提交，不混进 studio 代码合并**。

---

## 2. 分支拓扑

```
origin/main (02aa4dc5)   ← engine + gateway MVP1 已在此；studio API 对着这里的真 gateway 接
   └── feat/studio-mvp1-integration   ← 本基线建的集成分支（长期 staging，绿了才合 main）
```

- 集成分支当前 = main tip 空壳 + 本文件（首个提交）。
- 独立工作区：`.worktrees/studio-mvp1-integration`。

---

## 3. 内容来源（三股汇一处）

| 来源 | 位置 | 内容 |
|---|---|---|
| **主体** | 分支 `codex/studio-mvp1-wave3-studio-only`，抢救提交 **`f5a1015d`**（152 文件） | studio-only 重放：WS-0（需求闸门）/ WS-1（本地文件系统基座）/ WS-2（创作工作台）/ WS-3（编译·预测·运行·轨迹接线）/ WS-4（设置·LLM·模型角色）/ WS-5（copilot 工作台）/ WS-7（i18n·校验）。**已剥离** packages 噪音和会撞锁的设计文档。 |
| **WS-6** | 分支 `codex/studio-mvp1-wave2`（PR #117） | golden 逐节点草稿 + 本地 git 存档历史，约 26 个文件：`routers/golden.py`、`services/golden_diff.py`、`git_local.py`（本地 git 自动提交存档服务）、`git_history.py`、9 个 diff 展示组件、`useGoldenDiff` hook、`contract-gate-ws6` + `task-ws6` 两份 .kiro 文档。**大多是新增文件，预期低冲突**（构造时确认；注意把 `client.ts` 的 `compareRunToGolden`（前端调 golden 对比接口的函数）加回）。 |
| **strategy** | 分支 `codex/fix-gateway-mvp1-tests`，提交 `30e58971` | 三份业务文档进 `docs/strategy/`。另：同分支提交 `c323f13a` 的 AGENTS.md「先核实再提问（铁律）」+「改后端必重启 Studio」两条规则，main/wave2 都没有，建议 cherry-pick。 |

---

## 4. 构造序列（下一轮执行）

1. ✅ **已做**：抢救提交 wave3 staged（`f5a1015d`）。
2. ✅ **已做**：建 `feat/studio-mvp1-integration` 空分支 + 工作区。
3. ⏭️ 把 studio-only 改动叠到集成分支，**解决 14 个冲突文件**（见 §5）。
4. ⏭️ 嫁接 WS-6 的 ~26 个文件。
5. ⏭️ 清理：修 `.gitignore` 回归（补回 `coverage/`、`.agent/`、`.agents/`、`.cursor/`、引擎快照目录等被 wave3 旧版覆盖丢掉的忽略项）；strategy 三份 + AGENTS.md 规则剥到独立提交。
6. ⏭️ push，开 draft PR 占位（标 WIP，CI 预期红——正常）。
7. ⏭️ 逐个把红测试（§6）转绿 → CI 全绿 → 一次性合 main，拆成 **studio-only 代码 / WS-6 / 文档** 三个 PR 方便 review。

---

## 5. 冲突面（14 个文件）

main 在 `92d33c34`（wave3 的基底，已是 main 祖先）之后改过、且 wave3 也改了的文件：

**后端（11）**：`models/runs.py`、`routers/llm.py`、`services/copilot.py`、`services/diagnostic_export.py`、`services/predictor.py`、`tests/routers/test_llm_registry_api.py`、`tests/services/test_copilot_event_translator.py`、`tests/services/test_run_manager_gateway_events.py`、`tests/test_predict_e2e.py`、`tests/test_predict_skill_integration.py`、`tests/test_predictor_service.py`

**前端（3）**：`components/studio/panels/panel-files.ts`、`components/welcome/WelcomePage.tsx`、`hooks/useCopilot.ts`

- **11 个是机械合并**：main 的 Sonar 安全修复（随机盐、后台任务强引用等）vs 新功能撞在同段 → 两边都留。
- **3 个与 resolver 决策纠缠（见 §7）**：`routers/llm.py`、`services/copilot.py`、`useCopilot.ts` —— 它们的冲突段正是 `ModelResolver` vs `resolve_role` 那处，**必须先定 §7 再解**。

---

## 6. 红测试 = API 对接工作清单（10 个）

这些 `.red.test`（TDD「先写失败测试」红灯）就是下一轮要逐个转绿的目标。CI（`ci.yml`）跑 `uv run pytest apps/studio/backend/tests` + `npm --prefix apps/studio/frontend test`，前端 vitest 只排除 `tests/e2e/**`、**不排除 `.red.`**，所以它们全在 CI 路径里 —— 这也是集成分支没接完就一定红、因而必须待在 main 外的原因。

1. `backend/tests/test_studio_mvp1_requirements_ws3_red.py`（WS-3 后端结构化错误契约）
2. `frontend/.../TracePanel.red.test.tsx`（运行轨迹面板）
3. `frontend/.../copilot/__tests__/copilot-thinking.red.test.tsx`（copilot 思考流）
4. `frontend/.../history/RunHistoryRow.red.test.tsx`（运行历史行）
5. `frontend/.../studio/Workspace.ws3.red.test.tsx`（WS-3 画布接线）
6. `frontend/.../studio/center-action-bar.red.test.tsx`（中央动作条）
7. `frontend/.../settings/copilot/CopilotTab.red.test.tsx`（copilot 设置页）
8. `frontend/.../settings/copilot/copilot-role-derivation.red.test.ts`（从模型组推导 copilot 角色）
9. `frontend/.../hooks/useRunStream.red.test.ts`（运行事件流订阅 hook）
10. `frontend/.../store/copilotStore.session.red.test.ts`（copilot 会话持久化）

**已知半成品（带进集成分支，记为 deferred，不阻塞合并）**：WS-3 只做了节点状态灯一半，`TracePanel` 在 wave2/wave3 上仍全局零挂载；WS-1 的 `RuntimeGate`（sidecar 没起来全屏拦截的门组件）退役没做；WS-8（调试续跑）只有需求文档——但 engine 侧 WS-E7 resume API 已在 main，阻塞已解除，可排期。

---

## 7. 下一轮开场第一题：resolver API 方向

集成分支 §5 的 3 个冲突文件解不了，除非先定这个：

- **`ModelResolver`**（gateway 旧的类式解析器，直接返回可调用模型）—— main 当前 studio 代码用它。
- **`resolve_role`**（gateway registry 包里新的函数式角色解析 API，返回有序 `ResolvedRoute` 链由调用方自己执行）—— wave3 staged 改用它。

两者**都是** `docs/graph-agent-gateway/mvp1/02-orch-role-resolution/` 绑定的合法公共接口（不是合规问题，是选哪边）。倾向 `resolve_role`（更贴「编排与调用分离」方向，且签名与当前 main 的 gateway 兼容），但**由 PM 定**。

---

## 8. 设计文档回写（单独第三个 PR，绝不走 merge）

17 份 baseline 设计文档的「现状」段回写在 main 上是 FROZEN + 哈希锁（`_audited-ready-hashes.json` 记冻结哈希、`test_doc_hash_lock.py` 校验）保护的，混进代码合并必撞锁。留到最后，在 main 冻结版之上重写，走 `studio-doc-exemptions.yaml`（改冻结文档的豁免登记表）报批；顺带回写本目录 `IMPL_PLAN.md` 的真实完成态。

---

## 9. 同期仓库清理（与本基线并行，已分析未执行）

- **关闭 PR**：#112、#114、#115（gateway 已在 main，合会回退）、#87、#88（MVP0 时代，已被取代）。
- **删分支**：10 个本地（7 个零独有提交 + `docs/mvp1-design-20260604`/`mvp0`/`llm-provider-intelligence-v2-phase2`）+ 对应 8 个远端；drop main 上的 stash。
- **抢救**：engine↔gateway 契约 e2e 测试在 `.worktrees/engine-gateway-api-e2e`（分支 `codex/engine-gateway-api-e2e`，未提交，丢了就没）——属 engine 线，单独 commit。
- **gc.log**：`.git` 有 "unreachable loose objects" 警告，分支清理完一起 `git prune`。
- 4 个 dependabot PR（#122/#110/#109/#98）独立处理，#98（qs 安全补丁）优先。
