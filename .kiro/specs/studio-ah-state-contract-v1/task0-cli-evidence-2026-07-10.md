# Task 0 — 前置 CLI 行为取证（raw capture）

- **spec**: studio-ah-state-contract-v1
- **task**: tasks.md 任务 0（纯 CLI 行为验证，不写生产代码）
- **date**: 2026-07-10
- **ah 版本**: `1.5.0`（`ah version` → `1.5.0`；`ah --version` → `ah 1.5.0`）。**本机只装了 1.5.0，没有 1.4.0 binary**（`/root/.cargo/bin/ah` 是唯一一份，`find` 未发现其他）。tasks.md 说 1.4.0 附近行为「若需要也可测」，本机无法测，仅记 1.5.0。
- **采集者**: g1（泳道1 闸门），只读取证，未写任何生产代码。
- **采集环境**: 本机有一套**活跃编队**（就是本会话自己）。其 `state_dir = /root/.local/state/ah/f2647adf`（= 绝对黑名单，全程未碰）。所有观测均为只读，或在**私有 namespace 沙箱**里对隔离对象操作，活编队全程未受影响（每步都复核了 host 的 state dir 列表 + ahd PID 187284 存活 + 无残留进程）。

---

## 0. 结论速览（7 类证据 + 附加项）

| # | 证据类 | 结果 | 采集手段 |
|---|--------|------|----------|
| 1 | `ah start` 对已有 active stack 同 config 的拒绝行为 | ⚠️ **无法安全复现**（详见 §1，附已捕获的 start 错误路径） | — |
| 2 | F1：daemon-absent 下 `status`（无 JSON/exit1/stderr）vs `events`（结构化 `daemon_absent`） | ✅ **复现** | 私有 mount-ns 遮蔽 socket 路径 |
| 3 | F8：同 cwd 有 ah.toml、无 `--config` 时 status/ps/events 的解析差异 | ✅ **复现**（并对旧措辞提一处细化，见 §3） | 只读 |
| 4 | NF1：`--config` 回显击穿（config_path 被回显、state_dir/session 是活编队） | ✅ **复现** | 只读 |
| 5 | NF2：读面忽略 `AH_STATE_DIR` env clamp | ✅ **复现** | 只读 |
| 6 | 坑洞 3.2：`status` 恒为 sequence:1/initial；events 首帧 1/initial | ✅ **复现 + 细化**（events 流内 sequence 单调递增，见 §6） | 只读 |
| 7 | 一份真实 `degraded` 快照 + 一份 `starting` 快照 | ⚠️ **无法安全复现**（详见 §7，附 spec 已录得的 degraded 形状） | — |
| + | 附加：live **active** 全量快照（fixture 任务 1 的 active 样本） | ✅ **复现** | 只读 |
| + | 附加：`ah version` 裸版本 vs `ah --version`（Req 1.8） | ✅ **复现** | 只读 |

**一句话**：2/3/4/5/6 + 两个附加项成功复现；1 与 7 因 `ah start` 在本机（WSL + 活编队 + 共享 systemd-user）无法安全拉起独立真栈而**无法复现**，已给出 evidence-backed 原因，且 spec 自身（Req 3.4/5.8）本就把「1」标注为**待验证假设**。

---

## 关键横切发现：ahd 发现机制是「固定路径 socket 扫描」，与 `AH_STATE_DIR`/`HOME`/PID-ns 都无关

这是理解 NF1/NF2/F1 的底座，先记在前面。本机只有**一个** ahd 在跑（PID 187284，socket = `/root/.local/state/ah/f2647adf/ahd.sock`）。`ah status`/`ah events`/`ah ps` 的读面**总是**连上它，无论我怎么隔离：

| 隔离手段 | `ah status --json` 返回的 `state_dir` | 结论 |
|----------|----------------------------------------|------|
| `env AH_STATE_DIR=/tmp/<fresh empty>` | `/root/.local/state/ah/f2647adf` | 读面**忽略** AH_STATE_DIR（= NF2） |
| `env HOME=/tmp/<fresh empty>` | `/root/.local/state/ah/f2647adf` | 发现机制**不是** HOME 派生的 |
| `unshare --pid --fork --mount-proc`（私有 /proc，隐藏 host 进程） | `/root/.local/state/ah/f2647adf` | 发现机制**不是** /proc 扫描 |
| `unshare --mount` + `mount --bind <empty> /root/.local/state/ah`（遮蔽 state root） | daemon **absent** | 发现机制 = **扫描 `/root/.local/state/ah/*/ahd.sock` 固定路径** |

