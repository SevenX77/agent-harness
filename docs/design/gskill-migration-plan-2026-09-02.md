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

主仓 `AGENTS.md`「Development Principles」另定三条贯穿要求，本文逐条遵守：不做向后兼容、第一性原理修复而非打补丁、以及 `AGENTS.md:233` 的「先看成熟工程怎么解,再决定自己怎么写。」——它要求写明**参照对象、借了什么、拒绝了什么、为什么**，本文每一个引入新机制的决定（D1/D2/D4/D6）都按这四段写，见 §12 的参照汇总。

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

**成熟工程参照**：

**参照对象一 = uv 官方 workspace 文档**（<https://docs.astral.sh/uv/concepts/projects/workspaces/>）。原文：

> In a workspace, each package defines its own `pyproject.toml`, but the workspace shares a single lockfile, ensuring that the workspace operates with a consistent set of dependencies.

> Every workspace needs a root, which is _also_ a workspace member.

**参照对象二 = `pydantic/pydantic-ai`**——一个真实在跑「根包 + 成员 + 单锁」的仓库。2026-09-03 实测（`gh api repos/pydantic/pydantic-ai/contents/...`，根 `pyproject.toml` blob `0418b5a383be3c96c9c7020b9475eba2c8f4cda8`）：根 `pyproject.toml` 同时声明 `[build-system]` （`build-backend = "hatchling.build"`）与 `[project] name = "pydantic-ai"`，即**根自身就是一个可发布包**；同一份文件里有 `[tool.uv.workspace] members = ["pydantic_ai_slim", "pydantic_evals", "pydantic_graph", "clai", "examples"]`；仓根有且只有一个 `uv.lock`，那五个成员目录里**只有 `pyproject.toml`、没有各自的锁**。

**借**：**一仓一锁、成员各自持有 `pyproject.toml`、而根 project 本身也是成员且照样可发布**——这正是 D1 要的三件事，主仓也已经在跑其中前两件（`AGENTS.md:22`），搬迁因此不引入新的依赖管理范式。另借 pydantic-ai 根包用 `[tool.hatch.build.targets.wheel]` 自管 wheel 内容这一点：**发布产物由构建后端的配置决定，与仓里有几个 workspace 成员无关**，这是 D1「`release.yml` 零改动」的依据。

**拒绝**：把根做成**虚包**（只有 workspace 声明、没有自己的可发布身份）。**为什么**：那样就得把 runtime 从仓根搬进子目录，连带改 `release.yml` 的构建路径、`[project.urls]` 与 README 安装说明，收益为零。

**参照对象二不能证明的那一半，必须写明**：pydantic-ai 根包的**源码**在成员 `pydantic_ai_slim` 里，仓根没有 `src/`；而本方案的 runtime 是**源码就在仓根 `src/graph_skill_runtime`**。所以它证明的是「根即成员 + 单锁 + 根可发布」，**不证明**「根持有源码树时也成立」——后半段由 uv 官方文档的 `Every workspace needs a root, which is _also_ a workspace member.` 与本仓 §9.1 的实跑（四成员真实 workspace 解出 154 包、退出 0）承担。

**撤销的参照**：本文初稿写「langchain monorepo（`libs/*` 为成员、单一锁文件）」。该描述与其公开事实相反——LangChain 自己的开发文档写明每个 `libs/` 包各有自己的 `pyproject.toml` **和自己的 `uv.lock`**（<https://github.com/langchain-ai/langchain/blob/master/CLAUDE.md>）。初稿凭印象写下未经核对的参照，**该条作废**。

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

**借**：两者共有的那一半——**把跨仓搬运压成单个提交，同时在提交信息里留一个机器可读的源提交指针**，使「这批文件从哪来、对应源仓哪个提交」永远可回答。本文的 `Source-Commit:` 就是 `Kubernetes-sha:` 的同形字段。**拒绝**：`git subtree` 不带 `--squash` 时的真正历史移植（会产生跨仓合并提交），以及 publishing-bot 的持续双向同步（它服务的是长期并存的镜像关系）。**为什么**：前者与新仓的线性历史保护冲突，后者与决议 `:180` 冲突（该行**意为**：主仓在迁移完成后归档为只读）——本仓要的是一次性搬完即封，不是长期镜像。

### 3.3 D3 · 命名：精确拼法

决议 `:575`（§11.5-3）把精确拼法交给批C。**决定**如下：

| 对象 | 取值 | 理由 |
|---|---|---|
| gateway 发行名（PyPI distribution） | `gskill-gateway` | **前缀**：`gskill` 是产品短名，做命名空间用，同 `langchain-openai`／`langchain-anthropic` 惯例——前缀让同族包在按名排序的列表里聚成一块。**连字符**：PEP 503 的规范化形式，下划线在 PyPI 上会被归一成连字符，直接用规范形式避免两种写法并存 |
| studio 发行名 | `gskill-studio` | 同上 |
| gateway 目录 | `packages/gskill-gateway` | 目录名与发行名一致，免去「目录叫一个名、包叫另一个名」的二次查表 |
| studio 目录 | `apps/gskill-studio`（其下仍为 `backend` / `frontend` / `tauri` / `tests-e2e`） | 同上；`apps/` 与 `packages/` 的分工承载决议 `:172` 原文「- **studio**:应用(app),不是库。」 |
| gateway Python import 名 | `gskill_gateway` | Python 包名不能带连字符，下划线是唯一合法形式 |
| studio Python import 名 | **保持 `app`，不改** | studio 是应用不是库，它的顶层模块不作为公开 import 身份被外部引用 |
| Tauri `productName` 与 Display name | `gskill Studio` | 与产品短名一致 |
| 冻结旧 engine 的发行名与 import 名 | **保持 `graph-agent` / `graph_agent`，不改** | 它在批E 整包删除，改名只是一次无收益改动 |

**执行时点（本条同样是决定）**：**C-1 逐字节保留原路径与原名，改名单独成 C-2 做纯机械重命名。**

理由：盘点 `:124` 要求「搬迁不改行为」，而「不改行为」要能被**机械核验**才算数——C-1 的验收判据是源文件与目标文件的 **git blob 哈希**相等（§8.1-①）。把改名混进 C-1，每个文件内容都变，核验就从「哈希相等、0 差异」退化成「人工审两千余个文件的 diff」。附带收益：git 的 rename 检测在「纯移动」与「纯改名」分成两步时最可靠。

### 3.4 D4 · 冻结旧 engine 的随迁形状：源码 + 测试 + 契约清单 + 门禁数据一起搬，`graph-agent-tests` 保留为必过门

**决定**：`packages/graph-agent` 除下面「不搬的三处」外**整包随迁**——`pyproject.toml`、`README.md`、`src/**`（124）、`tests/**`（340）、`spec/**`（4）、`scripts/**`（1）合计 471 个文件，再减去孤儿测试 `tests/tools/test_dual_run_shadow.py`，**实搬 470 个**；版本号 `0.3.1` 不动；主仓 CI 的 `graph-agent-tests` job **原样移植到新仓并保持必过**，直到批E 删除整包时与包一起删；同时用一道**冻结封印**把「冻结」做成门禁，封印钉住**四棵子树**的 git tree id——`packages/graph-agent`（含 `tests/**`）、`docs/engine`（105 份，见 §4.1.1(b)）、以及两个 `.kiro` spec 轮次目录（见下面的连带项表），载体与断言见本节「冻结封印的载体」。

**依据（协调方 2026-09-02 依据「因果验证」原则裁定）**：**源码不变不等于行为不变。** 冻结包与其余三个成员共用同一把 `uv.lock`，批D 的任何依赖变更、任何一次安全升级，都会换掉它脚下的 langchain / langgraph / pydantic；封印只锁住这个包自己的字节，锁不住它的依赖闭包。要证明「行为没变」，唯一可观察的因果证据是**它自己的测试在新的依赖闭包下仍然全绿**——间接覆盖（studio 测试经 adapter 打到它）、构建成功（`build_vendor.py` 打出 wheel）、导入成功（`verify_installed_sidecar.ps1:136` 的 `import graph_agent` 探针）都只证明「装得上、进得去」，不证明「算得对」。

**冻结封印的载体：新建 `tests/frozen-subtrees.yaml` + `tests/test_frozen_subtree_lock.py`，不复用 `contract-seals.yaml`（协调方 2026-09-03 依据「钉值即治理记录」与 git 内容寻址推导裁定）。**

**为什么必须另建载体，而不是往 `contract-seals.yaml` 里塞**：本文上一稿写「直接复用，不新造一套」，那句话是错的——复用装不下。新仓 `a4f43d83` 的 `tests/test_contract_hash_lock.py` 对该文件强制三条约束，本封印每一条都不满足：①记录必须带 `sha256` 且为 **64 位**十六进制（`:146-147`），而子树 id 是 **40 位**；②`file` 必须指向一个**普通文件**（`:197-198` 断言 `(repo_root / candidate).is_file()`），而本封印的对象是**目录**；③该测试维护 **`status: FROZEN` 文档 ⇔ seal 记录的双向一一对应**（`:271` 起），塞进四条谁也不对应 FROZEN 文档的记录，会直接打破那条不变量。**三者都不是可以「顺手放宽」的细节**：放宽①②等于让那个文件同时承载两种语义不同的钉值，放宽③等于拆掉它自己的核心断言。**生命周期也不同**：`contract-seals.yaml` 服务的是「单份文档解冻要走 exemption」，而本封印的唯一合法终局是**批E 整包删除**，中间不存在逐份解冻。**一个概念、一个文件、一个 owner** ——这正是 F-T3 把 exemption 与 byte seal 拆成两个文件时给出的理由，本方案照它办，而不是反着来。**本方案的冻结封印用 `tests/frozen-subtrees.yaml` 的 tree id，不用它。**

**借什么**：`contract-seals.yaml` 的**治理字段形状与 fail-closed 读法**——记录带 id / 对象 / 钉值 / `reason` / `pr` / `pm_approval`，同一对象的**最后一条记录即现值**，早先记录留作审计轨迹、永不原地改写；loader 严格 fail-closed（未知顶层键、缺 `version`、版本不认识、缺字段、多字段、id 重复、路径为绝对或含 `..` 一律抛错，绝不 `continue` 跳过）。**拒什么**：它的 `sha256` 字段、`file` 必须是文件的断言，以及 FROZEN 文档双射。**为什么**：借的是「钉值必须是一条有人签字的治理记录」这条机制，拒的是「对象是单份文档」这个与本封印不符的前提。**本方案的冻结封印用 `tests/frozen-subtrees.yaml` 的 tree id，不用它。**

**记录形状（`tests/frozen-subtrees.yaml`，C-1 的交付物之一）**：

```yaml
version: "1"
subtrees:
  - subtree_id: FS-0001-frozen-engine-package
    path: "packages/graph-agent"
    tree_id: "<40 位十六进制，C-1 PR head 上 git rev-parse HEAD:packages/graph-agent 的输出>"
    reason: "批C C-1 导入冻结引擎整包（源码 + 测试 + 契约清单）。冻结的唯一合法终局是批E X-T1b 整包删除，期间任何字节变动都必须先有一条新记录。"
    pr: "<新仓 C-1 的 PR 编号>"
    pm_approval: "<用户对批C 搬迁方案的批准记录；重钉时写批准这次重钉的裁决>"
  - subtree_id: FS-0002-frozen-engine-gate-docs
    path: "docs/engine"
    tree_id: "<40 位十六进制>"
    reason: "冻结引擎门禁数据：validate_round28_manifest.py 与 graph-agent-tests 按路径读取它（方案 §4.1.1(b)）。不含 graph-skill-runtime/ 三件，见同节例外。"
    pr: "<新仓 C-1 的 PR 编号>"
    pm_approval: "<同上>"
  - subtree_id: FS-0003-frozen-engine-spec-round-10
    path: ".kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch"
    tree_id: "<40 位十六进制>"
    reason: "冻结引擎门禁数据：test_gamma0_contract_tdd.py:212,228 按路径读取（方案 §3.4 连带项表）。"
    pr: "<新仓 C-1 的 PR 编号>"
    pm_approval: "<同上>"
  - subtree_id: FS-0004-frozen-engine-spec-round-28
    path: ".kiro/specs/engine-mvp0-rebuild-v030/round-28-feature-checklist-redesign"
    tree_id: "<40 位十六进制>"
    reason: "冻结引擎门禁数据：test_round28_contract_manifests.py 的 test_cutover_discipline_quantifies_overlap 按路径读取（方案 §3.4 连带项表）。"
    pr: "<新仓 C-1 的 PR 编号>"
    pm_approval: "<同上>"
```

**字段闭集**：`subtree_id`（`FS-NNNN-<小写 slug>`，全文件唯一）、`path`（仓库相对路径，指向一个**目录**）、`tree_id`（40 位小写十六进制）、`reason`、`pr`、`pm_approval`——**六个键，缺一个或多一个都是硬失败**。顶层键闭集为 `version` 与 `subtrees`。`version` 当前为 `"1"`；loader 只读它认得的版本。

**`tests/test_frozen_subtree_lock.py` 的断言清单（C-1 必须逐条落地）**：

