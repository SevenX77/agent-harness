# Studio 功能开发单 Agent SOP — 前端驱动的全栈任务生效

> **生效边界(只读一次,记牢)**:本文件在我(主控 Claude)做 **Studio 功能开发**类任务时生效——
> 以前端为入口,但**允许并预期**顺着功能改到 `apps/studio/backend`,以及在正确设计要求时改到
> `packages/graph-agent`(engine)/ `packages/graph-agent-gateway`(gateway)。
> **修一个功能常常就是全栈的**;不许为了留在"纯前端"舒适区而把功能做残,也不许把一个功能
> 硬拆成"前端先上、后端以后再说"。仅当任务是纯 engine/gateway 内部重构、Rust 层
> (`apps/studio/tauri`)或顶层架构调整时,退回全局 `~/.claude/` 那套多 agent PM 宪法 + SOP。
>
> **优先级**:本文件是项目级用户指令,按全局宪法自身的优先级表(`用户当下 instruction (CLAUDE.md) > 本文件(全局 rules)`),在 Studio 功能任务上**覆盖**全局重型 SOP 中与之冲突的部分。

---

## 一、这套流程砍掉了什么(功能任务专用)

下列全局重型流程在 Studio 功能开发任务里**一律不走**:

- ❌ 不派 a1 / a2 / a3,不用 ccb —— **我自己一个 agent 直接写代码**(显式覆盖全局「主控不写代码」铁律,仅限本 SOP 范围)
- ❌ 不走 12 步 PR 审计闭环(SOP-08)
- ❌ 不开 60s ccb 监控 loop
- ❌ 不走「设计阶段主控不思考、只传话」机制(SOP-07)
- ❌ 不写 kiro spec 4 件套 / research / design / tasks
- ❌ 不走 a1↔a2↔a3 audit 链
- ❌ 纯视觉/样式优化不强制 TDD、不新增测试,也不维护只锁死 class、像素、间距、颜色、圆角的旧测试(碰到应同步删除或收窄)。**但业务逻辑(前端数据流/状态/API、后端、engine/gateway)必须 TDD**:先写能复现缺陷/验证新功能的失败测试,再写生产代码。

## 二、开发原则(凌驾于快捷省事之上;违反 = 直接出错)

权威版在 `AGENTS.md`「Development Principles」,这里是执行摘要:

1. **不向后兼容**。当前没有发布版本、没有外部用户:所有规范/schema/API/文件格式都可以直接改,
   **所有已存数据都可以丢弃**。禁止写迁移垫片、legacy 别名、"保留旧字段"、双格式读取、
   版本嗅探分支——换掉旧设计就在**同一个改动里删干净旧路径**。旧数据装不进新形状时,
   答案是"重新生成/删数据",不是"两种都支持"。
2. **第一性原理修复,不打补丁**。挖到出问题的逻辑真正所在的那一层,在那一层重新设计。
   症状级补丁——给某个调用方加特判、try/except 把坏状态吞掉、事后修数据、复制一份
   workaround——即使测试全绿也算不合格。先问"这个坏状态为什么可能存在",再问"怎么让报错消失"。
3. **模块边界只决定改动落在哪层,绝不是把改动挤去更差位置的理由**。第一性原理分析说该改
   engine/gateway,就**直接去改**(对齐该模块 MVP1 设计 + 补该模块测试 + 过 `mypy --strict`
   等门禁),而不是在 studio 层绕着锁写次优方案——**为了绕开 SDK 改动而造的 studio 层
   workaround 本身就是缺陷**。反方向仍然禁止:studio 专属关注点不许漏进 SDK,不许图省事绕过 adapter。

## 三、这套流程保留什么(不可省)

