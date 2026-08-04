# 决议 2026-08-02 — Open in CLI 的残留状态诚实化 + Claude CLI 自更新入口

> 本文件是 PM 于 2026-08-02 批准的实施方案落盘件，覆盖两项独立缺陷的修复决策、
> 关键设计决定与验收判据。它修订 `studio-ah-state-contract-v1` 的状态投影部分
> （`design.md` 的 phase→UI 投影、`requirements.md` Req 3.2/5.1 中"全部会话终态 ⇒ 可 Open"
> 一条），不修订该 spec 的其余部分。

## 一、缺陷 A：CLI 会话退出后，Studio 谎称"可以重新打开"

### 1. 现象

用户在 Studio 打开的 Claude Code 终端里执行 `/exit`。tmux 窗格变成 `Pane is dead (status 0)`，
终端窗口停在那一屏；Studio 右上角控件却变回 `Open in CLI`。再点 Open，打开的仍是那块死窗格。

### 2. 根因（已取证）

四个事实叠加成这个现象：

1. **ah 故意保留死窗格**：`ah` 在每个 spawn 出的窗格上设 `remain-on-exit on`
   （ah 仓 `src/tmux/session.rs:319-333`，spawn 时必调，同文件 `:165`）。CLI 进程退出后窗格
   保留为 `[dead]`，用于事后取证。这是有意设计，本决议不改变它。
2. **ah 把会话标记为终态，但不回收 tmux**：master 进程在无活跃工作时退出，ah 将该 session
   置为 `CLOSED`（ah 仓 `src/master_revival.rs:378-401`）。ah 生产代码中回收 tmux 的唯一位置
   是 ahd 守护进程收到 SIGTERM/SIGINT 时的整体清理（ah 仓 `src/bin/ahd.rs:214-241`：逐个
   `kill-session` → `tmux kill-server` → 删 socket）。**没有任何路径在"单个会话走到终态"时回收
   它的 tmux。**
3. **快照因此变成 `inactive`**：会话终态后 `ahd_has_inventory` 为假，`runtime_state` 落到
   `inactive`（ah 仓 `src/runtime_events.rs:320-328`）。
4. **Studio 直接把 phase 投影成 UI 状态**：`inactive` → `AssistantStatus::Inactive` → 前端渲染
   `Open in CLI`（`apps/studio/tauri/src/lib.rs:3323`、
   `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:333-345`）。

即：**ah 的运行时（ahd 进程 + 它持有的 tmux server + 那块死窗格）都还在，Studio 却呈现为
"什么都没在跑"。** 这是状态撒谎，不是按钮逻辑写错。

### 3. 决策

**PM 裁决（2026-08-02）：不修改 ah。死窗格保留。修复落在 Studio 的状态投影层——
只要该 config 的 ah 运行时还没被回收，Studio 就不得呈现"可以重新打开"，而必须呈现
"运行时仍在，可以从 Studio 关闭"。**

### 4. 关键设计决定

#### D-A1：判据取 `ahd_alive`，不取 `cleanup_required`

**决定**：新状态的触发条件是 `runtime_state == inactive && ahd_alive == true`。

**理由（第一性原理）**：需要的信号是"这套运行时是否已被回收"。ah 只在 ahd 进程退出时回收
tmux（根因第 2 条），因此 `ahd_alive == true` 与"tmux 尚未回收"是同一件事，且它是**可收敛**的
——Close 走 `ah stop`（ah 仓 `src/bin/ah.rs:1225-1229` → `system.shutdown` → 自发 SIGTERM →
上述整体清理），ahd 一死，Studio 就再也取不到快照，状态自然归零。

