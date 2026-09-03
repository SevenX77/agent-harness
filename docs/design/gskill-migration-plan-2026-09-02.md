---
doc: gskill-migration-plan-2026-09-02
status: drafted（2026-09-02 落盘；**方案整体待用户批准**，批准前不得开工其中任何一张 PR；§11 列出两个需用户明确授权的动作）
role: workflow-record
---

# 批C 搬迁执行方案：gateway 与 studio 整体迁入 graph-skill-runtime

> **本文是什么**：把已批决议 `docs/design/gskill-restructure-decision-2026-08-31.md` §4.3（决定 b：gateway 与 studio 整体迁入 `graph-skill-runtime`）落成一份**可执行、可复现核验**的搬迁方案。它规定目标形状、逐目录处置、PR 序列、门禁扩展、验收判据与明确不做项。
>
> **本文不是什么**：①**不是实施记录**——本文落盘时一行代码、一个文件都还没搬；②**不是进度状态**——「在做什么、到哪一步、被什么挡住」的唯一可变状态载体是 `docs/development/DELIVERY_LEDGER.md`（交付台账），本文不复制状态；③**不是模块设计变更**——搬迁不改 studio / gateway / engine 的任何行为，行为层面的重整属于后续批次（批D/批E/批F）。

**本文的名词约定（全文只用这一套指代，不另造代称）**：

- **主仓** = GitHub 仓库 `SevenX77/agent-harness`，即本文所在的仓库。
- **新仓** = GitHub 仓库 `SevenX77/graph-skill-runtime`，搬迁的目的地；决议 §11.5-1 已定该名不改，本方案**不含仓库改名项**。
- **monorepo**（单体仓库）= 一个 git 仓库里放多个可独立发布的包。决议 §4.3:174 原文：**包边界不等于仓边界**:同一个仓库里各包仍各自守住自己的膜,搬仓不放松任何模块边界。
- **uv workspace**（uv 工作区）= Python 包管理器 uv 的多包模式：一个仓库里多个 `pyproject.toml` 成员共用**一把** `uv.lock` 锁文件，成员之间以源码路径互相引用而不走 PyPI。主仓已是这个形状（`AGENTS.md:22` 原文：- **Python is one uv workspace** with a SINGLE root `uv.lock` shared by all）。
- **冻结旧 engine** = 主仓 `packages/graph-agent`（发行名 `graph-agent`，版本 0.3.1）。决议 §4.2 已把它定为只读镜像，§4.3 定它随迁、并在 Studio 切换门禁（§4.5 五条）全过后整包删除。
- **sidecar**（边车进程）= Studio 桌面应用启动的那个 Python 后端进程，由 `apps/studio/tauri/sidecar.rs` 拉起。
- **执笔席** = `docs/development/PARALLEL_ORCHESTRATION.md` §1.1 定义的席位：新建的、未继承协调方会话历史的后台 agent（Opus 5，xhigh，干净上下文），按自包含 brief 撰写权威正文，且不自审自己的产出。

**本文的决定编号（D1–D11）与所在节**：D1 目标形状 §3.1 · D2 历史处置 §3.2 · D3 命名 §3.3 · D4 冻结随迁 §3.4 · D5 钉版对齐 §3.5 · D6 逐目录处置 §4 · D7 CI 与分支保护 §6 · **D8 权威文档改写清单 §7** · D9 验收判据 §8 · D10 PR 序列 §5 · D11 明确不做 §10。编号连续、无空号。

## 1. 上位依据与本文的落点

本文落在决议 `docs/design/gskill-restructure-decision-2026-08-31.md` 的 **§4.3 + §4.4 + §11.5 + §11.7** 之下，并执行盘点交付物 `docs/design/gskill-restructure-inventory-2026-08-31/inventory-synthesis.md:174` 的要求（该行原文：血止批 Opus(xhigh)≤2 worktree、一单一 PR、TDD、codex 审 diff 后放行——已开工。批B/B′ 随后;批C 搬迁出独立执行方案(结构性变更,先呈)。每模块六步管线+DoD 五锁;真机点验串行占 `cdp-9222`。真机待验:白窗采样、无 CORS 500 打包复现、gemini ImportError、golden 空洞通过实跑、删 route 快照存档(脱敏)。）。

| 上位依据 | 原文（逐字，坐标见左列） | 本文落点 |
|---|---|---|
| 决议 `:168`（§4.3） | gateway 与 studio **整体搬入** `graph-skill-runtime`,该仓成为 monorepo,内部分工: | §3.1（D1） |
| 决议 `:174`（§4.3） | **包边界不等于仓边界**:同一个仓库里各包仍各自守住自己的膜,搬仓不放松任何模块边界。 | §3.1（D1） |
| 决议 `:178`（§4.3） | **过渡安排(显式迁移,带退出条件)**:把**冻结的旧 engine 包(v0.3)随迁**,供 studio 在切换完成前继续使用;**Studio 切换门禁(§4.5)全部通过后,整包删除**。这不违反"不做向后兼容"——它是一次**显式声明、带明确退出条件**的迁移,不是长期并存的双读路径。 | §3.4（D4） |
| 决议 `:180`（§4.3） | `agent-harness`(本仓)在迁移完成后**归档为只读**。 | §5 的 C-4、§11 授权点二 |
| 决议 `:186`（§4.4-3） | 3. **复刻 CI / 分支保护 / 门禁。** 目标仓必须先具备与本仓等强度的门禁(必过检查、`main` 只能通过绿色 PR 进入),否则搬进去的代码立刻失去约束。 | §2 前置条件核对 |
| 决议 `:573`（§11.5-1） | 1. **主仓名 = `graph-skill-runtime`**(GitHub repository `SevenX77/graph-skill-runtime`),**早已命名,不改**;批C 不含"仓库改名"项。新仓 `docs/design/v1-alignment.md` §2.1 工作名表**整表维持**——GitHub repository / PyPI distribution / Display name / Python import 取 `graph-skill-runtime` 族,console command 与 MCP namespace 取 `gskill`,两半都与用户裁决同向,**无需重写**。 | §10 明确不做 |
| 决议 `:575`（§11.5-3） | 3. **gateway 与 studio 带 `gskill` 词缀短名**(如 `gskill-gateway`、`gskill-studio`);精确拼法(前缀还是后缀、连字符还是下划线、各 registry 上的具体标识符)由批C 定。 | §3.3（D3） |
| 决议 `:577`（§11.5-5） | 5. **对 §4.4-2 的影响**:「包名裁决」的选名与复核**均已完成**;批C 的该项前置**已满足**。 | §2 前置条件核对第 2 条 |
| 决议 `:606`（§11.7-1） | 1. **不移植历史**:`gskill` 主仓,以及搬入的 gateway 与 studio,**一律不 graft、不 `subtree --with-history`、不 filter-repo 回灌**;搬入即为**新提交**,干净起步。 | §3.2（D2） |
| 决议 `:607`（§11.7-2） | 2. **权威文档全部重写**:**不搬运旧文正文**;旧文**只作证据引用**(引用时给路径与行号,并按 §2.3 三道检验对待)。 | §4.1.1、§7（D8） |
| 决议 `:610`（§11.7-5） | 5. **落点**:批C(搬迁)方案必须按本条写,并在呈批时附**权威文档重写清单**(哪些文档在新仓重写、各由谁执笔、以哪些旧文为证据)。 | §7（D8） |
| 决议 `:624`（§11.8-3） | 3. **批C(搬迁)仍须先呈完整方案**——它是结构性变更,按既有工作规则必须先呈方案、用户确认后再动手,**不因本条自动开工**。 | §2 开工门 |
| 盘点 `inventory-synthesis.md:124` | ### 批C · 搬迁(§4.4 顺序固定):113 落 main → 命名裁决(§8-5)→ 目标仓 CI/分支保护/必过检查生效 → gateway+studio 整体迁入,**旧 engine 冻结随迁**(§4.3:显式迁移带退出条件;五门禁全过后整包删除)→ 主仓归档只读。搬迁不改行为;验收=迁后全门禁绿+打包链可跑。 | §8 验收判据 |
| 主仓 `AGENTS.md:366` | - **MVP1 design = source of truth — align to the design, NOT the code.** When the | §4.1.1 的 (c) 类判据 |

主仓 `AGENTS.md`「Development Principles」另定三条贯穿要求，本文逐条遵守：不做向后兼容、第一性原理修复而非打补丁、以及「先看成熟工程怎么解，再决定自己怎么写」——后者要求写明**参照对象、借了什么、拒绝了什么、为什么**，本文每一个引入新机制的决定（D1/D2/D4/D6）都按这四段写，见 §12 的参照汇总。

## 2. 前置条件核对（决议 §4.4，逐条给证据）

**第 1 步「新仓 113 个未提交文件先落 main」——已收口。** 证据：交付台账 `docs/development/DELIVERY_LEDGER.md:21` 有一段原文：**批B 前置「113 落 main」**以封存分支 `sealed/113-unified-agent-kit` 收口（130 文件与已批裁决冲突，全部封存，新仓 main 未动）。。收口形式是**封存**而非合入：那批文件与已批裁决冲突，落 main 会把冲突内容变成基线。决议 §4.4-1 要的是「未提交的工作树内容不构成可被引用的基线」，封存达成同一目的——工作树已清空，新仓 main 是唯一基线。

**第 2 步「包名裁决」——已完成。** 证据：决议 `:577` 原文见 §1 表。占名与商标复核证据归档在 `docs/design/gskill-restructure-inventory-2026-08-31/name-clearance-2026-09-01.md`。§11.5-3 交给批C 的只剩**精确拼法**，由 §3.3 定。