1. **改完亲眼看再报 done;报 done ≠ 收敛,PM 在 app 里确认完才算收敛** —— 前端改动**必须**我自己把 app 跑起来,在浏览器或 Tauri 壳里点过受影响的界面(主成功路径 + 明显的取消/错误态),**看到效果**才向你说「完成」。agent reply / filesystem diff / typecheck 通过 **都不等于**视觉验证。且我的自验只是**前置条件**:前端任务的**收敛条件是 PM 亲自在主 app 里确认过效果**(PM 决策 2026-07-02)——报 done 时必须附一份**逐项 PM 验证清单**(每条改动一行:界面路径 / 操作 / 预期 / 状态;强制格式与规矩见 Phase 8),并把主仓 app 保障到能直接看的状态(见第 4 条),然后等 PM 逐条确认;**任一条没确认就不算收敛**,PM 指出的问题继续在本任务内修。
2. **推送前 CI Gates 本地全绿** —— 改了前端,在 `apps/studio/frontend` 下必须跑通:
   ```bash
   npm run lint
   npm run typecheck
   npm test          # vitest run
   npm run build     # tsc -b && vite build
   ```
   改了后端/engine/gateway,还要按 `AGENTS.md`「CI Gates」跑对应的
   `uv run ruff check` / `uv run mypy`(SDK 是 `--strict`)/ `uv run pytest`。
   全绿才推,别把 `main` 弄红。
3. **多 agent 并行阶段:一任务一 worktree,预览用 `scripts/wt-dev.sh`** —— 用
   `scripts/wt-new.sh <type>/<short-desc>` 开工;它会**后台**预装前端 `node_modules`
   和 Python `uv sync`(都不碰 `src/`,worktree 建好即可开始改代码,只有跑
   dev/lint/test 时才需要装完)。主仓根保持**唯一一套完整 app**(Tauri + sidecar :8787 +
   Vite 5173,`scripts/studio-dev.ps1` 启动);每个 worktree 里用 `scripts/wt-dev.sh`
   起自己的轻量 Vite(自动挑 5174-5199 空闲端口,同源代理、无 CORS 问题):
   - **只改了前端** → 默认模式,`/api`、`/ws` 代理到主仓共享 sidecar。
   - **改了 backend / engine / gateway** → `scripts/wt-dev.sh --backend`,额外从
     **本 worktree 的 Python 代码**起一个私有 sidecar(8788-8799 挑空闲端口,自动生成
     `STUDIO_API_TOKEN` 并打印),Vite 代理指向它——后端改动也在自己这棵树上验证,
     绝不拿 `main` 的后端"验证"自己的后端改动。
   浏览器开 `http://localhost:<port>/#tkn=<token>` 亲眼验证**自己这棵树**。
   不要在 worktree 里再起第二套 Tauri,也不要动主仓根工作区或其他 agent 的
   worktree。发 PR 用 `scripts/wt-ship.sh`;`main` 仍是 protected,不要直接 push。
4. **合并后主仓依赖跟上,把 app 保障到 PM 能直接看** —— PR 合并后主仓根 `git pull`;
   **若 PR 改了依赖清单必须在主仓补装**:`package.json`/`package-lock.json` 变了 →
   在 `apps/studio/frontend` 跑 `npm install`;`pyproject.toml`/`uv.lock` 变了 →
   `uv sync --all-packages --all-extras --group dev`。跑着的主 app(Tauri + Vite
   5173 + sidecar)解析的是**主仓根**的 node_modules/venv,不补装就会在新依赖上
   直接报 unresolved import 红屏(2026-07-02 `@shadcn/react` 教训)。Vite 已在跑时,
   装完 `touch apps/studio/frontend/vite.config.ts` 让它原地重启重新解析。

## 四、样式/布局判断基准