- 本机真实 `HOME=/root/.cache/ah/sandboxes/3d4e6e423263`，但 state root 却是 `/root/.local/state/ah/`——所以 state root 是按 passwd home（`/root`）或固定路径解析，**不吃 `$HOME` env**。
- 只有把 `/root/.local/state/ah` 这个目录本身遮蔽掉（私有 mount-ns bind 一个空目录），读面才拿不到活 daemon → 返回 daemon-absent。这就是 §2 复现 F1 的唯一安全办法。
- 附带发现：即使 state root 被遮空，`status` 的报错里仍点名 `…/f2647adf/ahd.sock`，说明**在 state root 之外还有一份 registry/pointer**记着「预期的 daemon」。未深挖具体位置（超出取证范围），但它解释了为什么 daemon-absent 快照里 `state_dir` 仍是 `f2647adf`。

> **对生产代码的含义（呼应 Req 4.7a/NF2）**：env clamp 完全不能作为读面 daemon 隔离手段——读面按固定路径找活 daemon。承重的读面隔离只能靠快照身份校验（Req 2.7/4.8）。本轮实测再次坐实这一点。

---

## 1. `ah start` 对已有 active stack 同 config 的拒绝 —— ⚠️ 无法安全复现

**目标**（Req 3.4 / 5.8 / task 6）：对一个已 active 的 stack 用同 config 再发 `ah start`，记录退出码/stderr/snapshot 形状。

**为什么无法安全复现（第一性原因，已实测坐实）**：

1. `ah start` 在 WSL 上**硬性要求 systemd user session**，在拉起 ahd 之前就 gate。实测（私有 namespace 内）：
   ```
   $ ah start --config <isolated>/ah.toml --wait
   WSL detected, but the systemd user session is not available. ah needs systemd
   user services/scopes. Enable systemd in WSL: add [boot] systemd=true ...
   START_EXIT=3
   ```
2. 这个 systemd user session 是**主机全局、且与活编队共享**的（binary strings 证实 ahd 跑在 systemd user scope `ahd.service` / slice `ahd-agents.slice` 下）。给第二套栈用它 → 会创建与活编队并存的全局 unit，可能干扰活编队 → **禁区**。
3. 唯一能保证「自动、干净拆除」的隔离（`unshare --pid --fork` PID namespace）会**切断** systemd-user 连接，于是 `ah start` 在里面直接 gate 失败（就是上面的 exit 3）。
4. 试过伪造容器身份绕过（私有 tmpfs `/run` + `/run/.containerenv`，host `/run` 全程未被碰）：`ah setup --check` 确实识别到「container hint present」，但 `ah start` 的 WSL-systemd gate **依然触发**、依然 exit 3。加 `--cgroup` 一起 unshare 也一样。ah 的 `should_skip_systemd_bootstrap_for_cgroup` 需要真实的容器 cgroup（`/proc/self/cgroup` 里有 docker/containerd），伪造不出来。

→ **在「本机（WSL）+ 有活编队 + systemd-user 主机共享」这三者叠加下，无法安全拉起一套独立 active 栈来观测重复 start 的拒绝行为。** 不编造数据。

**附：本轮真实捕获到的 `ah start` 错误路径**（对 task 2 版本门/错误诊断有用，但**不是**「重复 active 栈」那条）：

| 触发条件 | 退出码 | stderr（原文） |
|----------|--------|----------------|
| 非法 ah.toml（缺 `[agents.<id>]`） | `3` | `invalid ah.toml: TOML parse error … missing field 'agents'` |
| agents 表存在但为空（`agents = {}`） | `3` | `ah.toml must define at least one [agents.<id>]` |
| agent 缺 provider | `3` | `invalid ah.toml: TOML parse error … missing field 'provider'` |
| WSL 无 systemd-user | `3` | `WSL detected, but the systemd user session is not available. …` |

> **给 master 的建议**：spec 里 **Req 3.4** 原文已写明「依赖『ah start 对已活跃 stack 拒绝』这一**未验证假设**」，**Req 5.8** 要求「实现 3.4 前必须在真实 ah binary 上跑一遍并记录 exit/stderr/snapshot」。本条正是那个 pre-implementation 验证——结论是**在本机环境采不到**。task 6（Req 3.4）落地前，这份证据需要在一台「无活编队 + systemd-user 可用 / 或真容器」的干净机器上补齐，或走上游确认。当前不足以据此写 duplicate-start 的 fixture。