> **修正（2026-08-04）：面板呈现这条道的判据改为 `tmux_server_alive`。**
>
> 本条的推理是"ah 只在 ahd 退出时才回收 tmux ⇒ `ahd_alive == true` 与『tmux 尚未回收』
> 是同一件事"。这个蕴含**只有一个方向**：ahd 活着并**不代表** tmux server 存在——它可以
> 从来没建过，也可以被外部带走（机器重启把 tmux 全清掉、而 ahd 又被重新拉起，就是本机
> 实测到的形状）。
>
> 真机取证（2026-08-04，本机 WSL，`ah 1.7.0`）：Studio 管的 6 份 config 里有 **4 份**处于
> `runtime_state:"inactive"` + `ahd_alive:true` + `tmux_server_alive:false` +
> `ahd_has_inventory:false`，全部 agent `state:"KILLED"`/`tmux_alive:false`。旧判据把这
> 4 份都报成 `lingering`，面板给出一个 **attach 不到任何东西、也无事可关**的 Close 控件。
> 逐字捕获的那一帧已冻结为 fixture `SNAPSHOT_AHD_ALIVE_TMUX_GONE`。
>
> **修正后的判据**：`runtime_state == inactive && tmux_server_alive == true` ⇒ `lingering`。
> 依据是本条本来就想表达的那件事——**死窗格活在 tmux server 里，server 没了就什么都没
> 剩下**，而这个事实快照里直接带着，不需要经由 ahd 推断。本条要解决的原始场景（`/exit`
> 之后 ah 标终态却不回收 tmux）里 server 仍在，因此判定不变、缺陷 A 的修复不受影响。
>
> **范围**：只改**面板呈现**。启动前该不该先清残留是另一条道
> （`reconcile_snapshot_lifecycle`），它**继续用 `ahd_alive`**——游离的 ahd 即使没有 tmux
> 也该在启动新运行时之前清掉（D-A4），那一层宁可多清。两条道用各自真正需要的那个事实。

**被否决的替代项**：用快照里的 `sessions[].cleanup_required`。该字段定义为
`终态状态 && (… || master_pid > 0 || …)`（ah 仓 `src/runtime_events.rs:635-648`），而 ah 没有
任何路径把 `master_pid` 清零——连 `ah kill --session --force` 的终态分支也只改 status 不清 pid
（ah 仓 `src/rpc/handlers/sessions.rs:211-215`）。**该标志一旦为真便永远为真**，用它驱动 UI 会把
Studio 永久钉死在"运行中"，Close 也解不开。

#### D-A2：新增独立状态 `lingering`，不复用 `degraded`

**决定**：`AssistantStatus` 增加取值 `lingering`，wire 值 `"lingering"`。
其定义为：**该 config 的 ah 运行时仍然存在，但其中已经没有活的 CLI 会话。**

**理由**：`degraded` 在既有契约里的前端映射就是"不可 attach → 回落到 Open 控件"
（`copilot-panel.tsx:326-345` 的注释与实现），正是本决议要消除的行为；复用它会同时污染
ah 侧 `degraded` 的既有语义（有 ACTIVE 会话但 master/worker 的 tmux 不在）。

**措辞约束**：该状态**不表示 CLI 进程还在运行**。UI 文案与文档一律表述为"运行时仍在"，
不得表述为"Claude 正在运行"。

#### D-A3：~~`lingering` 可 Close，不可 Attach~~ → **已被 PM 裁决 2026-08-04 取代**

