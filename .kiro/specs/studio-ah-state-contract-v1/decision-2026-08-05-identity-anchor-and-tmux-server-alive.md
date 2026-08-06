# 决议 2026-08-05 — 身份校验的锚点必须是请求方能预测的字段 + ah `tmux_server_alive` 假报

> 本文件是 2026-08-05 补测轮（用户指令："把没实测的都补上"）挖出的两个缺陷的处置落盘件。
> 它修订 `requirements.md` Req 2.7 与 `design.md` 中「stateDir 为权威身份字段」的表述，
> 不修订该 spec 的其余部分。前序：`decision-2026-08-03-status-stream-ownership.md`。

## 一、缺陷 D：恒假的 state_dir 前置门把 bootstrap 整条路杀死

### 1. 现象（补测直接观测）

运行时活着、`ah status --json` 退出 0、两条道（status / events）的身份字段完全一致
（`project_id=exp-a-round3`、`path=/mnt/d/coding/skills/exp-a-round3`、
`state_dir=/root/.local/state/ah/9cc1e7dd`、`schema_version=2`），但 Studio 的
`bootstrap-seeded` 计数恒为 **0**——每一次冷启动播种都落到 `bootstrap-empty`。

### 2. 根因（代码 + 实测）

`verify_snapshot_identity`（`lib.rs`）在 session 身份检查**之前**有一道前置门：

```rust
let is_state_dir_under_workspace = state_dir_wsl_path.starts_with(requested_wsl_path)
    || state_dir_wsl.contains(&requested_wsl);
let is_state_dir_matching_hash = state_dir_wsl.contains(&hash);
if !is_state_dir_under_workspace && !is_state_dir_matching_hash { return Err(...) }
```

它要求 ah 的 `state_dir` 要么位于工作区目录之下，要么包含 Studio 的 16 位 workspace
hash。而实测的 `state_dir` 是 `/root/.local/state/ah/9cc1e7dd`——ah 用**自己的内部算法**
从 **config 路径**派生的 8 位 hash，与工作区路径无关，与 Studio 的 hash 也无关。
**两个条件恒假 ⇒ 这道门恒 `Err` ⇒ `resolve_open_snapshot` 的 bootstrap 分支恒返回 None。**

由它连带死掉的路径：

- D-C4 的 `bootstrap-seeded` 播种（本轮观测证实：运行时活着仍报 `bootstrap-empty`）；
- `close_code_assistant` 里 `ah kill --session --force` 的升级——`resolve_cleanup_snapshot`
  走同一条 `resolve_open_snapshot`，拿不到快照就永远选不出 kill 目标；
- Open/Attach 在无缓存帧的冷窗口拿不到运行时信息，退化成 start-fresh 判断。

UI 状态呈现不受影响：events 那条道不经过身份校验（per-config 流天然限定了对象）。

**为什么测试没拦住**：task 3 的身份测试喂的是 `SchemaDerived` fixture——按（错误的）
预期**构造**出来的 `state_dir`，而不是逐字捕获的真实形状。fixture 模块自己的 provenance
纪律（"Do not present as measured"）警告过这类风险；这次是"校验的全部价值取决于真实
形状"的场景用了构造数据，于是实现和测试共享同一个错误假设，互相印证了七个星期。

### 3. 第一性原理

**验证 = 比较预期与观察。请求方无法独立形成预期的字段，不能充当验证条件。**

Studio 能预测的：工作区路径（可规范化为 WSL 形式）、它的 basename（= `project_id`）。
Studio 不能预测的：ah 的 `state_dir`——要预测它就得复刻 ah 的内部 hash 算法，那是
向 core 泄漏 provider 内部实现（violates 稳定依赖/Port-Adapter），ah 换算法 Studio
静默坏掉。所以这道门不是"写错了的检查"，是**不可能写对的检查**。

### 4. 决定

#### D-D1：身份锚点 = `sessions[].path` + `project_id`；`state_dir` 降为诊断信息

删除 state_dir 前置门。身份校验只保留（并保持）session 检查：至少一个 session 的
规范化 `path` 等于请求工作区的 WSL 形式、且 `project_id` 等于工作区 basename。
这两个字段正是设计自己列名的身份字段，且都是请求方可预测、可跨 Windows↔WSL 规范化的。
`state_dir` 与 `config_path` 同级：advisory，只进诊断文本，不进判定。

