# Studio 功能开发 Handoff Prompt（交接模板 · 唯一真相源）

> 把 Studio 功能任务（前端驱动、允许全栈）交给某个 agent 时，复制下面
> 「--- 模板正文 ---」之间整段，把末尾 `任务:` 后面替换成本次具体改动，发给该 agent。
>
> **这份是交接模板的单一真相源。** 规则变了就改这份、走 PR 进 `main`，别再把交接
> 话术散落在聊天里。它只是把仓库里既有规则（功能 SOP `apps/studio/frontend/CLAUDE.md`、
> `AGENTS.md`「Development Principles」、`docs/development/FRONTEND_UI_SPEC.md`、
> 手册方法论两份）串成一段“开工须知”——真相仍在那些文档，模板与它们冲突时以那些文档为准。

---- 模板正文 ----

Studio 功能开发 handoff

你这次的任务是 Studio 功能开发:以前端为入口,但**功能牵扯到哪层就改哪层**——
apps/studio/backend 可以改,第一性原理分析说该改 packages/graph-agent(engine)/
packages/graph-agent-gateway(gateway)时也直接去改。开工前必读 / 必守:

必读(按顺序):
1. apps/studio/frontend/CLAUDE.md —— Studio 功能开发单 agent SOP(必读第一份)。它覆盖
   全局重型多 agent PM 流程:本任务我自己一个 agent 直接写代码,不派 ccb/不派
   subagent、不走 12 步 PR 审计、不写 kiro spec、不开 60s loop。其「五、一个完整
   功能任务的端到端 SOP」是这次要照走的主干(Phase 0 锁范围 → 1 开 worktree →
   2 设计对齐 → 3 实施 → 4 亲眼验证 → 5 门禁 → 6 回写手册 → 7 发 PR →
   8 报 done 附逐项 PM 验证清单)。
2. AGENTS.md「Development Principles」—— 三条开发原则,凌驾于快捷省事之上(下面
   「开发原则」段是执行摘要)。
3. docs/development/FRONTEND_UI_SPEC.md(尤其 §2)—— 样式/组件/布局基准 = 唯一真相。
4. docs/studio/mvp1/_impl/frontend-handbook/index.html —— N6《前端实施说明书》,
   是「活的实施追踪器」(由 tpl-*.json 切片经 build_template_slice.py 生成),
   讲「做什么 / 怎么实施 / 现在到哪了」。它的状态标签是手维护的、会滞后代码,默认
   当它可能过时、用代码核对再信。手册怎么看 / 怎么改 / 何时改 / 测试截图怎么截 /
   切片字段 schema / 状态点配色,见 docs/studio/mvp1/handbook-methodology/ 两份
   方法论文档(frontend-page-authoring-methodology.md + handbook-operations-
   schema-lifecycle.md)。
5. 大方向以 MVP1 设计为真理、不看代码:入口 AGENTS.md「Standard Documents → MVP1
   design = source of truth」。studio 看 docs/studio/mvp1/(README +
   DESIGN_UNITS_INDEX.md),engine 看 docs/engine/mvp1/,gateway 看
   docs/graph-agent-gateway/mvp1/(各自 mvp1-alignment.md = 真理)。设计与代码
   冲突时设计赢。
6. apps/studio/frontend/src/components/ui/ 下现有 shadcn/Radix 封装 + 相关组件/
   design token —— 优先复用,缺原语先在 ui/ 补 shadcn 风格封装再用,不硬编码颜色。

开发原则(违反 = 直接不合格,即使测试全绿):
- 不向后兼容:当前没有发布版本、没有外部用户。规范/schema/API/文件格式都可以直接改,
  所有已存数据都可以丢弃。禁止迁移垫片、legacy 别名、保留旧字段、双格式读取、版本
  嗅探;换掉旧设计就在同一个改动里删干净旧路径。旧数据装不进新形状 → 重新生成/删数据。
- 第一性原理修复,不打补丁:挖到坏逻辑真正所在的那一层,在那一层重新设计。给调用方
  加特判、try/except 吞坏状态、事后修数据、复制 workaround 都不合格。先问"这个坏
  状态为什么可能存在",再问"怎么让报错消失"。
- 模块边界只决定改动落在哪层,不是禁区:该改 engine/gateway 就直接改(对齐该模块
  MVP1 设计 + 补该模块测试 + 过 mypy --strict 门禁),不许在 studio 层绕着写次优
  方案——为绕开 SDK 改动而造的 workaround 本身就是缺陷。反向仍禁止:studio 专属
  关注点不进 SDK,不绕过 adapter。
- Server-authoritative state + event-driven revalidation: mutable truth 只由
  后端/gateway/storage 的唯一 owner 决定;前端缓存只是 read-through 副本。某个
  cache key 可以在所属 app/feature scope 首次需要时 cold load 一次,并且所有消费者
  必须共享同一个 in-flight/result。之后只有三类 truth-changing trigger 能重拉:写操作
  成功并返回 canonical server snapshot、后端在 commit 后发出精确指向该 dataset 的
  domain event、用户显式点击 refresh/probe/test 这类本意就是更新该 dataset 的命令。
  组件 mount/unmount、Settings 打开/关闭、tab switch、window focus、timer polling、
  WebSocket connect/reconnect、泛泛的 resync 都不是数据更新,不得触发 settings/
  registry/roles/templates 等 mutable truth 重拉。事件无法精确说明变更对象时,修 event
  contract,不要 broad refresh。