- **大方向以 MVP1 设计为真理(看齐设计、不看代码)** —— 设计与代码冲突时设计赢;入口见 `AGENTS.md`「Standard Documents → MVP1 design = source of truth」。
- **N6 手册是活的实施追踪器,不是只读说明书** —— `docs/studio/mvp1/_impl/frontend-handbook/index.html`(由 `tpl-*.json` 切片经 `build_template_slice.py` 生成)。它讲「做什么 / 怎么实施 / 现在到哪了」,与讲「样式怎么对齐」的 `FRONTEND_UI_SPEC.md` 互补。四条铁律:
  - **入口读它 + 缺了向上补**:动手前读被指派节点/surface 的设计页(应该长啥样)+ 实施页/测试页(当前状态);**手册设计页缺/不全/和 MVP1 设计文档打架,就去设计源补对**(完整级联见下「五」Phase 2)。手册设计页是 MVP1 设计文档的**派生视图**,不是设计真相本身。
  - **它的状态标签会滞后代码**:`fe_status`/`be_status`/`be_dep` 是手维护的,默认当它可能过时,**用代码核对**再信(见根记忆 `feedback_no_overclaim_verify_status_against_code`)。
  - **出口回写它**:改了代码就在同一轮改动里把对应切片状态改对 + 重生成 `index.html`(见下「五」Phase 6)。
  - **唯一真相源 + 唯一网络出口 = `main` 主仓根**:手册(切片 + `screenshots/` 真机图 + `index.html`)只认 `main` 这一份。改手册跟改代码一样:在**自己的 worktree** 里改切片 / 加截图 / 重生成,随同一个 PR 合进 `main` —— **不把 worktree / `/tmp` 里的中间产物当第二份手册对外、也不为它单开第二条隧道**;对外网页固定从主仓根伺服,合并后主仓根 `git pull` 即刷新。截图必须随切片一起进 git(不许只烤进 `index.html` 而源 PNG 不入库)。伺服配方见 `docs/development/RUN_AND_SCREENSHOT.md` §4。
  - 手册的看/改/何时改/截图/字段 schema/配色,全在 `docs/studio/mvp1/handbook-methodology/` 两份方法论文档(`frontend-page-authoring-methodology.md` + `handbook-operations-schema-lifecycle.md`)。
- **`docs/development/FRONTEND_UI_SPEC.md` 为样式/组件唯一真相**,改前先读,**尤其 §2「UI 组件与样式基准规范」**。
- 优先复用 `src/components/ui/` 下已有的 shadcn/ui / Radix 封装;缺哪个原语就先在 `src/components/ui/` 补 shadcn 风格封装再用。
- 用语义化 design token 和现有 variant,**不硬编码 hex 颜色 / 一次性 Tailwind 调色**。
- 折叠/弹窗/下拉/select/tooltip/tabs/alert/确认 这类交互,用本地 `@/components/ui/*` 封装。
- 前端迭代中发现可复用的新规则 → **同一次改动里**回写进 `FRONTEND_UI_SPEC.md`,别只留在对话里。

## 五、一个完整功能任务的端到端 SOP(手册贯穿首尾)

> 这是上面所有规则串成的**一条流水线**。手册不是旁边的参考书,而是**每个阶段都参与**:
> 入口靠它理解契约 + 当前状态,出口靠回写它保持「手册 ↔ 代码」同步。
> 每阶段标了【手册触点】。机械细节(字段 schema / 截图方法 / 生成命令)指向方法论文档,不在此重复。

**Phase 0 · 接活 & 锁范围**
- PM 给一个页面/范围 → **严格锁定被指派的那一页(对应一个 N 切片 / surface),不反向扩张到整个节点**。
- 读三样:① 本 SOP ② `FRONTEND_UI_SPEC.md`(尤其 §2,样式真相)③ 【手册触点】手册里这个节点/surface 的**设计页**(应该长啥样)+ **实施页/测试页**(当前状态)。
- 【手册触点·关键】手册自带的状态标签可能滞后代码 → **这一步就用代码核对一遍现状**(grep 前端/后端确认动作到底接没接、后端能力建没建),否则会基于旧状态做错判断。核对范围**含机制卡的 `backend_status[].status`**——它现在直接进导航状态点圆点(圆点 = 该页全部徽章取最差,见方法论 `handbook-operations-schema-lifecycle.md` §5.3),据真实代码老实标,别留乐观值。

**Phase 1 · 开 worktree,锁定任务边界**
- 用 `scripts/wt-new.sh <type>/<short-desc>` 从 `origin/main` 切本任务专属 worktree。它会后台预装
  前端 `node_modules` 和 Python `uv sync`(都不碰 `src/`,建好即可开始改代码;
  跑 dev/lint/test 才需要装完,`scripts/wt-dev.sh` 会自动等它们)。