`requirements.md` Req 2.7 与 `design.md` 中「identity is validated on `stateDir` +
session identity」的表述据此修订：**requester 侧的判定锚只有 session 身份**；
`stateDir` 的"权威"仅指它在 ah 侧标识运行时实例，不构成请求方可用的校验锚。

#### D-D2：空 `sessions` = 无证据，不是反证——接受

快照 `sessions` 为空时无从做 session 检查。接受它（维持既有的 vacuous-accept 语义），
理由是消费者动作矩阵：open 决策拿到空会话的 inactive 快照 → StartFresh（本来就该如此）；
kill 升级拿到空列表 → 无目标可杀（无害）。NF1 echo 那类"错 daemon"威胁由非空 sessions
的路径不匹配拦截；空 sessions 的快照对两个消费者都天然无害。

**被否决的替代项**：拒绝空 sessions。下游效果与接受完全相同（`resolve_open_snapshot`
返回 None 同样导致 start-fresh / 无 kill 目标），却把"ah 如实说没有会话"这句真话
标成身份不符——用错误的语义换来相同的行为，不做。

#### D-D3：身份测试必须以逐字捕获的快照为准

新测试喂 `SNAPSHOT_AHD_ALIVE_TMUX_GONE`（2026-08-04 逐字捕获，`state_dir` 是真实的
ah 内部 hash 形状）：对它自己的工作区必须通过（修复前 RED——被恒假门拒绝），对别的
工作区必须以 session 不匹配拒绝。旧的 SchemaDerived 身份 fixture 里为满足错误预期而
构造的 state_dir 期望一并清除。

### 5. 验收判据（缺陷 D）

| # | 判据 | 验证方式 |
|---|---|---|
| D-1 | 逐字捕获快照 + 它自己的工作区 → 身份校验通过 | Rust 单测（修复前 RED） |
| D-2 | 同一快照 + 别的工作区 → 以 session 不匹配拒绝 | Rust 单测 |
| D-3 | 空 sessions 快照 → 接受（修复前同样被恒假门拒绝，RED） | Rust 单测 |
| D-4 | 真机：运行时活着时切走再切回工作区，日志出现 `bootstrap-seeded` ≥ 1 | 操作者实测（合并后） |

## 二、缺陷 E：ah `tmux_server_alive` 在残留存在时报 false（→ ah#53）

### 1. 现象（1.14.1 实测）

SIGKILL master 窗格进程后，同一个 socket `ahd-2a2eae589bf4d78e` 上：

- `tmux list-panes -a` → `master_exp-a-round3 dead=1`——server **活着**，
  `remain-on-exit` 的取证死窗格在；
- `ah events` 首帧 → `runtime_state=inactive ahd_alive=true tmux_server_alive=false`。

报告与现实矛盾。对照：1.8.2 上 `/exit`（干净路径）整台 server 被回收，两侧一致；
矛盾只出现在异常死亡路径。

### 2. 处置

- **ah 侧**：已提 [ah#53](https://github.com/SevenX77/ah/issues/53)。要求二选一并写明契约：
  `tmux_server_alive` 按快照时刻对运行时自己的 socket 探测取真值（首选——保住
  `remain-on-exit` 特意留下的取证窗格）；或者异常死亡路径真的把 server 回收掉，让字段
  按构造为真。证据留着、又宣布证据所在的容器不存在，两头都不占。
- **Studio 侧**：判据不动。#589 的取舍仍成立——`ahd_alive` 是过报（把 4 份无物可关的
  config 说成"运行中"、堵死 Open），`tmux_server_alive` 是漏报（用户只是少看一屏，Open
  的启动前清理仍按 `ahd_alive` 把残留清掉）。漏报的代价严格小于过报。Studio 自行探测
  tmux 是设计明令禁止的（design.md:27/178），不开这个口子。
- **依赖标注**：`lingering` 相位与 #591 的 attach-dead-pane 行为，可达性依赖 ah#53 修复；
  台账 T3-12 已标注。ah 修复后的验收步骤写在 issue 里（kill master 窗格 → 面板呈现
  lingering → attach 见最后一屏 → Close 回收）。

## 三、范围边界

不改 ah 仓任何代码；不改 UI 投影判据；不动 app 退出时的全量清扫语义（
`discover_studio_ah_configs()` 会杀掉其它工作区仍在跑的会话——独立隐患，另案待用户裁决）。
