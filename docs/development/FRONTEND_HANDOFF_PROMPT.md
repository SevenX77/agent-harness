# Studio 功能开发 Handoff Prompt（交接模板 · 唯一真相源）

> 把 Studio 功能任务（前端驱动、允许全栈）交给某个 agent 时，复制下面
> 「--- 模板正文 ---」之间整段，把末尾 `任务:` 后面替换成本次具体改动，发给该 agent。
>
> **这份是交接模板的单一真相源。** 规则变了就改这份、走 PR 进 `main`，别再把交接
> 话术散落在聊天里。它只是把仓库里既有规则（功能 SOP `apps/studio/frontend/CLAUDE.md`、
> `AGENTS.md`、`docs/development/FRONTEND_UI_SPEC.md`、手册方法论两份）串成一段
> "开工须知"——真相仍在那些文档，模板与它们冲突时以那些文档为准。

---- 模板正文 ----

Studio 功能开发 handoff

任务性质:Studio 功能开发——以前端为入口,功能牵扯到哪层就改哪层:
apps/studio/backend 可以改,第一性原理分析说该改 packages/graph-agent(engine)/
packages/graph-agent-gateway(gateway)就直接去改。仅纯 engine/gateway 内部重构、
Rust 层(apps/studio/tauri)或顶层架构调整才退回全局重型 SOP。

必读(按顺序;真相在文档,这里只是索引):
1. apps/studio/frontend/CLAUDE.md —— 单 agent 功能 SOP,必读第一份。你一个 agent
   直接写代码(不派 subagent、不走 12 步审计、不写 kiro spec);照其「五、端到端
   SOP」走:锁范围 → 开 worktree → 设计对齐 → 实施 → 验证环境&截图 → 门禁 →
   回写手册 → 发 PR+收尾 → 报 done 附 PM 验证清单。
2. AGENTS.md(每会话自动加载)——「Development Principles」三条原则(不向后兼容 /
   第一性原理不打补丁 / 模块边界不是禁区也不是借口)+「Three-Module Architecture」
   两条 SSOT 铁律:数据读取 SSOT(mount/focus/轮询/重连都不许 refetch mutable
   truth)、compile/lint 诊断 SSOT(engine compile_skill 唯一出口、一趟全量聚合、
   节点徽章/字段 tooltip/编辑器 marker/drawer 投影同一份列表)。违反 = 直接不合格,
   即使测试全绿。
3. docs/development/FRONTEND_UI_SPEC.md(尤其 §2)—— 样式/组件/布局唯一真相;优先
   复用 src/components/ui/ 现有 shadcn/Radix 封装,缺原语先补封装再用,不硬编码颜色。
4. N6 手册 docs/studio/mvp1/_impl/frontend-handbook/index.html —— 活的实施追踪器;
   状态标签手维护、会滞后,用代码核对再信;看/改方法见
   docs/studio/mvp1/handbook-methodology/ 两份方法论。
5. MVP1 设计 = 真理(与代码冲突时设计赢):studio → docs/studio/mvp1/,engine →
   docs/engine/mvp1/,gateway → docs/graph-agent-gateway/mvp1/(各自
   mvp1-alignment.md)。

纪律(不可省;细则以 SOP 为准):
- 设计先于实施:先用手册设计页对齐需求;设计页缺/不全 → 回 MVP1 设计源补;设计源也
  没有 → 先设计(必要时跟我对齐方向)、写回设计源,再补手册设计页。绝不对着缺失或
  自创的设计写代码;backend/engine/gateway 接口定稿同样写回对应模块设计源。
- 一任务一 worktree:scripts/wt-new.sh <type>/<short-desc> 开工,所有改动只在自己的
  树里;不动主仓根、不动别人的树。design token、components/ui/、手册 index.html 这类
  共享文件并行必冲突,要动先跟我对调度。
- 业务逻辑走 TDD:前端数据流/状态/API、后端、engine/gateway 先写失败测试再写生产
  代码;纯视觉不新增测试,只锁视觉细节的旧测试同步删/收窄。
- 手册随代码同步:收尾据代码真相回写切片状态(fe_status / be_status / 机制卡
  backend_status[].status / tests / 截图 / shot_na),重生成 index.html,与代码同一个
  PR;状态老实标——导航圆点 = 全页徽章取最差。
- 验证环境自己备,逐项点验归 PM(PM 决策 2026-07-06):在自己 worktree 起
  scripts/wt-dev.sh(改了 backend/engine/gateway 用 --backend 起本树私有 sidecar,
  绝不拿 main 的后端充数),确认 app 能起、受影响界面能打开不报错,顺手截手册要的
  真机图;不在 5173 验自己的活、不起第二套 Tauri。
- 推送前门禁全绿:前端四件套(lint/typecheck/test/build)+ 按 AGENTS.md「CI Gates」
  的 ruff / mypy(SDK --strict)/ pytest。scripts/wt-ship.sh 发 PR、上 auto-merge;
  不直接 push main。
- 合并后收尾全部自己做:scripts/wt-clean.sh 清自己的树(只清自己的)、主仓根 git
  pull、依赖清单变了补装(npm install / uv sync)、engine/gateway 源码变了重建
  vendor + 重启 app —— 机械步骤绝不列清单甩给 PM。
- 报 done ≠ 收敛:附逐项 PM 验证清单,格式强制
  | # | 改动(PR) | ① 界面路径 | ② 操作 | ③ 预期 | ④ 状态 |;一条改动一行不合并、
  只列验证步骤不列机械步骤、跨 PR 的会话汇总所有待确认 + 已确认项。PM 逐条确认完才算
  收敛,反馈问题本任务内继续修(小修可开后续 PR)。

任务:<在这里写你这次要做的功能改动>

---- 模板正文结束 ----