**第 3 步「复刻 CI / 分支保护 / 门禁」——已生效。** 证据：2026-09-02 协调方实测
`env -u GITHUB_TOKEN gh api repos/SevenX77/graph-skill-runtime/branches/main/protection`，结果为：必过检查 = `quality-gates`、`runtime-tests (3.11)`、`runtime-tests (3.12)`、`runtime-tests (3.13)`、`cross-platform-smoke (windows-latest)`、`cross-platform-smoke (macos-latest)` 共 6 项；`required_linear_history = true`（禁止合并提交）；`enforce_admins = true`（管理员不豁免）。

**第 4 步「整体迁移」——本方案。** 其**开工门**是交付台账 gskill 工单表里「批C 搬迁方案」一行 `前驱` 列所列 17 个工单全部为 ✅ 已合并（本文不复制这些状态，台账是唯一载体）。**开工门之外还有批准门**：决议 `:624` 原文见 §1 表——批C 是结构性变更，未获用户批准前不得开工。

## 3. 目标形状

### 3.1 D1 · 新仓变成 uv workspace，runtime 留在仓根当 workspace 根包

**决定**：新仓根 `pyproject.toml` 保持 `name = "graph-skill-runtime"`、hatchling 的 `packages = ["src/graph_skill_runtime"]` 不变，新增：

```toml
# C-1 落地时的形状：成员名与目录名一律沿用主仓原样（改名归 C-2）
[tool.uv.workspace]
members = ["packages/*", "apps/studio/backend"]

[tool.uv.sources]
graph-agent = { workspace = true }
graph-agent-gateway = { workspace = true }
studio-backend = { workspace = true }
```

C-2 改名后，后两个键随发行名变为 `gskill-gateway` 与 `gskill-studio`，`members` 里的 `apps/studio/backend` 变为 `apps/gskill-studio/backend`（§3.3）。整仓共用一把根 `uv.lock`，四个成员一次解出（实测形状与结果见 §9.1）。

**依据**：决议 §4.3 要求 runtime 包保持精瘦、可独立发布的身份。这条身份由**发布产物**定义，而发布产物的内容由 hatchling 的 `packages` 白名单决定，与仓里有几个 workspace 成员无关——因此把 runtime 留在仓根、同时让它当 workspace 根包，既满足 monorepo 要求，又让新仓现有的 `release.yml`（release published → build → 三平台 verify → publish-to-pypi）**零改动**。

**成熟工程参照**：**参照对象** = uv 官方 workspace 模型（允许根 project 同时是成员）与 langchain monorepo（`libs/*` 为成员、单一锁文件）。**借**其「一仓一锁、成员各自持有自己的 `pyproject.toml`」——主仓已经在跑这个形状（`AGENTS.md:22`），搬迁因此不引入新的依赖管理范式。**拒绝**其「根包是虚包（只有 workspace 声明、没有源码）」这一半。**为什么**：采用虚包就必须把 runtime 从仓根搬进子目录，连带改 `release.yml` 的构建路径、`[project.urls]` 与 README 安装说明，而收益为零。

**为什么必须和搬迁在同一张 PR 里**：新仓当前 `pyproject.toml` 没有 `[tool.uv.workspace]`（2026-09-02 实测）。没有它，搬进来的三个 `pyproject.toml` 不被任何锁文件覆盖，`uv sync` 装不出 studio 的依赖，CI 的任何一个 Python job 都跑不起来——即 C-1 自己过不了门。

### 3.2 D2 · 历史：squash 导入 + 出处 trailer，不做历史合并

**决定**：搬迁提交是新提交，不接主仓历史。导入提交的提交信息里带三行出处标记（trailer，即提交信息末尾 `Key: value` 形式的机器可读字段）：

```
Source-Repo: https://github.com/SevenX77/agent-harness
Source-Commit: <C-1 开工时主仓 main 的 40 位全哈希>
Source-Paths: <本文 §4 处置表的源→目标路径映射>
```

**依据**：①决议 `:606`（§11.7-1）已裁不接历史（原文见 §1 表）；②实测约束：新仓 main `required_linear_history = true` 且只允许 squash 合并，带 `--allow-unrelated-histories` 的合并提交在物理上无法经 PR 落 main——要接历史就得临时放开分支保护；③主仓归档只读后完整历史仍可查，`git log -S` 式考古去归档仓做。

**成熟工程参照**：**参照对象一** = Kubernetes 的 publishing-bot（把 `kubernetes/kubernetes` 的 staging 目录发布成 `k8s.io/client-go` 等独立仓）。其 README（<https://github.com/kubernetes/publishing-bot>）原文：

> It records the SHA1 of the last cherrypicked commits in `Kubernetes-sha: <sha>` lines in the commit messages.

**参照对象二** = `git subtree` 的 `--squash`，其文档（`contrib/subtree/git-subtree.adoc`，OPTIONS FOR 'add' AND 'merge'）原文：

> Instead of merging the entire history from the subtree project, produce only a single commit that contains all the differences you want to merge, and then merge that new commit into your project.

**借**：两者共有的那一半——**把跨仓搬运压成单个提交，同时在提交信息里留一个机器可读的源提交指针**，使「这批文件从哪来、对应源仓哪个提交」永远可回答。本文的 `Source-Commit:` 就是 `Kubernetes-sha:` 的同形字段。**拒绝**：`git subtree` 不带 `--squash` 时的真正历史移植（会产生跨仓合并提交），以及 publishing-bot 的持续双向同步（它服务的是长期并存的镜像关系）。**为什么**：前者与新仓的线性历史保护冲突，后者与决议 §4.3「主仓迁移完成后归档为只读」冲突——本仓要的是一次性搬完即封，不是长期镜像。

### 3.3 D3 · 命名：精确拼法

决议 `:575`（§11.5-3）把精确拼法交给批C。**决定**如下：

| 对象 | 取值 | 理由 |
|---|---|---|
| gateway 发行名（PyPI distribution） | `gskill-gateway` | **前缀**：`gskill` 是产品短名，做命名空间用，同 `langchain-openai`／`langchain-anthropic` 惯例——前缀让同族包在按名排序的列表里聚成一块。**连字符**：PEP 503 的规范化形式，下划线在 PyPI 上会被归一成连字符，直接用规范形式避免两种写法并存 |
| studio 发行名 | `gskill-studio` | 同上 |
| gateway 目录 | `packages/gskill-gateway` | 目录名与发行名一致，免去「目录叫一个名、包叫另一个名」的二次查表 |
| studio 目录 | `apps/gskill-studio`（其下仍为 `backend` / `frontend` / `tauri` / `tests-e2e`） | 同上；`apps/` 与 `packages/` 的分工承载决议 §4.3「studio 是应用（app），不是库」 |
| gateway Python import 名 | `gskill_gateway` | Python 包名不能带连字符，下划线是唯一合法形式 |
| studio Python import 名 | **保持 `app`，不改** | studio 是应用不是库，它的顶层模块不作为公开 import 身份被外部引用 |
| Tauri `productName` 与 Display name | `gskill Studio` | 与产品短名一致 |
| 冻结旧 engine 的发行名与 import 名 | **保持 `graph-agent` / `graph_agent`，不改** | 它在批E 整包删除，改名只是一次无收益改动 |

**执行时点（本条同样是决定）**：**C-1 逐字节保留原路径与原名，改名单独成 C-2 做纯机械重命名。**

理由：盘点 `:124` 要求「搬迁不改行为」，而「不改行为」要能被**机械核验**才算数——C-1 的验收判据是源文件与目标文件 sha256 相等（§8.1-①）。把改名混进 C-1，每个文件内容都变，核验就从「哈希相等、0 差异」退化成「人工审两千余个文件的 diff」。附带收益：git 的 rename 检测在「纯移动」与「纯改名」分成两步时最可靠。

### 3.4 D4 · 冻结旧 engine 的随迁形状：源码 + 测试 + 契约清单一起搬，`graph-agent-tests` 保留为必过门

**决定**：`packages/graph-agent` 除 9 个误提交裸文件与 `tools/dual_run_shadow.py` 外**整包随迁**——`pyproject.toml`、`README.md`、`src/**`（124）、`tests/**`（340）、`spec/**`（4）、`scripts/**`（1），共 471 个文件；版本号 `0.3.1` 不动；主仓 CI 的 `graph-agent-tests` job **原样移植到新仓并保持必过**，直到批E 删除整包时与包一起删；同时用一条**树哈希锁**把「冻结」做成门禁，锁的覆盖范围**包含 `tests/**`**。

**依据（协调方 2026-09-02 依据「因果验证」原则裁定）**：**源码不变不等于行为不变。** 冻结包与其余三个成员共用同一把 `uv.lock`，批D 的任何依赖变更、任何一次安全升级，都会换掉它脚下的 langchain / langgraph / pydantic；树哈希只锁住这个包自己的字节，锁不住它的依赖闭包。要证明「行为没变」，唯一可观察的因果证据是**它自己的测试在新的依赖闭包下仍然全绿**——间接覆盖（studio 测试经 adapter 打到它）、构建成功（`build_vendor.py` 打出 wheel）、导入成功（`verify_installed_sidecar.ps1:136` 的 `import graph_agent` 探针）都只证明「装得上、进得去」，不证明「算得对」。

**树哈希锁的形状**：新仓新增 `tests/test_frozen_engine_hash_lock.py`，对 `packages/graph-agent` 下全部跟踪文件按路径排序、逐文件算 sha256（行尾按 LF 归一化后再算，避免 Windows 检出把 CRLF 混进哈希），与一份 seal（钉值）记录比对；任何漂移即红，失败信息自带重钉命令。seal 记录沿用新仓 `tests/contract-seals.yaml` 的同款机制——该机制由工单 F-T3（新仓 PR #22，合并提交 `a4f43d83`）**已经落地**，本方案直接复用，不新造一套。**锁必须覆盖 `tests/**`**：否则「改测试」就成了让门变绿的合法路径，冻结形同虚设。**放宽这把锁的唯一合法路径是删除整包**，即批E 的 X-T1b。

