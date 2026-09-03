---
doc: gskill-migration-plan-2026-09-02
status: drafted（2026-09-02 落盘；**方案整体待用户批准**，批准前不得开工其中任何一张 PR；§11 列出两个需用户明确授权的动作）
role: workflow-record
---

# 批C 搬迁执行方案：gateway 与 studio 整体迁入 graph-skill-runtime

> **本文是什么**：把已批决议 `docs/design/gskill-restructure-decision-2026-08-31.md` §4.3（决定 b：gateway 与 studio 整体迁入 `graph-skill-runtime`）落成一份**可执行、可机械核验**的搬迁方案。它规定目标形状、逐目录处置、PR 序列、门禁扩展、验收判据与明确不做项。
>
> **本文不是什么**：①**不是实施记录**——本文落盘时一行代码、一个文件都还没搬；②**不是进度状态**——「在做什么、到哪一步、被什么挡住」的唯一可变状态载体是 `docs/development/DELIVERY_LEDGER.md`（交付台账），本文不复制状态；③**不是模块设计变更**——搬迁不改 studio / gateway / engine 的任何行为，行为层面的重整属于后续批次（批D/批E/批F）。

**本文的名词约定（全文只用这一套指代，不另造代称）**：

- **主仓** = GitHub 仓库 `SevenX77/agent-harness`，即本文所在的仓库。
- **新仓** = GitHub 仓库 `SevenX77/graph-skill-runtime`，搬迁的目的地；决议 §11.5-1 已定该名不改，本方案**不含仓库改名项**。
- **monorepo**（单体仓库）= 一个 git 仓库里放多个可独立发布的包；包边界不等于仓边界（决议 §4.3 原文）。
- **uv workspace**（uv 工作区）= Python 包管理器 uv 的多包模式：一个仓库里多个 `pyproject.toml` 成员共用**一把** `uv.lock` 锁文件，成员之间以源码路径互相引用而不走 PyPI。
- **冻结旧 engine** = 主仓 `packages/graph-agent`（发行名 `graph-agent`，版本 0.3.1）。决议 §4.2 已把它定为只读镜像，§4.3 定它随迁、并在 Studio 切换门禁（§4.5 五条）全过后**整包删除**。
- **sidecar**（边车进程）= Studio 桌面应用启动的那个 Python 后端进程，由 `apps/studio/tauri/sidecar.rs` 拉起。
- **vendor 快照** = `apps/studio/tauri/vendor/site-packages`，桌面应用随包携带的 Python 依赖闭包；sidecar 永远从这里导入 engine 与 gateway（`AGENTS.md` 工作流第 7 条）。

## 1. 上位依据与本文的落点

本文落在决议 `docs/design/gskill-restructure-decision-2026-08-31.md` 的 **§4.3（决定 b）+ §4.4（决定 c）+ §11.5（命名）+ §11.7（不接历史、权威文档重写）** 之下，并执行盘点交付物 `docs/design/gskill-restructure-inventory-2026-08-31/inventory-synthesis.md:174` 的要求「批C 搬迁出独立执行方案（结构性变更，先呈）」。

逐条上位依据与本文对应节：

| 上位依据 | 原文要点 | 本文落点 |
|---|---|---|
| 决议 §4.3 | 「gateway 与 studio **整体搬入** `graph-skill-runtime`，该仓成为 monorepo」「runtime 包：保持精瘦、可独立发布的身份；gateway：独立包；studio：应用（app），不是库」「**包边界不等于仓边界**」 | §3.1 目标形状（D1） |
| 决议 §4.3 | 「把**冻结的旧 engine 包（v0.3）随迁**，供 studio 在切换完成前继续使用；**Studio 切换门禁（§4.5）全部通过后，整包删除**」 | §3.4 冻结随迁形状（D4） |
| 决议 §4.3 | 「`agent-harness`（本仓）在迁移完成后**归档为只读**」 | §5 的 C-4、§11 授权点二 |
| 决议 §4.4 | 搬家四步前置，顺序固定不可颠倒 | §2 前置条件核对 |
| 决议 §11.5-1 | 「主仓名 = `graph-skill-runtime`……批C 不含『仓库改名』项」 | §10 明确不做 |
| 决议 §11.5-3 | 「gateway 与 studio 带 `gskill` 词缀短名……**精确拼法**（前缀还是后缀、连字符还是下划线、各 registry 上的具体标识符）**由批C 定**」 | §3.3 命名（D3） |
| 决议 §11.5-5 | 「『包名裁决』的选名与复核**均已完成**；批C 的该项前置**已满足**」 | §2 前置条件核对第 2 条 |
| 决议 §11.7-1 | 「**不移植历史**：一律不 graft、不 `subtree --with-history`、不 filter-repo 回灌；搬入即为**新提交**」 | §3.2 历史处置（D2） |
| 决议 §11.7-2 / §11.7-5 | 「权威文档全部重写：**不搬运旧文正文**；旧文**只作证据引用**」「批C 方案必须按本条写，并在呈批时附**权威文档重写清单**」 | §7 权威文档改写清单 |
| 盘点 `inventory-synthesis.md:124` | 「批C · 搬迁（§4.4 顺序固定）……**旧 engine 冻结随迁**……→ 主仓归档只读。**搬迁不改行为**；验收 = 迁后全门禁绿 + 打包链可跑」 | §8 验收判据 |
| 主仓 `AGENTS.md`「Development Principles」 | 不做向后兼容；第一性原理修复而非打补丁；「先看成熟工程怎么解」并写明借了什么、拒绝了什么 | §3 各条的成熟参照段 |

## 2. 前置条件核对（决议 §4.4，逐条给证据）

决议 §4.4 规定四步顺序固定、不可颠倒。前三步是**搬家开工的硬前置**，第四步就是本方案。

