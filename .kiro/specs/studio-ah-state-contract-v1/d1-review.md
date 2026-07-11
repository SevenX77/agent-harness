---
spec: studio-ah-state-contract-v1
doc: d1-review
reviewer: d1-claude (设计执笔席 · 本次为严谨只读审角色)
date: 2026-07-10
base: main @ 880164ad (PR #483), lib.rs 未在其后再动 (最近改动 #476 60363785)
ah_cli_tested: 1.5.0 (spec 声明最低 1.4.0)
method: 行号锚点逐条读码亲验 + CLI 只读实测 (从不对当前 ah 编队做 start/stop/kill)
verdict: 有条件批准 (方向与 F1-F9 溯源成立、F8 数据模型修正被实测强证;但身份校验设计有实测漏洞、env-clamp 补救在 1.5.0 实测失效,须先修 requirements/design 再进实施)
---

# d1 严谨审:studio-ah-state-contract-v1 修订版 spec

## 0. 审计边界与方法声明

- 本审只读:未改任何 spec / 生产代码 / 测试;发现记录于本文,不现场改。
- 所有 CLI 实测均为只读观察(`ah version` / `ah status --json` / `ah events --format json`),
  **从未**对当前这套 ah 编队做 start/stop/kill;隔离场景用 `/tmp/ah-fixture-<n>` + 显式
  `AH_STATE_DIR`,用完清理。审后复测编队仍 `active`(d1/o1 在位),未受影响。
- 反讨好:不因"已合入 main / a4 已 ACCEPT"放宽核实;找不到依据直接写"无法核实"。

---

## 1. 锚点核实表

### 1a. `apps/studio/tauri/src/lib.rs` 行号锚点(逐条读当前 HEAD 对应行)

| 引用位置 | spec 断言 | 核实方法 | 结果 |
|---|---|---|---|
| lib.rs:63-73 | 前端 payload 为 `{claude: bool, codex: bool}`(Req 6.1 / design Data Models) | 读 55-73 | **一致**。`struct CodeAssistantStatus { claude: bool, codex: bool }` 在 61-66,`CodeAssistantStatusEvent` 在 68-73。范围含义准确。 |
| lib.rs:203-218 | `find_ah_config` 向上爬目录找 `ah.toml`(Req 4.6 / design) | 读 203-218 | **一致**(逐字)。`loop { candidate = current.join("ah.toml"); ... current.pop() }`。 |
| lib.rs:550 | moirai-intro skill 文本"`ah status` 不是可用命令"(F7 / task 10) | 读 540-559 | **一致**(逐字)。行 550:"用 `ah ps` 确认…。`ah status` 不是可用命令,不要调用…"。 |
| lib.rs:828-833 | `ah_config_for_status` 优先取发现的 config 而非 temp(Req 4.6) | 读 828-833 | **一致**(逐字)。`find_ah_config(workspace_root).or_else(|| transient…)` —— 发现的 workspace config 确实优先于 transient,零所有权区分。 |
| lib.rs:858 / 879 / 927 | 三处 `wsl.exe -e bash -lc` 登录 shell 调用点(Req 4.7 / task 6) | 读 842-935 + grep | **基本一致,一处需订正**:858=`run_ah_config_command_output`(ah 命令)、879=`spawn_ah_events_command`(ah events)、**927=`run_tmux_socket_command`(tmux,不是 ah)**。Req 4.7 原文"Before invoking **ah** through … (lib.rs:858/879/927)"把 927 也算作"invoking ah"路径不精确——927 是 tmux 调用。env-clamp 论据(登录 shell 吃 profile)对三者都成立,但描述应区分。 |
| lib.rs:1244-1246 | claude-wins 抑制 `if status.claude { status.codex = false; }`(Req 6.2) | 读 1230-1248 | **一致**(逐字)。 |
| lib.rs:1355 | events 订阅无版本门时 ~3s 一轮无限重生(Req 1.6 / F6) | 读 1340-1379 | **一致**。`while !thread_stop { spawn_ah_events_command()… }` 重生循环在 1354 起,spawn 在 1355;失败走 `backoff`=30×100ms=**3s** 后 `continue`,无版本门、无上限。 |
| lib.rs:357-368 | `CleanupStale` 判定路径今天能自愈 degraded(Req 3.7) | 读 350-372 | **一致**。`reconcile_code_assistant_lifecycle`:`ahd_has_inventory || master_tmux_alive || worker_tmux_alive` → `CleanupStale`。 |
| lib.rs:2358-2361 | `CleanupStale` → 清理后 StartFresh(Req 3.7) | 读 2350-2364 | **一致**。`CodeAssistantOpenDecision::CleanupStale => { cleanup_workspace_code_assistants()?; Ok(StartFresh) }`。 |
| lib.rs:1754 / 1836 / 1903 / 1960 | launcher 脚本里 4 份独立 `awk >= 1.3.4` 版本门(Req 1.5 / F6) | grep + 读 1748-1765 | **一致**(四处精确)。四行均为 `ah_version="$(ah --version 2>/dev/null \| awk '{{print $2}}')"`,门槛逻辑 major>1 ∨ (1,minor>3) ∨ (1,3,patch>=4) = **>= 1.3.4**。 |

### 1b. 前端锚点

| 引用位置 | spec 断言 | 核实方法 | 结果 |
|---|---|---|---|
| copilot-panel.tsx:303-306 | 前端已支持双活跃("Close assistants" 复数分支)(Req 6.2 / F3) | 读 290-307 | **一致**。`codeAssistantCloseButtonLabel`:`active.length > 1 → 'Close assistants'`;`activeCodeAssistantIds` 会同时返回 claude+codex。测试 copilot-panel.test.ts:277 亦断言双活文案。 |

### 1c. 设计文档锚点 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`(F7)

| 引用位置 | spec 断言 | 核实方法 | 结果 |
|---|---|---|---|
| :12 | "workspace 内只允许一个 Studio-managed ahd" 不变量(Req 6.3 引 ah-orchestration-design.md:12) | 读 1-19 | **一致**。行 12 逐字含该不变量。 |
| :185-193 | 活跃判定=两布尔;"runtime_state 只有 Active/Degraded/Inactive、没有 Starting"(task 10) | 读 180-201 | **一致**。行 185 两布尔(`ahd_has_inventory` ∧ `master_tmux_alive`);行 190 逐字:"ah 的 `runtime_state` 也只有 Active/Degraded/Inactive、没有 Starting 相位"。 |
| :629-644 | 把 `ah ps` 解析/tmux 兜底写成必须遵守的规则(task 10) | 读 625-647 | **一致**。行 637-638 逐字:"`ah ps` 输出解析必须提取 `tmux -L <socket>` 与 `sess_*` session id,供后续 tmux double-check 与 `ah kill --session` 兜底使用"——正是要改写的强制规则。 |
| :553 与 :644 | "`ah status` 不是可用命令"(task 10) | 读 545-559 / 625-647 | **一致**(两处均逐字)。553 在 MoirAI Intro 草案信息源;644 在验收/机制清单("声明 `ah status` 不是可用命令")。 |
| (旁证) `.ah/skills/moirai-intro/SKILL.md` | design:644 提及该文件"声明 ah status 不可用" | `find` | **文件不静态存在**(worktree 无 `.ah/skills/moirai-intro/`)——它是 Studio 运行时按 lib.rs:550 模板生成的派生文件。task 10 正确地把回写锚点落在**模板源 lib.rs:550**(存在),不是生成物。无缺陷。 |

### 1d. ah CLI 行为断言(1.5.0 只读实测 / CHANGELOG 核对)

| 断言(出处) | 核实方法 | 结果 |
|---|---|---|
| `ah version`→裸 `1.4.0`;`ah --version`→`ah 1.4.0` 取第二段(Req 1.8/F6) | `ah version` / `ah --version` | **一致(格式)**。实测 `1.5.0` 与 `ah 1.5.0`——版本号因 ah 已升 1.5.0 而不同,**输出格式**(裸 vs 前缀)与断言吻合。 |
| runtime snapshot 含 `runtime_state` 相位字段 | 读活快照 | **一致**。观测到 `runtime_state:"active"`。 |
| `runtime_state` 有 `starting`/`degraded`(F2,引 1.3.4 CHANGELOG) | WebFetch v1.4.0 CHANGELOG | **一致(文献)**。1.3.4 逐字:"snapshots now include a starting runtime_state…";"Consumers such as Studio should clean up only degraded runtimes; starting means startup is still in progress and must be left alone."——与 Req 3.6 内联引文完全一致。活/degraded/starting 三态无法在健康编队上按需复现,以文献+字段结构佐证。 |
| `sequence` 字段在真实快照(F5/Req 2.1) | 读活快照 | **一致**。顶层 `sequence:1`。 |
| `ahd_alive` 顶层字段(F8/Req 3.3/测试 5.1) | 读活快照 | **一致**。`ahd_alive:true`。 |
| 真实字段是 `live_agents`(+`db_tracked_agents`),非 `activeAgents`(F8) | 读活快照 sessions[] | **一致**。`live_agents:2`、`db_tracked_agents:2`;无 `activeAgents`。 |
| `sessions[].safe_to_cleanup` / `cleanup_required` 存在(F8/Req 4.2) | 读活快照 sessions[] | **一致**。`safe_to_cleanup:false`、`cleanup_required:false`。 |
| `config_path` 实测可为 null(F8) | 读活快照 | **一致**。daemon 无 config 运行时顶层 `config_path:null`。 |
| `state_dir` 字段存在(F4b/Req 2.7) | 读活快照 | **一致**。`state_dir:"/root/.local/state/ah/f2647adf"`;另 `schema_version:2`。 |
| `AH_STATE_DIR` 优先于显式 `--config`(F4b,引 README/1.4.0 CHANGELOG #117) | WebFetch v1.4.0 CHANGELOG | **文献一致**。1.4.0 逐字:"State-directory resolution follows the documented priority contract (AH_STATE_DIR > CCBD_STATE_DIR > XDG_STATE_HOME > explicit config > dev mode > project discovery)"。**但 1.5.0 运行时行为与此不符,见 §1e-NF2。** |
| F1:daemon-absent 时 `status --json` exit1/无 JSON/stderr 文本,`events` 给结构化 `daemon_absent` 快照 | 尝试隔离复现 | **无法独立复现(附因)**。见 §1e-NF-caveat:本机有活 ahd,`ah status`/`ah events` 无视隔离直接连上活编队,拿不到 daemon-absent。F1 需在**零 ahd** 机器复现;本审以操作者 1.4.0/1.5.0 实测记录+活快照字段结构佐证其可信,但未能亲验 daemon-absent 分支。 |
| F8 新证(1.5.0):同 cwd 含 `ah.toml`、无 `--config` 时 status/ps 与 events 的 state-dir 口径不一致 | 隔离 `--config`/`AH_STATE_DIR` 实测 | **一致且更强**。见 §1e-NF1:`ah events --config <隔离>` 回显 `config_path=<隔离>` 却返回**活编队的** `state_dir`+sessions——单个快照内部身份字段自相矛盾。 |

### 1e. 实测中浮现的 spec 缺陷(锚点核实的核心增值)

> 以下三条是"核实断言时实测到、但 spec 现有条款未正确覆盖"的问题,按严重级列。

**NF1(严重级:高)· 身份校验(Req 2.7 / 4.8)以 `config_path` 匹配为据,被 CLI 回显行为击穿。**
- 实测(1.5.0):`ah --config /tmp/ah-fixture-2/ah.toml events --format json`(该 config 指向一个**空的**隔离项目)返回的首帧快照为:
  `config_path:"/tmp/ah-fixture-2/ah.toml"`(= 我请求的隔离路径,**被原样回显**)、
  `state_dir:"/root/.local/state/ah/f2647adf"`(= **活编队**的 state dir)、
  `sessions[].path` = 活编队 worktree、`runtime_state:"active"`。
- 即:**ah 把快照的 `config_path` 无条件盖成"你请求的那个 config",而真正的 runtime 数据(state_dir/sessions/agents)属于另一套 daemon**。
- 后果:Req 2.7/4.8 要求"校验 `config_path` **和** `state_dir` 属于所请求 config"。但 `config_path` 恒等于请求值 → 这一半校验**零鉴别力**;若实施者(按字面)校验了 config_path 就放行,身份校验形同虚设,Studio 会把**操作者自己编队**的快照当作自己 temp config 的状态采信——这正是 F4a 要防的误伤,却从另一条通路(status/events 无视 --config)穿透。
- spec 缺口:未指明 `config_path` **因回显而不可作身份权威**;未指定 Studio 如何**独立推导**"期望的 state_dir"(活快照里 `workspace_path:null`,temp config 的期望 state_dir 不能仅由 config 路径得出)来做真正的比对。测试 5.10 的 fixture 若只覆盖"config_path 与 state_dir 都不匹配",会漏掉真实失效形态"**config_path 匹配、state_dir 不匹配**"。
- 须改:Req 2.7/4.8 明确以 `state_dir`(和/或 `sessions[].project_id`/`path` 会话身份)为**唯一权威身份字段**,并显式声明 `config_path` 系请求回显、不得单独作为身份依据;task 0 追加"记录 `--config <隔离>` 下快照 config_path 被回显、state_dir 指向他者"的证据;测试 5.10 fixture 必含"config_path 匹配但 state_dir/会话身份不匹配即丢弃"用例。

**NF2(严重级:中-高)· env-clamp 补救(Req 4.7)在 spec 实际准入的版本(1.5.0)上实测无法达成隔离。**
- 实测:`env AH_STATE_DIR=/tmp/ah-fixture-2 ah status --json`(空隔离 state dir,cwd 亦隔离)与 `env AH_STATE_DIR=/tmp/ah-fixture-2 ah --config /tmp/ah-fixture-2/ah.toml status --json` **都**返回活编队(`state_dir` 仍为 `f2647adf`,agents d1/o1)。`ah events` 同。即 **1.5.0 下 `ah status`/`ah events` 无视 `AH_STATE_DIR`(以及 `--config`),经全局机制连上正在运行的 daemon。**
- 与文献冲突:1.4.0 CHANGELOG 记 `AH_STATE_DIR > … > explicit config > … > project discovery`;操作者 F8 自己也注"1.5.0 state-dir 解析口径换边"。故这是 1.4.0→1.5.0 的**已知行为漂移**,而本 spec 最低版本门是 `>= 1.4.0`(准入 1.5.0)。
- 后果:Req 4.7"在每次调用前 clear/pin AH_STATE_DIR/CCBD_STATE_DIR/XDG_STATE_HOME"这一**读面隔离**手段,在 1.5.0 上对 `ah status`/`ah events` **拿哪套 daemon** 不起作用;design 的集成测试"Env clamp prevents an inherited AH_STATE_DIR from redirecting which ah instance a … invocation talks to"**按字面不可通过**(clamp 改了也不改结果)。真正承重的控制是身份校验(NF1),不是 env-clamp。
- 须改:Req 4.7 降级定位为"防止 state 目录**互相污染写入**"这类它仍能保证的目标,并显式说明它**不**保证读面 daemon 选择的隔离;把读面隔离的承重责任明确移交给 NF1 的身份校验;task 0 追加"clamp AH_STATE_DIR 后 status/events 仍连活 daemon"的实测记录;修正 design Testing Strategy 中不可达成的 env-clamp 集成断言。

**NF-caveat(流程,非缺陷,但影响 task 0 可执行性)· F1 daemon-absent 分支在有活 ahd 的机器上不可复现。**
- 因 NF2 同源:`ah status`/`ah events` 会全局连上任何在跑的 daemon,故本机(有 operator 编队)拿不到"daemon 不存在"的输出。task 0 的 F1/daemon-absent 采集**必须在零 ahd 的干净机器**上做,否则采到的不是 daemon-absent 而是某个残留编队快照。tasks.md task 0 当前未点出这一前置条件,建议补一句。

---

## 2. tasks.md 可实施性 / TDD 顺序发现(逐条,标严重级)

**T-1(通过)· 任务 0 确在所有生产任务之前。** task 0 = 纯前置 CLI 验证(明写"不写生产代码");task 1 = fixtures(测试输入);tasks 2-10 = 生产代码。宏观 TDD 顺序(验证→RED fixture→生产)成立。task 0 覆盖 F8 的 `ah start` 重复启动行为、F1 daemon-absent、F8 新 state-dir 证据、degraded/starting 采集,方向正确。

**T-2(中)· 安全护栏任务(task 6)排在会发出生命周期命令的任务(task 5)之后——顺序倒置。**
- task 5"重做 Open/Attach 决策"包含发 `ah start`(含 duplicate-start 处理);task 6 才实现"所有权分类器 + 只对 Studio-managed config 允许 start/stop/kill"。按 Req 4.6,发 `ah start` 前必须先过所有权闸。护栏(task 6)是发命令(task 5)的**前置条件**,却排在其后。虽同 PR 落地可缓解,但派单顺序应把 task 6 提到 task 5 之前(或合并),避免出现"Open 决策已能 start、所有权闸尚未接入"的中间态。

**T-3(中)· NF1/NF2 使 task 3 的身份校验、task 6 的 env-clamp 目标本身需重定义,当前任务描述会把实施者引向按字面(config_path 匹配 / env-clamp 达成隔离)实现,而那已被实测证伪。** task 3"加入快照身份校验:config_path/state_dir 必须匹配"、task 6"钳制 AH_STATE_DIR…不吃 profile pin 值"——在 requirements 未按 §1e 修正前,这两个任务不可安全派单:实施者会实现一个被 CLI 回显击穿的 config_path 校验、和一个在 1.5.0 上不改变读面结果的 clamp。**阻塞项**:先修 Req 2.7/4.8/4.7,再派 task 3/6。

**T-4(低-中)· 每个生产任务缺"先写哪条失败测试(测试名+断言目标)"的 TDD 框线,只在文件头和 Req 5 各写一遍。** tasks 2-9 主要描述生产改动,只有 task 5/9/11 提到"用 fixture 验证";"先写失败测试再写生产代码"仅在"实现约束"头部声明,断言目标散在 Req 5.1-5.12,靠 `_Requirements:` 反查。按 d1 方法论"tasks 内含 TDD 框线:测试名+断言目标",tasks.md 偏薄:建议每个生产任务显式列出它先要写红的测试点(可直接引 5.x 编号并写清断言),否则派单后实施者可能先写生产代码。不阻塞,但会降低 TDD 可执行性。

**T-5(低)· task 3 依赖 task 4 的仲裁语义却排在其前。** task 3 明写"不把 status 非结构化失败当权威(见任务 4)",即 task 3 的正确行为依赖 task 4 的 events-primary 仲裁。二者高度耦合,同 PR 可接受;若拆 PR 会出现 task 3 单独存在时 status 仍被当主面的中间态。建议注明二者必须同批。

**T-6(通过)· 任务描述边界总体清楚、可派单。** 每条列了改哪个函数/行(如 task 2 点名 lib.rs:1754/1836/1903/1960、task 6 点名 lib.rs:828-833/858/879/927、task 8 点名 63-73/1244-1246),范围不需实施者猜。除 T-2/T-3/T-4 外,粒度可执行。

**T-7(通过)· task 10(F7 回写)覆盖 operator-review-findings F7 全部锚点。** 逐条比对:
- ah-orchestration-design.md:185-193 → task 10 第 1 bullet(加 starting/degraded 语义)✓
- 629-644 → task 10 第 2 bullet(ah ps 解析改写为 events-primary + ownership guard)✓
- 553 → task 10 第 3 bullet ✓;644 → task 10 第 3 bullet 同句 + 第 2 bullet 范围 ✓
- lib.rs:550 → task 10 第 4 bullet(moirai-intro 文本,注明与 moirai spec 排序,本 spec 先行)✓
- 四处锚点(185-193 / 629-644 / 553 / 644)+ lib.rs:550 **全覆盖**,且都已在 §1a/1c 亲验存在。

---

## 3. 验收标准可测性发现(逐条,标严重级)

**A-1(通过)· 大多数新增/修订条款已具体到可直接转一条自动化断言:**
- 1.1/1.8(版本门+两种输出格式)、2.1(sequence 单调,旧序号不覆盖新)、2.2/2.3(status 非结构化失败不作权威,见 5.11)、3.6(starting → 三按钮禁用+显示 starting,见 5.6)、3.7(degraded → cleanup-then-Open 可用,见 5.7)、4.2/5.5(清理只打 `cleanup_required`/非 `safe_to_cleanup` 的 session id)、6.1/5.12(per-assistant 枚举、双活不抑制)——均可测。Req 5.1-5.12 与 3.x/4.x/6.x 一一映射,覆盖面好。

**A-2(高)· Req 2.7 / 4.8 的可测性被 NF1 破坏。** 条款措辞"校验 config_path 和 state_dir 匹配"未言明 config_path 恒被回显,故"匹配"这一断言对 config_path 恒真、无鉴别力。测试 5.10 若不特指"config_path 匹配、state_dir 不匹配即丢弃",会写出一个通过但无效的测试。**须**把断言目标改写为"以 state_dir/会话身份为准,config_path 匹配但 state_dir 不匹配的快照必须被丢弃"。

**A-3(中)· design Testing Strategy 的 env-clamp 集成断言在 1.5.0 不可达成(NF2)。** "Env clamp prevents an inherited AH_STATE_DIR … from redirecting which ah instance a … invocation talks to"——实测 clamp 不改变 status/events 连哪套 daemon,该断言按字面无法写成通过的测试。须随 Req 4.7 重定义一并改。

**A-4(低-中)· "wait briefly" 未量化(Req 2.3)。** "shall start (or wait briefly for) an events subscription … before making a decision"——"briefly" 无时限,不能直接转成确定性断言(等多久算超时?超时后落哪个态?)。建议给出明确超时值与超时后的回落态(应回落到"inconclusive/inactive 可启动",而非 error),再写断言。

**A-5(低)· 偏架构原则、非单条可断言的条款(可接受,但宜标注为设计约束而非验收点):** Req 2.6("read-through replicas, not Studio-owned truth")、Req 3.8("不得把 runtime_state 降维回单布尔")属设计不变量,难以单条自动化;它们通过 5.x 的具体投影测试间接覆盖即可,不必强行写成独立断言。

**A-6(通过)· Req 3.4 的未验证假设已被诚实降级并挂前置验证。** "依赖 `ah start` 拒绝重复启动这一未验证假设,须先用真实 CLI 验证(5.8/task 0)"——把未坐实的行为标为待验证而非既定事实,符合"论据先行",是修订版的加分项。

---

## 4. 总体 Verdict:有条件批准(Conditional Approve)

**成立并值得肯定的部分**
- F1-F9 → requirements/design/tasks 的逐条溯源(REVISION-TRACE.md)真实可指认,§1 抽查的行号锚点**全部命中当前 main**,无一处失效或漂移。
- **F8 数据模型修正被 1.5.0 活快照实测强证**:`live_agents`(非 `activeAgents`)、`db_tracked_agents`、`ahd_alive`、`sequence`、可空 `config_path`、`safe_to_cleanup`/`cleanup_required`、`state_dir`、`schema_version:2` 全部如修订所述存在——这是本次修订最扎实的一块。
- F2 的 starting/degraded 语义有 1.3.4 CHANGELOG 逐字背书;F6 的 4 份 awk 门、events 重生循环、版本输出格式均亲验属实;Req 3.4 未验证假设诚实降级。
- 方向(用结构化状态合约取代 Studio 第二套弱状态机、events 为主决策面、所有权二分类、per-assistant payload)正确,不动。

**必改项(实施前须先在辩论/修订层修 requirements/design,不能带病派单)**
1. **[NF1/A-2/T-3,高] 身份校验重设计**:Req 2.7/4.8 以 `state_dir`(+会话身份)为唯一权威,显式声明 `config_path` 因被 ah 回显而不可作身份依据;指定 Studio 如何独立推导期望身份;测试 5.10 覆盖"config_path 匹配、state_dir 不匹配即丢弃"。**理由**:实测 `ah events --config <隔离>` 回显请求 config_path 却返回他套 daemon 的 state_dir,现条款可被击穿。
2. **[NF2/A-3/T-3,中-高] env-clamp 定位修正**:Req 4.7 明确它不保证 1.5.0 上读面 daemon 选择的隔离,把读面隔离承重责任移交身份校验;删/改 design 中不可达成的 env-clamp 集成断言。**理由**:实测 clamp AH_STATE_DIR 后 status/events 仍连活编队。
3. **[T-2,中] 任务顺序**:把 task 6(所有权闸+env-clamp)提到 task 5(发 `ah start` 的 Open/Attach)之前或合并,避免"能 start 但护栏未接"的中间态。
4. **[NF-caveat,流程] task 0 补前置条件**:F1/daemon-absent 采集须在**零 ahd** 机器进行,并追加"`--config`/`AH_STATE_DIR` 隔离对 status/events 无效"、"config_path 被回显"两条 1.5.0 证据的采集项。

**建议项(不阻塞)**
- [A-4] Req 2.3 的 "wait briefly" 量化为明确超时+回落态。
- [T-4] 每个生产任务补 TDD 框线(先写红的测试名+断言目标,直接引 5.x)。
- [1a-858/879/927] Req 4.7 区分 927(tmux)与 858/879(ah)调用点,措辞勿把 tmux 路径称作"invoking ah"。
- [T-5] 注明 task 3 与 task 4 必须同批落地。

**结论**:方向批准、溯源与 F8 修正扎实;但身份校验与 env-clamp 两处安全承重条款被 1.5.0 实测证明按现措辞会失效/不可测,且相关任务(3/6)会把实施者引向已被证伪的实现。**须先完成上列必改项 1-4(经 master 走修订层改 requirements/design),再解锁 tasks 派单实施**。在此之前不建议进入生产编码。