- 本任务的**所有**改动只发生在自己的 worktree 里:不动主仓根工作区,不动其他 agent 的 worktree,
  更不要因为别处工作区不干净就 `git reset` / `git checkout --` / `git pull` 别人的树。
- **共享基础设施要先对调度**:design token、`components/ui/` 封装、手册 `index.html` 重生成这类
  多任务都会碰的文件,并行改必然在合并时冲突——发现要动它们时先跟 PM/用户排队或指定单一 owner;
  `index.html` 是生成物,合并冲突时在合并侧重跑 `build_template_slice.py` 重生成,不手工解。

**Phase 2 · 设计对齐:先把权威设计立起来,再动手** 【手册触点·核心前置】
- **铁律:绝不对着"缺失的设计"或"自己临时编的设计"写代码。** 设计真相在 MVP1 设计文档,手册设计页只是它的**派生视图**。动手前按这条级联把"它应该长啥样"确立成权威设计:
  1. **手册设计页已有这条 + 与 MVP1 设计文档一致** → 对齐它,直接进 Phase 3。
  2. **手册设计页缺 / 不全** → 去 MVP1 设计源(`AGENTS.md` Standard Documents →「MVP1 design = source of truth」;studio 在 `docs/studio/mvp1/` 的 `README.md` + `DESIGN_UNITS_INDEX.md` + 设计单元)找,据它**补全手册设计页切片**(`atoms`:cap/func/action/fe_design/fe_modules/be_contract)。
  3. **手册设计页与 MVP1 设计文档打架** → **设计文档赢**(看齐设计、不看代码、不看旧手册),把手册设计页改成跟设计文档一致。
  4. **MVP1 设计文档也没有这条** → 真·设计缺口,不能硬写:① 先**设计**它(对齐现有设计语言 / 交互范式 / design token);② 若是**全新方向 / 取舍**(不是工程细节),按「需求+方向归 PM」先用文字跟 PM 对齐方向再定;③ 把定下来的设计**写回 MVP1 设计源**(让设计文档成为真相),**再**据它补手册设计页。
  5. 设计页定稿后 → **补对应的实施页 + 测试页骨架**:实施页列要做的 `functions` 条目,测试页列 `tests` 覆盖点 / `layer1` / `layer2` 测试计划——给 Phase 3 一个明确靶子。
- 一句话:**设计页 = 动手前的靶子(应该长啥样);实施/测试页的状态 = 动手后的结果(做到没 / 测到没,Phase 6 回填)**。缺了就沿级联向上补,补到 MVP1 设计源为止;设计源缺就先设计再写回源,绝不跳过。
- **功能涉及 backend / engine / gateway 时,设计对齐同样适用**:studio 后端看
  `docs/studio/mvp1/`,engine 看 `docs/engine/mvp1/`,gateway 看
  `docs/graph-agent-gateway/mvp1/`(各自 `mvp1-alignment.md` = 真理)。按
  「二、开发原则」第 3 条定改动落点——该落在哪层就落在哪层,不绕。若正确方案要求
  调整某模块的接口/规范,直接调(不向后兼容,原则第 1 条),并把新设计写回该模块设计源。

**Phase 3 · 实施(自己直接写)**
- 复用 `src/components/ui/` 已有封装;缺原语先补 shadcn 风格封装;语义 token,不硬编码颜色。
- **业务逻辑走 TDD**:前端数据流/状态/API、后端、engine/gateway 的改动,先写能复现缺陷/
  验证新功能的失败测试,再写生产代码;纯视觉/样式调整不新增测试,遇到只约束视觉细节的旧测试
  直接清理或收窄。照 Phase 2 定稿的设计页做,不偏靶。
- 时刻对照「二、开发原则」:改坏逻辑所在的那一层,不打补丁;换掉的旧规范/旧数据路径当场删干净。