> **现行规则（PM 裁决 2026-08-04，原话）**：「有残留的状态就当作还在 running，用户点击
> attach 就打开死 pane，必须点击 close 把所有残留清干净才能再点击 open。」
>
> **即**：残留 = 还有运行时，Attach 与 Close 覆盖同一个集合；`Open in CLI` 在残留清干净
> 之前不出现（这一条本来就是现状——有残留时头部渲染的是管理控件）。
>
> **推翻本条的理由**：D-A3 的出发点是「attach 上去就是那块死窗格，等于把缺陷换个位置
> 重现」。但那块死窗格恰恰是 ah **有意**用 `remain-on-exit` 留下来供事后取证的东西，
> 而那一屏正是使用者想看的——CLI 是怎么退的、最后报了什么。原方案等于：保留一份证据，
> 然后让自己的 UI 拒绝展示它。
>
> **更严重的是它的落地方式**：D-A3 把「不给 attach」实现成了「attach 即销毁」——
> attach 走到 `CleanupStale` 分支，先 `cleanup_workspace_code_assistants` 清掉整个
> 运行时，再返回一句 "was stale and has been closed"。一次**观察**动作把**观察对象**
> 毁掉了。销毁只能由 Close 显式发起。
>
> **落地**：attach 这条道有自己的判据 `reconcile_snapshot_attach`（与 Open 的
> `reconcile_snapshot_lifecycle` 分开，因为两条道对同一帧快照问的是不同的问题）：
> 残留 → `AttachResidue`（直接 attach，不清理）；`degraded` → 仍然 `CleanupStale`
> （坏状态，没有可读的窗格，attach 上去什么也看不到）；`active` → attach；
> 真空位 → not running；`starting` → hands-off。
>
> **附加约束**：残留的 Attach 菜单项必须标明会话已退出（`Attach X (exited)`）。不标出来，
> 点下去看到一块冻住的窗格会被读成卡死——那是把一个诚实的入口做成了陷阱。
>
> **判据同源**：「面板说还有运行时（`lingering`）」与「attach 能落到一块可看的窗格上」
> 是同一个问题，因此共用同一个谓词 `runtime_has_unreaped_residue`（会话终态 + tmux
> server 仍在，见 D-A1 的 2026-08-04 修正），并有测试锁住两者一致，避免出现「面板给了
> Attach、点下去却报 not running」的裂缝。

（以下为已被取代的原文，保留供追溯）

**决定**：前端把 `lingering` 归入"有运行时需要关闭"的一类，头部呈现管理控件而非 Open 控件；
但下拉中的 **Attach 项只列真正 `active` 的助手**。

**理由**：`lingering` 下 attach 上去就是那块死窗格——正是用户报告的现象。给出一个必然导向
死窗格的入口，等于把缺陷换个位置重现。

#### D-A4：启动任何 CLI 之前，清掉该 workspace 下的全部残留运行时

**规则（PM 裁决 2026-08-02 第二轮，原话）**：只允许一个 CLI 在跑；启动一个 CLI 之前必须把
全部残留清干净。

**决定**：
1. `lingering` 与 `degraded` 一样映射为 `CleanupStale`——Open 先清理该 workspace 下的全部
   运行时残留，再启动。
2. `RejectOtherActive` 的判定**优先于** `CleanupStale`：当另一个助手真的处于 `active` 时，
   Open 一律拒绝并提示先关闭它。

**理由**：本决议初版曾以"`CleanupStale` 的落地动作 `cleanup_workspace_code_assistants`
（`lib.rs`）会 stop 掉该 workspace 下的全部 config"为由放弃这条清理，担心
"请求方有残留 + 另一个助手正在运行"时误关正在运行的那个。PM 指出**该组合本身就是不允许的
状态**：它之所以能出现，恰恰是因为上一次启动没有清残留。把"启动前清残留"做实，这个组合
就不再产生；而"另一个真的在跑"这一条由 `RejectOtherActive` 单独拦住，不被"清残留"扩大解释成
"替用户关掉正在干活的 CLI"。

**由此确定的决策表**（requested 的相位 × 其他助手的相位）：

| requested | others | 决策 |
|---|---|---|
| `starting` | 任意 | `HandsOff` |
| 非 `active` | 含 `active` | `RejectOtherActive` |
| `lingering` / `degraded` | 无 `active` | `CleanupStale` |
| `inactive` | 含 `lingering`/`degraded` | `CleanupStale` |
| `inactive` | 全 `inactive` | `StartFresh` |
| `active` | 含 `active` | `CleanupStale` |
| `active` | 无 `active` | `AttachRequested` |

其中 `inactive` 一律指 `ahd_alive == false` 的真空位（运行时确实被回收过）；`ahd_alive == true`
的 `inactive` 相位一律是 `lingering`。

#### D-A5：残留清理的主路径是"关闭时清"，启动时清是双保险

**规则（PM 澄清 2026-08-02，原话）**：一个 CLI 关闭时就应该把残留清干净；启动时清理是双保险。

**现状**：Close 已经走 `ah stop`，ah 侧的 SIGTERM 处理路径会逐个 `kill-session` 并
`tmux kill-server`（ah 仓 `src/bin/ahd.rs:214-241`），所以"关闭 ⇒ 残留被回收"这条链本身成立。

