# 前端单 Agent 轻量 SOP — 仅本目录前端优化任务生效

> **生效边界(只读一次,记牢)**:本文件**仅**在我(主控 Claude)做 **`apps/studio/frontend/` 前端优化/样式/交互**类任务时生效。
> 一旦任务触及 `packages/graph-agent` / `packages/graph-agent-gateway` / `apps/studio/backend` / `apps/studio/tauri`(Rust)/ 顶层架构,**立即退回全局 `~/.claude/` 那套多 agent PM 宪法 + SOP**,本文件不适用。
>
> **优先级**:本文件是项目级用户指令,按全局宪法自身的优先级表(`用户当下 instruction (CLAUDE.md) > 本文件(全局 rules)`),在前端任务上**覆盖**全局重型 SOP 中与之冲突的部分。

---

## 一、这套流程砍掉了什么(前端任务专用)

下列全局重型流程在前端优化任务里**一律不走**:

- ❌ 不派 a1 / a2 / a3,不用 ccb —— **我自己一个 agent 直接写前端代码**(显式覆盖全局「主控不写代码」铁律,仅限本目录前端)
- ❌ 不走 12 步 PR 审计闭环(SOP-08)
- ❌ 不开 60s ccb 监控 loop
- ❌ 不走「设计阶段主控不思考、只传话」机制(SOP-07)
- ❌ 不写 kiro spec 4 件套 / research / design / tasks
- ❌ 不走 a1↔a2↔a3 audit 链
- ❌ 不强制 TDD(纯视觉/样式优化往往写不出有意义的失败测试;若改动是真功能逻辑,自行判断补测试)

## 二、这套流程保留什么(不可省)

1. **改完亲眼看再报 done** —— 前端改动**必须**我自己把 app 跑起来,在浏览器或 Tauri 壳里点过受影响的界面(主成功路径 + 明显的取消/错误态),**看到效果**才向你说「完成」。agent reply / filesystem diff / typecheck 通过 **都不等于**视觉验证。
2. **推送前 CI Gates 本地全绿** —— 在 `apps/studio/frontend` 下,推送前必须跑通:
   ```bash
   npm run lint
   npm run typecheck
   npm test          # vitest run
   npm run build     # tsc -b && vite build
   ```
   四个全绿才推。绿了再推,别把 `main` 弄红。
3. **branch → PR → 自动 merge** —— 仍走标准流水线,不在 `main` 直接改:
   ```bash
   scripts/wt-new.sh fix/<short-desc>      # 从 origin/main 切 worktree+分支
   # ...在该 worktree 内改前端...
   scripts/wt-ship.sh "PR title"           # push + 开 PR + 武装 squash auto-merge
   ```
   CI 5 个必过 check 绿后 GitHub 自动 squash 进 main;`scripts/wt-clean.sh` 清理已合并 worktree。

## 三、样式/布局判断基准

- **大方向以 MVP1 设计为真理(看齐设计、不看代码)** —— 设计与代码冲突时设计赢;入口见 `AGENTS.md`「Standard Documents → MVP1 design = source of truth」。
- **N6 手册是活的实施追踪器,不是只读说明书** —— `docs/studio/mvp1/_impl/frontend-handbook/index.html`(由 `tpl-*.json` 切片经 `build_template_slice.py` 生成)。它讲「做什么 / 怎么实施 / 现在到哪了」,与讲「样式怎么对齐」的 `FRONTEND_UI_SPEC.md` 互补。三条铁律:
  - **入口读它**:动手前读被指派节点/surface 的设计页(应该长啥样)+ 实施页/测试页(当前状态),理解契约再写。
  - **它的状态标签会滞后代码**:`fe_status`/`be_status`/`be_dep` 是手维护的,默认当它可能过时,**用代码核对**再信(见根记忆 `feedback_no_overclaim_verify_status_against_code`)。
  - **出口回写它**:改了代码就在**同一个 PR**里把对应切片改对 + 重生成 `index.html`(见下「四」的 Phase 5)。
  - 手册的看/改/何时改/截图/字段 schema/配色,全在 `docs/studio/mvp1/handbook-methodology/` 两份方法论文档(`frontend-page-authoring-methodology.md` + `handbook-operations-schema-lifecycle.md`)。
- **`docs/development/FRONTEND_UI_SPEC.md` 为样式/组件唯一真相**,改前先读,**尤其 §2「UI 组件与样式基准规范」**。
- 优先复用 `src/components/ui/` 下已有的 shadcn/ui / Radix 封装;缺哪个原语就先在 `src/components/ui/` 补 shadcn 风格封装再用。
- 用语义化 design token 和现有 variant,**不硬编码 hex 颜色 / 一次性 Tailwind 调色**。
- 折叠/弹窗/下拉/select/tooltip/tabs/alert/确认 这类交互,用本地 `@/components/ui/*` 封装。
- 前端迭代中发现可复用的新规则 → **同一次改动里**回写进 `FRONTEND_UI_SPEC.md`,别只留在对话里。

## 四、一个完整前端任务的端到端 SOP(手册贯穿首尾)