**第 1 步「新仓 113 个未提交文件先落 main」——已收口。** 证据：交付台账 `docs/development/DELIVERY_LEDGER.md:21` 原文「**批B 前置「113 落 main」**以封存分支 `sealed/113-unified-agent-kit` 收口（130 文件与已批裁决冲突，全部封存，新仓 main 未动）」。收口形式是**封存**而非合入：那 130 个文件与已批裁决冲突，落 main 会把冲突内容变成基线。决议 §4.4-1 的目的是「未提交的工作树内容不构成可被引用的基线」，封存同样达成该目的——工作树已清空，新仓 main 是唯一基线。

**第 2 步「包名裁决」——已完成。** 证据：决议 §11.5-5 原文「『包名裁决』的选名与复核**均已完成**；批C 的该项前置**已满足**」。占名与商标复核证据归档在 `docs/design/gskill-restructure-inventory-2026-08-31/name-clearance-2026-09-01.md`。§11.5-3 交给批C 的只剩**精确拼法**，由本文 §3.3 定。

**第 3 步「复刻 CI / 分支保护 / 门禁」——已生效。** 证据：2026-09-02 协调方实测 `env -u GITHUB_TOKEN gh api repos/SevenX77/graph-skill-runtime/branches/main/protection`，结果为：必过检查（required status checks）= `quality-gates`、`runtime-tests (3.11)`、`runtime-tests (3.12)`、`runtime-tests (3.13)`、`cross-platform-smoke (windows-latest)`、`cross-platform-smoke (macos-latest)` 共 6 项；`required_linear_history = true`（要求线性历史，即禁止合并提交）；`enforce_admins = true`（管理员不豁免）。这与主仓的强度同构：`main` 只能经绿色 PR 进入。

**第 4 步「整体迁移」——本方案。** 其**开工门**是：交付台账 `docs/development/DELIVERY_LEDGER.md` 的 gskill 工单表里，「批C 搬迁方案」一行 `前驱` 列所列的全部 17 个工单状态均为 ✅ 已合并。本文**不复制**这些工单的状态（状态的唯一载体是台账），只声明这条门。

**开工门之外还有一条批准门**：批C 是结构性变更，决议 §11.8-3 原文「**批C（搬迁）仍须先呈完整方案**——它是结构性变更，按既有工作规则必须先呈方案、用户确认后再动手，**不因本条自动开工**」。因此即使 17 个前驱全绿，本方案未获用户批准前不得开工。

## 3. 目标形状

### 3.1 新仓变成 uv workspace，runtime 留在仓根当 workspace 根包（D1）

**决定**：新仓根 `pyproject.toml` 保持 `name = "graph-skill-runtime"`、hatchling 的 `packages = ["src/graph_skill_runtime"]` 不变，**新增**：

```toml
# C-1 落地时的形状：成员名与目录名一律沿用主仓原样（改名归 C-2）
[tool.uv.workspace]
members = ["packages/*", "apps/studio/backend"]

[tool.uv.sources]
graph-agent = { workspace = true }
graph-agent-gateway = { workspace = true }
studio-backend = { workspace = true }
```

C-2 改名后，后两个键随发行名变为 `gskill-gateway` 与 `gskill-studio`，`members` 里的 `apps/studio/backend` 变为 `apps/gskill-studio/backend`（§3.3）。整仓共用**一把**根 `uv.lock`，四个包一次解出。

**依据**：决议 §4.3 要求「runtime 包保持精瘦、可独立发布的身份」。这条身份由**发布产物**定义，而发布产物的内容由 hatchling 的 `packages` 白名单决定，与仓里还有几个 workspace 成员无关——因此把 runtime 留在仓根、同时让它当 workspace 根包，既满足 monorepo 要求，又让新仓现有的 `release.yml`（release published → build → 三平台 verify → publish-to-pypi，OIDC 免密发布）**零改动**。

**成熟工程参照（`AGENTS.md` 要求写明借了什么、拒绝了什么、为什么）**：参照对象是 **uv 官方 workspace 模型**（允许根 project 同时是成员）与 **langchain monorepo**（`libs/*` 为成员、单一锁文件）。**借**其「一仓一锁、成员各自持有自己的 `pyproject.toml`」——这正是主仓已经在跑的形状（`AGENTS.md`：「Python is one uv workspace with a SINGLE root `uv.lock`」），搬迁因此不引入任何新的依赖管理范式。**拒绝**其「根包是虚包（只有 workspace 声明、没有源码）」这一半：采用它就必须把 runtime 从仓根搬进 `libs/` 或 `packages/` 的子目录，连带改 `release.yml` 的构建路径、`[project.urls]` 与 README 里的安装说明，而收益为零。

**这一步为什么必须和搬迁在同一张 PR 里**：新仓当前 `pyproject.toml` **没有** `[tool.uv.workspace]`（2026-09-02 实测）。没有它，搬进来的三个 `pyproject.toml` 不被任何锁文件覆盖，`uv sync` 装不出 studio 的依赖，CI 的任何一个 Python job 都跑不起来——即 C-1 自己过不了门。

### 3.2 历史：squash 导入 + 出处 trailer，不做历史合并（D2）

**决定**：搬迁提交是**新提交**，不接主仓历史。导入提交的提交信息里带三行出处标记（trailer，即提交信息末尾 `Key: value` 形式的机器可读字段）：

```
Source-Repo: https://github.com/SevenX77/agent-harness
Source-Commit: <C-1 开工时主仓 main 的 40 位全哈希>
Source-Paths: <本文 §4 处置表的源→目标路径映射>
```

