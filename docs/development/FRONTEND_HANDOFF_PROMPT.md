# 前端开发 Handoff Prompt（交接模板 · 唯一真相源）

> 把前端任务交给某个 agent 时，复制下面「--- 模板正文 ---」之间整段，把末尾
> `任务:` 后面替换成本次具体改动，发给该 agent。
>
> **这份是交接模板的单一真相源。** 规则变了就改这份、走 PR 进 `main`，别再把交接
> 话术散落在聊天里。它只是把仓库里既有规则（前端 SOP `apps/studio/frontend/CLAUDE.md`、
> `docs/development/FRONTEND_UI_SPEC.md`、手册方法论两份）串成一段“开工须知”——
> 真相仍在那些文档，模板与它们冲突时以那些文档为准。

---- 模板正文 ----

前端开发handoff

你这次的任务是 apps/studio/frontend 前端改动。开工前必读 / 必守:

必读(按顺序):
1. apps/studio/frontend/CLAUDE.md —— 前端单 agent 轻量 SOP(必读第一份)。它覆盖
   全局重型多 agent PM 流程:本任务我自己一个 agent 直接写前端代码,不派 ccb/不派
   subagent、不走 12 步 PR 审计、不写 kiro spec、不开 60s loop。其「四、一个完整
   前端任务的端到端 SOP」是这次要照走的主干(Phase 0 锁范围 → 2 设计对齐 → 3 实施
   → 4 亲眼验证 → 6 回写手册 → 7 发 PR)。
2. docs/development/FRONTEND_UI_SPEC.md(尤其 §2)—— 样式/组件/布局基准 = 唯一真相。
3. docs/studio/mvp1/_impl/frontend-handbook/index.html —— N6《前端实施说明书》,
   是「活的实施追踪器」(由 tpl-*.json 切片经 build_template_slice.py 生成),
   讲「做什么 / 怎么实施 / 现在到哪了」。它的状态标签是手维护的、会滞后代码,默认
   当它可能过时、用代码核对再信。手册怎么看 / 怎么改 / 何时改 / 测试截图怎么截 /
   切片字段 schema / 状态点配色,见 docs/studio/mvp1/handbook-methodology/ 两份
   方法论文档(frontend-page-authoring-methodology.md + handbook-operations-
   schema-lifecycle.md)。
4. 大方向以 MVP1 设计为真理、不看代码:入口 AGENTS.md「Standard Documents → MVP1
   design = source of truth」;前端相关本体看 docs/studio/mvp1/(README +
   DESIGN_UNITS_INDEX.md)。设计与代码冲突时设计赢。
5. apps/studio/frontend/src/components/ui/ 下现有 shadcn/Radix 封装 + 相关组件/
   design token —— 优先复用,缺原语先在 ui/ 补 shadcn 风格封装再用,不硬编码颜色。

边界与纪律(不可省):
- 只动 apps/studio/frontend;碰到 packages/graph-agent、packages/graph-agent-gateway、
  apps/studio/backend、apps/studio/tauri(Rust)或顶层架构 → 立即退回全局重型 SOP,
  本轻量流程不适用。

- 设计先于实施:开工前先用手册设计页对齐这次需求(应该长啥样)。手册设计页缺 / 不全
  → 回 MVP1 设计源(docs/studio/mvp1/)补;设计源也没有 → 先设计(对齐现有设计语言)、
  必要时跟我对齐方向、写回设计源,再补手册设计页。绝不对着缺失或自创的设计写代码。

- 手册随代码同步(不可省):改完在收尾按代码真相回写对应切片的状态(fe_status /
  be_status / 机制卡 backend_status[].status(值 ok/partial/bad/review) / tests /
  截图 / 截不到的标 shot_na),跑 python3 build_template_slice.py 重生成 index.html,
  跟前端改动放同一个 PR;别只改代码、把手册落在后面。注意导航状态点圆点 = 该页全部
  徽章取最差、全绿才绿(机制卡状态也算在内),所以这些标签要据真实代码老实标、别留
  乐观值,否则页面有没做完的部分却显绿(规则见方法论 handbook-operations-schema-
  lifecycle.md §5.3)。

- 一任务一 worktree:开工先 scripts/wt-new.sh <type>/<short-desc> 从 origin/main
  切本任务专属 worktree(它会后台预装前端 node_modules,建好即可开始改代码)。所有
  改动只发生在自己的 worktree 里;不动主仓根工作区、不动其他 agent 的 worktree,
  也不要因为别处不干净去 reset / checkout / pull。本轮只碰被指派的前端文件和必要
  手册切片;design token、components/ui/ 封装、手册 index.html 重生成这类共享文件
  并行必冲突,要动它们先跟我对调度。

- 改完必须把 app 真跑起来、亲眼点过受影响界面才报「完成」;typecheck/diff 通过不算
  视觉验证。验证方式:主仓根跑着唯一一套完整 app(studio-dev.ps1: Tauri + sidecar
  :8787 + Vite 5173,展示的是 main 的代码、不含你的改动);在自己 worktree 里跑
  scripts/wt-fe-dev.sh 起本任务专属 Vite(自动挑 5174-5199 空闲端口,/api、/ws 代理
  到主仓 sidecar,同源无 CORS),浏览器开 http://localhost:<port>/#tkn=<sidecar-token>
  验证自己这棵树。不要在 5173 上"验证"自己的活,也不要在 worktree 里另起第二套
  Tauri/sidecar;主仓没 app 在跑时按 AGENTS.md「Studio Tauri Dev」标准启动。

- 推送前在 apps/studio/frontend 下本地跑通 npm run lint / typecheck / test / build
  四件套全绿。然后 scripts/wt-ship.sh ["PR title"] 推分支、开 PR、上 auto-merge;
  远端 main 仍 protected,不要直接 push。合并后 scripts/wt-clean.sh 清理 worktree。

任务:<在这里写你这次要做的前端改动>

---- 模板正文结束 ----