**缺口在宣布时机**：ah 的 shutdown handler 先返回 RPC，再 spawn 一个 50 毫秒后给自己发 SIGTERM
的任务（ah 仓 `src/rpc/handlers/system.rs:10-22`）。因此 `ah stop` 返回时 ahd 尚未退出、tmux
尚未回收；而 Studio 在命令返回后立即清空状态缓存并 emit（`lib.rs` 的 `close_code_assistant`），
UI 会在残留还在时就变回 `Open in CLI`——这正是"命令发出即宣布成功"，违反 AGENTS.md 的因果验证
铁律，也破坏 D-A1 建立的不变量。

**决定**：Close 在 `ah stop` 之后轮询确认 ah 运行时确实消失（探测不到快照，或快照自报
`ahd_alive:false`），确认之后才清空状态缓存；确认不了就**保留 `lingering` 状态**，让使用者
可以再关一次，而不是谎报已清理。

#### D-A6：Studio 内不存在"一个 CLI 开着还能开另一个"的入口

**事实（PM 澄清 2026-08-02）**：面板头部只有一个控件位——只要任一助手处于 `active` 或
`lingering`，渲染的就是管理控件（Attach/Close），`Open in CLI` 根本不出现。因此"另一个助手
正在运行时点 Open"这个交互在 Studio 内不可达。

**因此**：`RejectOtherActive` 保留为**后端边界的 fail-fast**（Tauri command 可被直接调用，
边界校验不能省），而不是一个 UI 会走到的分支。它不应被当作"使用者可能遇到的交互"来设计，
也不构成放弃 D-A4 清理规则的理由。

### 5. 验收判据（缺陷 A）

| # | 判据 | 验证方式 |
|---|---|---|
| A-1 | `runtime_state:"inactive"` 且 `ahd_alive:true` 的快照投影为 `lingering` | Rust 单测，喂 `SNAPSHOT_TERMINAL_CLOSED` 与 `SNAPSHOT_INACTIVE` 两个既有 fixture |
| A-2 | `ahd_alive:false` 的快照仍投影为 `inactive` | Rust 单测，喂 `SNAPSHOT_DAEMON_ABSENT` fixture（对照组，证明不是常量） |
| A-3 | `lingering` 渲染管理控件（含 Close），不渲染 `Open in CLI` | 前端单测 |
| A-4 | `lingering` 的下拉中不出现该助手的 Attach 项 | 前端单测 |
| A-5 | 真机：`/exit` 后控件保持可关闭态；点 Close 后 tmux 会话与死窗格消失，控件才变回 `Open in CLI` | PM 点验（清单见 PR） |
| A-6 | 请求方自身是 `lingering` → Open 决策为 `CleanupStale`（先清后启） | Rust 单测 |
| A-7 | 另一个助手是 `lingering` → 同样 `CleanupStale`（不留下"残留 + 在跑"的组合） | Rust 单测 |
| A-8 | 另一个助手是 `active` → `RejectOtherActive`，且该判定优先于清理 | Rust 单测 |
| A-9 | 两侧运行时都已被回收（`ahd_alive:false`）→ `StartFresh`，不跑多余的清理 | Rust 单测（对照组，证明不是常量） |
| A-10 | Close 在 `ah stop` 之后持续探测，直到运行时确实消失才确认；每一轮都重新探测 | Rust 单测（注入探测器） |
| A-11 | 运行时卡住不退时，确认返回失败而不是假装已清理，且状态缓存不被清空（UI 保持可关闭） | Rust 单测 |

## 二、缺陷 B：WSL 里的 Claude CLI 停在旧版本

### 1. 现象

Windows 侧 Claude CLI 已自更新至 2.1.220，WSL 侧停在 2.1.199（2026-07-02 安装）。

### 2. 根因（已取证）

- **不是 `autoUpdates` 开关**：两侧配置完全相同（`installMethod:"native"`、`autoUpdates:false`、
  `autoUpdatesProtectedForNative:true`、`migrationVersion:13`），Windows 侧却一路更新到 2.1.220。
  该开关对 native 安装不起作用。