**依据**：①决议 §11.7-1 已裁「不 graft、不 `subtree --with-history`、不 filter-repo 回灌；搬入即为新提交，干净起步」；②实测约束：新仓 main 的 `required_linear_history = true` 且只允许 squash 合并，带 `--allow-unrelated-histories` 的合并提交在物理上无法经 PR 落 main——要接历史就得临时放开分支保护，那违反「`main` 只能经绿色 PR 进入」；③主仓归档为只读后其完整历史仍可查（决议 §11.7-3：「`agent-harness` 原仓历史即档案」），`git log -S`（按内容变更搜索历史）式的考古去归档仓做。

**成熟工程参照**：`git subtree add --squash` 的形状——它把被并入子树的历史压成一个提交，但在提交信息里记下源仓与源提交，使「这批文件从哪来」可被机器读出。**借**其「squash 但可追溯到源提交」的出处标记；**拒绝**其真正的历史移植部分（`git subtree` 不带 `--squash` 时会产生跨仓合并提交），理由同上第②点。

### 3.3 命名：精确拼法（D3）

决议 §11.5-3 把精确拼法交给批C。**决定**如下：

| 对象 | 取值 | 理由 |
|---|---|---|
| gateway 发行名（PyPI distribution） | `gskill-gateway` | **前缀**：`gskill` 是产品短名，做命名空间用，同 `langchain-openai`／`langchain-anthropic` 惯例——前缀让同族包在任何按名排序的列表里聚成一块。**连字符**：PEP 503 的规范化形式，下划线在 PyPI 上会被归一成连字符，直接用规范形式避免两种写法并存 |
| studio 发行名 | `gskill-studio` | 同上 |
| gateway 目录 | `packages/gskill-gateway` | 目录名与发行名一致，避免「目录叫一个名、包叫另一个名」的二次查表 |
| studio 目录 | `apps/gskill-studio`（其下仍为 `backend` / `frontend` / `tauri` / `tests-e2e`） | 同上；`apps/` 与 `packages/` 的分工承载决议 §4.3「studio 是应用（app），不是库」 |
| gateway Python import 名 | `gskill_gateway` | Python 包名不能带连字符，下划线是唯一合法形式 |
| studio Python import 名 | **保持 `app`，不改** | 决议 §4.3：studio 是应用不是库，它的顶层模块不作为公开 import 身份被外部引用 |
| Tauri `productName` 与 Display name | `gskill Studio` | 与产品短名一致 |
| 冻结旧 engine 的发行名与 import 名 | **保持 `graph-agent` / `graph_agent`，不改** | 它在批E 整包删除（决议 §4.3），改名只会制造一次纯粹的无收益改动 |

**执行时点（本条同样是决定）**：**C-1 逐字节保留原路径与原名，改名单独成 C-2 做纯机械重命名。**

理由：盘点 `inventory-synthesis.md:124` 要求「搬迁不改行为」，而「不改行为」要能被**机械核验**才算数——C-1 的验收判据是「源文件与目标文件 sha256 相等」（§8-①）。一旦把改名混进 C-1，每个文件的内容都变了，核验就从「哈希相等，0 差异」退化成「人工审 1973 个文件的 diff」，而人工审 diff 恰恰是这类大规模搬运最不可靠的一环。附带收益：git 的 rename 检测（`git log --follow` 之类）在「纯移动」与「纯改名」分成两步时最可靠。

### 3.4 冻结旧 engine 的随迁形状（D4）

**决定**：只带 `packages/graph-agent/` 下的 `pyproject.toml`、`README.md`、`src/**`（124 个文件），**不带** `tests/`（340）、`spec/`（4）、`tools/`（1）、`scripts/`（1），也不带 9 个误提交的裸文件；版本号 `0.3.1` 不动；并用一条**树哈希锁**把「冻结」做成门禁。

**树哈希锁的形状**：新仓新增 `tests/test_frozen_engine_hash_lock.py`，对 `packages/graph-agent` 下全部跟踪文件按路径排序、逐文件算 sha256（行尾统一按 LF 归一化后再算，避免 Windows 检出把 CRLF 混进哈希），与一份 seal（钉值）记录比对；任何漂移即红，失败信息里自带重钉命令。seal 记录沿用新仓 `tests/contract-seals.yaml` 的同款机制（由工单 F-T3 落地，见交付台账 gskill 工单表）——即「钉值即治理记录」：钉的不是一个数字，而是「这份内容在此刻被谁、以什么理由锁住」。**放宽这把锁的唯一合法路径是删除整包**，那属于批E 的 X-T1b。

**依据**：
- 决议 §4.3 定的是「冻结……五门禁全过后整包删除」。**冻结的可核验定义就是字节不变**；口头承诺「大家别改它」在一个多 agent 并发推进的仓里不成立，门禁才成立。
- **不搬 340 个测试与 spec/tools/scripts 的理由**：它们随包在批E 一起死亡，搬进来只增加每个 PR 的 CI 时长，不增加任何信息。冻结包的行为由三层现存证据覆盖：①studio backend 的 443 文件测试套件经 `apps/studio/backend/app/core/adapters/engine.py` 间接覆盖它实际被消费的表面；②`apps/studio/backend/scripts/build_vendor.py` 会真实构建它的 wheel；③`apps/studio/tauri/scripts/verify_installed_sidecar.ps1:136` 的探针 `import graph_agent, graph_agent_gateway` 断言装出来的 app 能导入它。
- **9 个裸文件不进新仓**：`e1.txt`、`e2.txt`、`e3.txt`、`err.txt`、`err2.txt`、`hb`、`owner`、`owner2`、`lk/owner`（2026-09-02 实测 `git ls-files packages/graph-agent | grep -v -E '/(src|tests|spec|tools|scripts)/'`，除去 `README.md` 与 `pyproject.toml` 后即这 9 个）。它们是误提交的调试残留，搬进去等于把垃圾连同治理成本一起搬。