---

## 2. F1 — daemon-absent 下 status vs events 的差异 —— ✅ 复现

**手段（安全性说明）**：本机读面总连活编队（见横切发现），无法靠 env 得到 daemon-absent。用**私有 mount namespace** 把 `/root/.local/state/ah` bind 成一个空目录（只在 namespace 内生效，host 的该目录、活编队 socket/sqlite 的已打开 fd 全不受影响；namespace 退出即消失）。每次都复核了 host `/root/.local/state/ah` 前后一致、ahd 存活。

**2a. `ah status --json`（daemon absent）** → 退出码 **1**，**无 JSON**，stderr 为人读文本：
```
$ ah status --json      # (state root 被私有 ns 遮空)
ahd daemon is not running at /root/.local/state/ah/f2647adf/ahd.sock
Start it with: ah start
# exit=1  (stdout 上没有任何 JSON)
```

**2b. `ah events --format json`（同一 daemon-absent 情形）** → **结构化 `daemon_absent` 快照**（单行，此处美化）：
```json
{
  "schema_version": 2,
  "event": "snapshot",
  "sequence": 1,
  "reason": "daemon_absent",
  "runtime_state": "inactive",
  "config_path": "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/ah.toml",
  "workspace_path": "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl",
  "state_dir": "/root/.local/state/ah/f2647adf",
  "tmux_socket": null,
  "ahd_alive": false,
  "active": false,
  "ahd_has_inventory": false,
  "tmux_server_alive": false,
  "master_tmux_alive": false,
  "worker_tmux_alive": false,
  "worker_tmux_expected_count": 0,
  "sessions": [],
  "agents": [],
  "jobs": [],
  "job_events": [],
  "job_event_cursor": 0
}
```
（`events` 是流，读到首帧后被 `timeout` 终止，exit 124。）

**判定**：与 requirements.md Req 2.2 已录证据完全一致——`status` daemon-absent = exit1 + 人读 stderr + 无 JSON；`events` daemon-absent = 结构化 `{"reason":"daemon_absent","runtime_state":"inactive","ahd_alive":false,"active":false,…}`。生产代码**不得**嗅探 status 的 stderr，必须以 events 的 `daemon_absent` 结构化帧做决策（Req 2.3/5.11）。

> **fixture 注意**：本快照的 `config_path`/`state_dir` 仍是本 worktree/f2647adf（§横切发现里说的 registry 残留），并非一台从未起过 daemon 的纯净机器的值。**决策相关字段**（`reason:"daemon_absent"`、`runtime_state:"inactive"`、`ahd_alive:false`、`active:false`、`sessions:[]`、`agents:[]`）是**忠实**的；task 1 建 daemon-absent fixture 时可把 `config_path`/`state_dir` 换成中性/请求值，其余字段照抄。

---

## 3. F8 — 同 cwd 有 ah.toml、无 `--config` 时 status/ps/events 的解析 —— ✅ 复现（含一处细化）

在 `cwd=/tmp/ah-fixture-f8`（内含一个自造 `ah.toml`，**不是**活编队的 config）、**不带 `--config`** 下三条命令的解析结果：

| 命令 | `state_dir` | `config_path` | 解析对象 |
|------|-------------|---------------|----------|
| `ah status --json` | `/root/.local/state/ah/f2647adf` | **`null`** | 连活 daemon，报 daemon 自己的 config（null） |
| `ah ps` | （表格）显示 `sess_6ddea78e… / feat-studio-ah-state-contract-impl / ACTIVE` | — | 同样连活 daemon（**不理会** cwd 的本地 ah.toml） |
| `ah events --format json` | `/root/.local/state/ah/f2647adf` | **`/tmp/ah-fixture-f8/ah.toml`** | state 连活 daemon，但 `config_path` 回显 project-discovery 找到的**本地** ah.toml |

`ah ps`（无 --config，原样）：
```
sessions
| session_id                                | project_id                         | path                                                              | status | master_state | db_tracked_agents |
| sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28 | feat-studio-ah-state-contract-impl | /root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl | ACTIVE | IDLE         | 6                 |
```