- **是沙箱 HOME 吞掉了更新**：Claude CLI 的自更新是"运行中的进程更新它自己 `$HOME` 下的那份
  安装"。而 WSL 中的 claude 几乎只被 ah 拉进沙箱运行，ah 为每个会话指定独立的临时 `HOME`
  （ah 仓 `src/monitor/master_reaper.rs:66-70` 设 `HOME` 与 `CLAUDE_CONFIG_DIR`），会话结束即删除。
  更新即使成功也落在临时目录，**永远回不到 `/root/.local/bin/claude` 指向的真实安装**。
- 宿主 HOME 下的 claude 自 2026-07-02 起几乎未被直接启动（`numStartups: 3`），自更新机制没有
  运行机会；唯一痕迹是 `versions/` 下一个 2026-07-07 留下的 0 字节 `2.1.203`（一次未完成的更新）。

### 3. 决策

**在 Studio 每次 Open 生成的 WSL 启动脚本中，于宿主 HOME、进入 ah 沙箱之前，调用官方安装器
入口升级 Claude CLI。** Studio 只负责给官方机制一个能生效的运行位置与时机，**不自行比对版本号、
不自行下载、不自行安装**。

### 4. 关键设计决定

#### D-B1：入口用 `claude install latest`

**决定**：调用 `claude install latest`。

**理由**：2.1.199 的 `claude --help` 中不存在 `update` 子命令；官方入口是
`install [target]`（"Install Claude Code native build. Use [target] to specify version
(stable, latest, or specific version)"）。

#### D-B2：位置在 Open 的 WSL payload 中、`ah start` 之前

**决定**：插入 `wsl_payload_script`（`lib.rs`）的 ah 版本门禁之后、`ah --config "$CFG" start` 之前。
**不**插入 `wsl_attach_payload_script`（attach 路径连的是已在运行的会话，升级无意义且会拖慢）。

**理由**：该 payload 正好运行在宿主 HOME、沙箱之外——这是根因第 2 条要求的唯一有效位置。

#### D-B3：只对 Claude 生效

**决定**：仅当 `assistant == Claude` 时插入该段。Codex 的分发路径不同（Windows 侧为权威），
不在本决议范围内。

#### D-B4：24 小时节流

**决定**：以 `$HOME/.cache/studio-claude-cli-update-check` 为时间戳，距上次检查不足 24 小时则跳过。

**理由**：native build 单文件约 250 MB。在无法确证"已是最新时安装器会立即返回"之前，
每次 Open 都调用存在重复下载的风险，会把冷启动从约 15 秒拖到分钟级。

#### D-B5：失败不阻断打开

**决定**：该段带超时（300 秒），失败时打印一行提示并继续用已安装版本启动，
不中断 `ah start`。

**理由**：能否打开 CLI 不应由一次网络抖动决定。

### 5. 验收判据（缺陷 B）

| # | 判据 | 验证方式 |
|---|---|---|
| B-1 | Open 的 WSL payload 含 `claude install latest`，且位于 `ah start` 之前 | Rust 单测断言脚本文本与顺序 |
| B-2 | Attach 的 WSL payload 不含该段 | Rust 单测 |
| B-3 | Codex 的 Open payload 不含该段 | Rust 单测 |
| B-4 | 该段带超时且失败不阻断（`||` 兜底后继续） | Rust 单测断言脚本文本 |
| B-5 | 真机：点一次 Open in CLI，终端打印官方安装器输出，之后 `claude --version` 升到最新 | PM 点验 |

## 三、范围边界

本决议**不包含**：修改 ah 仓任何代码；修改 `scripts/install-claude-code-wsl.ps1`；
清理 `versions/` 下的 0 字节残留文件；修复 `ah attach master` 落到非活跃窗口的定位缺陷
（该缺陷已取证：ah 仓 `src/bin/ah.rs:1617-1624` 为 session 级 attach，
新窗口以 `new-window -d` 创建不切换当前窗口——留作 ah 侧后续事项）。