### 3.5 搬迁前先在主仓做「钉版对齐」（D5）

两把锁合成一把，依赖解析结果必然变化——这是搬迁**唯一不可避免**的行为面改动。处理方式是把它**隔离到搬迁之前、在主仓用主仓的门禁证明**，使 C-1 只承担「文件从哪到哪」这一件事。

**C-0a**：主仓 `packages/graph-agent-gateway/pyproject.toml` 把 `langchain-openai` 从 `>=1.1.7,<1.3.0`（实测第 9 行）钉到 `>=1.3.5,<1.4.0`。依据见 §9.1 的依赖共解探针：这是四包同锁时**唯一**的版本冲突。

**C-0b**：主仓用「合锁后的解析结果」重解 `uv.lock`（§9.1 给出的目标版本表：langchain-openai 1.3.5、mcp 2.1.1 等），跑通 studio backend + gateway 的全套门禁。**若红，就在主仓修到绿**——这些是既有的潜在不兼容，不是搬迁引入的，在源仓修才有源仓的测试套件与真机环境可用。

## 4. 逐目录处置表（D6）

**怎么读这张表**：

- **「逐字节搬」**= C-1 里源文件与目标文件内容完全相同，由 §8-① 的哈希脚本机械核验（0 差异）。
- **「C-1 合并/新建」**= 该文件在 C-1 里内容必须变化，否则 C-1 自己过不了门（依赖解析、忽略规则、CI 定义）。这些文件不进哈希核验，改由 codex 交叉审 diff + 门禁绿证明。
- **「留」**= 不搬，留在归档后的主仓；归档仓只读可查，需要时按决议 §11.7-2「旧文只作证据引用」的方式引用。
- **一条贯穿规则**：凡内容需要改写但改写本身不是 C-1 过门的必要条件的文件（如 `CLAUDE.md` 的指向、`.ah/` 里的路径引用），**C-1 先逐字节搬入、改写归 C-3**。这样 C-1 的哈希核验保持无例外。

### 4.1 逐字节搬（C-1，共 1973 个文件）

| 源路径（主仓） | 目标路径（新仓，C-1 时） | 文件数 | 说明 |
|---|---|---|---|
| `apps/studio/frontend/**` | 同路径 | 715 | React/TS 前端 |
| `apps/studio/backend/**` | 同路径 | 443 | FastAPI 后端（含 `pyproject.toml`，即 workspace 成员之一） |
| `apps/studio/tauri/**` | 同路径 | 45 | Rust 原生外壳 + vendor 构建/校验脚本 |
| `apps/studio/tests-e2e/**` | 同路径 | 9 | Playwright 端到端测试 |
| `packages/graph-agent-gateway/**` | 同路径 | 140 | gateway 包全量（src 61 + tests 77 + 2） |
| `packages/graph-agent/{pyproject.toml,README.md,src/**}` | 同路径 | 126 | 冻结 engine 子集，见 §3.4 |
| `docs/**` | 同路径 | 439 | 见下方「为什么整搬 docs」 |
| `scripts/**` | 同路径 | 18 | worktree/PR 流水线脚本、并行黑板、交叉审脚本 |
| `.claude/skills/**` | 同路径 | 26 | shadcn（15）+ studio-verify（11）；后者是真机验证的唯一方法 |
| `skills-lock.json` | 同路径 | 1 | 上一行的版本锁 |
| `.ah/**` + `ah.toml` | 同路径 | 10 | 本仓多 agent 编排实例；**路径引用的校正归 C-3** |
| `.pre-commit-config.yaml` | 同路径 | 1 | 提交前钩子 |
| `CLAUDE.md` | 同路径 | 1 | **改指向新仓 `AGENTS.md` 归 C-3** |

**为什么 `docs/**` 整搬（439 个文件、156 KB）**：逐文件筛选的错误代价高于整搬的代价。文档引用门禁（`apps/studio/backend/tests/docs/`）与生产代码读 docs 的路径散布在多处——例如 `apps/studio/backend/app/services/llm_notable_models.py:13` 按 `parents[5]` 上溯读 `docs/development/llm_provider_notes`——漏搬一份就是一个红门禁或一次运行时缺文件，而多搬一份的代价只是仓里多一个待收敛的文件。旧 engine 的文档随包在批E 删，整体文档收敛是批F 的事。

**这不与决议 §11.7-2「权威文档全部重写、不搬运旧文正文」冲突的边界在哪**：§11.7-2 约束的是**权威文档**这一类载体（新仓的 `AGENTS.md` / `README.md` / 台账头部 / 契约文档），本文 §7 给出它们的重写清单；`docs/**` 里的设计正文在新仓的角色是**证据**（§11.7-2 原文「旧文只作证据引用」），载体本身必须在场才引用得到。**这条边界的精确划法待协调方补证**：`docs/studio/mvp1/**`（61 个文件）与 `docs/engine/mvp1/**` 按主仓 `AGENTS.md` 是「MVP1 design = source of truth」，它们究竟算「随迁的证据」还是「必须重写的权威文档」，本文按前者处理（整搬 + 批F 收敛），但该判定不在已批决议的字面里。

### 4.2 C-1 里合并 / 新建的文件