**判定 + 对旧措辞的细化（请 master 过目，非改 spec）**：
- 核心事实**成立**：`status`/`ps` 与 `events` 用**不同的 config 解析路径**——前者连全局活 daemon 报 `config_path:null`，后者走 project discovery 把本地 `ah.toml` 回显进 `config_path`。两条读面对「当前 config 是谁」的回答**不一致**（null vs 本地路径）。这正是 Req 2.7/4.8 要求「必须显式做身份校验、不能信回显 config_path」的现实依据。
- **细化点**：requirements.md 第 108 行把这种分歧表述为「status/ps 落 **default state dir**、二者可能对『在说哪个 state dir』都不一致」。在**本机（只有一套活 daemon）**下，两条读面的 `state_dir` **其实一致**（都指向唯一在跑的 `f2647adf`），分歧体现在 **`config_path`**（null vs 本地发现路径），而不是 `state_dir`。机制（不同解析路径）与旧结论一致，只是「分歧落在哪个字段」取决于机器上有几套 daemon。**这不是矛盾，是同一机制在单-daemon 机器上的具体表现**；记此备 master 判断是否要微调 Req 4.8 的举例措辞。

---

## 4. NF1 — `--config` 身份回显击穿 —— ✅ 复现

`ah --config /tmp/ah-fixture-nf1/ah.toml events --format json` 首帧（`/tmp/ah-fixture-nf1` 是一个隔离的空项目，只有一个 minimal ah.toml，**绝非**活编队）：
```json
{
  "schema_version": 2, "sequence": 1, "reason": "initial",
  "runtime_state": "active", "active": true, "ahd_alive": true,
  "config_path": "/tmp/ah-fixture-nf1/ah.toml",          // ← 请求路径被原样回显
  "workspace_path": null,
  "state_dir": "/root/.local/state/ah/f2647adf",          // ← 却是活编队的 state dir
  "tmux_socket": "ahd-5a709091c406a3fa",
  "sessions": [{
    "session_id": "sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28",   // ← 活编队会话身份
    "project_id": "feat-studio-ah-state-contract-impl",
    "path": "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl",
    "status": "ACTIVE", "live_agents": 6, "db_tracked_agents": 6,
    "cleanup_required": false, "safe_to_cleanup": false, "master_tmux_alive": true
  }]
}
```

**判定**：`config_path` **匹配请求路径**（`/tmp/ah-fixture-nf1/ah.toml`），但 `state_dir` + `sessions[].session_id/path/project_id` 全是**另一套活 daemon** 的。→ 只看 `config_path` 的身份校验会**错误接受**这帧。这正是 NF1 击穿形态，坐实 Req 2.7/4.8/5.10(a)：身份必须以 `state_dir` + 会话身份为权威，`config_path` 只能当诊断。

**同时坐实 NF1 的第二半**：活 daemon 顶层 `config_path` **可为 `null`**——见 §附加 的 live `status --json`（顶层 `"config_path": null`）。即 `config_path` 既可能是 null（无鉴别力），又可能被 `--config` 原样回显（零鉴别力），两头都不能当身份依据。

---

## 5. NF2 — 读面忽略 `AH_STATE_DIR` env clamp —— ✅ 复现

```
$ env AH_STATE_DIR=/tmp/ah-fixture-nf2 ah status --json | grep state_dir
  "state_dir": "/root/.local/state/ah/f2647adf"      # ← 仍是活编队，不是 /tmp/ah-fixture-nf2
# 且 /tmp/ah-fixture-nf2 里没被创建任何东西（读命令没落盘）

$ env AH_STATE_DIR=/tmp/ah-fixture-nf2b ah events --format json   # 首帧
  "state_dir": "/root/.local/state/ah/f2647adf"      # ← events 读面同样忽略
  "config_path": "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/ah.toml"
```

**判定**：把 `AH_STATE_DIR` 指向一个全新空目录，`status` 与 `events` 的读面**都仍返回活编队的 `state_dir`**，且未在该目录落任何盘。→ 坐实 Req 4.7a：env clamp **不**保证 1.5.0 读面连哪套 daemon，只能防「写面互相污染 state dir」；读面隔离承重责任在身份校验（Req 2.7/4.8），不在 clamp。

---

## 6. 坑洞 3.2 — sequence 语义 —— ✅ 复现 + 细化

**6a. `ah status --json`（one-shot）恒为 `sequence:1 / reason:"initial"`**（连测 4 次）：
```
call 1: sequence=1 reason='initial' runtime_state='active' active=True
call 2: sequence=1 reason='initial' runtime_state='active' active=True
call 3: sequence=1 reason='initial' runtime_state='active' active=True
call 4: sequence=1 reason='initial' runtime_state='active' active=True
```