**成熟工程参照**：**参照对象** = Go 的 vendor 机制。`go mod vendor` 生成的清单文件与校验命令构成一对：Go Modules Reference（<https://go.dev/ref/mod>）原文——

> `go mod vendor` also creates the file `vendor/modules.txt` that contains a list of vendored packages and the module versions they were copied from.

> When the `go` command reads `vendor/modules.txt`, it checks that the module versions are consistent with `go.mod`.

`go mod verify` 的命令帮助（<https://pkg.go.dev/cmd/go>）原文：

> Verify checks that the dependencies of the current module, which are stored in a local downloaded source cache, have not been modified since being downloaded. If all the modules are unmodified, verify prints "all modules verified." Otherwise it reports which modules have been changed and causes 'go mod' to exit with a non-zero status.

**借**：**「一份内容清单 + 一条把漂移变成硬错误的校验」**——不是靠口头约定「大家别改」，而是让任何字节变动直接让命令以非零状态退出。本文的 seal 记录对应 `modules.txt`，`test_frozen_engine_hash_lock.py` 对应 `go mod verify`。**拒绝**：Go 那套「清单由工具重新生成即可修复」的宽松语义。**为什么**：`go mod vendor` 重新生成清单是正常工作流（依赖本来就会升级），而本仓的冻结包**不允许**正常演进——它只有「不变」和「整包删除」两种合法终局，所以重钉必须是一次**带记录的显式动作**，不是一条随手可跑的刷新命令。

**不搬的两处**：①9 个误提交裸文件——`e1.txt`、`e2.txt`、`e3.txt`、`err.txt`、`err2.txt`、`hb`、`owner`、`owner2`、`lk/owner`（2026-09-02 实测 `git ls-files packages/graph-agent | grep -v -E '/(src|tests|spec|tools|scripts)/'`，除去 `README.md` 与 `pyproject.toml` 后即这 9 个）；②`tools/dual_run_shadow.py`——2026-09-02 实测 `git grep -n 'graph-agent/tools'` 在 `.github`、`apps`、`packages`、`scripts` 下 0 处引用。两者同一条判据：**没有任何消费者**。

**随迁的连带项（由本决定机械推出，不是另一个决定）**：`packages/graph-agent/tests` 读取包外两处路径，不搬它们 `graph-agent-tests` 就是红的——

| 被读取的路径 | 读取点（实测坐标） | 文件数 |
|---|---|---|
| `code-diagnostics/**` | `packages/graph-agent/tests/core/test_code_health_metrics.py:18,23,30,42`（`parents[4]` 上溯到仓根后拼 `code-diagnostics/build_tree.py`、`run_static_audit.py`） | 6 |
| `config/**` | `packages/graph-agent/tests/integration/test_mvp1_smoke.py:70`（`REPO_ROOT / "config" / "llm_roles.yaml"`） | 2 |

`packages/graph-agent/scripts/validate_round28_manifest.py` 同理**必须随迁**：它既是主仓 `graph-agent-tests` job 的一步（`.github/workflows/ci.yml:127`），又被 `packages/graph-agent/tests/test_round28_contract_manifests.py:21` 当作被测对象读取。

### 3.5 D5 · 搬迁前在主仓先做「钉版对齐」

两把锁合成一把，依赖解析结果必然变化——这是搬迁唯一不可避免的行为面改动。处理方式是把它**隔离到搬迁之前、在主仓用主仓的门禁证明**，使 C-1 只承担「文件从哪到哪」这一件事。

**C-0a**：主仓 `packages/graph-agent-gateway/pyproject.toml:9` 把 `langchain-openai` 从 `>=1.1.7,<1.3.0` 钉到 `>=1.3.5,<1.4.0`。依据见 §9.1 的探针：不加这一钉，四成员 workspace **根本解不出锁**。

**C-0b**：主仓用合锁后的解析结果重解 `uv.lock`（§9.1 的版本表），跑通 studio backend、gateway 与 graph-agent 的全套门禁。**若红，就在主仓修到绿**——这些是既有的潜在不兼容，不是搬迁引入的，在源仓修才有源仓的测试套件与真机环境可用。**C-0b 的前驱是 C-0a，两者不可并行**（理由见 §5 表注）。

## 4. D6 · 逐目录处置表

**怎么读这张表**：

- **「逐字节搬」**= C-1 里源文件与目标文件内容完全相同，由 §8.1-① 的哈希脚本机械核验（0 差异）。
- **「C-1 合并/新建」**= 该文件在 C-1 里内容必须变化，否则 C-1 自己过不了门（依赖解析、忽略规则、CI 定义）。这些文件不进哈希核验，改由 §8.2-⑧ 的人证判据证明。
- **「留」**= 不搬，留在归档后的主仓；需要时按归档坐标 `agent-harness@<Source-Commit>:<路径>:<行号>` 作证据引用。
- **一条贯穿规则**：凡内容需要改写、但改写本身不是 C-1 过门必要条件的文件（如 `CLAUDE.md` 的指向、`.ah/` 里的路径引用），**C-1 先逐字节搬入、改写归 C-3**。这样 C-1 的哈希核验没有例外。
- **所有计数由 `scripts/` 下的一支脚本机械复现**，脚本正文与运行输出见 §13 附录 A；本节的每个数字都出自那次运行，不是手工加总。

### 4.1 逐字节搬（C-1，共 2015 个文件）

| 源路径（主仓） | 目标路径（新仓，C-1 时） | 文件数 | 说明 |
|---|---|---|---|
| `apps/studio/**` | 同路径 | 1212 | frontend 715 / backend 443 / tauri 45 / tests-e2e 9 |
| `packages/graph-agent-gateway/**` | 同路径 | 140 | gateway 包全量（src 61 + tests 77 + 2） |
| `packages/graph-agent/{pyproject.toml,README.md,src,tests,spec,scripts}` | 同路径 | 471 | 冻结 engine，见 §3.4 |
| `docs/**` 的 (a)(b) 两类 | 同路径 | 127 | **不整搬**；三类分法见 §4.1.1 |
| `scripts/**` | 同路径 | 18 | worktree/PR 流水线、并行黑板、交叉审脚本 |
| `.claude/skills/**` | 同路径 | 26 | shadcn 15 + studio-verify 11；后者是真机验证的唯一方法 |
| `code-diagnostics/**` | 同路径 | 6 | 冻结 engine 测试读它，见 §3.4 连带项 |
| `.ah/**` + `ah.toml` | 同路径 | 10 | 多 agent 编排实例；**路径引用校正归 C-3** |
| `config/**` | 同路径 | 2 | 同上 |
| `skills-lock.json` | 同路径 | 1 | `.claude/skills` 的版本锁 |
| `.pre-commit-config.yaml` | 同路径 | 1 | 提交前钩子 |
| `CLAUDE.md` | 同路径 | 1 | **改指向新仓 `AGENTS.md` 归 C-3** |

#### 4.1.1 `docs/**` 分三类处置：**不整搬**

决议 `:607`（§11.7-2）原文：2. **权威文档全部重写**:**不搬运旧文正文**;旧文**只作证据引用**(引用时给路径与行号,并按 §2.3 三道检验对待)。；`:610`（§11.7-5）要求本方案附权威文档重写清单（§7）。主仓 `AGENTS.md:366` 另定：- **MVP1 design = source of truth — align to the design, NOT the code.** When the——`docs/studio/mvp1/**` 与 `docs/graph-agent-gateway/mvp1/**` 正是该条点名的目标设计真相载体（`AGENTS.md:374` 原文：V4 target design = truth) next to `baseline.md` (current / migration state):）。**因此这两棵树属第 (c) 类，不搬。**（协调方 2026-09-02 依据决议 `:607` 与 `AGENTS.md:366` 裁定，推翻本文初稿把它们归入「门禁数据」的写法。）

439 个文件按**在新仓里的身份**分三类：

**(a) 记录类——逐字节搬（110 个文件）。** 它们记录「某时某人裁了什么、发现了什么」，是**事实记录而非设计权威**；重写记录等于伪造历史。

| 路径 | 文件数 |
|---|---|
| `docs/design/**`（决议、盘点、审计与决策记录） | 88 |
| `docs/studio-mvp1-execution/**` | 9 |
| `docs/handoffs/**` | 4 |
| `docs/engine/graph-skill-runtime/**`（`README.md` / `baseline.md` / `v1-alignment.md`，记录的是新仓本身） | 3 |
| `docs/pr-reports/**` | 2 |
| `docs/development/DELIVERY_LEDGER.md`、`docs/development/PROBLEM_LEDGER.md` | 2 |
| `docs/references/**` | 1 |
| `docs/deferred-items.md` | 1 |

**(b) 数据类——逐字节搬（17 个文件）。** 判据窄且唯一：**随迁的生产代码或随迁的测试在运行时按路径读取它**（不是在注释、docstring 里引用它）。逐条列出消费者：

| 文件 | 消费者（实测坐标） | 文件数 |
|---|---|---|
| `docs/development/llm_provider_notes/**` | **生产代码** `apps/studio/backend/app/services/llm_notable_models.py:13`（`parents[5]` 上溯拼路径）；索引键由 `apps/studio/backend/app/data/provider_identity.json:2` 与 `app/services/provider_config.py:7` 定义 | 10 |
| `docs/development/design-doc-standards/**` | `apps/studio/backend/tests/docs/test_design_doc_standards_governance.py:101`（`ROLE_REQUIRED_ROOTS` 之一）、`:108`（`EXAMPLE_ROOT`）、`:370`（断言 `example/` 非空） | 5 |
| `docs/development/STUDIO_REQUEST_AUDIT.md` | `apps/studio/backend/tests/docs/test_studio_request_audit_ledger.py:150,161`、`test_ledger_tables_hold_their_shape.py:100` | 1 |
| `docs/graph-agent-gateway/USAGE.md` | `packages/graph-agent-gateway/tests/test_gateway_docs_name_real_files.py:29`（`_DOCS` 元组成员，逐行核对文中提到的 Python 路径与符号真实存在） | 1 |