| 文件（新仓） | 处置 | 理由 |
|---|---|---|
| `pyproject.toml` | 加 `[tool.uv.workspace]` + `[tool.uv.sources]`；把主仓 `.importlinter` 的两条契约并入既有的 `[tool.importlinter]`（`root_packages` 追加 `graph_agent` 与 `app`） | §3.1；两条契约实测为「SDK cannot depend on Studio application code」与「Studio cannot bypass the public SDK boundary」，它们守的正是搬迁后同仓共处时最容易被越过的边界 |
| `uv.lock` | 四包重解（`graph-skill-runtime[embedded]` + `graph-agent` + gateway + studio backend） | §3.1、§9.1 |
| `.gitignore` | 与主仓版**合并**：并入 `.worktrees/`、前端 `src/lib/*` 白名单、vendor 产物、playwright 产物；保留新仓的 `.gskill/` | 主仓版 vs 新仓版（14 行）；漏掉前端 `src/lib/*` 白名单会让新增文件被静默忽略，本地 tsc 过、CI 全新检出失败 |
| `.gitattributes` | 与主仓版**合并**：并入 `.ps1`/`.bat` 的 CRLF 例外与 binary 段；新仓版仅 8 行且**没有**这两项 | PowerShell 启动脚本若被检出成 LF，Windows 上行为不确定；binary 段缺失会让截图等二进制文件被当文本处理 |
| `.editorconfig` | 与主仓版**合并** | 同上一类 |
| `codecov.yml` | 新仓版追加 `backend`、`gateway` 两个 flag | 覆盖率分包可见，否则三个包的覆盖率被搅成一个数字 |
| `.sonarcloud.properties` | **取主仓版** | 主仓版含 Python + TypeScript 双语规则；搬入前端后新仓必须能扫 TS |
| `.github/workflows/ci.yml` | 扩 job，见 §6 | C-1 自身要过门就必须先有跑 studio/gateway 的 job |
| `.github/workflows/package.yml` | 从主仓移植（按路径触发，非必过） | 「打包链可跑」是盘点给批C 的验收项之一 |
| `tests/test_frozen_engine_hash_lock.py` + seal 记录 | 新建 | §3.4 |
| `LICENSE` | **不动**：两仓的 `LICENSE` 是同一个 git blob（2026-09-02 实测两侧 blob sha 均为 `c7ed1e4abe5749619a5a11534f10fbbb32de75df`，Apache-2.0），新仓已有 | 同一份文件无所谓搬不搬 |

### 4.3 留在归档仓（不搬）

| 路径 | 文件数 | 不搬的依据（2026-09-02 实测，扫描范围 `apps packages scripts .github .claude .ah pyproject.toml`，排除 `*.md`） |
|---|---|---|
| `.kiro/**` | 484 | 27 处引用**全部**在 docstring/注释里做出处标注，**无任何路径读取** |
| `graph-agent-explainer/**` | 14 | 0 处引用（1.8 MB 截图） |
| `code-diagnostics/**` | 6 | 5 处引用全在 `packages/graph-agent/tests/core/test_code_health_metrics.py`，而该测试属于冻结 engine 的 tests，本身不搬 |
| `services/community-catalog-gate/**` | 12 | 0 处引用 |
| `config/**` | 2 | `config/llm_roles.yaml` 只被 `packages/graph-agent/tests/integration/test_mvp1_smoke.py:24` 读，同上不搬 |
| `.agents/` | 1 | 0 处引用 |
| `tools/fix_imports.py` | 1 | 一次性迁移脚本，0 处引用 |
| `Makefile` | 1 | 唯一 target `dev-tunnel` 已经是脚本 |
| `CHANGELOG.md` | 1 | 主仓自己的变更历史，随主仓归档 |
| `packages/graph-agent/{tests,spec,tools,scripts}` + 9 个裸文件 | 355 | §3.4 |
| `.github/workflows/ci.yml` 的 `graph-agent-tests` job | — | 冻结 engine 的 tests 不搬，无测试可跑 |

**账目闭合**：1973（逐字节搬）+ 877（留）+ 12（根级单文件按 §4.2 合并/改写/新建处置，或如 `LICENSE` 两侧同一 blob）+ 6（`.github/**`：`ci.yml` 扩 job、`package.yml` 移植，均见 §6；`CODEOWNERS` 由 C-3 追加条目，见 §7；`dependabot.yml`、`codeql.yml`、`scorecard.yml` 新仓已有同等配置——2026-09-02 实测两仓 `dependabot.yml` 语义相同，均只覆盖 pip 与 github-actions 两个生态——主仓副本不搬）= **2868**，等于主仓 `377e82e0` 的 `git ls-tree -r --name-only | wc -l` 实测值。**处置表无遗漏文件**。

> 上述文件数是 2026-09-02 在主仓提交 `377e82e0` 上的实测快照。主仓 `main` 此后仍在推进（本文落盘时已到 `6547029e`，2872 个文件），因此 §8-① 的哈希核验以 **C-1 开工当时主仓 main 的实际哈希**为 `Source-Commit`，不以 `377e82e0` 为准；处置表按目录给规则，新增文件自动落入对应目录的规则里。

## 5. PR 序列（D10）

每张 PR 都遵守既有交付纪律：一任务一 worktree、PR-only、codex（GPT-5.6-sol，推理强度 xhigh）交叉审、裁决贴 PR 评论首行 `交叉审 r<N>:approve|rework`。