**Phase 4 · 亲眼验证(顺手产出手册要用的真机图)**
- 跑 app 亲眼点过受影响界面(主成功路径 + 取消/错误态);agent reply / diff / typecheck 通过都**不等于**视觉验证。
- **验证用自己 worktree 的 Vite(`scripts/wt-dev.sh`)**:主仓根跑着**唯一一套**完整 app
  (`scripts/studio-dev.ps1` 启动的 Tauri + sidecar :8787 + Vite 5173)。只改了前端 →
  `scripts/wt-dev.sh`(Vite 代理到主仓共享 sidecar);改了 backend/engine/gateway →
  `scripts/wt-dev.sh --backend`(从**本 worktree 的代码**起私有 sidecar,前后端改动
  都在自己这棵树上验证)。浏览器开 `http://localhost:<port>/#tkn=<token>` 验证
  (--backend 模式的 token 由脚本生成并打印)。
  注意:主仓的 5173 展示的是 `main` 的代码、**不含你 worktree 的改动**,别在那上面"验证"自己的活;
  也不要在 worktree 里另起第二套 Tauri。主仓没 app 在跑时,先按标准启动把主仓 app 拉起来
  (见 `AGENTS.md`「Studio Tauri Dev」),不要绕过 launcher 直接 `cargo tauri dev`。
- 【手册触点】这一步的截图**就是手册测试页要挂的真机图** → 按 ops 文档 §4 命名(`n<节点>-<序号>-<语义>.png`,特写 `-closeup`)存进 handbook 的 `screenshots/`;截不到的(系统对话框/文件管理器/瞬态帧)记下来,Phase 6 在切片标 `shot_na` + 原因。

**Phase 5 · 本地 CI 门禁(按改动范围)**
- 改了前端 src:`apps/studio/frontend` 下 `npm run lint && npm run typecheck && npm test && npm run build` 四件全绿。
- 改了 backend / engine / gateway:按 `AGENTS.md`「CI Gates」跑对应的
  `uv run ruff check <改动包>`、`uv run mypy`(engine/gateway 用 `--strict`)、
  `uv run pytest <对应 tests>`。全绿才推。

**Phase 6 · 回写手册切片状态(与代码改动同一轮完成,不许拖到以后)** 【手册触点·核心】
- Phase 2 已立好"应该长啥样"的设计页;这一步据**代码真相**(不抄旧文案)回填"做到没 / 测到没"的状态:`fe_status`/`current`/`gap`、`be_status`/`be_dep`、`tests[]`、把 Phase 4 的图挂进 `screenshots:[{file,caption}]`、截不到的标 `shot_na`。
- 自检 design 切片 vs impl 切片状态**不打架**(打架=漂移信号,拿代码裁决)。
- 跑 `python3 build_template_slice.py` **重生成 `index.html`**,和切片 JSON 一起提交。
- 生成自检:无蓝点(`grep -c 'status-dot review'`=0)、无死链、截图数对得上。字段 schema / 枚举 / 配色锁定见 ops 文档 §2 §3 §5。

**Phase 7 · 发 PR & 合并**
- 在 worktree 里完成实现、视觉验证和手册回写后,`scripts/wt-ship.sh ["PR title"]` 推分支、开 PR、
  上 auto-merge;**PR 同时含 前端 src + 切片 JSON + 重生成的 index.html**(若 Phase 2 改了 MVP1
  设计源,也一并带上)。你发出去的 PR 内容就是你验证过的那棵树——不需要再从脏工作区里挑 hunk。
  远端 `main` 仍 protected,不得直接 push。合并后 `scripts/wt-clean.sh <本分支>` 清理**自己这棵** worktree(只清自己命名的、绝不扫别人的),
  主仓根 `git pull` 让 5173 和对外手册网页刷新到最新;**PR 若改了依赖清单,主仓根还必须补装**
  (`package.json` 变 → `apps/studio/frontend` 里 `npm install`;`uv.lock` 变 → `uv sync`),
  否则跑着的主 app 在新依赖上直接红屏(「三、保留什么」第 4 条)。