清单的产出方式（可复现）：在 §4.1「搬」列的代码/测试/脚本里跑
`git grep -nE '(DOCS_ROOT|/ *"docs|docs/)' -- <搬列路径> ':!*.md'`，取其中**构成路径读取**的每一条（判据：该行把字符串拼进 `Path` 或传给 `open`/`read_text`/`rglob`），再展开成文件清单。注释、docstring 里的「Design: docs/…」不算——2026-09-02 实测这类出处标注在 `apps/studio` 与两个 package 下有 11 个测试文件、10 个生产文件命中，它们随代码搬走后引用的是**归档仓的旧文**，不构成随迁需求。

**(c) 权威文档——不搬、重写（312 个文件）。** 清单、执笔席与证据来源见 §7。它们在新仓落地之前，新仓正文引用这些设计源时**一律写归档坐标**（`agent-harness@<Source-Commit>:<路径>:<行号>`），这正是决议 `:607` 括号里要求的引用形式。

**这三类的边界为什么是这样**：决议 `:607` 禁止的是「把旧的设计权威正文原样搬过去继续当权威」；它没有、也不能禁止搬运**事实记录**（(a)：重写记录即伪造）与**被代码按路径读取的数据**（(b)：不搬则随迁的代码自己就是坏的）。三类都以「在新仓里它是什么身份」为唯一判据，不以目录形状为判据。

**成熟工程参照**：**参照对象** = Python 的 PEP 体系。PEP 1（<https://peps.python.org/pep-0001/>）原文：

> In general, PEPs are no longer substantially modified after they have reached the Accepted, Final, Rejected or Superseded state. Once resolution is reached, a PEP is considered a historical document rather than a living specification.

**借**：**把「历史文档」与「活规范」当成两种不同载体分开处置**——前者定稿后不再实质修改，后者随系统演进而重写。本文的 (a) 类对应「historical document」（决议、盘点、审计报告、台账），(c) 类对应「living specification」（模块设计体、开发 SOP）。**拒绝**：PEP 用 `Superseded-By` / `Replaces` 头把新旧串成链、旧文永久留在同一个仓里这一半。**为什么**：PEP 服务的是一个公开、长期、必须可追溯的标准流程；本仓的旧设计体在批D 重写后就没有读者了，把它留在新仓只会制造「两份都在、不知道该信哪份」的第二真相源——它的追溯需求由归档仓 + 归档坐标满足，这是决议 §11.7-3 已定的方案。

（**另一个候选参照未采用**：Kubernetes 的 KEP 与 kubernetes.io 用户文档的分工。2026-09-02 读 <https://github.com/kubernetes/enhancements/blob/master/keps/README.md>，其中只有「Our aim with KEPs is to clearly communicate new efforts to the Kubernetes contributor community.」一类表述，**找不到**「KEP 是提案记录、不是文档」的明文，证不成，故不引。）

**门禁暂缺表（显式迁移，不是静默丢门）**：这两棵树不搬，随迁的测试里凡**按路径读取它们**的用例在 C-1 里删除，并在此登记复位工单。判据是「读取」而非「引用」——2026-09-02 实测 `git grep -l 'docs/studio/mvp1\|docs/graph-agent-gateway/mvp1' apps/studio/backend/tests packages/graph-agent-gateway/tests` 命中 19 个文件，其中 13 个只在 docstring 里写「Design: …」，**原样保留不动**；真正读取的是下面 6 个：

| C-1 里删除的用例 | 它守的是什么 | 批D 复位工单 |
|---|---|---|
| `apps/studio/backend/tests/docs/test_doc_code_references_exist.py`（整文件：`_governed_docs()` 断言 `baseline.md`/`mvp1-alignment.md` 载体非空，两棵树不在则该断言必假） | 权威设计文档里的代码路径引用必须解析得到 | 批D-studio-1：新设计体落地后重建该门 |
| `apps/studio/backend/tests/docs/test_design_doc_standards_governance.py` 的 `ROLE_REQUIRED_ROOTS` 中 `docs/studio/mvp1` 一项、`test_summary_role_names_an_authority_file_that_exists`、`test_at_least_one_real_summary_role_exists`（其余用例保留，仍守 `design-doc-standards/**`） | 设计文档的 `status:`/`role:` 落在闭集、`summary` 必须指向真实权威 | 批D-studio-2 |
| `apps/studio/backend/tests/test_doc_hash_lock.py`（整文件） | `audited-ready` 文档的哈希锁 | 批D-studio-3 |
| `apps/studio/backend/tests/test_design_unit_lock_snapshot.py`（整文件） | 设计单元索引与锁快照一致 | 批D-studio-4 |
| `packages/graph-agent-gateway/tests/test_gateway_doc_locks.py`（整文件） | gateway 设计体的哈希锁与单元快照 | 批D-gateway-1 |
| `packages/graph-agent-gateway/tests/test_gateway_design_units_bind_real_code.py`（整文件） | 每个 gateway 设计单元绑定真实代码 | 批D-gateway-2 |

这张表是**显式迁移的退出条件**：批D 每重写完一棵设计树，对应工单必须把门装回去；表未清零前，新仓 `AGENTS.md` 由 C-3 写明「设计文档治理门禁暂缺，正在批D 复位」。

### 4.2 C-1 里合并 / 新建的文件

| 文件（新仓） | 处置 | 理由 |
|---|---|---|
| `pyproject.toml` | 加 `[tool.uv.workspace]` + `[tool.uv.sources]`；把主仓 `.importlinter` 的两条契约并入既有的 `[tool.importlinter]`（`root_packages` 追加 `graph_agent` 与 `app`） | §3.1；两条契约实测为「SDK cannot depend on Studio application code」与「Studio cannot bypass the public SDK boundary」，它们守的正是搬迁后同仓共处最容易被越过的边界 |
| `uv.lock` | 四成员重解，形状与结果见 §9.1 | §3.1 |
| `.gitignore` | 与主仓版**合并**：并入 `.worktrees/`、前端 `src/lib/*` 白名单、vendor 产物、playwright 产物；保留新仓的 `.gskill/` | 新仓版仅 14 行；漏掉前端 `src/lib/*` 白名单会让新增文件被静默忽略——本地 tsc 过、CI 全新检出失败 |
| `.gitattributes` | 与主仓版**合并**：并入 `.ps1`/`.bat` 的 CRLF 例外与 binary 段；新仓版仅 8 行且没有这两项 | PowerShell 启动脚本被检出成 LF 会在 Windows 上行为不确定；binary 段缺失会让截图等二进制文件被当文本处理 |
| `.editorconfig` | 与主仓版**合并** | 同上一类 |
| `codecov.yml` | 新仓版追加 `backend`、`gateway` 两个 flag | 覆盖率分包可见，否则四个成员的覆盖率被搅成一个数字 |
| `.sonarcloud.properties` | **取主仓版** | 主仓版含 Python + TypeScript 双语规则；搬入前端后新仓必须能扫 TS |
| `.github/workflows/ci.yml` | 扩 job，见 §6 | C-1 自身要过门就必须先有跑 studio/gateway/engine 的 job |
| `.github/workflows/package.yml` | 从主仓移植（按路径触发，非必过） | 「打包链可跑」是盘点给批C 的验收项之一 |
| `tests/test_frozen_engine_hash_lock.py` + seal 记录 | 新建 | §3.4 |
| `LICENSE` | **不动**：两仓的 `LICENSE` 是同一个 git blob（2026-09-02 实测两侧 blob sha 均为 `c7ed1e4abe5749619a5a11534f10fbbb32de75df`，Apache-2.0） | 同一份文件无所谓搬不搬 |

### 4.3 留在归档仓（不搬，836 个文件）

| 路径 | 文件数 | 不搬的依据 |
|---|---|---|
| `.kiro/**` | 484 | 2026-09-02 实测 27 处引用**全部**在 docstring/注释里做出处标注，无任何路径读取 |
| `docs/**` 的 (c) 权威文档类 | 312 | §4.1.1；在新仓**重写**而不是搬运，清单见 §7 |
| `graph-agent-explainer/**` | 14 | 0 处引用（1.8 MB 截图） |
| `services/community-catalog-gate/**` | 12 | 0 处引用 |
| `packages/graph-agent/` 的 9 个裸文件 + `tools/dual_run_shadow.py` | 10 | §3.4：无任何消费者 |
| `Makefile` | 1 | 唯一 target `dev-tunnel` 已经是脚本 |
| `CHANGELOG.md` | 1 | 主仓自己的变更历史，随主仓归档 |
| `tools/fix_imports.py` | 1 | 一次性迁移脚本，0 处引用 |
| `.agents/` | 1 | 0 处引用 |

### 4.4 账目闭合

**2015（逐字节搬）+ 836（留）+ 11（根级配置/权威文件，按 §4.2 逐份处置）+ 6（`.github/**`）= 2868**，等于 `git ls-tree -r --name-only 377e82e0 | wc -l` 的实测值。