**6b. `ah events --format json` 首帧同为 `sequence:1 / reason:"initial"`，但流内 sequence 单调递增**（同一订阅流内实录 311 帧）：
```
frame 1:   sequence=1   reason='initial'         runtime_state='active'
frame 2:   sequence=2   reason='tmux_changed'    runtime_state='active'
frame 3:   sequence=3   reason='job_changed'     runtime_state='active'
…
frame 311: sequence=311 reason='job_changed'     runtime_state='active'
```

**判定 + 细化（比旧「恒为 1」更精确，且不矛盾）**：
- `status` one-shot：**每次都是全新 baseline** `sequence:1/reason:"initial"` ✅（= 坑洞 3.2 断言）。
- `events` 流：**首帧** `sequence:1/reason:"initial"` ✅，之后在**同一订阅流内 sequence 单调递增**（2,3,…,311），`reason` 转为 `job_changed`/`tmux_changed`。
- requirements.md 第 50 行的表述是「`status` 每次 1/initial、`events` **首帧**为 1/initial」——本实测与之**完全一致**，只是额外坐实了「流内会递增」这一点。这恰好印证 Req 2.1 的设计承重逻辑：`sequence` 是**每流的 baseline 计数器**，不是跨流/跨 daemon 生命周期的全局单调值——每次新订阅 / 每次 one-shot `status` / daemon 重启都重置回 1。因此生产代码遇到 `reason:"initial"` / 新订阅 / `session_id` 变化时必须**无条件重置** applied-sequence 缓存，只在同一流内用旧序号挡新帧（Req 2.1 / 5.13）。天真的全局 max 会让某条旧流的高 sequence 永久挡掉 post-close/post-restart 的新帧。

---

## 7. 一份真实 `degraded` + 一份 `starting` 快照 —— ⚠️ 无法安全复现

**为什么无法复现**：与 §1 同根——要得到 `starting`/`degraded` 相位，必须**真的拉起一套栈**再把它驱入这些状态（starting = 启动中；degraded = master tmux 死但 session/agents 还在）。本机 `ah start` 因 WSL systemd-user gate + 活编队共享 systemd 而无法安全拉起独立真栈（详见 §1）。因此这两种相位快照**采不到**。不编造。

**可复现的两个端点**（已在本文件其他节给出，供 fixture 参考）：
- `inactive` / daemon-absent（§2b）。
- `active` 全量（§附加）。

**spec 已录得的 `degraded` 形状**（来自 requirements.md 第 82 行 Req 3.7，非本轮采集，转录备 task 1）：
> real snapshot observed: `active:false, runtime_state:"degraded"`，one session `status:"ACTIVE"` with `live_agents=10`, dead master tmux, `cleanup_required:true`。

> **给 master 的建议**：task 1 的 `starting`/`degraded` fixture（Req 3.6/3.7/5.6/5.7）目前只能**基于 spec 转录的 degraded 形状 + 对 schema_version:2 字段的推断**来构造，缺一份本机独立实采。若要一份「真采」的 degraded/starting，需要在一台能安全 `ah start`（无活编队 / systemd-user 可用 / 真容器）的机器上补。当前 fixture 若照 spec 形状写，务必标注「来源 = spec 转录，未经本机 CLI 独立复采」。

---

## 附加 A. live **active** 全量快照（fixture 任务 1 的 active 样本，schema_version:2）