| 编号 | 仓 | 范围 | 前驱 | 门（合并条件） | 交叉审的审查对象 |
|---|---|---|---|---|---|
| **C-0a** | 主仓 | gateway `pyproject.toml` 把 `langchain-openai` 钉到 `>=1.3.5,<1.4.0` | 台账 17 个前驱全绿 + 用户批准本方案 | 主仓 7 道必过检查 | 单行 diff + 探针结论（§9.1） |
| **C-0b** | 主仓 | 按合锁解析结果重解主仓 `uv.lock`；跑通 backend + gateway 全套门禁，红则在主仓修到绿 | 与 C-0a 可并行 | 主仓 7 道必过检查 | 锁文件版本跳变清单 + 为修红所做的每一处改动 |
| **C-1** | 新仓 | 一张 squash PR：文件导入（§4.1）+ workspace（§3.1）+ 合锁 + CI 扩展（§6）+ 冻结锁测试（§3.4）+ 三份忽略/属性文件合并（§4.2） | C-0a、C-0b 均已合并 | 新仓必过检查（扩展后 8 项，见 §6）+ §8-① 哈希核验 0 差异 | **①** §8-① 脚本的输出（总数与 0 差异）；**②** 非搬运部分的 diff（§4.2 那张表的每一行） |
| **C-2** | 新仓 | 机械改名：`packages/graph-agent-gateway` → `packages/gskill-gateway`、import `graph_agent_gateway` → `gskill_gateway`、`apps/studio` → `apps/gskill-studio`、发行名与 `productName`（§3.3） | C-1 已合并 | 新仓必过检查全绿 | 改名是否**穷尽**：源码 import、`pyproject.toml` 三处、vendor 构建与校验脚本里的路径字面量、`ensure_vendor.js` 的硬编码路径、CI 的 working-directory |
| **C-3** | 新仓 | 权威文档改写（§7）+ `CLAUDE.md` 改指向 + `.ah/` 路径引用校正 | C-1 已合并（与 C-2 可并行） | 新仓必过检查全绿 | 改写后的正文是否自包含、是否与新仓实际路径/必过检查集一致 |
| **分支保护扩必过集** | 新仓 | 把 `studio-gates`、`frontend-gates` 加入必过检查 | **在 C-1 合并前**执行 | 仓库设置变更，非 PR | — |
| **C-4** | 主仓 | 主仓 `README.md` / `AGENTS.md` 顶部加归档横幅（指向新仓 + C-1 的导入提交哈希）；随后把仓库设为 archived | C-1、C-2、C-3 全部合并 | 主仓 7 道必过检查；archive 动作需用户明确授权（§11 授权点二） | 横幅措辞与哈希正确性 |

**为什么「分支保护扩必过集」排在 C-1 合并之前而不是之后**：必过检查是按名字匹配的，一个尚未在任何工作流里出现过的检查名加进保护列表后，PR 会一直等它——所以顺序是：C-1 的 PR 先把 job 定义推上去、让两个新 job 在该 PR 上真实跑出结果，协调方随即把这两个名字加进保护列表，C-1 再合并。这样 C-1 之后的每一张 PR 都受完整门禁约束，中间不留窗口。

## 6. CI 与分支保护（D7）

**全部 CI 改动在 C-1 内完成**，否则 C-1 自身无法过门（新仓现有 job 只跑 runtime，跑不到搬进来的 studio 与 gateway）。

**新增 job**：

- **`studio-gates`**（Linux）：studio backend 的 `ruff check` + `mypy` + `pytest`；gateway 的 `mypy --strict` + `pytest`；`pip-audit` 覆盖整个 workspace。
- **`frontend-gates`**（Linux）：tauri 启动脚本测试（`node --test`，只依赖 Node 内建模块，放在 npm 安装之前快速失败）+ 前端 `lint` / `typecheck` / `test` / `build` + 两档 `npm audit`（`--omit=dev --audit-level=low` 与 `--audit-level=high`：进入用户手里的产物零容忍，开发工具链只拦 high/critical）。

**扩展 job**：

- **`cross-platform-smoke`**（windows-latest / macos-latest）：在现有 runtime 测试之外，加 studio backend、gateway、e2e 三套 pytest + 前端 build + stub vendor 文件 + `cargo test`（tauri lib）。
  > **待协调方补证**：主仓的 `cross-platform-smoke` 实际跑的三套 pytest 是 backend / gateway / graph-agent（`.github/workflows/ci.yml:257-263`），**不含 e2e**；主仓的 `e2e-tests` 是独立 job 且 `if: github.event_name == 'workflow_dispatch'`（`ci.yml:184-188`），原因写在它自己的注释里：「E2E suite needs the frontend dev server (Vite) plus Playwright Chromium, which requires a dedicated runner setup」。把 e2e 放进必过的 `cross-platform-smoke`，等于把一个主仓从未在 PR 上跑过的套件变成必过门——这既是行为改动（与「搬迁不改行为」相抵），又要为两个平台的 runner 装 Playwright。本文按上位指令照写「三套 pytest 含 e2e」，但该项的取舍需协调方确认后再落到 C-1 的工作流文件里。

**移植 job**：`package.yml`（Windows 上跑完整 `cargo tauri build`、装包并断言 sidecar 三件套落在安装目录内）按主仓形状移植，保持**按路径触发、非必过**——理由与主仓相同：一次冷跑要编译整个 Rust release 栈并下载可移植 CPython，数十分钟起，绝大多数 PR 碰不到打包链。

**不动的 job**：`quality-gates` 与 `runtime-tests`（3.11/3.12/3.13）原样保留。

**风格**：所有 action 按新仓既有风格**用 commit SHA 钉版**（新仓现状如 `actions/checkout@3d3c42e5… # v7.0.1`），主仓那种 `@v7` 浮动标签写法在移植时改成 SHA。

**必过检查集**：由现有 6 项扩为 **8 项** = `quality-gates` + `runtime-tests (3.11|3.12|3.13)` + `cross-platform-smoke (windows-latest|macos-latest)` + `studio-gates` + `frontend-gates`。

**分支保护是仓库设置、不是 PR**：该变更由协调方在 C-1 合并前执行；用户批准本方案即一并授权该动作（§11 授权点一）。

## 7. 权威文档改写清单（C-3；决议 §11.7-5 要求本方案必附）

改写而非搬运，依据决议 §11.7-2：「不搬运旧文正文；旧文只作证据引用」。执笔席为干净上下文的独立 agent（用户全局规范「干净上下文独立执笔」），brief 自包含。