- **11 个根级文件**：`uv.lock`、`AGENTS.md`、`pyproject.toml`、`.gitignore`、`.gitattributes`、`.importlinter`、`codecov.yml`、`.sonarcloud.properties`、`.editorconfig`、`README.md`、`LICENSE`。（另外 4 个根级单文件 `CLAUDE.md`、`skills-lock.json`、`ah.toml`、`.pre-commit-config.yaml` 已计入「逐字节搬」，`Makefile`、`CHANGELOG.md` 已计入「留」。）
- **6 个 `.github` 文件**：`ci.yml` 扩 job、`package.yml` 移植（均见 §6）；`CODEOWNERS` 由 C-3 追加条目（§7）；`dependabot.yml`、`codeql.yml`、`scorecard.yml` 新仓已有同等配置——2026-09-02 实测两仓 `dependabot.yml` 语义相同，均只覆盖 pip 与 github-actions 两个生态——主仓副本不搬。
- **零重叠、零遗漏由脚本断言**：附录 A 的脚本对四个桶做 `uniq -d` 重叠检查并比对全集，任一文件落入两桶即非零退出。**两处误差互相抵消是本方案明确要防的失败形态**，所以判据不是「总数对上」，而是「四桶并集 == 全集 且 两两不交」。

> 上述文件数是 2026-09-02 在主仓提交 `377e82e0` 上的实测快照。主仓 `main` 此后仍在推进（本文落盘时已到 `6547029e`，2872 个文件），因此 §8.1-① 的哈希核验以 **C-1 开工当时主仓 main 的实际哈希**为 `Source-Commit`，不以 `377e82e0` 为准。处置表按目录与身份给规则，快照之后新增的文件按同一套规则归类——例如 `docs/development/PARALLEL_ORCHESTRATION.md`（主仓 #1096 合入，晚于快照）是开发 SOP，落入 (c) 类由 C-3 重写。**C-1 实施方必须在开工当时的 `Source-Commit` 上重跑附录 A 的脚本，把四桶计数贴进 PR 正文。**

## 5. D10 · PR 序列

每张 PR 遵守既有交付纪律：一任务一 worktree、PR-only、codex（GPT-5.6-sol，xhigh）交叉审、裁决贴 PR 评论首行 `交叉审 r<N>:approve|rework`。

| 编号 | 仓 | 范围 | 前驱 | 门（合并条件） | 交叉审的审查对象 |
|---|---|---|---|---|---|
| **C-0a** | 主仓 | gateway `pyproject.toml:9` 把 `langchain-openai` 钉到 `>=1.3.5,<1.4.0` | 台账 17 个前驱全绿 + 用户批准本方案 | 主仓 7 道必过检查 | 单行 diff + §9.1 探针结论 |
| **C-0b** | 主仓 | 按合锁解析结果重解主仓 `uv.lock`；跑通 backend、gateway、graph-agent 全套门禁，红则在主仓修到绿 | **C-0a**（不可并行，见表注） | 主仓 7 道必过检查 | 锁文件版本跳变清单 + 为修红所做的每一处改动 |
| **C-1** | 新仓 | 一张 squash PR：文件导入（§4.1）+ workspace（§3.1）+ 合锁 + CI 扩展（§6）+ 冻结锁测试（§3.4）+ 三份忽略/属性文件合并（§4.2）+ 门禁暂缺表所列用例的删除（§4.1.1） | C-0a、C-0b 均已合并 | 新仓必过检查（扩展后 9 项，见 §6）+ §8.1-① 哈希核验 0 差异 + §8.1-② 四桶计数复现 | **①** 附录 A 脚本与哈希脚本的输出；**②** §4.2 那张表的每一行 diff；**③** 门禁暂缺表逐行核对（删的是不是只有读取用例） |
| **C-2** | 新仓 | 机械改名：`packages/graph-agent-gateway` → `packages/gskill-gateway`、import `graph_agent_gateway` → `gskill_gateway`、`apps/studio` → `apps/gskill-studio`、发行名与 `productName`（§3.3） | C-1 已合并 | 新仓必过检查全绿 | 改名是否**穷尽**：源码 import 155 行、`pyproject.toml` 三处、vendor 构建与校验脚本里的路径字面量、`ensure_vendor.test.js` 的硬编码路径、CI 的 working-directory |
| **C-3** | 新仓 | 权威文档改写（§7.1）+ `CLAUDE.md` 改指向 + `.ah/` 路径引用校正 | **C-2**（C-3 写的是改名后的路径，见表注） | 新仓必过检查全绿 | 改写后的正文是否自包含、是否与新仓实际路径与 9 项必过检查集一致 |
| **分支保护扩必过集** | 新仓 | 把 `studio-gates`、`frontend-gates`、`graph-agent-tests` 加入必过检查 | **在 C-1 合并前**执行 | 仓库设置变更，非 PR | — |
| **终态打包门** | 新仓 | 在 C-2 合并后的 `main` 终态提交上手动触发一次 `package.yml` 并绿 | C-2、C-3 均已合并 | §8.2-⑨ | 工作流运行链接 + 装包断言输出 |
| **C-4** | 主仓 | 主仓 `README.md` / `AGENTS.md` 顶部加归档横幅（指向新仓 + C-1 的导入提交哈希）；随后把仓库设为 archived | 终态打包门已绿 | 主仓 7 道必过检查；archive 动作需用户明确授权（§11 授权点二） | 横幅措辞与哈希正确性 |

**表注一：C-0b 的前驱是 C-0a，两者不可并行。** 不带 C-0a 的 manifest 改动，四成员 workspace 在 `uv lock` 下**无解**（§9.1 给出退出码与错误原文），C-0b 写不出正文要求的锁。

**表注二：C-3 的前驱是 C-2。** C-3 要写的是新仓 `AGENTS.md` 里的路径、目录与命令；这些路径在 C-2 改名后才成型。C-3 排在 C-2 之前就得写一遍旧路径、再改一遍新路径，等于同一份权威正文写两次。

**表注三：为什么「分支保护扩必过集」排在 C-1 合并之前。** 必过检查按名字匹配；一个尚未在任何工作流里出现过的名字加进保护列表后，PR 会一直等它。所以顺序是：C-1 的 PR 先把 job 定义推上去、让新 job 在该 PR 上真实跑出结果，协调方随即把名字加进保护列表，C-1 再合并。这样 C-1 之后的每一张 PR 都受完整门禁约束，中间不留窗口。

**表注四：终态打包门为什么单列一格、且排在 C-2 之后。** 打包链的资源路径、`productName`、安装目录名全都随 C-2 改名而变；只在 C-1 上验一次打包，验的是一个**将被改掉的形状**。所以「打包链可跑」的判据钉在**改名后的终态提交**上，并作为主仓归档（C-4）的前驱——归档是不可逆动作，前面必须有一次终态的、装得起来的证据。

## 6. D7 · CI 与分支保护

**全部 CI 改动在 C-1 内完成**，否则 C-1 自身无法过门（新仓现有 job 只跑 runtime，跑不到搬进来的三个成员）。

**新增 job**：

- **`studio-gates`**（Linux）：studio backend 的 `ruff check` + `mypy` + `pytest`；gateway 的 `mypy --strict` + `pytest`；`pip-audit` 覆盖整个 workspace。
- **`frontend-gates`**（Linux）：tauri 启动脚本测试（`node --test`，只依赖 Node 内建模块，放在 npm 安装之前快速失败）+ 前端 `lint` / `typecheck` / `test` / `build` + 两档 `npm audit`（`--omit=dev --audit-level=low` 与 `--audit-level=high`：进入用户手里的产物零容忍，开发工具链只拦 high/critical）。
- **`graph-agent-tests`**（Linux，matrix 3.11/3.12/3.13）：从主仓 `.github/workflows/ci.yml:81-131` 原样移植——冻结 engine 的 pytest 套件 + `validate_round28_manifest.py` 契约清单校验。**它是必过检查**，理由见 §3.4：共享锁会换掉冻结包脚下的依赖，只有它自己的测试能证明行为没变。它与冻结包同生共死，批E 删包时一并删除。

**扩展 job**：

- **`cross-platform-smoke`**（windows-latest / macos-latest）：在现有 runtime 测试之外，加 studio backend、gateway、graph-agent **三套 pytest** + 前端 `npm ci` 与 build + stub vendor 文件 + `cargo test`（tauri lib）。这是对主仓形状的**逐项镜像**：主仓该 job 跑的正是这三套（`.github/workflows/ci.yml:257-263`），**不含 e2e**。

**原样移植、不进必过集的 job**：

- **`e2e-tests`**：按主仓形状移植为独立 job 且只在手动触发时运行（主仓 `ci.yml:188`：`if: ${{ github.event_name == 'workflow_dispatch' }}`）。理由写在主仓该 job 自己的注释里（`ci.yml:185-186`）：

  ```
  # E2E suite needs the frontend dev server (Vite) plus Playwright Chromium,
  # which requires a dedicated runner setup. Disabled on PR/push for now;
  ```

  把它塞进必过的 `cross-platform-smoke` 会同时犯两个错：**改行为**（主仓从未在 PR 上跑过这套），以及给两个平台的 runner 平添一套 Playwright 依赖。

- **`package.yml`**（Windows 上跑完整 `cargo tauri build`、装包并断言 sidecar 三件套落在安装目录内）：按主仓形状移植，保持按路径触发、非必过——一次冷跑要编译整个 Rust release 栈并下载可移植 CPython，数十分钟起，绝大多数 PR 碰不到打包链。它的绿由 §8.2-⑨ 的终态打包门承担。

**不动的 job**：`quality-gates` 与 `runtime-tests`（3.11/3.12/3.13）原样保留。

**风格**：所有 action 按新仓既有风格**用 commit SHA 钉版**（新仓现状如 `actions/checkout@3d3c42e5… # v7.0.1`），主仓那种 `@v7` 浮动标签写法在移植时改成 SHA。