> 这是上面所有规则串成的**一条流水线**。手册不是旁边的参考书,而是**每个阶段都参与**:
> 入口靠它理解契约 + 当前状态,出口靠回写它保持「手册 ↔ 代码」同步。
> 每阶段标了【手册触点】。机械细节(字段 schema / 截图方法 / 生成命令)指向方法论文档,不在此重复。

**Phase 0 · 接活 & 锁范围**
- PM 给一个页面/范围 → **严格锁定被指派的那一页(对应一个 N 切片 / surface),不反向扩张到整个节点**。
- 读三样:① 本 SOP ② `FRONTEND_UI_SPEC.md`(尤其 §2,样式真相)③ 【手册触点】手册里这个节点/surface 的**设计页**(应该长啥样)+ **实施页/测试页**(当前状态)。
- 【手册触点·关键】手册自带的状态标签可能滞后代码 → **这一步就用代码核对一遍现状**(grep 前端/后端确认动作到底接没接、后端能力建没建),否则会基于旧状态做错判断。

**Phase 1 · 切分支**
- `scripts/wt-new.sh <type>/<short-desc>` 从 **fetch 过的** `origin/main` 切;每个新 scope 一个新 worktree(别在刚合并的旧分支上堆改动)。

**Phase 2 · 实施(自己直接写)**
- 复用 `src/components/ui/` 已有封装;缺原语先补 shadcn 风格封装;语义 token,不硬编码颜色。
- 真功能逻辑补测试(纯视觉/样式不强制 TDD)。

**Phase 3 · 亲眼验证(顺手产出手册要用的真机图)**
- 跑 app 亲眼点过受影响界面(主成功路径 + 取消/错误态);agent reply / diff / typecheck 通过都**不等于**视觉验证。
- **多 agent 同仓 → 跑自己 worktree 的独立实例**:sidecar 端口 / Vite 端口(`--strictPort`)/ Xvfb display / `VITE_CACHE_DIR` 各一套独有值;`git worktree list` 先看,**别碰**别人「有未提交 + open PR + 刚改过」的活跃 worktree。隔离配方见 `RUN_AND_SCREENSHOT.md §3`,headless 截图法见 §2。
- 【手册触点】这一步的截图**就是手册测试页要挂的真机图** → 按 ops 文档 §4 命名(`n<节点>-<序号>-<语义>.png`,特写 `-closeup`)存进 handbook 的 `screenshots/`;截不到的(系统对话框/文件管理器/瞬态帧)记下来,Phase 5 在切片标 `shot_na` + 原因。

**Phase 4 · 本地 CI 门禁(改了前端 src 才需要)**
- `apps/studio/frontend` 下 `npm run lint && npm run typecheck && npm test && npm run build` 四件全绿才推。

**Phase 5 · 回写手册切片(与代码改动同一个 PR,不许拖到以后)** 【手册触点·核心】
- 据**代码真相**(不抄旧文案)更新这个 surface 的切片:`fe_status`/`current`/`gap`、`be_status`/`be_dep`、`tests[]`、把 Phase 3 的图挂进 `screenshots:[{file,caption}]`、截不到的标 `shot_na`。
- 自检 design 切片 vs impl 切片状态**不打架**(打架=漂移信号,拿代码裁决)。
- 跑 `python3 build_template_slice.py` **重生成 `index.html`**,和切片 JSON 一起提交。
- 生成自检:无蓝点(`grep -c 'status-dot review'`=0)、无死链、截图数对得上。字段 schema / 枚举 / 配色锁定见 ops 文档 §2 §3 §5。

**Phase 6 · 发 PR & 合并**
- `scripts/wt-ship.sh "PR title"`;**PR 同时含 前端 src + 切片 JSON + 重生成的 index.html**。CI 5 个必过 check 绿后 GitHub 自动 squash 进 main。

**Phase 7 · 沉淀(同一次改动里,别只留对话)**
- 可复用**样式规则** → `FRONTEND_UI_SPEC.md`;**手册方法论/坑** → 方法论文档;**行为类教训** → 记忆。
- 报 done:自然语言 + 附**亲眼验证的截图/描述**,对齐「设计是什么 / 是否按设计做到 / 做完什么效果」三段;不问「是否继续」。

---

### 纯手册任务(只动 `tpl-*.json` / build 脚本,不碰前端 src)
走 **Phase 0(读+用代码核对状态)→ Phase 5(改切片 + 重生成 + 生成自检)→ Phase 6(发 PR)**;
跳过 Phase 2-4 的 src 实施与 npm 门禁(docs 改动不触发 `frontend-gates` 的 lint/build scope)。
但「视觉验证」仍要做——用 Playwright + `file://` 加载重生成的 `index.html`,亲眼确认状态点/徽章/截图渲染对了(本轮就靠这个抓到侧栏颜色)。

> 找不到下一步、或目标已达 → 直接报告「已完成 X,亲眼验证如下」,不问「是否继续」。遇到**真的拿不准的方向/取舍**(不是工程细节)才问你,且用文字罗列,不做选择题。