| # | 断言 | 失败即红的理由 |
|---|---|---|
| 1 | `frozen-subtrees.yaml` 存在且是一个 mapping；顶层键 ⊆ {`version`,`subtrees`}；`version == "1"` | 一份 loader 读不懂的治理文件，读下去就是在猜它的含义 |
| 2 | 每条记录的键集**恰好等于**上面那六个 | 少一个是治理记录不完整；多一个多半是拼错了某个必填键 |
| 3 | `subtree_id` 匹配 `^FS-[0-9]{4}-[a-z0-9-]+$` 且全文件唯一 | 重复 id 会让「最后一条即现值」失去唯一解 |
| 4 | `path` 是仓库相对路径、不含 `..`、且 `(REPO_ROOT / path).is_dir()` | 钉一个不存在的目录等于一条永远不会红的假记录 |
| 5 | `tree_id` 匹配 `^[0-9a-f]{40}$` | 40 位是 git 对象 id 的形状；写成 64 位说明有人把文件级封印那套摘要塞了进来（`contract-seals.yaml`，见本节开头） |
| 6 | 对每个 `path` 取**最后一条**记录，断言 `git rev-parse HEAD:<path>` 的输出 == 该记录的 `tree_id` | 这是封印本身：子树漂了一个字节，tree id 就变 |
| 7 | 记录里出现的 `path` 集合**恰好等于**四条：`packages/graph-agent`、`docs/engine`、`.kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch`、`.kiro/specs/engine-mvp0-rebuild-v030/round-28-feature-checklist-redesign` | 少一条 = 有一棵冻结子树没上锁；多一条 = 有人把不属于冻结包的东西也钉死了。这个集合与 §3.4 的冻结范围是同一份事实，两处必须一致 |
| 8 | 失败信息里打印重钉命令（`git rev-parse HEAD:<path>`）与「必须同 PR 追加一条带 `pm_approval` 的记录」这句话 | 否则下一个人会去改测试而不是走治理 |

**重钉 = 在同一张 PR 里追加一条新记录**（不是改旧记录的十六进制串），新记录带自己的 `reason` / `pr` / `pm_approval`；旧记录原样留下当审计轨迹。**封印覆盖 `tests/**`**——`packages/graph-agent` 的子树 id 天然包含它——否则「改测试」就成了让门变绿的合法路径，冻结形同虚设。**放宽这道封印的唯一合法路径是删除整包**，即批E 的 X-T1b：那时四条记录与这个测试文件一起删掉。

**为什么钉 tree id 而不是另列一份逐文件摘要清单**：git 的 tree 对象**本身就是一份内容寻址清单**——它逐条记录子项的模式、名字与子对象 id，任何一个字节变动都会沿路径向上改变 tree id。另写一份逐文件摘要清单，等于在同一份事实上立第二个真相源（违反「文档事实唯一所有权」），而且它必须自己处理行尾归一化、路径排序、可执行位这些 git 已经处理好的问题——本文初稿要求「行尾按 LF 归一化后再算摘要」，正是在手工重做 git 的 clean filter，该要求已作废。**同一条理由也决定了 §8.1-① 用 git blob 哈希做逐字节核验**：那一步问的是「哪一个文件不一致」，用的是同一个对象库里的同一套 id。

**钉值取自 C-1 的 PR head：合并前就能算，合并后再证（协调方 2026-09-03 裁定）。** 上一稿写「合并之后取值」，那形成一个死环——分支保护要求检查先绿再合并，而「合并提交」只有合并之后才存在，同一张 PR 不可能既先绿又后写值。正确的时序是：

1. **C-1 的 PR head 上算值**：`git rev-parse HEAD:<四条 path>`，写进 `tests/frozen-subtrees.yaml`，与封印测试同在这张 PR 里；PR 的 CI 在 PR head 上跑，封印测试**在合并前就是绿的**。
2. **合并后 `main` 的 CI 再跑一次，即「合并后复核」**：值不对就红在 `main` 上，立刻可见。

**这个时序成立，靠的是两条可核验的事实，不是乐观假设**：①**新仓 `main` 在 C-1 之前没有这四棵子树**——2026-09-03 实测新仓 `main`（`96019595`）上 `git ls-files packages | wc -l`、`docs/engine`、`.kiro` 三者**均为 0**，顶层只有 `docs/ examples/ scripts/ spec/ src/ tests/ tools/` 等；②**新仓只允许 squash 合并**——实测 `gh api repos/SevenX77/graph-skill-runtime` 返回 `allow_squash_merge=true`、`allow_merge_commit=false`、`allow_rebase_merge=false`。两条合起来意味着：这四个路径上**不存在 main 侧的并发改动可以混进结果树**，squash 合并提交在这四棵子树上的内容与 PR head **逐字节相同**，因此 tree id 也相同。**C-1 若因 main 前移而需要 rebase，这四个 tree id 同样不变**——rebase 改的是父提交与其他路径，这四个路径没有 main 侧改动可与之合并。

**这条推理有一个前提，必须在 C-1 里当场复核**：如果在 C-1 待合并期间，有另一张 PR 先一步往这四个路径里写了东西，前提就不成立。C-1 的合并后复核（上面第 2 步）正是它的捕捉网——`main` 的 CI 一红就说明前提被破坏，处理方式是重算并追加一条新记录，而不是放宽测试。

**SHA-1 碰撞不在威胁模型内**：两仓的对象格式实测均为 `sha1`（`git rev-parse --show-object-format` → `sha1`），所以 tree id 与 blob id 都是 40 位。这道封印防的是**误改与漂移**——有人无意改了冻结包的一个字节，或依赖升级顺手动了它——不防一个能构造 SHA-1 碰撞的攻击者。真要防后者，该换的是整个仓库的对象格式，不是在 git 之上再叠一层自制摘要。

**成熟工程参照**：**参照对象** = Go modules 的 `go.sum` 与 `go mod verify`。Go Modules Reference（<https://go.dev/ref/mod#go-sum-files>）原文——

> The `go.sum` file contains cryptographic hashes of the module's direct and indirect dependencies.