**必过检查集**：由现有 6 项扩为 **9 项** = `quality-gates` + `runtime-tests (3.11|3.12|3.13)` + `cross-platform-smoke (windows-latest|macos-latest)` + `studio-gates` + `frontend-gates` + `graph-agent-tests`。（`graph-agent-tests` 若也按主仓那样按 Python 版本分三格，必过项相应为 11 项；C-1 实施方按移植后的实际 job 名把清单钉死，并与分支保护的名字逐字一致。）

**分支保护是仓库设置、不是 PR**：该变更由协调方在 C-1 合并前执行；用户批准本方案即一并授权（§11 授权点一）。

## 7. D8 · 权威文档改写清单（决议 `:610` 要求本方案必附）

改写而非搬运，依据决议 `:607`。每一行给三项：**目标路径 / 执笔席 / 证据来源**。执笔席一律是干净上下文的独立 agent（`PARALLEL_ORCHESTRATION.md` §1.1）。证据来源统一写归档坐标 `agent-harness@<Source-Commit>:<路径>`，`<Source-Commit>` 即 C-1 导入提交里记的那个哈希。

### 7.1 第一档 · C-3 重写（本批次内完成，5 份文档 + 4 项就地校正）

| 目标路径（新仓） | 执笔席 | 证据来源（归档仓路径） | 改写内容 |
|---|---|---|---|
| `AGENTS.md` | 批C 仓级权威执笔席（Opus 5，xhigh，干净上下文） | `AGENTS.md`、`CLAUDE.md` | **删**第 18 行段落里的那一句「Gateway and Studio plugins are not deliverables in this release line; the design retains only their future external Port/Adapter ownership boundaries.」——搬入后该句为假；**删的是这一句，不是整行**（该行是一整段，其余部分讲 `docs/design/v1-alignment.md` 的 `drafted` 状态与各 Phase 验收）。**并入并以新仓路径与 9 项必过检查集重写**：CI 门禁清单、三模块架构与边界、Workflow Pipeline、Studio Tauri Dev、并行任务黑板、vendor 重建规则。**另须写明两件事**：①§4.1.1 (c) 类设计源不在本仓，引用一律写归档坐标；②§4.1.1 门禁暂缺表所列治理门禁暂缺、正在批D 复位 |
| `README.md` | 同上 | `README.md` | 改写为 monorepo 分工：runtime（可独立发布的精瘦包）/ gateway（独立包）/ studio（应用）/ 冻结 engine（带退出条件的过渡包） |
| `docs/design/v1-alignment.md` §2.1 工作名表 | 同上 | 决议 §11.5、本文 §3.3 | 加 gateway、studio 两行（发行名、目录、import 名、Display name） |
| `.github/CODEOWNERS` | 同上 | `.github/CODEOWNERS` | 加 studio 与 gateway 的契约文件条目；删指向未随迁的 `docs/engine/**` 的三条 |
| `docs/development/DELIVERY_LEDGER.md` 头部 | 同上 | 台账正文已按 (a) 类随迁 | 只加「仓库 = 新仓」声明，正文不动 |
| `docs/development/CROSS_PLATFORM.md`、`FRONTEND_UI_SPEC.md`、`JOURNEY_TEST_RULES.md`、`RUN_AND_SCREENSHOT.md`、`FRONTEND_HANDOFF_PROMPT.md`、`PARALLEL_ORCHESTRATION.md` | 批C 开发 SOP 执笔席（Opus 5，xhigh，干净上下文） | 归档仓同名文件 | 以新仓路径、9 项必过检查集、新仓 worktree/PR 流水线重写。（`PARALLEL_ORCHESTRATION.md` 晚于本文快照，按同一规则归此档） |
| `docs/development/design-doc-standards/**` | 同上 | 已按 (b) 类随迁的同名文件 | **先搬后重写**：它被 `test_design_doc_standards_governance.py` 逐树读取，不搬则 C-1 红；重写落地时删除搬来的旧文 |
| `CLAUDE.md`（就地校正） | 同上 | 已随迁的同名文件 | 改指向新仓 `AGENTS.md` |
| `.ah/**` + `ah.toml`（就地校正） | 同上 | 已随迁的同名文件 | 路径引用随迁校正 |
| **主仓** `README.md` / `AGENTS.md`（属 **C-4**，不在 C-3） | 批C 仓级权威执笔席 | — | 顶部加归档横幅：指向新仓 + C-1 的导入提交哈希 |

### 7.2 第二档 · 批D 各模块就地重整时重写（不在批C 内，共 202 份）

依据决议 §4.3「搬家在模块化重整之前……先搬后整，只需在最终的目录形状上重整一次」。逐文件清单**不列在正文**，由附录 B 的命令在 `Source-Commit` 上生成；本文快照上的分组计数如下。

| 待重写范围（目标路径 = 新仓同名目录） | 文件数 | 执笔席 | 证据来源（归档坐标前缀 `agent-harness@<Source-Commit>:`） |
|---|---|---|---|
| `docs/studio/**`（MVP1 设计体 85 + mvp0 24 + `_reorg` 10 + `INDEX.md` 1；含 §4.1.1 门禁暂缺表要复位的四项） | 122 | 批D studio 设计执笔席（Opus 5，xhigh，干净上下文） | `docs/studio/**` |
| `docs/graph-agent-gateway/**`（`mvp1` 39 + `mvp0` 4 + `README.md` 1 + 其余 1；`USAGE.md` 已按 (b) 类随迁） | 45 | 批D gateway 设计执笔席（Opus 5，xhigh，干净上下文） | `docs/graph-agent-gateway/**` |
| `docs/development/` 下其余非 SOP 文档（`CONTRIBUTING.md`、`STUDIO_DESKTOP_BOUNDARY_SPEC.md`、`LLM_MODEL_CONFIGURATION_FLOW.md` 等 11 份 + `examples/` 2） | 13 | 批D 开发文档执笔席（Opus 5，xhigh，干净上下文） | `docs/development/**` |
| `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/**` | 6 | 批D 接口设计执笔席（Opus 5，xhigh，干净上下文） | 同名归档路径 |
| `docs/superpowers/**`（`plans` 3 + `specs` 3） | 6 | 批D 开发文档执笔席 | 同名归档路径 |
| `docs/architecture/**` | 4 | 批D 架构执笔席（Opus 5，xhigh，干净上下文） | 同名归档路径 |
| `docs/strategy/**` | 4 | 批D 架构执笔席 | 同名归档路径 |
| `docs/public/**` | 1 | 批D 开发文档执笔席 | 同名归档路径 |
| `docs/DESIGN-PROCESS.md` | 1 | 批D 架构执笔席 | 同名归档路径 |
| **小计** | **202** | | |

**与 §4 账目的对账（三档之和必须等于 (c) 类总数）**：312 = **5**（第一档里不搬而由 C-3 重写的 SOP：`CROSS_PLATFORM.md`、`FRONTEND_UI_SPEC.md`、`JOURNEY_TEST_RULES.md`、`RUN_AND_SCREENSHOT.md`、`FRONTEND_HANDOFF_PROMPT.md`）+ **202**（第二档，本表小计）+ **105**（第三档 `docs/engine/**`，§7.3）。注意 `docs/development` 在附录 A 的桶里共 18 份未随迁，其中 5 份是上列 SOP（第一档）、13 份在本表（第二档），两处不重复计。`PARALLEL_ORCHESTRATION.md` 晚于本文快照，不在这 312 份里，按同一规则归第一档。

### 7.3 第三档 · 不重写

`docs/engine/**` 是旧 engine 的文档（105 份），它随冻结包在批E 一起死亡——重写一份即将被删除的包的设计文档没有收益。它只留在归档仓当档案，需要时按归档坐标引用。**唯一例外**是 `docs/engine/graph-skill-runtime/**` 三件，它们记录的是新仓本身，按 §4.1.1(a) 归记录类逐字节搬。

## 8. D9 · 验收判据

判据分两段：**机械核验项**（脚本或 CI 给出确定输出，人只读结果）与**人证项**（必须有人看过、留下可复核的记录）。本节标题不再声称全部可机械核验——CDP 真机旅程与逐文件 diff 人审在本质上是人证。

### 8.1 机械核验项

1. **C-1 逐字节核验**：对 §4.1 处置表的每一个文件，`git show <Source-Commit>:<源路径>` 的 sha256 与新仓 `<目标路径>` 的 sha256 相等。核验脚本随 C-1 提交，输出「核验文件总数」与「差异数」，**判据是差异数 = 0 且总数等于附录 A 脚本给出的逐字节桶计数**。
2. **四桶计数复现**：在 `Source-Commit` 上跑附录 A 的脚本，输出四桶计数、`uniq -d` 无重叠、并集等于全集；结果贴进 C-1 的 PR 正文。
3. **新仓全部必过检查绿**，含新增的 `studio-gates`、`frontend-gates`、`graph-agent-tests`（§6）。
4. **冻结锁有效性实跑**：改 `packages/graph-agent` 下任意一个字节（含 `tests/` 下的字节）→ `test_frozen_engine_hash_lock.py` 变红；改回 → 变绿。
5. **全新克隆可装**：在一个全新的 `git clone` 里 `uv sync --all-packages --all-extras --group dev` 成功。
6. **主仓已归档**：C-4 之后 `env -u GITHUB_TOKEN gh repo view SevenX77/agent-harness --json isArchived` 返回 `true`。
7. **门禁暂缺表零遗漏**：在新仓跑 `git grep -l 'docs/studio/mvp1\|docs/graph-agent-gateway/mvp1' -- apps packages ':!*.md'`，命中的每一个文件都必须只在 docstring/注释里出现该路径；有任何一处构成路径读取即判失败。

### 8.2 人证项