| 文档（新仓，除非注明） | 改写内容 | 以哪些旧文为证据 |
|---|---|---|
| `AGENTS.md` | **删**第 18 行段落中的那一句「Gateway and Studio plugins are not deliverables in this release line; the design retains only their future external Port/Adapter ownership boundaries.」——搬入后该句为假；**删的是这一句，不是整行**（该行是一整段，其余部分讲 `docs/design/v1-alignment.md` 的 `drafted` 状态与各 Phase 验收，与本次搬迁无关）。**并入并以新仓路径与 8 项必过检查集重写**：CI 门禁清单、三模块架构与边界、Workflow Pipeline（branch → PR → auto-merge → cleanup）、Studio Tauri Dev、并行任务黑板、vendor 重建规则。**是重写，不是拼贴** | 主仓 `AGENTS.md`、主仓 `CLAUDE.md` |
| `README.md` | 改写为 monorepo 分工说明：runtime（可独立发布的精瘦包）/ gateway（独立包）/ studio（应用）/ 冻结 engine（带退出条件的过渡包） | 主仓 `README.md`、决议 §4.3 |
| `docs/design/v1-alignment.md` §2.1 工作名表 | 加 gateway、studio 两行（发行名、目录、import 名、Display name），与本文 §3.3 一致 | 决议 §11.5 |
| `.github/CODEOWNERS` | 加 studio 与 gateway 的契约文件条目 | 主仓同名文件 |
| `docs/development/DELIVERY_LEDGER.md` | 台账头部加「仓库 = 新仓」声明（搬迁后台账随代码在新仓维护） | 主仓台账 |
| **主仓** `README.md` / `AGENTS.md` | 顶部加归档横幅：指向新仓 + C-1 的导入提交哈希（属 C-4） | — |

## 8. 验收判据（D9，每条可机械核验）

1. **C-1 逐字节核验**：对 §4.1 处置表的每一个文件，`git show <Source-Commit>:<源路径>` 的 sha256 与新仓 `<目标路径>` 的 sha256 相等。核验脚本随 C-1 提交，输出「核验文件总数」与「差异数」，**判据是差异数 = 0 且总数 = 处置表规则展开后的文件数**。脚本形状（在新仓工作树内运行，`<主仓路径>` 为归档前的主仓本地克隆）：

   ```bash
   # 对每条映射：逐文件比对 sha256；差异一律打印源路径与两侧摘要
   git -C <主仓路径> ls-tree -r --name-only <Source-Commit> -- <源目录> |
   while IFS= read -r src; do
     a=$(git -C <主仓路径> show "<Source-Commit>:$src" | sha256sum | cut -d' ' -f1)
     b=$(sha256sum "<目标目录>/${src#<源目录>/}" | cut -d' ' -f1)
     [ "$a" = "$b" ] || echo "DIFF $src $a $b"
   done
   ```

2. **新仓全部必过检查绿**，含新增的 `studio-gates` 与 `frontend-gates`（§6）。
3. **`package.yml` 在 C-1 上手动触发一次并通过**——即盘点要求的「打包链可跑」。
4. **真机验证**：在新仓仓根用 `scripts/studio-dev.ps1` 拉起桌面应用，按 `.claude/skills/studio-verify` 的方法（CDP 驱动真 Tauri 窗口，端口 9222）走「打开 Recent 里的一个 skill → 点 Compile → 编译通过」这一条最小旅程并截图。真机验证串行占用运行时资源黑板的 `cdp-9222`（`scripts/wt-board.sh claim cdp-9222`），验完释放。
5. **冻结锁有效性实跑**：改 `packages/graph-agent` 下任意一个字节 → `test_frozen_engine_hash_lock.py` 变红；改回 → 变绿。**只声称锁已加不算数，要跑给人看**。
6. **全新克隆可装**：在一个全新的 `git clone` 里 `uv sync --all-packages --all-extras --group dev` 成功。
7. **主仓已归档**：C-4 之后 `env -u GITHUB_TOKEN gh repo view SevenX77/agent-harness --json isArchived` 返回 `true`。

## 9. 风险与已核验事实

### 9.1 依赖共解探针（2026-09-02 协调方实测，原文保留）

方法：建临时 workspace，四个包以 editable path source 方式同锁，跑 `uv lock --no-cache`。

**第一次失败**，唯一冲突原文：

> `graph-agent-gateway==1.0.0 depends on langchain-openai>=1.1.7,<1.3.0 … graph-skill-runtime[embedded]==0.1.0a1 depends on langchain-openai>=1.3.5,<1.4.0 … incompatible`

加 `override-dependencies = ["langchain-openai>=1.3.5,<1.4.0"]` 后 **Resolved 106 packages**，退出码 0。解出的关键版本，与主仓当前锁的对照：

| 包 | 合锁解出 | 主仓当前锁 |
|---|---|---|
| langchain | 1.3.14 | — |
| langchain-core | 1.4.9 | — |
| langchain-openai | 1.3.5 | 1.2.1 |
| langchain-anthropic | 1.4.8 | 1.4.6 |
| langchain-google-genai | 4.2.7 | 4.2.2 |
| langgraph | 1.2.11 | — |
| **mcp** | **2.1.1** | **1.29.0** |
| openai | 2.54.0 | — |
| pydantic | 2.13.5 | — |
| fastapi | 0.141.1 | — |

**风险一：`mcp` 主版本跳变（1.29.0 → 2.1.1）。** studio backend 对 `mcp` 的用法只有两处 import——`apps/studio/backend/app/main.py:17` 的 `from mcp.server.streamable_http_manager import StreamableHTTPSessionManager` 与 `apps/studio/backend/app/services/cli_mcp_surface.py:28` 的 `from mcp.server.lowlevel import Server`。两个模块路径在 mcp 2.1.1 下 import 成功（新仓虚拟环境实测），**但构造签名是否兼容未验**。这正是 §3.5 把 C-0b 放在搬迁之前的原因：在主仓、用主仓的 443 个 backend 测试把它证伪或证实，而不是让它在 C-1 的哈希核验里混成一团。