> When the `go` command downloads a module `.mod` or `.zip` file into the [module cache](#module-cache), it computes a hash and checks that the hash matches the corresponding hash in the main module's `go.sum` file.

同一份文档的 `go mod verify` 一节（<https://go.dev/ref/mod#go-mod-verify>）原文：

> `go mod verify` checks that dependencies of the [main module](#glos-main-module) stored in the [module cache](#glos-module-cache) have not been modified since they were downloaded.

（**引文坐标可离线复核**：上面三句取自 Go 官网这一页的仓库源文件 <https://raw.githubusercontent.com/golang/website/master/_content/ref/mod.md>——`go.sum files` 一节的标题行（带锚 `{#go-sum-files}`）在第 4139 行，`go mod verify` 一节的标题行（带锚 `{#go-mod-verify}`）在第 2421 行；原文在源文件里按行折行，本文按句合并成一行，字符未改。本文全部 8 条外部引文都以同样方式抓取上游原始文件后逐条比对，结果见 PR 正文。）

**这两者比对的不是同一份记录，必须写明**：`go.sum` 是**下载时**自动比对的哈希清单；`go mod verify` 比对的是模块缓存里**首次下载时记录的**哈希。它们是同一条原理的两个落点——**先把内容哈希记下来，再让任何偏离以非零状态退出**——而不是「清单 + 读清单的命令」这种配对。**本文初稿把 `vendor/modules.txt` 与 `go mod verify` 说成后一种配对，该说法作废**：按同一份文档，`modules.txt` 只被检查与 `go.mod` 的**版本一致性**，`go mod verify` 不读它；初稿自己引的 `local downloaded source cache` 一句已经证伪了那个映射。

**借**：上面那条共有的原理——内容哈希一旦记录，任何偏离都必须让命令以非零状态退出，而不是靠口头约定「大家别改」。本文的 `tests/frozen-subtrees.yaml` 承担「记录」，`tests/test_frozen_subtree_lock.py` 承担「非零退出」。**拒绝**两件事：①Go 那套「清单可由工具自动重新生成」的宽松语义（`go mod tidy` 会自动增删 `go.sum` 行）；②「逐文件列摘要」的清单形式。**为什么**：依赖升级是 Go 的正常工作流，而本仓的冻结包**不允许**正常演进——它只有「不变」和「整包删除」两种合法终局，所以重钉必须是一次带 `pm_approval` 记录的显式动作；逐文件清单则如上一段所说，是在 git 的 tree 对象之外另立第二个真相源。

**不搬的三处**：①9 个误提交裸文件——`e1.txt`、`e2.txt`、`e3.txt`、`err.txt`、`err2.txt`、`hb`、`owner`、`owner2`、`lk/owner`（2026-09-02 实测 `git ls-files packages/graph-agent | grep -v -E '/(src|tests|spec|tools|scripts)/'`，除去 `README.md` 与 `pyproject.toml` 后即这 9 个）；②`tools/dual_run_shadow.py`——2026-09-02 实测 `git grep -n 'graph-agent/tools'` 在 `.github`、`apps`、`packages`、`scripts` 下 0 处引用；③**它的测试** `packages/graph-agent/tests/tools/test_dual_run_shadow.py`，在 C-1 里一并删除。前两条同一条判据：**没有任何消费者**；第三条是前一条的机械后果——被测对象不随迁，这个测试在新仓里必然红，**实证见 §4.1.1 的孤儿测试一行**。

**随迁的连带项（由本决定机械推出，不是另一个决定）**：`packages/graph-agent/tests` 与 `scripts/validate_round28_manifest.py` 读取包外四处路径，不搬它们 `graph-agent-tests` 就是红的——

| 被读取的路径 | 读取点（实测坐标） | 文件数 |
|---|---|---|
| `code-diagnostics/**` | `packages/graph-agent/tests/core/test_code_health_metrics.py:18,23,30,42`（`parents[4]` 上溯到仓根后拼 `code-diagnostics/build_tree.py`、`run_static_audit.py`） | 6 |
| `config/**` | `packages/graph-agent/tests/integration/test_mvp1_smoke.py:70`（`REPO_ROOT / "config" / "llm_roles.yaml"`） | 2 |
| `docs/engine/**`（不含 `graph-skill-runtime/` 三件，§4.1.1(b)） | `scripts/validate_round28_manifest.py` 与 `tests/**` 里读它的用例，逐条见 §4.1.1(b) | 105 |
| `.kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch/**` | `packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:212`（`GAMMA0_SPEC_DIR.glob("*.md")`）、`:228`（`GAMMA0_SPEC_DIR / "tasks.md"`） | 5 |
| `.kiro/specs/engine-mvp0-rebuild-v030/round-28-feature-checklist-redesign/**` | `packages/graph-agent/tests/test_round28_contract_manifests.py` 的 `test_cutover_discipline_quantifies_overlap`（读该目录的 `tasks.md`） | 4 |

后两行是 2026-09-03 在模拟 C-1 目标树上跑出来的，不是推想：只删「留在归档仓」桶时 engine 全套 **4 failed, 1717 passed**，四条红里有三条就是这两个目录缺失（`test_γ0_4_validator_signature_and_error_placeholders_are_documented`、`test_γ0_5_docs_ship_gates_match_source_contract`、`test_cutover_discipline_quantifies_overlap`）；把这 9 个文件放回去再跑同样三个测试文件，得 **1 failed, 28 passed, 1 xfailed**，唯一剩下的红是孤儿测试 `test_dual_run_shadow`。**这不是一条新决定，是同一条判据的第二次应用**（协调方 2026-09-03 确认）：`docs/engine/**` 之所以随迁，判据是「随迁的冻结包测试按路径读取的门禁数据」；这两个目录**逐字满足同一条判据**，因此落在同一条规则下，共 9 个文件随迁；`.kiro/**` 其余 **475** 份仍留在归档仓。同一条判据在本方案里已应用四次——`code-diagnostics/**`、`config/**`、`docs/engine/**`、这两个 `.kiro` 目录，它们同列在上面那张连带项表里，不分主次。**被拒绝的替代做法**：把这三条断言删掉、进门禁暂缺表。拒绝的理由是它和 §3.4 本身的论证直接冲突——本节刚论证过「只有冻结包自己的测试能证明行为没变」，转头就为省 9 个文件删掉它三条断言，等于自毁论据。

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

### 4.1 逐字节搬（C-1，共 2119 个文件）

| 源路径（主仓） | 目标路径（新仓，C-1 时） | 文件数 | 说明 |
|---|---|---|---|
| `apps/studio/**` | 同路径 | 1208 | frontend 715 / backend 443 / tauri 45 / tests-e2e 9，**减去 §4.1.1 门禁暂缺表里属于 backend 的 4 个文件**（3 个 C-1 删除、1 个 C-1 修改） |
| `packages/graph-agent-gateway/**` | 同路径 | 138 | gateway 包全量 140，**减去门禁暂缺表里的 2 个测试文件**（均 C-1 删除） |
| `packages/graph-agent/{pyproject.toml,README.md,src,tests,spec,scripts}` | 同路径 | 470 | 冻结 engine，见 §3.4；包内全量 471 **减去孤儿测试 `tests/tools/test_dual_run_shadow.py`**（C-1 删除，见 §4.1.1） |
| `docs/**` 的 (a)(b) 两类 | 同路径 | 229 | **不整搬**；三类分法见 §4.1.1。其中 `docs/engine/**`（除 `graph-skill-runtime/` 三件外的 105 份）是**冻结引擎的门禁数据**，见 §4.1.1(b) |
| `.kiro/specs/engine-mvp0-rebuild-v030/{round-10-PR-gamma0-contract-patch,round-28-feature-checklist-redesign}/**` | 同路径 | 9 | 冻结引擎测试按路径读取的门禁数据，与 `docs/engine/**` 同族，见 §3.4 的连带项表；`.kiro/**` 其余 475 份留在归档仓 |
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

**(a) 记录类——逐字节搬（107 个文件）。** 它们记录「某时某人裁了什么、发现了什么」，是**事实记录而非设计权威**；重写记录等于伪造历史。

| 路径 | 文件数 |
|---|---|
| `docs/design/**`（决议、盘点、审计与决策记录） | 88 |
| `docs/studio-mvp1-execution/**` | 9 |
| `docs/handoffs/**` | 4 |
| `docs/pr-reports/**` | 2 |
| `docs/development/DELIVERY_LEDGER.md`、`docs/development/PROBLEM_LEDGER.md` | 2 |
| `docs/references/**` | 1 |
| `docs/deferred-items.md` | 1 |

**(b) 数据类——逐字节搬（122 个文件）。** 判据窄且唯一：**随迁的生产代码或随迁的测试在运行时按路径读取它**（不是在注释、docstring 里引用它）。逐条列出消费者：

| 文件 | 消费者（实测坐标） | 文件数 |
|---|---|---|
| `docs/development/llm_provider_notes/**` | **生产代码** `apps/studio/backend/app/services/llm_notable_models.py:13`（`parents[5]` 上溯拼路径）；索引键由 `apps/studio/backend/app/data/provider_identity.json:2` 与 `app/services/provider_config.py:7` 定义 | 10 |
| `docs/development/design-doc-standards/**` | `apps/studio/backend/tests/docs/test_design_doc_standards_governance.py:101`（`ROLE_REQUIRED_ROOTS` 之一）、`:108`（`EXAMPLE_ROOT`）、`:370`（断言 `example/` 非空） | 5 |
| `docs/development/STUDIO_REQUEST_AUDIT.md` | `apps/studio/backend/tests/docs/test_studio_request_audit_ledger.py:150,161`、`test_ledger_tables_hold_their_shape.py:100` | 1 |
| `docs/graph-agent-gateway/USAGE.md` | `packages/graph-agent-gateway/tests/test_gateway_docs_name_real_files.py:29`（`_DOCS` 元组成员，逐行核对文中提到的 Python 路径与符号真实存在） | 1 |
| **`docs/engine/**` 除 `graph-skill-runtime/` 三件外的全部**（`skill-spec/**`、`public-api-contract.md`、`feature-compliance-checklist.md`、`error-handling/**`、`mvp0/**`、`mvp1/**` 及其哈希锁文件、`graph-agent-gateway/**`） | 冻结引擎自己的测试与契约校验脚本：`packages/graph-agent/scripts/validate_round28_manifest.py`（读 `docs/engine/skill-spec/11-error-code-spec.md` 等）、`packages/graph-agent/tests/**` 里读 `docs/engine/**` 的用例（`test_action_module_private_helpers.py`、`test_llm_role_layering.py`、`contract-exemptions.yaml` 等） | 105 |

清单的产出方式（可复现）：在 §4.1「搬」列的代码/测试/脚本里跑
`git grep -nE '(DOCS_ROOT|/ *"docs|docs/)' -- <搬列路径> ':!*.md'`，取其中**构成路径读取**的每一条（判据：该行把字符串拼进 `Path` 或传给 `open`/`read_text`/`rglob`），再展开成文件清单。注释、docstring 里的「Design: docs/…」不算——2026-09-02 实测这类出处标注在 `apps/studio` 与两个 package 下有 11 个测试文件、10 个生产文件命中，它们随代码搬走后引用的是**归档仓的旧文**，不构成随迁需求。

**`docs/engine/**` 为什么在 (b) 而不在 (c)（协调方 2026-09-03 裁定）**：它随冻结包在批E 一起死亡、**从不重写**，所以它不是「要重写的权威正文」，而是**冻结包的门禁数据**——跟 `code-diagnostics/**`、`config/llm_roles.yaml` 同一类，判据同样是「随迁的测试按路径读取它」。不搬的后果是实测的：只保留 `docs/engine/graph-skill-runtime/**` 时，`validate_round28_manifest.py` 因缺 `docs/engine/skill-spec/11-error-code-spec.md` **退出 1**，engine 五个相关测试文件 **10 failed**——而 §3.4 又要求 `graph-agent-tests` 在批E 之前保持必过，两者直接打架。**正文必须写明的边界**：新仓的格式权威是它自己的 `docs/skill-spec/**`；搬进去的 `docs/engine/**` **在新仓不是权威、不被任何新正文引用，只供冻结引擎的门禁读取**，并随冻结包一起进封印（§3.4）、在批E 同删。C-3 重写新仓 `AGENTS.md` 时必须写上这一句，否则后来者会把它当成第二套格式真相。

**唯一的例外：`docs/engine/graph-skill-runtime/` 三件不搬（协调方 2026-09-03 依据「文档事实唯一所有权」裁定）。** `README.md`、`baseline.md`、`v1-alignment.md` 三件是新仓 `docs/design/` 下**同名三件的被取代前身**（2026-09-03 实测：新仓 `docs/design/v1-alignment.md` 102575 字节，主仓 `docs/engine/graph-skill-runtime/v1-alignment.md` 40479 字节，两者不同）。搬进去就是同仓并存两份同名不同内容的文档，也就是两份真相；靠在 `AGENTS.md` 里写一句「以 `docs/design/` 那份为准」压住它，是补丁不是修根——**根在于它根本不该同仓存在**。三件因此落入「留在归档仓」桶（§4.3），需要引用时走归档坐标 `agent-harness@377e82e0:docs/engine/graph-skill-runtime/<file>`。

**排除它们不损坏任何门禁，这是查过的**：2026-09-03 实测 `git grep -n 'graph-skill-runtime/' packages/graph-agent/tests packages/graph-agent/scripts packages/graph-agent/spec` **零命中**（退出码 1）；放宽到整个包 `git grep -n -F -e 'graph-skill-runtime' 377e82e0 -- packages/graph-agent` 共 **5 处**，全部不是路径读取——`README.md:5,140,141` 是 markdown 相对链接，`README.md:23` 是一句讲未来 PyPI 发行名的散文（`not yet published under the future graph-skill-runtime PyPI name`），`tests/test_contract_hash_lock.py:29` 是一句注释；全仓 `git grep -n 'docs/engine/graph-skill-runtime' -- ':!*.md'` 同样零命中。并以模拟树复核：把三件从目标树删掉后重跑四套,红名单逐条相同(数字与那 1 个消失的参数化用例见下面「表是全的」一节的对照组二)。**顺带的后果**：`packages/graph-agent/README.md` 里那两条相对链接在新仓会指向不存在的文件；它随包在批E 整体删除，且本方案不改任何随迁文件的内容（§4.1「逐字节搬」），故不在 C-1 里修——如果批D/批E 之前需要修，那是一次独立的内容改动，走独立工单。

**(c) 权威文档——不搬（210 个文件；其中 207 份在批D 重写，3 份是上面刚排除的 `graph-skill-runtime/` 前身、不重写）。** 清单、执笔席与证据来源见 §7。它们在新仓落地之前，新仓正文引用这些设计源时**一律写归档坐标**（`agent-harness@<Source-Commit>:<路径>:<行号>`），这正是决议 `:607` 括号里要求的引用形式。

**这三类的边界为什么是这样**：决议 `:607` 禁止的是**把旧的设计权威正文原样搬过去、在新仓继续充当权威**（这是本文对该行的理解，不是它的原文；原文见 §1 表）；它没有、也不能禁止搬运**事实记录**（(a)：重写记录即伪造）与**被代码按路径读取的数据**（(b)：不搬则随迁的代码自己就是坏的）。三类都以「在新仓里它是什么身份」为唯一判据，不以目录形状为判据。

**成熟工程参照**：**参照对象** = Python 的 PEP 体系。PEP 1（<https://peps.python.org/pep-0001/>）原文：

> In general, PEPs are no longer substantially modified after they have reached the Accepted, Final, Rejected or Superseded state. Once resolution is reached, a PEP is considered a historical document rather than a living specification.

**借**：**把「历史文档」与「活规范」当成两种不同载体分开处置**——前者定稿后不再实质修改，后者随系统演进而重写。本文的 (a) 类对应「historical document」（决议、盘点、审计报告、台账），(c) 类对应「living specification」（模块设计体、开发 SOP）。**拒绝**：PEP 用 `Superseded-By` / `Replaces` 头把新旧串成链、旧文永久留在同一个仓里这一半。**为什么**：PEP 服务的是一个公开、长期、必须可追溯的标准流程；本仓的旧设计体在批D 重写后就没有读者了，把它留在新仓只会制造「两份都在、不知道该信哪份」的第二真相源——它的追溯需求由归档仓 + 归档坐标满足，这是决议 §11.7-3 已定的方案。

（**另一个候选参照未采用**：Kubernetes 的 KEP 与 kubernetes.io 用户文档的分工。2026-09-02 读 <https://github.com/kubernetes/enhancements/blob/master/keps/README.md>，其中只有「Our aim with KEPs is to clearly communicate new efforts to the Kubernetes contributor community.」一类表述，**找不到**可用来支撑「KEP 是提案记录而非用户文档」这一分法的明文，证不成，故不引。）

**C-1 删除清单（显式迁移，不是静默丢门）**：这两棵树不搬，随迁的测试里凡**按路径读取它们**的用例在 C-1 里删除，并在此登记复位工单。判据是「读取」而非「引用」——2026-09-02 实测命中 **20 个文件**（`git grep -l 'docs/studio/mvp1\|docs/graph-agent-gateway/mvp1' apps/studio/backend/tests packages/graph-agent-gateway/tests | wc -l` = 20，其中 `apps/studio/backend/tests` 一侧 15 个），**6 个构成路径读取、14 个只在 docstring/注释里写「Design: …」**。那 14 个原样保留不动——包括 `packages/graph-agent-gateway/tests/test_gateway_docs_name_real_files.py`，它正文只读 `docs/graph-agent-gateway/USAGE.md`（该文件按 (b) 类随迁），对 `mvp1/` 的提及在 `:14` 的模块 docstring 里。

**入表判据（协调方 2026-09-03 裁定）：只有在模拟 C-1 目标树上实跑变红的用例才进表，每行必须带「实证」一栏给出命令与失败断言。** 「读它就得删」是推想，推想会连坐无辜的用例——初稿据此删掉了 `test_summary_role_names_an_authority_file_that_exists` 与 `test_at_least_one_real_summary_role_exists` 两条**通用**治理断言，而实跑显示两条**都通过**（它们不依赖那两棵树的存在）；删掉它们等于让批D 重写剩余文档期间，「`role: summary` 必须指向真实存在的权威文件」「仓内至少有一份真 summary」这两条保护凭空消失。**两条已从表中移除，不删。**

**模拟树怎么造的（可复现）**：`git clone --local --no-checkout` 主仓 → `checkout --detach 377e82e0` → `git rm --pathspec-from-file=<附录 A 脚本产出的 stay.txt>`，得到 **2137** 个文件的 C-1 目标树（= 2868 − 731 留档；`docs/engine` 105 份在、`docs/engine/graph-skill-runtime` 0 份、`docs/studio/mvp1` 0 份、`.kiro` 只剩随迁的 9 份）。**量红时再把下表那 6 个待删文件放回去**（2137 + 6 = **2143** 个文件），否则它们不在场就无红可量。**必须用 `git clone` + `git rm` 而不是 `git archive` + `tar`**：本次实测到 `git archive` 解出来的树不是 git 仓，`test_round30_pr4_scorecard_sbom_config.py` 的 `_is_executable()` 在 Windows 上是 shell 出 `git ls-files -s` 读文件模式位的（`:33-40`），非仓目录下必然返回 False，于是凭空多出 2 条与搬迁无关的红。**用错脚手架就会把脚手架的毛病记进方案。**

需要动的是下面 **7 个文件**：**6 个整文件删除**（第 1、3、4、5、6 行属门禁暂缺、等批D 复位；第 7 行是孤儿测试、无复位工单）与 **1 个就地修改**（第 2 行，即 §4.4 的「特殊处置」桶那一个文件——只删那一个红掉的用例，文件里其余 12 个用例与 `ROLE_REQUIRED_ROOTS` 全部原样保留）：

**这条判据也约束「顺手多改一点」（协调方 2026-09-03 裁定）**：本文上一稿还要求 C-1 把 `ROLE_REQUIRED_ROOTS` 里的 `docs/studio/mvp1` 一项删掉，理由是「它不报红，只是静默缩小语料」——那是一条**推断出来的额外改动，没有失败断言支撑**，与本节刚立的入表判据自相矛盾。**该要求已撤销**：C-1 不动 `ROLE_REQUIRED_ROOTS`，一个指向暂时不存在的目录的根**不产生任何红**（`_priority_docs()` 对缺失的根返回空，语料因此变小，而「变小」正由 `test_priority_roots_are_non_empty` 这条断言守着）；批D 重写 `docs/studio/mvp1` 时那个根会重新有内容，届时无需任何改动就自动恢复。**保留它反而更安全**：万一批D 之前有人往 `docs/studio/mvp1` 下重新放文档，这个根还在，治理扫描就还会覆盖它。

| C-1 里删除或修改的用例 | 它守的是什么 | 实证（2026-09-03，模拟 C-1 目标树） | 批D 复位工单 |
|---|---|---|---|
| `apps/studio/backend/tests/docs/test_doc_code_references_exist.py`（整文件） | 权威设计文档里的代码路径引用必须解析得到 | `uv run pytest apps/studio/backend/tests/docs/test_doc_code_references_exist.py` → `test_stale_reference_backlog_entries_are_governed_docs` 红：`AssertionError: backlog entries without a governed doc: docs/architecture/…/baseline.md, docs/graph-agent-gateway/mvp1/…, docs/studio/mvp1/…`（共 23 条） | 批D-studio-1：新设计体落地后重建该门 |
| `apps/studio/backend/tests/docs/test_design_doc_standards_governance.py` 的**一处**：`test_priority_roots_are_non_empty`（`:256-258`）。**该文件其余 12 个用例全部保留**（含两条 `summary` 断言），`ROLE_REQUIRED_ROOTS`（`:102`）里的 `docs/studio/mvp1` 一项**原样不动** | 受治理语料规模不塌、`status:`/`role:` 落在闭集 | `uv run pytest apps/studio/backend/tests/docs/test_design_doc_standards_governance.py` → **1 failed, 12 passed**，唯一红项 `test_priority_roots_are_non_empty`：`AssertionError: assert 5 > 50`（语料从 181 份缩到 5 份） | 批D-studio-2 |
| `apps/studio/backend/tests/test_doc_hash_lock.py`（整文件） | `audited-ready` 文档的哈希锁 | 同一次运行 → `test_studio_audited_ready_doc_hashes_match_baseline_or_exemption` 红：`FileNotFoundError: … docs\studio\mvp1\_audited-ready-hashes.json` | 批D-studio-3 |
| `apps/studio/backend/tests/test_design_unit_lock_snapshot.py`（整文件） | 设计单元索引与锁快照一致 | 同上 → `test_studio_design_unit_lock_snapshot_matches_current_index` 红：`AssertionError: Missing Studio design unit lock snapshot: docs/studio/mvp1/_design-unit-lock-snapshot.json` | 批D-studio-4 |
| `packages/graph-agent-gateway/tests/test_gateway_doc_locks.py`（整文件） | gateway 设计体的哈希锁与单元快照 | 同上 → 两条红：`AssertionError: Missing gateway doc hash lock: docs/graph-agent-gateway/mvp1/_audited-ready-hashes.json`、`AssertionError: Missing gateway design-unit lock snapshot: docs/graph-agent-gateway/mvp1/_design-unit-lock-snapshot.json` | 批D-gateway-1 |
| `packages/graph-agent-gateway/tests/test_gateway_design_units_bind_real_code.py`（整文件） | 每个 gateway 设计单元绑定真实代码 | 同上 → `test_every_design_unit_binds_code_that_exists` 红：`AssertionError: no binds_code coordinates found — did the frontmatter format change?` | 批D-gateway-2 |
| **孤儿测试** `packages/graph-agent/tests/tools/test_dual_run_shadow.py`（整文件） | 一个**不随迁**的工具 `packages/graph-agent/tools/dual_run_shadow.py` 的行为 | `uv run pytest packages/graph-agent/tests` → `test_dual_run_shadow_passes_explicit_resolver_to_compile_and_assemble` 红：`FileNotFoundError: … packages\graph-agent	ools\dual_run_shadow.py` | **无**——被测对象 0 消费者、随主仓归档（§3.4「不搬的三处」），门不需要复位 |

**表是全的，不是抽查出来的**：在**最终形状的 C-1 目标树**上（**2143** 个文件，构造见上一段）跑完四套，红项与本表逐条对齐、没有第七个：

| 套件 | 命令 | 结果 | 红项 |
|---|---|---|---|
| studio backend 全套 | `uv run pytest apps/studio/backend/tests -q` | **4 failed, 2172 passed, 7 skipped**（609.01s） | 本表第 1、2、3、4 行各一条 |
| gateway 全套 | `uv run pytest packages/graph-agent-gateway/tests -q` | **3 failed, 648 passed, 1 xfailed** | 本表第 5、6 行（`test_gateway_doc_locks.py` 一个文件贡献 2 条） |
| engine 全套 | `uv run pytest packages/graph-agent/tests -q` | **1 failed, 1720 passed, 2 skipped, 4 xfailed, 2 xpassed** | 只有第 7 行的孤儿测试 |
| 契约清单校验 | `uv run python packages/graph-agent/scripts/validate_round28_manifest.py …` | **EXIT=0** | 无 |

**对照组一，说明为什么 `docs/engine/**` 与两个 `.kiro` 目录必须随迁**：**不搬它们**时 engine 全套是 **4 failed, 1717 passed**（多出的三条见 §3.4 连带项表），契约校验 **EXIT=1**（`docs/engine/skill-spec/11-error-code-spec.md` 缺失）。

**对照组二，说明排除 `docs/engine/graph-skill-runtime/` 三件不损坏任何门禁**：在同一棵树上**保留**那三件（2146 个文件）跑同样四套——backend **4 failed, 2173 passed, 7 skipped**、gateway **3 failed, 648 passed, 1 xfailed**、engine **1 failed, 1720 passed, 2 skipped, 4 xfailed, 2 xpassed**、契约校验 **EXIT=0**。与上表相比**红名单逐条相同**（四条 backend 红、三条 gateway 红、一条 engine 红，测试名一字不差），**唯一差别是 backend 多 1 个通过用例**（2173 vs 2172），已定位到具体是哪一个：`pytest --collect-only` 在两棵树上分别收 2184 与 2183 个用例，差的那一个是 `tests/docs/test_doc_code_references_exist.py::test_code_references_in_authority_and_baseline_docs_exist[docs/engine/graph-skill-runtime/baseline.md]`——一个**按受治理载体逐份参数化**的用例。**它不构成门禁损失**：`test_doc_code_references_exist.py` 整文件本来就在上表第 1 行、C-1 里删除，那条参数化用例在真正的 C-1 目标树上根本不存在。

**这一组对照是必要的，不能用 grep 代替**：`baseline.md` 是本仓治理体系里的**受治理载体名**，凡按载体名扫全仓的断言都会因为少一份语料而改变行为；「没人按路径读它」证明不了「没有断言会因它消失而变红」。上面这次实跑才是证据。

**第 1–6 行是显式迁移的退出条件**：批D 每重写完一棵设计树，对应工单必须把门装回去；表未清零前，新仓 `AGENTS.md` 由 C-3 写明「设计文档治理门禁暂缺，正在批D 复位」。第 7 行（孤儿测试）没有退出条件，它随被测对象一起终结。

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
| `tests/frozen-subtrees.yaml` + `tests/test_frozen_subtree_lock.py` | 新建 | §3.4：四棵冻结子树的 tree id 治理记录与它的门；**不复用 `tests/contract-seals.yaml`**，理由（64 位摘要 / 对象必须是文件 / FROZEN 双射三条约束都不满足）见 §3.4 |
| `LICENSE` | **不动**：两仓的 `LICENSE` 是同一个 git blob（2026-09-02 实测两侧 blob sha 均为 `c7ed1e4abe5749619a5a11534f10fbbb32de75df`，Apache-2.0） | 同一份文件无所谓搬不搬 |

### 4.3 留在归档仓（不搬，731 个文件）

| 路径 | 文件数 | 不搬的依据 |
|---|---|---|
| `.kiro/**` 除随迁的两个 spec 轮次目录外 | 475 | 2026-09-03 在模拟 C-1 目标树上实跑：只有 `round-10-PR-gamma0-contract-patch/**`（5）与 `round-28-feature-checklist-redesign/**`（4）被随迁的 engine 测试按路径读取（已进「逐字节搬」桶，§3.4），其余 475 份的引用全部在 docstring/注释里做出处标注 |
| **C-1 里删除的 6 个测试文件**（5 个门禁暂缺 + 1 个孤儿测试） | 6 | §4.1.1；前 5 个读取不随迁的两棵 MVP1 树，第 6 个（`packages/graph-agent/tests/tools/test_dual_run_shadow.py`）的被测对象不随迁。**它们不在「逐字节搬」桶里**——C-1 的目标树里根本没有这六个文件，若留在该桶，§8.1-① 会以「目标缺失」失败 |
| `docs/**` 的 (c) 权威文档类 | 207 | §4.1.1；在新仓**重写**而不是搬运，清单见 §7 |
| `docs/engine/graph-skill-runtime/{README,baseline,v1-alignment}.md` | 3 | §4.1.1 的例外：新仓 `docs/design/` 同名三件的被取代前身，同仓并存即两份真相；**不搬也不重写**，引用走归档坐标。实测无任何测试/脚本按路径读它们 |
| `graph-agent-explainer/**` | 14 | 0 处引用（1.8 MB 截图） |
| `services/community-catalog-gate/**` | 12 | 0 处引用 |
| `packages/graph-agent/` 的 9 个裸文件 + `tools/dual_run_shadow.py` | 10 | §3.4：无任何消费者（它的测试单列在上面那一行） |
| `Makefile` | 1 | 唯一 target `dev-tunnel` 已经是脚本 |
| `CHANGELOG.md` | 1 | 主仓自己的变更历史，随主仓归档 |
| `tools/fix_imports.py` | 1 | 一次性迁移脚本，0 处引用 |
| `.agents/` | 1 | 0 处引用 |

### 4.4 账目闭合

**2119（逐字节搬）+ 731（留）+ 11（根级配置/权威文件，按 §4.2 逐份处置）+ 6（`.github/**`）+ 1（特殊处置：C-1 里改内容的那个门禁文件）= 2868**，等于 `git ls-tree -r --name-only 377e82e0 | wc -l` 的实测值。**这是 `377e82e0` 的快照值**；主仓 `main` 已推进到 `1a0d1203`（2873 个文件），同一支脚本在该提交上给出 **2122 + 733 + 11 + 6 + 1 = 2873**，C-1 按开工当时的 `Source-Commit` 重算，不照抄本行数字。

**为什么必须有第五个桶**：§4.1.1 登记的 7 个文件在 C-1 的目标树里**不是源文件的样子**——6 个被删除（5 个门禁暂缺 + 1 个孤儿测试）、1 个被改内容。把它们留在「逐字节搬」桶，§8.1-① 会必然报「目标缺失」或「内容不等」，即方案自相矛盾。因此：**6 个删除的进「留在归档仓」桶，1 个修改的进「特殊处置」桶**，而附录 A 的脚本用**同一份删除清单**把它们从「逐字节搬」桶里显式排除——排除清单与 §4.1.1 的表是一份来源，不是两处各写一遍。

- **11 个根级文件**：`uv.lock`、`AGENTS.md`、`pyproject.toml`、`.gitignore`、`.gitattributes`、`.importlinter`、`codecov.yml`、`.sonarcloud.properties`、`.editorconfig`、`README.md`、`LICENSE`。（另外 4 个根级单文件 `CLAUDE.md`、`skills-lock.json`、`ah.toml`、`.pre-commit-config.yaml` 已计入「逐字节搬」，`Makefile`、`CHANGELOG.md` 已计入「留」。）
- **6 个 `.github` 文件**：`ci.yml` 扩 job、`package.yml` 移植（均见 §6）；`CODEOWNERS` 由 C-3 追加条目（§7）；`dependabot.yml`、`codeql.yml`、`scorecard.yml` 新仓已有同等配置——2026-09-02 实测两仓 `dependabot.yml` 语义相同，均只覆盖 pip 与 github-actions 两个生态——主仓副本不搬。
- **零重叠、零遗漏由脚本断言**：附录 A 的脚本对**五个**桶做 `uniq -d` 重叠检查并比对全集，任一文件落入两桶即非零退出。**两处误差互相抵消是本方案明确要防的失败形态**，所以判据不是「总数对上」，而是「五桶并集 == 全集 且 两两不交」。

> 上述文件数是 2026-09-02 在主仓提交 `377e82e0` 上的实测快照。主仓 `main` 此后仍在推进（本文落盘时已到 `1a0d1203`，2873 个文件），因此 §8.1-① 的哈希核验以 **C-1 开工当时主仓 main 的实际哈希**为 `Source-Commit`，不以 `377e82e0` 为准。处置表按目录与身份给规则，快照之后新增的文件按同一套规则归类——例如 `docs/development/PARALLEL_ORCHESTRATION.md`（主仓 #1096 合入，晚于快照）是开发 SOP，落入 (c) 类由 C-3 重写。**C-1 实施方必须在开工当时的 `Source-Commit` 上重跑附录 A 的脚本，把五桶计数贴进 PR 正文。**

## 5. D10 · PR 序列

每张 PR 遵守既有交付纪律：一任务一 worktree、PR-only、codex（GPT-5.6-sol，xhigh）交叉审、裁决贴 PR 评论首行 `交叉审 r<N>:approve|rework`。

| 编号 | 仓 | 范围 | 前驱 | 门（合并条件） | 交叉审的审查对象 |
|---|---|---|---|---|---|
| **C-0a** | 主仓 | gateway `pyproject.toml:9` 把 `langchain-openai` 钉到 `>=1.3.5,<1.4.0` | 台账 17 个前驱全绿 + 用户批准本方案 | 主仓 7 道必过检查 | 单行 diff + §9.1 探针结论 |
| **C-0b** | 主仓 | 按合锁解析结果重解主仓 `uv.lock`；跑通 backend、gateway、graph-agent 全套门禁，红则在主仓修到绿 | **C-0a**（不可并行，见表注） | 主仓 7 道必过检查 | 锁文件版本跳变清单 + 为修红所做的每一处改动 |
| **C-1** | 新仓 | 一张 squash PR：文件导入（§4.1，含随冻结包搬入的 `docs/engine/**` 105 份与两个 `.kiro` spec 轮次目录 9 份）+ workspace（§3.1）+ 合锁 + CI 扩展（§6）+ 冻结封印（`tests/frozen-subtrees.yaml` 四条记录 + `tests/test_frozen_subtree_lock.py`，§3.4）+ 三份忽略/属性文件合并（§4.2）+ §4.1.1 所列 6 个用例的删除 | C-0a、C-0b 均已合并 | 新仓必过检查（扩展后 11 项，见 §6）+ §8.1-① 哈希核验 0 差异 + §8.1-② 五桶计数复现 | **①** 附录 A 脚本与哈希脚本的输出；**②** §4.2 那张表的每一行 diff；**③** §4.1.1 删除清单逐行核对（删的是不是只有读取用例与那一个孤儿测试）；**④** `frozen-subtrees.yaml` 的四条 `tree_id` 是否等于本 PR head 上 `git rev-parse HEAD:<path>` 的输出，且 `path` 集合恰好是 §3.4 那四条（§3.4） |
| **C-2** | 新仓 | 机械改名：`packages/graph-agent-gateway` → `packages/gskill-gateway`、import `graph_agent_gateway` → `gskill_gateway`、`apps/studio` → `apps/gskill-studio`、发行名与 `productName`（§3.3） | C-1 已合并 | 新仓必过检查全绿 | 改名是否**穷尽**：源码 import 155 行、`pyproject.toml` 三处、vendor 构建与校验脚本里的路径字面量、`ensure_vendor.test.js` 的硬编码路径、CI 的 working-directory |
| **C-3** | 新仓 | 权威文档改写（§7.1）+ `CLAUDE.md` 改指向 + `.ah/` 路径引用校正 | **C-2**（C-3 写的是改名后的路径，见表注） | 新仓必过检查全绿 | 改写后的正文是否自包含、是否与新仓实际路径与 11 项必过检查集一致 |
| **分支保护扩必过集** | 新仓 | 把 `studio-gates`、`frontend-gates` 与 `graph-agent-tests` 的三个 matrix context 加入必过检查（共 5 个名字） | **在 C-1 合并前**执行 | 仓库设置变更，非 PR | — |
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
- **`graph-agent-tests`**（Linux，matrix 3.11/3.12/3.13）：从主仓 `.github/workflows/ci.yml:81-131` 原样移植——冻结 engine 的 pytest 套件 + `validate_round28_manifest.py` 契约清单校验。**它是必过检查**，理由见 §3.4：共享锁会换掉冻结包脚下的依赖，只有它自己的测试能证明行为没变。**它读包外四处路径**（`code-diagnostics/**`、`config/**`、`docs/engine/**`、两个 `.kiro` spec 轮次目录），这四处都已按 §3.4 的连带项表随迁——2026-09-03 在模拟 C-1 目标树上实跑证明：不搬后两处时它 **4 failed**，搬入后同样三个测试文件只剩孤儿测试一条红。它与冻结包同生共死，批E 删包时一并删除。

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

**必过检查集**：由现有 6 项扩为 **11 项**——`quality-gates`、`runtime-tests (3.11)`、`runtime-tests (3.12)`、`runtime-tests (3.13)`、`cross-platform-smoke (windows-latest)`、`cross-platform-smoke (macos-latest)`、`studio-gates`、`frontend-gates`、`graph-agent-tests (3.11, py311)`、`graph-agent-tests (3.12, py312)`、`graph-agent-tests (3.13, py313)`。**`graph-agent-tests` 按主仓形状是 3.11/3.12/3.13 三个独立 context，占 3 项而不是 1 项**（主仓 `.github/workflows/ci.yml:81-131` 的 matrix）；分支保护按名字逐字匹配，少填两个 context 就等于两格 CI 可以红着合并。C-1 实施方以移植后 GitHub 实际显示的 check 名为准逐字钉死。

**分支保护是仓库设置、不是 PR**：该变更由协调方在 C-1 合并前执行；用户批准本方案即一并授权（§11 授权点一）。

## 7. D8 · 权威文档改写清单（决议 `:610` 要求本方案必附）

改写而非搬运，依据决议 `:607`。每一行给三项：**目标路径 / 执笔席 / 证据来源**。执笔席一律是干净上下文的独立 agent（`PARALLEL_ORCHESTRATION.md` §1.1）。证据来源统一写归档坐标 `agent-harness@<Source-Commit>:<路径>`，`<Source-Commit>` 即 C-1 导入提交里记的那个哈希。

### 7.1 第一档 · C-3 重写（本批次内完成，5 份文档 + 4 项就地校正）

| 目标路径（新仓） | 执笔席 | 证据来源（归档仓路径） | 改写内容 |
|---|---|---|---|
| `AGENTS.md` | 批C 仓级权威执笔席（Opus 5，xhigh，干净上下文） | `AGENTS.md`、`CLAUDE.md` | **删**第 18 行段落里的那一句「Gateway and Studio plugins are not deliverables in this release line; the design retains only their future external Port/Adapter ownership boundaries.」——搬入后该句为假；**删的是这一句，不是整行**（该行是一整段，其余部分讲 `docs/design/v1-alignment.md` 的 `drafted` 状态与各 Phase 验收）。**并入并以新仓路径与 11 项必过检查集重写**：CI 门禁清单、三模块架构与边界、Workflow Pipeline、Studio Tauri Dev、并行任务黑板、vendor 重建规则。**另须写明两件事**：①§4.1.1 (c) 类设计源不在本仓，引用一律写归档坐标；②§4.1.1 门禁暂缺表所列治理门禁暂缺、正在批D 复位 |
| `README.md` | 同上 | `README.md` | 改写为 monorepo 分工：runtime（可独立发布的精瘦包）/ gateway（独立包）/ studio（应用）/ 冻结 engine（带退出条件的过渡包） |
| `docs/design/v1-alignment.md` §2.1 工作名表 | 同上 | 决议 §11.5、本文 §3.3 | 加 gateway、studio 两行（发行名、目录、import 名、Display name） |
| `.github/CODEOWNERS` | 同上 | `.github/CODEOWNERS` | 加 studio 与 gateway 的契约文件条目；指向 `docs/engine/**` 的三条**原样保留**——2026-09-03 裁定后这三个路径（`public-api-contract.md`、`skill-spec/*`、`feature-compliance-checklist.md`）随冻结包搬入，条目在新仓仍指向真实文件 |
| `docs/development/DELIVERY_LEDGER.md` 头部 | 同上 | 台账正文已按 (a) 类随迁 | 只加「仓库 = 新仓」声明，正文不动 |
| `docs/development/CROSS_PLATFORM.md`、`FRONTEND_UI_SPEC.md`、`JOURNEY_TEST_RULES.md`、`RUN_AND_SCREENSHOT.md`、`FRONTEND_HANDOFF_PROMPT.md`、`PARALLEL_ORCHESTRATION.md` | 批C 开发 SOP 执笔席（Opus 5，xhigh，干净上下文） | 归档仓同名文件 | 以新仓路径、11 项必过检查集、新仓 worktree/PR 流水线重写。（`PARALLEL_ORCHESTRATION.md` 晚于本文快照，按同一规则归此档） |
| `docs/development/design-doc-standards/**` | 同上 | 已按 (b) 类随迁的同名文件 | **先搬后重写**：它被 `test_design_doc_standards_governance.py` 逐树读取，不搬则 C-1 红；重写落地时删除搬来的旧文 |
| `CLAUDE.md`（就地校正） | 同上 | 已随迁的同名文件 | 改指向新仓 `AGENTS.md` |
| `.ah/**` + `ah.toml`（就地校正） | 同上 | 已随迁的同名文件 | 路径引用随迁校正 |
| **主仓** `README.md` / `AGENTS.md`（属 **C-4**，不在 C-3） | 批C 仓级权威执笔席 | — | 顶部加归档横幅：指向新仓 + C-1 的导入提交哈希 |

### 7.2 第二档 · 批D 各模块就地重整时重写（不在批C 内，共 202 份）

依据决议 `:176` 原文：

> **搬家在模块化重整之前**,理由是**就地重整一次到位**:先搬后整,只需在最终的目录形状上重整一次;先整后搬,等于在旧形状上整一遍、搬完再对齐一遍。

逐文件清单**不列在正文**，由附录 B 的命令在 `Source-Commit` 上生成；本文快照上的分组计数如下。

| 待重写范围（目标路径 = 新仓同名目录） | 文件数 | 执笔席 | 证据来源（归档坐标前缀 `agent-harness@<Source-Commit>:`） |
|---|---|---|---|
| `docs/studio/**` = `mvp1` **85** + `mvp0` **26** + `_reorg` **10** + `INDEX.md` **1**（`for p in docs/studio/mvp1 docs/studio/mvp0 docs/studio/_reorg docs/studio/INDEX.md; do git ls-tree -r --name-only <REV> -- $p \| wc -l; done`）；含 §4.1.1 门禁暂缺表要复位的四项 | 122 | 批D studio 设计执笔席（Opus 5，xhigh，干净上下文） | `docs/studio/**` |
| `docs/graph-agent-gateway/**` = `mvp1` **39** + `mvp0` **5** + `README.md` **1**（同上命令；该目录共 46 份，`USAGE.md` 已按 (b) 类随迁，故此处 45） | 45 | 批D gateway 设计执笔席（Opus 5，xhigh，干净上下文） | `docs/graph-agent-gateway/**` |
| `docs/development/` 下其余非 SOP 文档（`CONTRIBUTING.md`、`STUDIO_DESKTOP_BOUNDARY_SPEC.md`、`LLM_MODEL_CONFIGURATION_FLOW.md` 等 11 份 + `examples/` 2） | 13 | 批D 开发文档执笔席（Opus 5，xhigh，干净上下文） | `docs/development/**` |
| `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/**` | 6 | 批D 接口设计执笔席（Opus 5，xhigh，干净上下文） | 同名归档路径 |
| `docs/superpowers/**`（`plans` 3 + `specs` 3） | 6 | 批D 开发文档执笔席 | 同名归档路径 |
| `docs/architecture/**` | 4 | 批D 架构执笔席（Opus 5，xhigh，干净上下文） | 同名归档路径 |
| `docs/strategy/**` | 4 | 批D 架构执笔席 | 同名归档路径 |
| `docs/public/**` | 1 | 批D 开发文档执笔席 | 同名归档路径 |
| `docs/DESIGN-PROCESS.md` | 1 | 批D 架构执笔席 | 同名归档路径 |
| **小计** | **202** | | |

**与 §4 账目的对账（三档之和必须等于 (c) 类总数）**：210 = **5**（第一档里不搬而由 C-3 重写的 SOP：`CROSS_PLATFORM.md`、`FRONTEND_UI_SPEC.md`、`JOURNEY_TEST_RULES.md`、`RUN_AND_SCREENSHOT.md`、`FRONTEND_HANDOFF_PROMPT.md`）+ **202**（第二档，本表小计）+ **3**（第三档：`docs/engine/graph-skill-runtime/` 三件，不搬也不重写，§7.3）。**原第三档 `docs/engine/**` 的其余 105 份已退出 (c) 类**：协调方 2026-09-03 裁定它们随冻结包搬入（§4.1.1(b)），本节合计因此由 312 降为 210。注意 `docs/development` 在附录 A 的桶里共 18 份未随迁，其中 5 份是上列 SOP（第一档）、13 份在本表（第二档），两处不重复计。`PARALLEL_ORCHESTRATION.md` 晚于本文快照，不在这 210 份里，按同一规则归第一档。

### 7.3 第三档 · 不重写（两种情况，都不进批D 的重写清单）

**情况一：`docs/engine/**` 的 105 份——搬进新仓，但永不重写。** 协调方 2026-09-03 裁定它整树（除下面三件外）随冻结引擎搬入；判据、实证与同族的两个 `.kiro` 目录见 §3.4 与 §4.1.1(b)。它随冻结包在批E 一起死亡，重写一份即将被删除的包的设计文档没有收益。

**它在新仓的身份必须被写死，否则它就是第二套格式真相**：新仓的格式权威是它自己的 `docs/skill-spec/**`；搬进去的 `docs/engine/**` 只是**冻结引擎的门禁数据**——不被任何新正文引用，只供 `graph-agent-tests` 读取，随 `packages/graph-agent` 一起进 §3.4 的冻结封印，在批E 的 X-T1b 同删。C-3 重写新仓 `AGENTS.md` 时必须写上这一句。

**情况二：`docs/engine/graph-skill-runtime/{README,baseline,v1-alignment}.md` 三件——不搬，也不重写。** 它们是新仓 `docs/design/` 下**同名三件的被取代前身**，协调方 2026-09-03 依据「文档事实唯一所有权」裁定排除（完整依据、实测字节数与零读取取证见 §4.1.1(b) 的例外段）。**不重写的理由与情况一不同**：它们要写的那份正文**新仓已经有了、而且是活的**（`docs/design/v1-alignment.md` 由新仓自己维护），批D 要做的是继续维护那一份，而不是把这三件搬过去或再写一遍。需要看它们当年写了什么，走归档坐标 `agent-harness@377e82e0:docs/engine/graph-skill-runtime/<file>`。

**这两种情况合起来，说明「不重写」不等于「不搬」**：情况一搬而不重写（门禁数据），情况二不搬也不重写（已被取代的前身）。判据始终是同一条——**在新仓里它是什么身份**，不是它在旧仓的目录形状。

## 8. D9 · 验收判据

判据分两段：**机械核验项**（脚本或 CI 给出确定输出，人只读结果）与**人证项**（必须有人看过、留下可复核的记录）。本节标题不再声称全部可机械核验——CDP 真机旅程与逐文件 diff 人审在本质上是人证。

### 8.1 机械核验项

1. **C-1 逐字节核验（协调方 2026-09-03 依据「文档事实唯一所有权」裁定：全文统一用 git blob 哈希，不另算第二套摘要）**：对 §4.1 处置表的每一个文件，比对**同一套 git 对象 id**——源侧由 `git -C <归档 clone> ls-tree -r <Source-Commit>` 一次读出的 blob id，目标侧由新仓工作树里 `git hash-object --stdin-paths` 一次算出的 blob id，两者相等。核验由附录 A 的脚本给出，输出「核验文件总数」与「差异数」，**判据是差异数 = 0 且总数等于附录 A 脚本给出的逐字节桶计数**。**不再要求任何形式的第二套文件摘要**：初稿同时写了「按文件算摘要后相等」与「用 git blob 哈希」，是两份互相冲突的验收契约，实施方无法同时满足——现统一到 git 这一套（理由与 §3.4 钉 tree id 相同：git 的对象 id 本身就是内容寻址的，再引入第二套哈希就是第二个真相源，还要自己重做行尾归一化与可执行位处理）。**对象格式实测为 `sha1`**（`git rev-parse --show-object-format` → `sha1`），**SHA-1 碰撞不在本方案的威胁模型内**：这一步防的是搬运过程中的漏搬、串行、误改，不是一个能构造碰撞的攻击者；真要防后者，该换的是整个仓库的对象格式，而不是在 git 之上叠一层自制哈希。
2. **五桶计数复现**：在 `Source-Commit` 上跑附录 A 的脚本，输出五桶计数（逐字节搬 / 留在归档仓 / 根级 / `.github` / 特殊处置）、`uniq -d` 无重叠、并集等于全集；结果贴进 C-1 的 PR 正文。
3. **新仓全部必过检查绿**，含新增的 `studio-gates`、`frontend-gates`、`graph-agent-tests`（§6）。
4. **冻结封印的取值、复核与有效性**：①**取值**——在 **C-1 的 PR head** 上读 `git rev-parse HEAD:<path>`（四条 path 见 §3.4），四个值写进 `tests/frozen-subtrees.yaml` 并贴进 C-1 的 PR 正文；PR 的 CI 在同一个 head 上跑绿 `tests/test_frozen_subtree_lock.py`，**合并前即绿**。②**合并后复核**——合并后 `main` 的 CI 再跑一次同一个测试，绿即证明「PR head 上算的值 == 合并提交上的值」；红即说明 §3.4 那条前提（这四个路径上无 main 侧并发改动）被破坏，处理方式是重算并**追加**一条新记录，不是放宽测试。③**有效性实跑**——四棵子树各改一个字节 → `test_frozen_subtree_lock.py` 变红；各改回 → 变绿；再把 `frozen-subtrees.yaml` 里删掉任意一条记录 → 断言 7（`path` 集合恰好四条）变红。
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
4. **不搬 `.kiro/**` 的绝大部分**（475 个文件，实测无路径读取）；例外是被冻结引擎测试按路径读取的两个 spec 轮次目录共 9 份，见 §3.4。
5. **不在 C-1 里顺手修任何缺陷**：搬迁途中发现的问题一律记进 `docs/development/PROBLEM_LEDGER.md` 并另开工单。
6. **不重命名仓库**（决议 `:573`）。
7. **不移植 git 历史**（决议 `:606`）。
8. **不在批C 里重写模块设计体**：`docs/studio/**`、`docs/graph-agent-gateway/**` 等按 §7.2 归**批D**（决议 §4.3「先搬后整」）；批C 只重写 §7.1 那批仓级权威与开发 SOP。
9. **不为旧 engine 文档写新版**：`docs/engine/**` 的 105 份随冻结包搬入（§7.3），但**不重写、不当权威**，批E 与包一起删；`docs/engine/graph-skill-runtime/` 三件**连搬都不搬**（§4.1.1(b) 的例外），留在归档仓，引用走归档坐标。
10. **不静默丢门**：任何因 (c) 类不随迁而删除的门禁用例，必须进 §4.1.1 的门禁暂缺表并写明复位工单。

## 11. 待用户批准项

1. **本方案整体**：批C 是结构性变更，按既有工作规则必须先呈方案、用户确认后再动手（决议 `:624`）。批准前不开工任何一张 PR。
2. **授权点一——新仓分支保护的必过检查集扩为 11 项**（§6）。仓库设置变更，不经 PR，由协调方在 C-1 合并前执行。
3. **授权点二——把主仓 `SevenX77/agent-harness` 设为 archived**（§5 的 C-4）。对外可见的设置变更，需用户在批准本方案时明确授权。

**本文没有其他待裁项**：初稿呈报与交叉审 r1 提出的全部挂起项已由协调方于 2026-09-02 逐条裁定并写入正文。

## 12. 成熟工程参照汇总

`AGENTS.md`「Development Principles」要求：引入新机制前先看成熟工程怎么解，并写明借了什么、拒绝了什么、为什么。本方案的四处新机制与其参照：

| 决定 | 参照对象（含坐标） | 借什么 | 拒绝什么 | 为什么拒绝 |
|---|---|---|---|---|
| D1 workspace 形状 | uv 官方 workspace 文档 <https://docs.astral.sh/uv/concepts/projects/workspaces/>（引「shares a single lockfile」「root, which is _also_ a workspace member」两句原文）；`pydantic/pydantic-ai` 根 `pyproject.toml`（blob `0418b5a3…`：`[build-system]` + `[project] name = "pydantic-ai"` + `[tool.uv.workspace] members` 五个 + 仓根唯一 `uv.lock`） | 一仓一锁、成员各自 `pyproject.toml`、根 project 本身也是成员且可发布；wheel 内容由构建后端配置决定 | 根做成虚包；**并撤销初稿的 langchain 参照**（其公开文档写明每个 `libs/` 包各有自己的 `uv.lock`，与初稿描述相反） | 虚包会把 runtime 从仓根挪走，连带改发布链，收益为零；错误参照无法复核 |
| D2 squash 导入 + 出处 trailer | Kubernetes publishing-bot README（`Kubernetes-sha: <sha>`）；`git subtree --squash` 文档（`contrib/subtree/git-subtree.adoc`） | 压成单提交 + 机器可读的源提交指针 | 真正的历史移植；持续双向同步 | 前者与新仓线性历史保护冲突；后者与决议 `:180`「归档为只读」冲突 |
| D4 冻结包的封印（钉 git tree id） | Go modules 的 `go.sum` 与 `go mod verify`（<https://go.dev/ref/mod#go-sum-files>、<https://go.dev/ref/mod#go-mod-verify>） | 「先记下内容哈希，再让任何偏离以非零状态退出」这条原理 | ①清单可由工具自动重新生成的宽松语义；②逐文件列哈希的清单形式 | 冻结包只有「不变」与「整包删除」两种终局，重钉必须是带 `pm_approval` 记录的显式动作；git 的 tree 对象本身已是内容寻址清单，再列一份就是第二真相源 |
| D6 文档三类处置 | PEP 1（<https://peps.python.org/pep-0001/>） | 历史文档与活规范分开处置 | `Superseded-By` 链、旧文永久同仓留存 | 旧设计体在批D 重写后没有读者，留在新仓即第二真相源；追溯由归档坐标满足 |

**未采用的候选参照**：Kubernetes KEP 与 kubernetes.io 的分工（原拟支撑 D6）。2026-09-02 读 `keps/README.md`，找不到可用来支撑「提案记录 vs 用户文档」这一分法的明文，**证不成，故不引**。

## 13. 附录

### 附录 A · 处置分桶与目标核验的可执行契约

脚本 `scripts/migration-buckets.sh` 随 C-1 提交到新仓。它**不是一段供人照抄的命令清单，而是一个会失败的门**：

**接口**：`migration-buckets.sh --source-repo <路径> --source-commit <sha> [--target-tree <路径>] [--out <目录>]`。
源提交**由参数给入**，脚本里没有任何硬编码的快照哈希；源仓一律用 `git -C "$SOURCE_REPO"` 访问。

**它在哪里跑**：C-1 的实施机上，**源仓归档 clone 与新仓目标树同时可见**的位置——例如
`migration-buckets.sh --source-repo ~/clones/agent-harness --source-commit <Source-Commit> --target-tree .`
在新仓 worktree 里执行。**不能在新仓里直接 `git ls-tree <Source-Commit>`**：新仓没有主仓的历史，
那条命令会以 128 退出（这正是脚本第一步就 `git -C "$SRC" cat-file -e "$REV^{commit}"` 的原因）。
目标树必须是一个 git 检出（脚本在其中用 `git hash-object --stdin-paths` 批量算内容哈希）。

**它断言什么**（任一不成立即非零退出，`set -euo pipefail`）：

| 断言 | 失败时的退出码 |
|---|---|
| `<source-commit>` 在源仓里是一个真提交 | 3 |
| 五桶两两不交（`uniq -d` 为空） | 1 |
| 五桶并集 == 源提交的全部跟踪文件 | 1 |
| 「逐字节搬」桶的每个文件在目标树里存在 | 1 |
| 该桶每个文件的内容哈希与源一致 | 1 |

**内容哈希用 git 的 blob 哈希，不另算第二套逐文件摘要**：源侧从一次 `git ls-tree -r <REV>` 直接读出
（blob 哈希就在输出里，零额外进程），目标侧一次 `git hash-object --stdin-paths` 批量算完。
两侧同法计算，相等当且仅当字节相同；代价是 2 次进程调用而不是 4000 次——在 Windows 上这是分钟与秒的差别。
**这与 §8.1-① 是同一条契约，不是两条**：全文只承认 git 对象 id 这一套（文件用 blob id、目录用 tree id），不再另要求任何第二套文件摘要（见 §8.1-① 与 §3.4）。

**2026-09-02 / 09-03 的实跑证据（含负例）**：

| 场景 | 命令要点 | 输出 | 退出码 |
|---|---|---|---|
| 正例 · 分桶（快照提交） | `--source-commit 377e82e0` | `逐字节搬 2119 / 留在归档仓 731 / 根级 11 / .github 6 / 特殊处置 1 / 全集 2868`，`OK 五桶两两不交`、`OK 并集等于全集 (2868)` | **0** |
| 正例 · 分桶（当前 main） | `--source-commit 1a0d1203` | `2122 / 733 / 11 / 6 / 1 / 全集 2873`，两条 OK | **0** |
| 正例 · 目标核验 | `--source-commit 1a0d1203 --target-tree <主仓工作树>` | `OK 逐字节核验 差异数=0 总数=2122` | **0** |
| 负例 · 桶重叠 | 注入 `CLAUDE.md` 同时进两个桶 | `FAIL overlap between buckets: CLAUDE.md` → `RESULT=FAIL` | **1** |
| 负例 · 内容不等 | 源 `377e82e0` 对目标 `1a0d1203` 工作树 | `FAIL content differs (7):` 后逐行列出 7 个文件（含 `docs/development/DELIVERY_LEDGER.md`） | **1** |
| 负例 · 目标缺文件 | 目标指向空 git 仓 | `FAIL missing in target:` ×2119 | **1** |
| 负例 · 源提交不存在 | `--source-commit deadbeef` | `FAIL: deadbeef is not a commit in <源仓>` | **3** |

「内容不等」那一例同时说明了为什么必须按 `Source-Commit` 重算：那 7 个文件（含 `docs/development/DELIVERY_LEDGER.md`）
在 `377e82e0` 与 `1a0d1203` 之间改过，拿旧快照去核验新目标就会（正确地）失败。本文写作期间主仓 `main`
自身就从 `377e82e0` 走到了 `6547029e` 再到 `1a0d1203`——这正是「快照数字不可照抄、C-1 必须重跑」的实证。

**C-1 删除清单是排除清单的唯一来源**：脚本把 §4.1.1 那 7 个文件写在一处（6 个删除 + 1 个修改），
「逐字节搬」桶用 `grep -v -x -F -f` 把它们排除，「留在归档仓」桶因是补集而自动收下那 6 个删除文件。
两处各写一遍就会漂移，所以只写一遍。

**脚本正文**（C-1 提交的即此文件）：

```bash
#!/usr/bin/env bash
# 批C 搬迁的处置分桶与目标核验(方案 docs/design/gskill-migration-plan-2026-09-02.md §4/§8.1)。
#
# 它回答两个问题,任一不成立即非零退出:
#   1. 源仓 <source-commit> 的每个跟踪文件,是否恰好落进五个桶里的一个?
#   2. 「逐字节搬」桶里的每个文件,在目标树里是否存在、内容是否与源一致?
#
# 用法:
#   migration-buckets.sh --source-repo <路径> --source-commit <sha> [--target-tree <路径>] [--out <目录>]
# 给了 --target-tree 才做第 2 问;C-1 里必须给,而且要在**源仓归档 clone 与新仓目标树同时可见**的
# 检出上运行(脚本对源仓一律用 `git -C "$SOURCE_REPO"`,不依赖当前目录所在仓的历史——新仓里没有
# 主仓的提交,直接 `git ls-tree <source-commit>` 会以 128 退出)。
set -euo pipefail

SRC="" REV="" TGT="" OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --source-repo)   SRC="$2"; shift 2 ;;
    --source-commit) REV="$2"; shift 2 ;;
    --target-tree)   TGT="$2"; shift 2 ;;
    --out)           OUT="$2"; shift 2 ;;
    --inject-overlap) INJECT="$2"; shift 2 ;;   # 仅供自测:把一个路径同时塞进两个桶
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$SRC" ] && [ -n "$REV" ] || { echo "usage: --source-repo <path> --source-commit <sha> [--target-tree <path>]" >&2; exit 2; }
git -C "$SRC" cat-file -e "$REV^{commit}" 2>/dev/null || { echo "FAIL: $REV is not a commit in $SRC" >&2; exit 3; }
OUT="${OUT:-$(mktemp -d)}"; mkdir -p "$OUT"

ls_() { git -C "$SRC" ls-tree -r --name-only "$REV" -- "$@"; }

# C-1 里删除的用例(方案 §4.1.1)—— 唯一来源,下面三处都引用它
# 前五条是门禁暂缺表(等批D 复位);第六条是孤儿测试(被测对象 tools/dual_run_shadow.py 不随迁,无复位工单)
cat > "$OUT/c1-delete.txt" <<'EOF'
apps/studio/backend/tests/docs/test_doc_code_references_exist.py
apps/studio/backend/tests/test_doc_hash_lock.py
apps/studio/backend/tests/test_design_unit_lock_snapshot.py
packages/graph-agent-gateway/tests/test_gateway_doc_locks.py
packages/graph-agent-gateway/tests/test_gateway_design_units_bind_real_code.py
packages/graph-agent/tests/tools/test_dual_run_shadow.py
EOF
echo 'apps/studio/backend/tests/docs/test_design_doc_standards_governance.py' > "$OUT/special.txt"

# 桶一 · 逐字节搬(显式排除上面七个:六个 C-1 删除、一个 C-1 修改)
{ ls_ apps/studio packages/graph-agent-gateway
  ls_ packages/graph-agent/pyproject.toml packages/graph-agent/README.md \
      packages/graph-agent/src packages/graph-agent/tests \
      packages/graph-agent/spec packages/graph-agent/scripts
  ls_ code-diagnostics config
  ls_ docs/design docs/studio-mvp1-execution docs/handoffs \
      docs/pr-reports docs/references docs/deferred-items.md \
      docs/development/DELIVERY_LEDGER.md docs/development/PROBLEM_LEDGER.md
  # 冻结引擎的门禁数据(r3 裁决):整树随冻结包搬入、批E 同删,但排除 graph-skill-runtime/ 三件
  # (r4 裁决:它们是新仓 docs/design/ 同名三件的被取代前身,同仓并存即两份真相)
  ls_ docs/engine | grep -v '^docs/engine/graph-skill-runtime/'
  # 同族的另两处:随迁的 engine 测试按路径读取这两个 spec 轮次目录(方案 §4.1.1(b))
  ls_ .kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
  ls_ .kiro/specs/engine-mvp0-rebuild-v030/round-28-feature-checklist-redesign
  ls_ docs/development/llm_provider_notes docs/development/design-doc-standards \
      docs/development/STUDIO_REQUEST_AUDIT.md docs/graph-agent-gateway/USAGE.md
  ls_ scripts .claude skills-lock.json .ah ah.toml .pre-commit-config.yaml CLAUDE.md
} | sort -u | grep -v -x -F -f "$OUT/c1-delete.txt" | grep -v -x -F -f "$OUT/special.txt" > "$OUT/move.txt"

# 桶三 · 根级配置/权威文件(§4.2 逐份处置)
printf '%s\n' uv.lock AGENTS.md pyproject.toml .gitignore .gitattributes .importlinter \
  codecov.yml .sonarcloud.properties .editorconfig README.md LICENSE | sort > "$OUT/root.txt"
# 桶四 · .github(§6 重写/移植)
ls_ .github | sort > "$OUT/gh.txt"
# 桶五 · 特殊处置(C-1 里改内容的门禁文件)= special.txt
# 桶二 · 留在归档仓 = 全集 − 其余四桶(C-1 删除的六个用例天然落在这里)
ls_ . | sort -u > "$OUT/all.txt"
if [ -n "${INJECT:-}" ]; then echo "$INJECT" >> "$OUT/root.txt"; sort -u -o "$OUT/root.txt" "$OUT/root.txt"; fi
cat "$OUT/move.txt" "$OUT/root.txt" "$OUT/gh.txt" "$OUT/special.txt" | sort -u > "$OUT/accounted.txt"
comm -23 "$OUT/all.txt" "$OUT/accounted.txt" > "$OUT/stay.txt"

printf 'SOURCE_COMMIT=%s\n' "$REV"
printf '%-12s %5d\n' 逐字节搬 "$(wc -l < "$OUT/move.txt")" 留在归档仓 "$(wc -l < "$OUT/stay.txt")" \
  根级 "$(wc -l < "$OUT/root.txt")" .github "$(wc -l < "$OUT/gh.txt")" 特殊处置 "$(wc -l < "$OUT/special.txt")"
printf '%-12s %5d\n' 全集 "$(wc -l < "$OUT/all.txt")"

fail=0
dup="$(cat "$OUT/move.txt" "$OUT/stay.txt" "$OUT/root.txt" "$OUT/gh.txt" "$OUT/special.txt" | sort | uniq -d || true)"
if [ -n "$dup" ]; then echo "FAIL overlap between buckets:"; echo "$dup"; fail=1; else echo "OK 五桶两两不交"; fi
union="$(cat "$OUT/move.txt" "$OUT/stay.txt" "$OUT/root.txt" "$OUT/gh.txt" "$OUT/special.txt" | sort -u | wc -l)"
total="$(wc -l < "$OUT/all.txt")"
if [ "$union" != "$total" ]; then echo "FAIL union=$union != all=$total"; fail=1; else echo "OK 并集等于全集 ($total)"; fi

if [ -n "$TGT" ]; then
  # 期望内容哈希:git 的 blob 哈希,源侧从 ls-tree 直接读(一次调用),目标侧用 hash-object 批量算(一次调用)
  git -C "$SRC" ls-tree -r "$REV" | awk '{print $3"\t"substr($0, index($0,$4))}' | sort -k2 > "$OUT/src-hashes.tsv"
  missing=0
  while IFS= read -r p; do
    [ -f "$TGT/$p" ] || { echo "FAIL missing in target: $p"; missing=$((missing+1)); }
  done < "$OUT/move.txt"
  [ "$missing" -eq 0 ] || { echo "RESULT=FAIL"; exit 1; }
  # 目标侧哈希:在目标树内用相对路径批量算(目标树必须是一个 git 检出——C-1 里就是新仓的 worktree)
  ( cd "$TGT" && git hash-object --stdin-paths ) < "$OUT/move.txt" > "$OUT/tgt-hashes.txt"
  paste "$OUT/tgt-hashes.txt" "$OUT/move.txt" | sort -k2 > "$OUT/tgt-hashes.tsv"
  diffs="$(join -j 2 -o 0,1.1,2.1 "$OUT/src-hashes.tsv" "$OUT/tgt-hashes.tsv" | awk '$2!=$3{print $1}' || true)"
  n_diff="$(printf '%s' "$diffs" | grep -c . || true)"
  if [ "$n_diff" != "0" ]; then echo "FAIL content differs ($n_diff):"; echo "$diffs" | head -20; fail=1
  else echo "OK 逐字节核验 差异数=0 总数=$(wc -l < "$OUT/move.txt")"; fi
fi
[ "$fail" -eq 0 ] || { echo "RESULT=FAIL"; exit 1; }
echo "RESULT=PASS"
```

### 附录 B · 不随迁的两棵 MVP1 设计树逐文件清单（124 份）

决议 `:610` 要求本方案附权威文档重写清单。§7.2 给的是分组、执笔席与证据来源，本附录给**逐文件**清单，
一行不少。**继承规则（表头即规则，逐行不再重复）**：

- **目标路径** = 新仓同名路径（`docs/studio/mvp1/**` → `docs/studio/mvp1/**`；批D 重写落地时若目录形状变化，
  以批D 的模块重整方案为准，本方案不预判）。
- **执笔席** = 按顶层目录继承 §7.2：`docs/studio/mvp1/**` 归**批D studio 设计执笔席（Opus 5，xhigh，干净上下文）**；
  `docs/graph-agent-gateway/mvp1/**` 归**批D gateway 设计执笔席（Opus 5，xhigh，干净上下文）**。
- **证据来源** = `agent-harness@<Source-Commit>:<下表路径>:<行号>`（归档坐标，决议 `:607` 要求的引用形式）。

清单由下列命令生成（本表是它在 `377e82e0` 上的输出，共 124 行）：

```bash
git ls-tree -r --name-only <Source-Commit> -- docs/studio/mvp1 docs/graph-agent-gateway/mvp1
```

  1. `docs/graph-agent-gateway/mvp1/01-handoff-interface/baseline.md`
  2. `docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md`
  3. `docs/graph-agent-gateway/mvp1/02-orch-role-resolution/baseline.md`
  4. `docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md`
  5. `docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/baseline.md`
  6. `docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md`
  7. `docs/graph-agent-gateway/mvp1/04-orch-registry-schema/baseline.md`
  8. `docs/graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md`
  9. `docs/graph-agent-gateway/mvp1/05-orch-capabilities-and-models/baseline.md`
 10. `docs/graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md`
 11. `docs/graph-agent-gateway/mvp1/06-orch-error-classification/baseline.md`
 12. `docs/graph-agent-gateway/mvp1/06-orch-error-classification/mvp1-alignment.md`
 13. `docs/graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/baseline.md`
 14. `docs/graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/mvp1-alignment.md`
 15. `docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/baseline.md`
 16. `docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`
 17. `docs/graph-agent-gateway/mvp1/09-inv-invocation-runtime/baseline.md`
 18. `docs/graph-agent-gateway/mvp1/09-inv-invocation-runtime/mvp1-alignment.md`
 19. `docs/graph-agent-gateway/mvp1/10-inv-route-chat-model-factory/baseline.md`
 20. `docs/graph-agent-gateway/mvp1/10-inv-route-chat-model-factory/mvp1-alignment.md`
 21. `docs/graph-agent-gateway/mvp1/11-inv-provider-profiles/baseline.md`
 22. `docs/graph-agent-gateway/mvp1/11-inv-provider-profiles/mvp1-alignment.md`
 23. `docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/baseline.md`
 24. `docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/mvp1-alignment.md`
 25. `docs/graph-agent-gateway/mvp1/14-media-generation/design-decision.md`
 26. `docs/graph-agent-gateway/mvp1/AUDIT_REMEDIATION_PLAN.md`
 27. `docs/graph-agent-gateway/mvp1/AUDIT_REPORT.md`
 28. `docs/graph-agent-gateway/mvp1/DESIGN_UNITS_INDEX.md`
 29. `docs/graph-agent-gateway/mvp1/README.md`
 30. `docs/graph-agent-gateway/mvp1/_audited-ready-hashes.json`
 31. `docs/graph-agent-gateway/mvp1/_design-unit-lock-snapshot.json`
 32. `docs/graph-agent-gateway/mvp1/_impl/IMPL_PLAN.md`
 33. `docs/graph-agent-gateway/mvp1/_impl/WS1-chatx-core.md`
 34. `docs/graph-agent-gateway/mvp1/_impl/WS2-base-url-gemini-handoff.md`
 35. `docs/graph-agent-gateway/mvp1/_impl/WS2-base-url.md`
 36. `docs/graph-agent-gateway/mvp1/_impl/WS4-fallback-events.md`
 37. `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`
 38. `docs/graph-agent-gateway/mvp1/predict-migration-to-engine.md`
 39. `docs/graph-agent-gateway/mvp1/references/chatx-provider-patterns.md`
 40. `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`
 41. `docs/studio/mvp1/01_workflows/00_settings.md`
 42. `docs/studio/mvp1/01_workflows/01_init.md`
 43. `docs/studio/mvp1/01_workflows/02_authoring.md`
 44. `docs/studio/mvp1/01_workflows/03_compile.md`
 45. `docs/studio/mvp1/01_workflows/04_run-and-verify.md`
 46. `docs/studio/mvp1/01_workflows/05_debugging.md`
 47. `docs/studio/mvp1/01_workflows/06_eval.md`
 48. `docs/studio/mvp1/01_workflows/INDEX.md`
 49. `docs/studio/mvp1/02_capabilities/README.md`
 50. `docs/studio/mvp1/02_capabilities/compile-lint/baseline.md`
 51. `docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`
 52. `docs/studio/mvp1/02_capabilities/conflict-overwrite/baseline.md`
 53. `docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md`
 54. `docs/studio/mvp1/02_capabilities/copilot-assist/baseline.md`
 55. `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
 56. `docs/studio/mvp1/02_capabilities/debug-resume/baseline.md`
 57. `docs/studio/mvp1/02_capabilities/debug-resume/mvp1-alignment.md`
 58. `docs/studio/mvp1/02_capabilities/file-editing/baseline.md`
 59. `docs/studio/mvp1/02_capabilities/file-editing/mvp1-alignment.md`
 60. `docs/studio/mvp1/02_capabilities/golden-eval/baseline.md`
 61. `docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md`
 62. `docs/studio/mvp1/02_capabilities/graph-authoring/baseline.md`
 63. `docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md`
 64. `docs/studio/mvp1/02_capabilities/media-generation/design-decision.md`
 65. `docs/studio/mvp1/02_capabilities/phase-editing/baseline.md`
 66. `docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md`
 67. `docs/studio/mvp1/02_capabilities/predict/baseline.md`
 68. `docs/studio/mvp1/02_capabilities/predict/mvp1-alignment.md`
 69. `docs/studio/mvp1/02_capabilities/publish/baseline.md`
 70. `docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md`
 71. `docs/studio/mvp1/02_capabilities/run-execution/baseline.md`
 72. `docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md`
 73. `docs/studio/mvp1/02_capabilities/skill-workspace/baseline.md`
 74. `docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md`
 75. `docs/studio/mvp1/02_capabilities/studio-settings/baseline.md`
 76. `docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md`
 77. `docs/studio/mvp1/02_capabilities/trace-observability/baseline.md`
 78. `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`
 79. `docs/studio/mvp1/03_regions/README.md`
 80. `docs/studio/mvp1/03_regions/assets/baseline.md`
 81. `docs/studio/mvp1/03_regions/assets/mvp1-alignment.md`
 82. `docs/studio/mvp1/03_regions/canvas/baseline.md`
 83. `docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md`
 84. `docs/studio/mvp1/03_regions/center-action-bar/baseline.md`
 85. `docs/studio/mvp1/03_regions/center-action-bar/mvp1-alignment.md`
 86. `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`
 87. `docs/studio/mvp1/03_regions/copilot/baseline.md`
 88. `docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md`
 89. `docs/studio/mvp1/03_regions/editor/baseline.md`
 90. `docs/studio/mvp1/03_regions/editor/mvp1-alignment.md`
 91. `docs/studio/mvp1/03_regions/input/baseline.md`
 92. `docs/studio/mvp1/03_regions/input/mvp1-alignment.md`
 93. `docs/studio/mvp1/03_regions/local-history/baseline.md`
 94. `docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md`
 95. `docs/studio/mvp1/03_regions/properties/baseline.md`
 96. `docs/studio/mvp1/03_regions/properties/mvp1-alignment.md`
 97. `docs/studio/mvp1/03_regions/settings/baseline.md`
 98. `docs/studio/mvp1/03_regions/settings/mvp1-alignment.md`
 99. `docs/studio/mvp1/03_regions/shell-layout/baseline.md`
100. `docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md`
101. `docs/studio/mvp1/03_regions/timeline/baseline.md`
102. `docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md`
103. `docs/studio/mvp1/03_regions/welcome/baseline.md`
104. `docs/studio/mvp1/03_regions/welcome/mvp1-alignment.md`
105. `docs/studio/mvp1/04_platform/README.md`
106. `docs/studio/mvp1/04_platform/engine/baseline.md`
107. `docs/studio/mvp1/04_platform/engine/mvp1-alignment.md`
108. `docs/studio/mvp1/04_platform/gateway/baseline.md`
109. `docs/studio/mvp1/04_platform/gateway/mvp1-alignment.md`
110. `docs/studio/mvp1/04_platform/i18n.md`
111. `docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md`
112. `docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md`
113. `docs/studio/mvp1/04_platform/native-fs/baseline.md`
114. `docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md`
115. `docs/studio/mvp1/04_platform/state-engine/baseline.md`
116. `docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md`
117. `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`
118. `docs/studio/mvp1/README.md`
119. `docs/studio/mvp1/_audited-ready-hashes.json`
120. `docs/studio/mvp1/_design-unit-lock-snapshot.json`
121. `docs/studio/mvp1/_impl/IMPL_PLAN.md`
122. `docs/studio/mvp1/_impl/STUDIO-MVP1-INTEGRATION-BASELINE.md`
123. `docs/studio/mvp1/_migrated-coverage-drift.md`
124. `docs/studio/mvp1/_proposal-skill-repo-git-model.md`

**这 124 份与 §4 账目的关系**：它们全在「留在归档仓」桶里，是 (c) 类 **210** 份中的 **124** 份；
**余下 86 份**（210 − 124）的分组见 §7.2 与 §7.3。

## 修订记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-03 | 交叉审 r4（codex，五条 P1 + 四条 P2）经协调方逐条裁定后返修 | ①**冻结封印改用独立载体**（协调方依据「钉值即治理记录」与 git 内容寻址裁定）：新建 `tests/frozen-subtrees.yaml` + `tests/test_frozen_subtree_lock.py`，**不复用 `tests/contract-seals.yaml`**——实测新仓 `a4f43d83` 的 `test_contract_hash_lock.py` 强制「64 位摘要」（`:146-147`）、「对象必须是文件」（`:197-198`）与「FROZEN 文档 ⇔ seal 记录双射」（`:271` 起），本封印三条都不满足；生命周期也不同（批E 整包删除 vs 逐份解冻）。记录借它的治理字段与 fail-closed 读法（`subtree_id`/`path`/`tree_id`/`reason`/`pr`/`pm_approval`，同一 `path` 最后一条即现值），正文给出 yaml 样例与 8 条断言清单，**封印范围由两棵扩为四棵子树**（补两个 `.kiro` 目录）。②**钉值时序改为「取自 C-1 的 PR head」**：上一稿的「合并后取值」与「合并前必须绿」是死环。依据两条实测事实——新仓 `main`（`96019595`）上 `packages`/`docs/engine`/`.kiro` 三者跟踪文件数**均为 0**，且仓库设置 `allow_squash_merge=true`、`allow_merge_commit=false`、`allow_rebase_merge=false`——这四个路径上不存在 main 侧并发改动，squash 结果树在这些路径上与 PR head 逐字节相同，故 PR head 上算的 tree id 就是合并提交上的值；合并后 `main` 的 CI 再跑一次即复核。rebase 亦不改变这四个值。§3.4 / §5 C-1 行 / §8.1-④ 三处同步改写。③**`sha256` 字样按裁决收敛**：全文 `grep -n -i sha256` 现只剩 4 处——两处在**描述 `contract-seals.yaml`**（新仓 #22 的文件级封印）的句子里，每处紧跟「本方案的冻结封印用 `tests/frozen-subtrees.yaml` 的 tree id，不用它」；另两处在修订历史里并已标注**已废弃**。其余（§8.1-①、附录 A 两处、断言表一处）改为「第二套摘要」等中性表述。④**撤销对 `ROLE_REQUIRED_ROOTS` 的改动要求**：它在模拟树上不报红，属于没有失败断言支撑的推断改动，与本方案自己的入表判据冲突；C-1 不动它，归批D，表里那半句删除。⑤**「四桶」四处统一为「五桶」**（§4.4 判据、§4 快照注、§5 C-1 门、§8.1-②）。⑥四条 P2：`packages/graph-agent` 下 `graph-skill-runtime` 命中数订正为 **5 处**（补 `README.md:23`）；全量表改以**最终形状目标树**（2143 文件）为准、backend 记 `4 failed, 2172 passed, 7 skipped`，保留三件的那次（2146 文件）降为对照组二；附录 A 脚本里 `.kiro` 那行的字面量换行符修好（此前 bash 会把它当成一个名为 `n` 的多余 pathspec，恰因仓里没有该路径才没出错），重嵌后与磁盘版逐字节相同并重跑全部正负例；附录 B 余数订正为 **210 − 124 = 86**。 |
| 2026-09-03 | 交叉审 r3 之后协调方补两条裁决（`.kiro` 确认 + `graph-skill-runtime` 三件排除）后返修 | ①**`.kiro` 那 9 份的随迁经协调方确认，并在正文改写为「同一条判据的第二次应用」而不是新决定**：判据仍是「随迁的冻结包测试按路径读取的门禁数据」，它与 `code-diagnostics/**`、`config/**`、`docs/engine/**` 同列在 §3.4 的连带项表里，不分主次；`.kiro/**` 其余 475 份留档。②**`docs/engine/graph-skill-runtime/{README,baseline,v1-alignment}.md` 三件改为不搬**（协调方依据「文档事实唯一所有权」裁定）：它们是新仓 `docs/design/` 同名三件的被取代前身，同仓并存两份同名不同内容的文档就是两份真相，靠 `AGENTS.md` 一句话压住是补丁不是修根；三件进「留在归档仓」桶，引用走归档坐标 `agent-harness@377e82e0:docs/engine/graph-skill-runtime/<file>`。**排除前先取证**：`git grep -n 'graph-skill-runtime/' packages/graph-agent/{tests,scripts,spec}` 零命中（退出 1），整包放宽后 4 处全是 markdown 链接与注释，全仓 `-- ':!*.md'` 零命中；再以模拟树复核，删掉三件后四套结果与保留时逐条相同（backend `4 failed, 2172 passed`、gateway `3 failed, 648 passed`、engine `1 failed, 1720 passed`、契约校验 `EXIT=0`）。③**封印钉值改为「C-1 合并后取值」**：删掉「可预言值 `7da0335d…`」的写法（两棵子树都不是整树平移，源侧值与目标必然不等，写预言只会让首跑无谓地红），改为在 C-1 合并提交上读 `git rev-parse <合并提交>:packages/graph-agent` 与 `:docs/engine` 写进 seal；源侧 tree id 降为核对参考，其「两个提交间未漂移」仍作为「冻结有意义」的前提证据。§5 交叉审对象④、§8.1-④ 同步改写。④**§7.3 重写为两种「不重写」并列**：情况一（105 份，搬而不重写，门禁数据）、情况二（3 份，不搬也不重写，已被取代的前身），并写明判据始终是「在新仓里它是什么身份」。⑤账目重算：(a) 107 + (b) 122 = **229** 份 docs 随迁，(c) **210**（= 批D 重写 207 + 不重写 3）；五桶 **2119 + 731 + 11 + 6 + 1 = 2868**（`377e82e0`）、**2122 + 733 + 11 + 6 + 1 = 2873**（当前 `1a0d1203`）；§7.2 三档对账 210 = 5 + 202 + 3。 |
| 2026-09-03 | 交叉审 r3（codex，五条 P1）经协调方逐条裁定后返修 | ①**`docs/engine/**` 108 份整树随冻结包搬入**（协调方裁定）：它是冻结引擎的门禁数据、不是格式权威，随迁后进冻结封印、批E 同删；连带把 §7.3 由「不搬」改写为「随迁但永不重写」、(c) 类由 312 收敛为 207、`.github/CODEOWNERS` 三条不再删。**同族排查另发现两处**：随迁的 engine 测试还按路径读 `.kiro/specs/engine-mvp0-rebuild-v030/{round-10-PR-gamma0-contract-patch,round-28-feature-checklist-redesign}/**` 共 9 份，按同一判据一并随迁（实证：不搬时 engine 全套 4 failed，放回后同三个文件 1 failed）。②**引文核验补上外部引文这一路**：此前 8 条外部引文标记为 `external` 后被核验器整段跳过，正是 uv 原文大小写走样却无人发现的原因；现把 8 份上游原始文件抓到本地（uv workspaces.md、Go `mod.md`、PEP 1、publishing-bot README、`git-subtree.adoc`），逐条与正文比对。uv 引文订正为大写 `In a workspace` 开头的完整句；§12 表里的「主仓迁完即归档」改为逐字的决议 `:180`「归档为只读」。三路核验结果：仓内 32 条 OK / 0 FAIL，外部 8 条 OK / 0 FAIL，反向 90 个「」串、未登记 0、白名单陈旧 0。③**门禁暂缺表改为「只收实跑变红者」**：撤销对 `test_summary_role_names_an_authority_file_that_exists` 与 `test_at_least_one_real_summary_role_exists` 的删除（实跑两条都通过，删了等于凭空丢掉两条通用治理保护），每行补「实证：命令 → 失败断言」；并在候选全部在场的模拟树上跑完四套证明表是全的：backend `4 failed, 2173 passed`、gateway `3 failed, 648 passed`、engine `1 failed, 1720 passed`、契约校验 `EXIT=0`。**模拟树改用 `git clone` + `git rm` 造**——`git archive` + `tar` 出来的不是 git 仓，会让 `_is_executable()` 凭空多报两条假红。④**验收契约统一到 git blob 哈希**：删掉 §8.1-① 的「sha256 相等」与 §3.4 的「逐文件算 sha256」（**这两处措辞已废弃**，r4 起全文只认 git 对象 id），全文只认 `git ls-tree` / `git hash-object` 这一套，并写明对象格式实测为 `sha1`、SHA-1 碰撞不在威胁模型内。⑤**D4 参照改为 `go.sum` ↔ `go mod verify`**：初稿把 `vendor/modules.txt` 与 `go mod verify` 说成一对清单/校验，按 Go 官方文档二者并不互校（`modules.txt` 只查与 `go.mod` 的版本一致性，`go mod verify` 读的是模块缓存），该说法已在正文声明作废；封印的钉值同时由「逐文件哈希清单」改为**两个 git tree id**，重钉 = 改一个十六进制串 + 一条带 `pm_approval` 的 seal 记录。⑥账目随 ①③ 重算：**2122 + 728 + 11 + 6 + 1 = 2868**（`377e82e0`）、**2125 + 730 + 11 + 6 + 1 = 2873**（当前 `1a0d1203`）。 |
| 2026-09-03 | 交叉审 r2（codex，七条 P1 + 两条 P2）经协调方逐条裁定后返修 | ①**引文核验改成双向**：正向核对每条登记引文逐字命中源文件，**反向**扫描正文里每一个「」串——它要么是登记引文的子串，要么在一份写明理由的白名单（本文自造的术语/节名/对自身草稿与工具输出的回指）里；当前 75 个串：登记引文覆盖 22、白名单 53、未登记 0。五条 MISS 按此处理：`AGENTS.md:233`、决议 `:172`、决议 `:176` 改为逐字引用，决议 `:180` 改为「意为」，「把旧的设计权威正文原样搬过去继续当权威」是本文的理解、去引号。②**门禁暂缺表的 6 个文件出「逐字节搬」桶**：5 个 C-1 删除的进「留在归档仓」桶、1 个 C-1 修改的进新增的「特殊处置」桶，附录 A 的脚本用**同一份暂缺表文件列**把它们显式排除——此前它们同时被要求「删/改」与「sha256 与源全等」（**该措辞已废弃**，r4 起统一为 git blob id），方案自相矛盾。账目重算 **2009 + 841 + 11 + 6 + 1 = 2868**（`377e82e0` 快照）、**2011 + 843 + 11 + 6 + 1 = 2872**（当前 `6547029e`）。③门禁暂缺表补 `test_priority_roots_are_non_empty`（`:256-258` 断言 `len(_priority_docs()) > 50`，两棵树不搬后语料只剩 5 份必红）；同族排查已覆盖 `tests/docs/**` 与两个 package 的全部文档类断言。④附录 A 改成**可执行契约**：源提交由参数给入、`set -euo pipefail`、五类断言各有退出码，并附三个负例与两个正例的实跑输出。⑤附录 B **逐行列出 124 份**不随迁的 MVP1 文档，表头给目标路径/执笔席/证据坐标的继承规则。⑥必过集 **9 → 11**（`graph-agent-tests` 是三个 matrix context），五处统一。⑦D1 参照**撤销 langchain**（其公开文档写明每个 `libs/` 包各有自己的 `uv.lock`，与初稿描述相反），改引 uv 官方 workspace 文档两句原文 + `pydantic/pydantic-ai` 的实测坐标，并写明后者不能证明的那一半。⑧grep 计数订正为 20 个文件 = 6 读取 + 14 docstring。⑨§7.2 分组按实跑订正为 studio `85+26+10+1=122`、gateway `39+5+1=45`。 |
| 2026-09-02 | 交叉审 r1（codex，十条 P1 + 一条 P2）经协调方逐条裁定后返修 | ①**全部引文改为逐字**，源自本仓文件的引文由脚本从源文件抽取后插入，并以 `grep -F` 逐条回核（核对输出贴在 PR）。②**`docs/studio/mvp1/**` 与 `docs/graph-agent-gateway/mvp1/**` 改判为不搬**（协调方依据决议 `:607` 与 `AGENTS.md:366` 裁定）：它们是目标设计真相载体，归 (c) 类由批D 重写；连带新增**门禁暂缺表**（6 个读取用例在 C-1 删除 + 批D 复位工单），(b) 类收窄为 17 份真正被代码按路径读取的数据文件。③§7 按 `:610` 补齐**目标路径 / 执笔席 / 证据来源**三项，逐文件清单移入附录 B 的生成命令。④账目按脚本重算 **2015 + 836 + 11 + 6 = 2868**，并把判据从「总数相等」改为「并集等于全集且两两不交」。⑤§9.1 改写为**可复现配方**，按真实 workspace 形状重跑得 154 包，并补「不加 C-0a 则无解」的退出码与错误原文；版本表两列均为实测。⑥C-0b 前驱改为 C-0a。⑦C-3 前驱改为 C-2，新增**终态打包门**并作为 C-4 前驱。⑧**冻结 engine 改为源码 + 测试 + 契约清单一起搬，`graph-agent-tests` 保留为必过门**（协调方依据「因果验证」裁定：共享锁会换掉它脚下的依赖，源码不变不等于行为不变），树哈希锁覆盖 `tests/**`，连带随迁 `code-diagnostics/**` 与 `config/**`。⑨§8 拆为**机械核验项**与**人证项**两段，合并桶补人证判据。⑩补 D8 编号与 §12 参照汇总（D1/D2/D4/D6 各写「参照—借—拒—为什么」，KEP 候选因证不成而不引）。⑪数字按实跑订正：import 132 行/34 文件（真 import 131）、gateway import 155 行/39 文件、受治理载体 151、backend 443 文件/2281 个测试，每个数字旁给生成命令。 |
| 2026-09-02 | 初稿落盘 | 按已批决议 §4.3 / §4.4 / §11.5 / §11.7 与盘点 `inventory-synthesis.md:124,174`，把批C 搬迁写成可执行方案。状态 `drafted`，**待用户批准**。 |