8. **合并桶逐文件人审**：§4.2 那张表的每一个文件，其 diff 由实施方在 C-1 的 PR 正文里逐文件列出「改了什么、为什么这一改是过门必需」，并经 codex 交叉审给出 `approve`。**没有这条记录的合并桶文件视为未验收**——哈希核验管不到它们，人证是它们唯一的证据形式。
9. **终态打包门**：在 C-2 合并后的新仓 `main` 终态提交上手动触发 `package.yml` 并绿，运行链接与装包断言输出贴进 C-4 的 PR 正文。这是 C-4 归档的前驱（§5 表注四）。
10. **真机旅程**：在新仓仓根用 `scripts/studio-dev.ps1` 拉起桌面应用，按 `.claude/skills/studio-verify` 的方法（CDP 驱动真 Tauri 窗口，端口 9222）走「打开 Recent 里的一个 skill → 点 Compile → 编译通过」这一条最小旅程并截图。串行占用运行时资源黑板的 `cdp-9222`（`scripts/wt-board.sh claim cdp-9222`），验完释放。

## 9. 风险与已核验事实

### 9.1 依赖共解探针（可复现配方 + 2026-09-02 实测输出）

**配方**（任何人可原样重跑）：

1. 取新仓提交 `dc6f32af` 的完整树（`git -C <新仓本地克隆> archive dc6f32af | tar -x -C <probe>`）。
2. 取主仓提交 `377e82e0` 的 `packages/graph-agent`、`packages/graph-agent-gateway`、`apps/studio/backend` 三棵树，解到 `<probe>` 的同名路径下。
3. 施加 C-0a：把 `<probe>/packages/graph-agent-gateway/pyproject.toml` 的 `"langchain-openai>=1.1.7,<1.3.0"` 改成 `"langchain-openai>=1.3.5,<1.4.0"`。
4. 施加 D1：在 `<probe>/pyproject.toml` 末尾追加 §3.1 那两个 TOML 段。
5. `rm -f <probe>/uv.lock && cd <probe> && uv lock --no-cache`。工具版本：`uv 0.11.24 (5e04460c0 2026-06-23 x86_64-pc-windows-msvc)`。

**输出（2026-09-02 实测）**：

```
Using CPython 3.11.15
Resolved 154 packages in 9.57s
```

退出码 0；`grep -c '^\[\[package\]\]' uv.lock` = 154。

**同一配方去掉第 3 步（不施加 C-0a）**：退出码 1，输出原文——

```
  × No solution found when resolving dependencies:
  ╰─▶ Because graph-agent-gateway depends on langchain-openai>=1.1.7,<1.3.0
      and graph-skill-runtime[dev] depends on langchain-openai>=1.3.5,<1.4.0,
      we can conclude that graph-agent-gateway[ark] and
      graph-skill-runtime[dev] are incompatible.
      And because your workspace requires graph-agent-gateway[ark] and
      graph-skill-runtime[dev], we can conclude that your workspace's
      requirements are unsatisfiable.
```

这就是 §5 表注一的依据：**没有 C-0a，四成员 workspace 连锁都解不出**，C-0b 无从谈起。

**形状差异的说明**：本文初稿报的是「Resolved 106 packages」。那次探针用的是**合成根项目**形状（一个虚拟根，依赖写作 `graph-skill-runtime[embedded]` + `graph-agent` + `graph-agent-gateway[google]` + `studio-backend`，只解这四条显式依赖），而本节的 154 是**真实 workspace** 形状（`uv lock` 解全部成员的全部 extras 与 dev 组）。**后者才是 C-1 落地后的实际形状**，故以 154 为准；106 那次形状与目标不符，作废。

**版本对照（两侧均为实测）**：

| 包 | 合锁解出（probe，154 包） | 主仓当前锁（`git show 377e82e0:uv.lock`） |
|---|---|---|
| langchain | 1.3.14 | 1.3.10 |
| langchain-core | 1.4.9 | 1.4.8 |
| langchain-openai | 1.3.5 | 1.2.1 |
| langchain-anthropic | 1.4.8 | 1.4.6 |
| langchain-google-genai | 4.2.7 | 4.2.2 |
| langgraph | 1.2.11 | 1.2.6 |
| **mcp** | **2.1.1** | **1.29.0** |
| openai | 2.54.0 | 2.34.0 |
| pydantic | 2.13.5 | 2.13.3 |
| fastapi | 0.141.1 | 0.136.1 |

**风险一：`mcp` 主版本跳变（1.29.0 → 2.1.1）。** studio backend 对 `mcp` 的用法只有两处 import——`apps/studio/backend/app/main.py:17` 的 `from mcp.server.streamable_http_manager import StreamableHTTPSessionManager` 与 `apps/studio/backend/app/services/cli_mcp_surface.py:28` 的 `from mcp.server.lowlevel import Server`。两个模块路径在 mcp 2.1.1 下 import 成功（新仓虚拟环境实测），**但构造签名是否兼容未验**。这正是 §3.5 把 C-0b 放在搬迁之前的原因：在主仓、用主仓的 2281 个 backend 测试把它证伪或证实。

### 9.2 跨模块硬引用的规模（2026-09-02 实测，附生成命令）

| 事实 | 数字 | 生成命令 |
|---|---|---|
| studio → engine import | **132 行 / 34 文件**；其中 1 行不是真 import（`apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py:513` 是断言字符串 `assert "from graph_agent import resume_skill" not in source`），故**真实 import 131 行** | `git grep -nE '\b(from\|import) graph_agent\b' -- 'apps/studio/**/*.py'` |
| 其中生产代码（非测试）文件 | 8，`apps/studio/backend/app/core/adapters/engine.py` 独占 60 行 | 同上，按路径含 `/tests` 过滤 |
| studio → gateway import | **155 行 / 39 文件** | `git grep -nE '\b(from\|import) graph_agent_gateway\b' -- 'apps/studio/**/*.py'` |
| gateway → engine 生产代码硬依赖 | **1 处**：`packages/graph-agent-gateway/src/graph_agent_gateway/errors.py:7` 的 `from graph_agent import ModelProviderError` | `git grep -nE '\b(from\|import) graph_agent\b' -- 'packages/graph-agent-gateway/src/**/*.py'` |
| 受治理设计文档载体（`baseline.md` / `mvp1-alignment.md`） | **151** | `git ls-tree -r --name-only 377e82e0 -- docs \| grep -cE '/(baseline\|mvp1-alignment)\.md$'` |
| studio backend 测试规模 | **443 个受跟踪文件，`pytest` 收集 2281 个测试** | `git ls-tree -r --name-only 377e82e0 -- apps/studio/backend \| wc -l`；`uv run pytest apps/studio/backend/tests --collect-only -q` |

**正则为什么带 `\b` 而不是行首锚点**：行首锚点 `^(from|import)` 只数到 85 行 / 26 文件，漏掉全部**函数体内的延迟导入**（`apps/studio/backend/app/core/adapters/engine.py` 里就有 9 处），而延迟导入同样是真实的模块依赖，C-2 改名时一个都不能漏。`\b` 同时保证 `graph_agent_gateway` 不被算成 `graph_agent`（`_` 是单词字符，`\bgraph_agent\b` 不匹配它）。

这些引用在 C-1 **一个都不动**（路径与名字原样），C-2 才随改名机械更新。C-2 的审查重点因此是「改名是否穷尽」。

### 9.3 仓根推算与路径字面量

主仓有 **89 行**按 `REPO_ROOT` / `parents[N]` 上溯推算仓根（`git grep -nE 'REPO_ROOT|parents\[[0-9]\]' -- apps/studio | wc -l`），例如 `apps/studio/backend/app/core/config.py:11-12`（`STUDIO_BACKEND_DIR = Path(__file__).resolve().parents[2]`；`REPO_ROOT = STUDIO_BACKEND_DIR.parents[2]`）；另有 **27 行 / 19 个文件**把 `packages/graph-agent` 写成路径字面量（`git grep -n 'packages/graph-agent' -- apps/studio | wc -l`；`git grep -l … | wc -l`），例如 `apps/studio/backend/scripts/build_vendor.py:131` 与 `apps/studio/tauri/scripts/ensure_vendor.test.js:716,729`（后者硬编码 `path.join(REPO,'packages','graph-agent','src','graph_agent')`）。

这类推算依赖的是**目录深度**，不是目录名：`apps/studio/backend` 与改名后的 `apps/gskill-studio/backend` 深度相同，因此 C-2 的改名不破坏它们；真正会全线崩掉的是**改变目录深度**的搬法——这正是 §4.1 坚持「路径原样」的第二个理由（第一个是哈希可核验）。

### 9.4 初稿两条风险的现状

- **「冻结包在新仓没有自己的测试」——已消解**：§3.4 改判后测试随迁、`graph-agent-tests` 保持必过。
- **「一份随迁的受治理文档引用了不随迁的冻结 engine 测试」——已消解，两个独立原因**：①`docs/studio/mvp1/**` 按 §4.1.1 整棵不搬，那份文档不进新仓；②即使它进了新仓，它引用的 `packages/graph-agent/tests/callbacks/test_a_run_has_one_clock.py` 等三条路径按 §3.4 已随迁，引用仍能解析。

### 9.5 本方案与「搬迁不改行为」的边界（诚实记账）

严格说，有四处不可能保持逐字节不变，本方案逐一显式化而不是掩盖：

1. **依赖解析结果**（两把锁合一把）——隔离进 C-0a / C-0b，在主仓用主仓门禁证明（§3.5、§9.1）。
2. **忽略规则、CI 定义、覆盖率与静态扫描配置**——两仓各有一份，必须合并（§4.2），由 §8.2-⑧ 的人证判据证明。
3. **名字与路径**（C-2）——机械改名，由新仓全套门禁证明。
4. **设计文档治理门禁的暂缺**（§4.1.1 门禁暂缺表）——这是**显式迁移**：删了什么、谁负责装回去、装回去的前提是什么，全部登记在案，退出条件是批D 各设计树重写完成。