**风险二：跨模块硬引用的规模（2026-09-02 `git grep` 实测）。**

- studio → engine：`^(from|import) graph_agent` 共 131 行 / 34 个文件；其中生产代码只 8 个文件，`apps/studio/backend/app/core/adapters/engine.py` 独占 60 行。
- studio → gateway：154 行 import。
- gateway → engine：生产代码唯一的硬依赖是 `packages/graph-agent-gateway/src/graph_agent_gateway/errors.py:7` 的 `from graph_agent import ModelProviderError`（实测全量扫描 gateway `src/` 确认唯一）。

这些引用在 C-1 **一个都不动**（路径与名字原样），在 C-2 才随改名机械更新。C-2 的审查重点因此是「改名是否穷尽」，尤其是 gateway 改名会同时波及 studio 的 154 行 import、`verify_installed_sidecar.ps1:136` 的 import 探针，以及 vendor 构建链里的包名。

**风险三：仓根推算与路径字面量。** 主仓有 67 行按 `REPO_ROOT` / `parents[N]` 上溯推算仓根，例如 `apps/studio/backend/app/core/config.py:11-12`（`STUDIO_BACKEND_DIR = Path(__file__).resolve().parents[2]`；`REPO_ROOT = STUDIO_BACKEND_DIR.parents[2]`）；另有 27 行 / 19 个文件把 `packages/graph-agent` 写成路径字面量，例如 `apps/studio/backend/scripts/build_vendor.py:131` 与 `apps/studio/tauri/scripts/ensure_vendor.test.js:716/729`（后者硬编码 `path.join(REPO,'packages','graph-agent','src','graph_agent')`）。

这类推算依赖的是**目录深度**，不是目录名：`apps/studio/backend` 与改名后的 `apps/gskill-studio/backend` 深度相同，因此 C-2 的改名不破坏它们；真正会全线崩掉的是**改变目录深度**的搬法——这正是 §4.1 坚持「路径原样」的第二个理由（第一个理由是哈希可核验）。`apps/studio/tauri/vendor` 的 141 行 / 28 文件引用同理。

**风险四：冻结 engine 的 `graph-agent-tests` 不随迁，冻结包在新仓没有自己的测试。** 这是 §3.4 的自觉取舍：它的行为由 studio 测试套件经 adapter 间接覆盖、由 `build_vendor.py` 真实构建、由安装后 import 探针断言，加上一把树哈希锁保证它一个字节都不会变——**不变的代码不需要回归测试，需要的是防止它被改动的锁**。

### 9.2 本方案与「搬迁不改行为」的边界（诚实记账）

严格说，有三处不可能保持逐字节不变，本方案把它们逐一显式化而不是掩盖：

1. **依赖解析结果**（两把锁合一把）——隔离进 C-0a / C-0b，在主仓用主仓门禁证明（§3.5）。
2. **忽略规则、CI 定义、覆盖率与静态扫描配置**——两仓各有一份，必须合并（§4.2），由 codex 审 diff + 门禁绿证明。
3. **名字与路径**（C-2）——机械改名，由新仓全套门禁证明。

除这三处外，C-1 的每一个文件都由 §8-① 的哈希核验钉死。

## 10. 明确不做（D11）

1. **不改** studio / gateway / engine 的任何行为。
2. **不动** Python import 名以外的任何标识；C-2 之外不做任何重命名。
3. **不引入兼容垫片**：两仓不并存、不双读；搬完主仓即归档只读（决议 §4.3）。
4. **不搬 `.kiro/**`**（484 个文件，实测无路径读取）。
5. **不在 C-1 里顺手修任何缺陷**：搬迁途中发现的问题一律记进 `docs/development/PROBLEM_LEDGER.md` 并另开工单。
6. **不复刻主仓的 `graph-agent-tests` job**（冻结 engine 的 tests 不随迁）。
7. **不重命名仓库**（决议 §11.5-1：主仓名 `graph-skill-runtime` 早已定，批C 不含改名项）。
8. **不移植 git 历史**（决议 §11.7-1）。

## 11. 待用户批准项

本节**只有**以下三项，不含任何选项式待裁问题——本文每一个技术取舍都已在正文里拍板并给出依据。

1. **本方案整体**：批C 是结构性变更，按既有工作规则必须先呈方案、用户确认后再动手（决议 §11.8-3）。批准前不开工任何一张 PR。
2. **授权点一——新仓分支保护的必过检查集扩为 8 项**（§6）。这是仓库设置变更，不经 PR，由协调方在 C-1 合并前执行。
3. **授权点二——把主仓 `SevenX77/agent-harness` 设为 archived**（§5 的 C-4）。这是对外可见、影响他人可见性的设置变更，需用户在批准本方案时明确授权。

另有一项**待协调方补证**（不是待用户裁决，不阻塞本方案呈批）：§6 中 `cross-platform-smoke` 是否纳入 e2e 套件——实测显示主仓从未在 PR 上跑过 e2e，纳入会改变行为并需要为两个平台准备 Playwright runner。

## 修订记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-02 | 初稿落盘 | 按已批决议 §4.3 / §4.4 / §11.5 / §11.7 与盘点 `inventory-synthesis.md:124,174`，把批C 搬迁写成可执行方案。全文事实以 2026-09-02 在主仓 `377e82e0`、新仓 `dc6f32af` 上的实测为准。状态 `drafted`，**待用户批准**。 |