- **合并后把主仓 app 备到「PM 能直接点验」= agent 的活,PM 不做任何机械步骤。** 这套收尾**全部我自己做完**,
  给 PM 的只有「在哪个界面、怎么点、该看到什么」——**绝不把 `git pull` / 补依赖 / 重建 vendor / 重启 app
  这类机械步骤列成 1/2/3 清单甩给 PM**(2026-07-02 教训:给 PM 发编号步骤 = 错)。完整收尾:
  1. 主仓根 `git pull`;
  2. 依赖清单变了 → `npm install` / `uv sync`(见上);
  3. **PR 动了 `packages/graph-agent`(engine)/ `packages/graph-agent-gateway`(gateway)源码
     (哪怕没碰 `pyproject.toml`/`uv.lock`)→ 必须重建 vendor**:桌面 app 的 sidecar 永远从冻结的
     `apps/studio/tauri/vendor/site-packages` import engine/gateway,不重建就跑旧 SDK(新字段被
     `extra_forbidden`、新参数 `TypeError`、bug 照旧),配方见 `AGENTS.md`「Workflow Pipeline」第 7 条
     (先关 app 免得 Windows 锁住 vendor `.pyd`/`.dll`,`build_vendor.py` + `compileall` 预热 `.pyc`);
  4. 按标准 launcher 重启 app(`scripts/studio-dev.ps1`),加载新的后端 `.py` + 新 vendor。
  做完这四步再 @ PM 点验。

**Phase 8 · 沉淀(同一次改动里,别只留对话)**
- 可复用**样式规则** → `FRONTEND_UI_SPEC.md`;**手册方法论/坑** → 方法论文档;**行为类教训** → 记忆。
- 报 done:自然语言 + 附**亲眼验证的截图/描述**,对齐「设计是什么 / 是否按设计做到 / 做完什么效果」三段;不问「是否继续」。
- **等 PM 收敛确认 · 报 done 必附「逐项 PM 验证清单」(强制格式)**:报 done 前**我自己**把主仓
  app 备到能直接点验的状态(Phase 7 完整收尾:pull + 补依赖 + engine/gateway 改动重建 vendor +
  重启 app)—— **机械准备步骤一律我做,绝不列成清单让 PM 执行**。给 PM 的只有一份**逐项验证清单**,
  让 PM 一条条照着点、不用回翻对话自己拼。硬性格式:**每条已合并的改动占一行**,四列写清——
  **① 界面路径**(点到哪一屏,如 `Settings → API Keys → Qiniu 卡`)· **② 操作**(点/填/hover
  什么)· **③ 预期**(该看到什么,具体到颜色/文案/数量)· **④ 状态**(`待确认` / `✅ 已确认`)。
  规矩:
  - **一条改动一行,不合并**:一屏能覆盖多条也要逐条列,别糊成一句话。
  - **只列验证步骤、不列机械步骤**:清单是"给 PM 点验的界面/操作/预期",**不是** pull/装依赖/
    重建 vendor/重启这类我该做完的机械收尾(那些一律我做,见 Phase 7)。
  - **跨多 PR 的会话要汇总**:清单覆盖**本会话所有**待 PM 确认项 + 已确认的存档一起列(标 ✅),
    PM 才能一眼看全、不漏验。
  - **PM 逐条确认完才算收敛**:**任一条没确认,任务就不算收敛**;PM 指出的问题在本任务内继续
    修(小修可直接开后续 PR,不另起任务)。PM 确认一条就把该行标 `✅ 已确认`。
  - 模板(逐行):`| # | 改动(PR) | ① 界面路径 | ② 操作 | ③ 预期 | ④ 状态 |`

---

### 纯手册任务(只动 `tpl-*.json` / build 脚本,不碰前端 src)
走 **Phase 0(读+用代码核对状态)→ Phase 5(改切片 + 重生成 + 生成自检)→ Phase 6(必要时发 PR)**;
跳过 Phase 2-4 的 src 实施与 npm 门禁(docs 改动不触发 `frontend-gates` 的 lint/build scope)。
但「视觉验证」仍要做——用 Playwright + `file://` 加载重生成的 `index.html`,亲眼确认状态点/徽章/截图渲染对了(本轮就靠这个抓到侧栏颜色)。

> 找不到下一步、或目标已达 → 直接报告「已完成 X,亲眼验证如下」,不问「是否继续」。遇到**真的拿不准的方向/取舍**(不是工程细节)才问你,且用文字罗列,不做选择题。