边界与纪律(不可省):
- 仅当任务是纯 engine/gateway 内部重构、Rust 层(apps/studio/tauri)或顶层架构调整
  时,才退回全局重型 SOP;正常功能开发(前端 ↔ studio 后端 ↔ 必要的 SDK 改动)都走
  本轻量流程。

- 设计先于实施:开工前先用手册设计页对齐这次需求(应该长啥样)。手册设计页缺 / 不全
  → 回 MVP1 设计源补;设计源也没有 → 先设计(对齐现有设计语言)、必要时跟我对齐方向、
  写回设计源,再补手册设计页。绝不对着缺失或自创的设计写代码。涉及 backend/engine/
  gateway 的接口调整,同样把定稿写回对应模块的设计源。

- 手册随代码同步(不可省):改完在收尾按代码真相回写对应切片的状态(fe_status /
  be_status / 机制卡 backend_status[].status(值 ok/partial/bad/review) / tests /
  截图 / 截不到的标 shot_na),跑 python3 build_template_slice.py 重生成 index.html,
  跟代码改动放同一个 PR;别只改代码、把手册落在后面。注意导航状态点圆点 = 该页全部
  徽章取最差、全绿才绿(机制卡状态也算在内),所以这些标签要据真实代码老实标、别留
  乐观值,否则页面有没做完的部分却显绿(规则见方法论 handbook-operations-schema-
  lifecycle.md §5.3)。

- 一任务一 worktree:开工先 scripts/wt-new.sh <type>/<short-desc> 从 origin/main
  切本任务专属 worktree(它会后台预装前端 node_modules 和 Python uv sync,建好即可
  开始改代码)。所有改动只发生在自己的 worktree 里;不动主仓根工作区、不动其他 agent
  的 worktree,也不要因为别处不干净去 reset / checkout / pull。本轮只碰本任务需要的
  文件;design token、components/ui/ 封装、手册 index.html 重生成这类共享文件并行必
  冲突,要动它们先跟我对调度。

- 业务逻辑走 TDD:前端数据流/状态/API、后端、engine/gateway 的改动,先写能复现缺陷/
  验证新功能的失败测试,再写生产代码。纯视觉/样式调整不新增测试,只锁死视觉细节的旧
  测试同步删除或收窄。

- 报「完成」≠ 收敛:前端任务以 **PM 在主 app 里逐条确认效果**为收敛条件。报 done 前先把主仓
  app 备到能直接点验的状态(git pull + 补依赖 + engine/gateway 改动重建 vendor + 重启 app)——
  **这些机械收尾一律你自己做完,绝不列成 1/2/3 清单甩给 PM**。给 PM 的只有一份**逐项 PM 验证
  清单**(强制格式):每条已合并改动占一行,四列写清 **① 界面路径**(点到哪一屏,如
  `Settings → API Keys → Qiniu 卡`)· **② 操作**(点/填/hover 什么)· **③ 预期**(该看到
  什么,具体到颜色/文案/数量)· **④ 状态**(`待确认` / `✅ 已确认`);一条改动一行不合并、
  只列验证步骤不列机械步骤、跨多 PR 的会话把本会话所有待确认 + 已确认项汇总一起列。**PM 逐条
  确认完才算收敛,任一条没确认就不算完**,反馈的问题继续在本任务内修(小修可直接开后续 PR)。
  模板:`| # | 改动(PR) | ① 界面路径 | ② 操作 | ③ 预期 | ④ 状态 |`。

- 改完必须把 app 真跑起来、亲眼点过受影响界面才报「完成」;typecheck/diff 通过不算
  视觉验证。验证方式:主仓根跑着唯一一套完整 app(studio-dev.ps1: Tauri + sidecar
  :8787 + Vite 5173,展示的是 main 的代码、不含你的改动)。只改了前端 → 在自己
  worktree 里跑 scripts/wt-dev.sh(本任务专属 Vite,自动挑 5174-5199 空闲端口,
  /api、/ws 代理到主仓 sidecar,同源无 CORS);改了 backend/engine/gateway →
  scripts/wt-dev.sh --backend(额外从本 worktree 的代码起私有 sidecar,8788-8799,
  token 自动生成并打印)——后端改动必须在自己这棵树上验证,不许拿 main 的后端充数。
  浏览器开 http://localhost:<port>/#tkn=<token> 验证。不要在 5173 上"验证"自己的活,
  也不要在 worktree 里另起第二套 Tauri;主仓没 app 在跑时按 AGENTS.md「Studio Tauri
  Dev」标准启动。

- 推送前本地门禁全绿:改了前端,在 apps/studio/frontend 下 npm run lint / typecheck /
  test / build 四件套;改了 backend/engine/gateway,按 AGENTS.md「CI Gates」跑对应的
  uv run ruff check / uv run mypy(SDK 用 --strict)/ uv run pytest。然后
  scripts/wt-ship.sh ["PR title"] 推分支、开 PR、上 auto-merge;远端 main 仍
  protected,不要直接 push。合并后 scripts/wt-clean.sh <本分支> 清理**自己这棵** worktree(只清自己的)、主仓根 git pull;
  **PR 若改了依赖清单,主仓根必须补装**(package.json 变 → apps/studio/frontend 里
  npm install;uv.lock 变 → uv sync),否则跑着的主 app 在新依赖上直接红屏,PM 没法确认。

任务:<在这里写你这次要做的功能改动>

---- 模板正文结束 ----
