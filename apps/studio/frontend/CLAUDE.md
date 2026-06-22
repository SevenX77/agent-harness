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

- **`docs/development/FRONTEND_UI_SPEC.md` 为唯一真相**,改前先读,**尤其 §2「UI 组件与样式基准规范」**。
- 优先复用 `src/components/ui/` 下已有的 shadcn/ui / Radix 封装;缺哪个原语就先在 `src/components/ui/` 补 shadcn 风格封装再用。
- 用语义化 design token 和现有 variant,**不硬编码 hex 颜色 / 一次性 Tailwind 调色**。
- 折叠/弹窗/下拉/select/tooltip/tabs/alert/确认 这类交互,用本地 `@/components/ui/*` 封装。
- 前端迭代中发现可复用的新规则 → **同一次改动里**回写进 `FRONTEND_UI_SPEC.md`,别只留在对话里。

## 四、我的前端任务循环(轻量)

1. 读 `FRONTEND_UI_SPEC.md`(尤其 §2)+ 看现有相关组件 / token。
2. `wt-new.sh` 切分支,自己直接改前端代码。
3. `npm run dev`(或 Tauri 壳)跑起来,**亲眼点过**受影响界面。
4. 本地跑 lint / typecheck / test / build 四件套全绿。
5. `wt-ship.sh` 开 PR,CI 绿后 auto-merge。
6. 有可复用规则 → 回写 `FRONTEND_UI_SPEC.md`。

> 找不到下一步、或目标已达 → 直接报告「已完成 X,亲眼验证截图/描述如下」,不问「是否继续」。遇到**真的拿不准的方向/取舍**(不是工程细节)才问你,且用文字罗列,不做选择题。