`ah status --json`（连本机活编队；job_events/jobs 噪声已裁掉，其余原样）：
```json
{
  "active": true,
  "ahd_alive": true,
  "ahd_has_inventory": true,
  "config_path": null,
  "event": "snapshot",
  "master_tmux_alive": true,
  "reason": "initial",
  "runtime_state": "active",
  "schema_version": 2,
  "sequence": 1,
  "state_dir": "/root/.local/state/ah/f2647adf",
  "tmux_socket": "ahd-5a709091c406a3fa",
  "tmux_server_alive": true,
  "worker_tmux_alive": true,
  "worker_tmux_expected_count": 6,
  "workspace_path": null,
  "agents": [
    {"agent_id":"d1","provider":"claude","state":"IDLE","sub_state":"LogEvent","tmux_alive":true,"tmux_session":"agent_d1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901582},
    {"agent_id":"g1","provider":"claude","state":"BUSY","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901703},
    {"agent_id":"g1-m1","provider":"antigravity","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g1-m1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901787},
    {"agent_id":"g2","provider":"claude","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g2","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901859},
    {"agent_id":"g2-m1","provider":"antigravity","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g2-m1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901922},
    {"agent_id":"o1","provider":"antigravity","state":"WAITING_FOR_ACK","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_o1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":903125}
  ],
  "sessions": [
    {
      "session_id": "sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28",
      "project_id": "feat-studio-ah-state-contract-impl",
      "path": "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl",
      "status": "ACTIVE",
      "master_state": "BUSY",
      "master_tmux_session": "master_feat-studio-ah-state-contract-impl",
      "master_tmux_alive": true,
      "master_pane_id": "%0",
      "master_pid": 187349,
      "master_last_exit_reason": null,
      "db_tracked_agents": 6,
      "live_agents": 6,
      "cleanup_required": false,
      "safe_to_cleanup": false
    }
  ]
}
```
**给 task 1 的字段清单确认**（schema_version:2 真实字段，全部实见，非 README 示例）：顶层 `schema_version / event / sequence / reason / runtime_state / active / ahd_alive / ahd_has_inventory / config_path(可 null) / workspace_path(可 null) / state_dir / tmux_socket(可 null) / tmux_server_alive / master_tmux_alive / worker_tmux_alive / worker_tmux_expected_count`；`sessions[]`：`session_id / project_id / path / status / master_state / master_tmux_session / master_tmux_alive / master_pane_id / master_pid / master_last_exit_reason / db_tracked_agents / live_agents / cleanup_required / safe_to_cleanup`；`agents[]`：`agent_id / provider / state / sub_state / tmux_alive / tmux_session / session_id / pid`。（daemon-absent 帧另有 `job_event_cursor`，值 0。）

> 注意：design.md 里模型用 camelCase（`ahdAlive`/`liveAgents`/…），CLI 实出 **snake_case**（`ahd_alive`/`live_agents`/…）。typed parser 做 snake→camel 映射时以 CLI 的 snake_case 为真源。

## 附加 B. `ah version` 裸版本 vs `ah --version`（Req 1.8）

```
$ ah version        →  1.5.0        (裸版本号 + 换行，无前缀)   exit 0
$ ah --version      →  ah 1.5.0     (带 "ah " 前缀，需取第二 token)   exit 0
```
**判定**：坐实 Req 1.8——`ah version` 直接给裸版本号，`trim` 即可；无需再解析 `ah --version` 的第二 token。全代码库统一到 `ah version` + `trim` 一条规则即可。

---

## 附：与已录 spec 证据的对账

- NF1（Req 2.7/5.10a）、NF2（Req 4.7a）、坑洞 3.2（Req 2.1）、F1（Req 2.2/2.3）、F8（Req 4.8）、Req 1.8：**均复现一致**，无冲突。
- 唯一提请 master 注意的**细化**（非矛盾）：F8 在**单-daemon 机器**上，status/ps 与 events 的分歧落在 `config_path`（null vs 项目发现路径）而非 `state_dir`（本机两者都是唯一活 daemon `f2647adf`）。见 §3。
- 两处**采集缺口**（因 `ah start` 无法安全在本机拉真栈）：evidence 1（duplicate-start 拒绝，Req 3.4/5.8 本就标注为未验证假设）与 evidence 7（degraded/starting 真采）。见 §1、§7。

## 附：采集手段与安全复核

- 只读命令：`ah version` / `ah --version` / `ah status --json` / `ah ps` / `ah events --format json`（读首帧即 `timeout` 终止）/ `ah ping` / `ah doctor` / `ah config validate` / `ah *_--help`。
- 隔离沙箱：`unshare --pid --fork --mount --mount-proc [--cgroup]` + `mount --bind <空目录> /root/.local/state/ah`（私有传播，host 不受影响）+ 私有 `HOME`/`TMUX_TMPDIR` + 伪造 `/run/.containerenv`（私有 tmpfs）。fixture 临时目录一律在 `/tmp/ah-*`，用完 `rm -rf`。
- **每一步都复核**：host `/root/.local/state/ah/` 目录列表（始终 `default e7d62924 f2647adf` 不变）、活编队 ahd PID 187284 存活、host `/run/.containerenv` 始终不存在、无残留 sandbox 进程。活编队（本会话自己）全程零生命周期操作。