除这四处外，C-1 的每一个文件都由 §8.1-① 的哈希核验钉死。

## 10. D11 · 明确不做

1. **不改** studio / gateway / engine 的任何行为。
2. **不动** Python import 名以外的任何标识；C-2 之外不做任何重命名。
3. **不引入兼容垫片**：两仓不并存、不双读；搬完主仓即归档只读。
4. **不搬 `.kiro/**`**（484 个文件，实测无路径读取）。
5. **不在 C-1 里顺手修任何缺陷**：搬迁途中发现的问题一律记进 `docs/development/PROBLEM_LEDGER.md` 并另开工单。
6. **不重命名仓库**（决议 `:573`）。
7. **不移植 git 历史**（决议 `:606`）。
8. **不在批C 里重写模块设计体**：`docs/studio/**`、`docs/graph-agent-gateway/**` 等按 §7.2 归**批D**（决议 §4.3「先搬后整」）；批C 只重写 §7.1 那批仓级权威与开发 SOP。
9. **不搬旧 engine 文档**（`docs/engine/**` 105 份，§7.3），也不为它们写新版。
10. **不静默丢门**：任何因 (c) 类不随迁而删除的门禁用例，必须进 §4.1.1 的门禁暂缺表并写明复位工单。

## 11. 待用户批准项

1. **本方案整体**：批C 是结构性变更，按既有工作规则必须先呈方案、用户确认后再动手（决议 `:624`）。批准前不开工任何一张 PR。
2. **授权点一——新仓分支保护的必过检查集扩为 9 项**（§6）。仓库设置变更，不经 PR，由协调方在 C-1 合并前执行。
3. **授权点二——把主仓 `SevenX77/agent-harness` 设为 archived**（§5 的 C-4）。对外可见的设置变更，需用户在批准本方案时明确授权。

**本文没有其他待裁项**：初稿呈报与交叉审 r1 提出的全部挂起项已由协调方于 2026-09-02 逐条裁定并写入正文。

## 12. 成熟工程参照汇总

`AGENTS.md`「Development Principles」要求：引入新机制前先看成熟工程怎么解，并写明借了什么、拒绝了什么、为什么。本方案的四处新机制与其参照：

| 决定 | 参照对象（含坐标） | 借什么 | 拒绝什么 | 为什么拒绝 |
|---|---|---|---|---|
| D1 workspace 形状 | uv 官方 workspace 模型；langchain monorepo（`libs/*` + 单锁） | 一仓一锁、成员各自持有 `pyproject.toml` | 根包为虚包 | 会把 runtime 从仓根挪走，连带改发布链，收益为零 |
| D2 squash 导入 + 出处 trailer | Kubernetes publishing-bot README（`Kubernetes-sha: <sha>`）；`git subtree --squash` 文档（`contrib/subtree/git-subtree.adoc`） | 压成单提交 + 机器可读的源提交指针 | 真正的历史移植；持续双向同步 | 前者与新仓线性历史保护冲突；后者与「主仓迁完即归档」冲突 |
| D4 冻结包的树哈希锁 | Go `vendor/modules.txt` + `go mod verify`（<https://go.dev/ref/mod>、<https://pkg.go.dev/cmd/go>） | 内容清单 + 把漂移变成非零退出的校验 | 「重新生成清单即可修复」的宽松语义 | 冻结包不允许正常演进，重钉必须是带记录的显式动作 |
| D6 文档三类处置 | PEP 1（<https://peps.python.org/pep-0001/>） | 历史文档与活规范分开处置 | `Superseded-By` 链、旧文永久同仓留存 | 旧设计体在批D 重写后没有读者，留在新仓即第二真相源；追溯由归档坐标满足 |

**未采用的候选参照**：Kubernetes KEP 与 kubernetes.io 的分工（原拟支撑 D6）。2026-09-02 读 `keps/README.md`，找不到「KEP 是提案记录、不是用户文档」的明文，**证不成，故不引**。

## 13. 附录

### 附录 A · 四桶处置的机械复现脚本

脚本随 C-1 提交到新仓 `scripts/migration-buckets.sh`，并在 C-1 的 PR 正文里贴出它在 `Source-Commit` 上的输出。四个桶的定义就是下面这几条命令，本文正文的每个计数均出自它们在 `377e82e0` 上的一次运行：

```bash
REV=377e82e0
ls() { git ls-tree -r --name-only "$REV" -- "$@"; }

# 桶一 · 逐字节搬
{ ls apps/studio packages/graph-agent-gateway
  ls packages/graph-agent/pyproject.toml packages/graph-agent/README.md      packages/graph-agent/src packages/graph-agent/tests      packages/graph-agent/spec packages/graph-agent/scripts
  ls code-diagnostics config
  # docs (a) 记录类
  ls docs/design docs/studio-mvp1-execution docs/handoffs docs/engine/graph-skill-runtime      docs/pr-reports docs/references docs/deferred-items.md      docs/development/DELIVERY_LEDGER.md docs/development/PROBLEM_LEDGER.md
  # docs (b) 被随迁代码按路径读取的数据文件
  ls docs/development/llm_provider_notes docs/development/design-doc-standards      docs/development/STUDIO_REQUEST_AUDIT.md docs/graph-agent-gateway/USAGE.md
  ls scripts .claude skills-lock.json .ah ah.toml .pre-commit-config.yaml CLAUDE.md
} | sort -u > move.txt

# 桶三 · 根级配置/权威文件(按 §4.2 逐份处置)
printf '%s
' uv.lock AGENTS.md pyproject.toml .gitignore .gitattributes .importlinter   codecov.yml .sonarcloud.properties .editorconfig README.md LICENSE | sort > root.txt

# 桶四 · .github(按 §6 重写/移植)
ls .github | sort > gh.txt

# 桶二 · 留在归档仓 = 全集 − 上面三桶
ls . | sort -u > all.txt
cat move.txt root.txt gh.txt | sort -u > accounted.txt
comm -23 all.txt accounted.txt > stay.txt

wc -l < move.txt; wc -l < stay.txt; wc -l < root.txt; wc -l < gh.txt
cat move.txt stay.txt root.txt gh.txt | sort | uniq -d          # 必须为空(两两不交)
cat move.txt stay.txt root.txt gh.txt | sort -u | wc -l         # 必须等于 wc -l < all.txt
```

**2026-09-02 在 `377e82e0` 上的实际输出**：

```
REV=377e82e0
逐字节搬    2015
留在归档仓   836
根级          11
.github        6
合计        2868
全集        2868
无重叠
```

**判据是最后两条断言，不是「总数对得上」**：并集必须等于全集，且四桶两两不交。总数相等可以由两处相反的误差互相抵消而来——本方案明确要防这种失败形态，所以脚本在任一条不满足时非零退出。

### 附录 B · 第二档重写清单的逐文件生成

```bash
# 在主仓（或归档仓）上运行，<Source-Commit> 取 C-1 导入提交里记录的哈希
bash scripts/migration-buckets.sh <Source-Commit>      # 产出 move.txt（逐字节搬清单）
git ls-tree -r --name-only <Source-Commit> -- docs | grep -v -x -F -f move.txt > docs-c-class.txt
# docs-c-class.txt 即 §4.1.1 的 (c) 类 312 份；按 §7.2 的目录分组切给各执笔席
```

本文快照 `377e82e0` 上该清单共 **312** 行，按目录分组的计数见 §7.2 表与 §4.3。

## 修订记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-02 | 交叉审 r1（codex，十条 P1 + 一条 P2）经协调方逐条裁定后返修 | ①**全部引文改为逐字**，源自本仓文件的引文由脚本从源文件抽取后插入，并以 `grep -F` 逐条回核（核对输出贴在 PR）。②**`docs/studio/mvp1/**` 与 `docs/graph-agent-gateway/mvp1/**` 改判为不搬**（协调方依据决议 `:607` 与 `AGENTS.md:366` 裁定）：它们是目标设计真相载体，归 (c) 类由批D 重写；连带新增**门禁暂缺表**（6 个读取用例在 C-1 删除 + 批D 复位工单），(b) 类收窄为 17 份真正被代码按路径读取的数据文件。③§7 按 `:610` 补齐**目标路径 / 执笔席 / 证据来源**三项，逐文件清单移入附录 B 的生成命令。④账目按脚本重算 **2015 + 836 + 11 + 6 = 2868**，并把判据从「总数相等」改为「并集等于全集且两两不交」。⑤§9.1 改写为**可复现配方**，按真实 workspace 形状重跑得 154 包，并补「不加 C-0a 则无解」的退出码与错误原文；版本表两列均为实测。⑥C-0b 前驱改为 C-0a。⑦C-3 前驱改为 C-2，新增**终态打包门**并作为 C-4 前驱。⑧**冻结 engine 改为源码 + 测试 + 契约清单一起搬，`graph-agent-tests` 保留为必过门**（协调方依据「因果验证」裁定：共享锁会换掉它脚下的依赖，源码不变不等于行为不变），树哈希锁覆盖 `tests/**`，连带随迁 `code-diagnostics/**` 与 `config/**`。⑨§8 拆为**机械核验项**与**人证项**两段，合并桶补人证判据。⑩补 D8 编号与 §12 参照汇总（D1/D2/D4/D6 各写「参照—借—拒—为什么」，KEP 候选因证不成而不引）。⑪数字按实跑订正：import 132 行/34 文件（真 import 131）、gateway import 155 行/39 文件、受治理载体 151、backend 443 文件/2281 个测试，每个数字旁给生成命令。 |
| 2026-09-02 | 初稿落盘 | 按已批决议 §4.3 / §4.4 / §11.5 / §11.7 与盘点 `inventory-synthesis.md:124,174`，把批C 搬迁写成可执行方案。状态 `drafted`，**待用户批准**。 |
