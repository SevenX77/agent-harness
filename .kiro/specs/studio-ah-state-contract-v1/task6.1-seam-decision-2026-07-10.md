# 任务 6.1 决策档案:events-primary 决策面接入活路径的架构裁决(架构 A)

- **整理人**:g1-claude(泳道1 gatekeeper / 验收测试执笔),受 master 委托把前一个
  g1 实例的物理核实 + master 的四条裁决整理成 g2 实施的权威依据。
- **日期**:2026-07-10
- **上游依据**:`task6-wiring-gap-finding-2026-07-10.md`(master 亲验的接线缺口)、
  `task6-cross-lane-review-2026-07-10.md` §五(承重 scope 提示)、`tasks.md` 任务 6.1。
- **性质**:本档案只做决策记录 + 测试契约,不含生产代码;实施(切活路径、删旧路径)
  由 g2 按本档案 + 任务 6.1 条目落地。

---

## 一、问题复述(为什么要开这个收尾单)

任务 3/4/6 建起了一整套 **typed 决策面**,但它至今**只被单元测试消费,零生产调用点**。
用户在 shipping UI 上点 Open/Attach 时,真正跑的仍是**老布尔面**(解析 `ah ps` 文本 +
探测 tmux),直接违反 design.md 明令。这是「先建缝、测试锚定、后接线」增量策略留下的、
本该由后续单闭合的接线 gap——不是任务 6 实现的缺陷(见 cross-lane-review §五 裁定)。

**设计权威(必须遵守,原样引文)**:
- `design.md:27`:"Remove `ah ps` text parsing and tmux liveness probing from normal
  status decisions."
- `design.md:178`:"Never use `ah ps` text or tmux probing for normal lifecycle
  decisions."
- `design.md:325`:"Open decision uses the events-primary/status-fallback plane, not
  `ah ps`."

---

## 二、物理核实:逐函数生产/测试调用点表(前一个 g1 实例翻遍 lib.rs,本实例已复核)

核实基准:`#[cfg(test)] mod tests` 起于 **lib.rs:3413**;此行以下的调用一律记为 test,
以上记为 PROD。行号为本会话核实时的实际值(lib.rs 共 5427 行)。

### 2.1 typed 决策面(任务 3/4/6 新建,全部只被测试消费)

| 符号 | 定义处 | 生产调用点 | 测试调用点 |
|---|---|---|---|
| `struct AhRuntimeSnapshot` | lib.rs:3228 | **0** | 单测 fixture 解析 |
| `fn parse_ah_runtime_snapshot` | lib.rs:3246 | **0** | 4155/4162/… 等 |
| `fn reconcile_snapshot_lifecycle` | lib.rs:3272 | **0** | 4157/4164/4360/4426 |
| `fn assistant_status_for_runtime_state` | lib.rs:3285 | **0** | 4380 |
| `struct SequenceArbiter` | lib.rs:3295 | **0** | 4193/4211/… |
| `fn resolve_bootstrap_snapshot` | lib.rs:3342 | **0** | 仅测试 |
| `fn verify_snapshot_identity` | lib.rs:3356 | **0** | 仅测试 |

**结论:typed 面生产侧调用点合计 = 0。** 全部只在 lib.rs:3413 之后的 `#[cfg(test)]` 模块里
被直接构造 fixture 调用。

### 2.2 老布尔面(当前真正在跑的生产路径)

| 符号 | 定义处 | 关键生产调用点 |
|---|---|---|
| `fn inspect_ah_runtime`(跑 `ah ps` 文本解析 + tmux 探测) | lib.rs:1157 | `prepare_code_assistant_open`(2549、2561);`attach_code_assistant_terminal`(2635);`force_cleanup_ah_runtime`(1193 内) |
| `struct AhLifecycleSnapshot`(布尔三元组) | lib.rs:445 | `inspect_ah_runtime` 产出;`status_snapshots` 缓存类型(141) |
| `fn code_assistant_lifecycle_is_active` | lib.rs:497 | `reconcile_code_assistant_lifecycle`(504);`prepare_code_assistant_open`(2584) |
| `fn reconcile_code_assistant_lifecycle` | lib.rs:501 | `attach_code_assistant_terminal`(2636) |
| `fn decide_code_assistant_open` | lib.rs:534 | **`prepare_code_assistant_open`(2572)** ← Open 按钮真正走这里 |

### 2.3 events 订阅流 / 状态缓存 / UI 投影(同样全是老布尔面)

- `start_code_assistant_status_stream`(lib.rs:1513 起):后台订阅 `ah events`,但产出喂进
  `status_snapshots` 缓存,**只驱动 UI 状态显示**——该函数自己的注释(lib.rs:1492)明写
  "Snapshots only drive the status display."
- 状态缓存 `status_snapshots`:类型是 `Mutex<BTreeMap<PathBuf, AhLifecycleSnapshot>>`
  (**lib.rs:141**)——布尔面,不含 `runtime_state` 相位。
- UI 投影 `code_assistant_status_from_snapshots`(lib.rs:1390):吃
  `BTreeMap<PathBuf, AhLifecycleSnapshot>`,同样是布尔面。

**一句话真相**:events 流拿到的结构化快照被塌成布尔存进缓存;三个真实生命周期入口
(Open/Attach/Close)各自另起炉灶跑 `inspect_ah_runtime`(`ah ps`),谁也不读 typed 面。

---

## 三、master 裁决(四条,g2 按此实施,不再重新讨论)

### 裁决 1 — 架构 A:events 流成为 typed 单一真相源,缓存改 typed

1. events 订阅流(`start_code_assistant_status_stream`)把每行解析为
   `AhRuntimeSnapshot`(`parse_ah_runtime_snapshot`),不再塌成布尔。
2. 状态缓存 `status_snapshots` 的类型从
   `BTreeMap<PathBuf, AhLifecycleSnapshot>` 改为
   **`BTreeMap<PathBuf, AhRuntimeSnapshot>`**(lib.rs:141;连带 1375/1390/1441 等
   吃该类型的函数一起改)。
3. UI 投影改用 `assistant_status_for_runtime_state`(按 `runtime_state` 相位投影)。
4. `prepare_code_assistant_open` / `attach_code_assistant_terminal` 两个入口
   **读缓存里最新的 identity-checked 快照**;缓存无帧(尚无 events 结果)时走
   `resolve_bootstrap_snapshot` + `status --json` fallback + `verify_snapshot_identity`
   校验身份后再决策(按 design.md:92-158 的 sequence graph)。

### 裁决 2 — 新增 open 决策函数(替代 `decide_code_assistant_open`)

- **建议名**:`decide_code_assistant_open_v2`(名字 g2 可定,本档案与 RED 测试统一用此名)。
- **建议签名**:
  ```rust
  fn decide_code_assistant_open_v2(
      requested: Option<&AhRuntimeSnapshot>,
      others: &[AhRuntimeSnapshot],
  ) -> CodeAssistantOpenDecision
  ```
- **输出复用既有枚举** `CodeAssistantOpenDecision`(lib.rs:471),相位→决策映射:
  | requested 的 `runtime_state` | open 决策 | 语义 |
  |---|---|---|
  | `Active` | `AttachRequested` | 附着既有 runtime |
  | `Inactive` | `StartFresh` | session 全终态,可启动 |
  | `Degraded`(`cleanup_required`) | `CleanupStale` | 先清理再 StartFresh(Open 保持可用) |
  | `Starting` | **`HandsOff`(新增变体)** | 启动进行中,不重复发起 start、不清理、不报错 |
- **枚举扩展**:`CodeAssistantOpenDecision` 现有四变体
  `StartFresh / AttachRequested / RejectOtherActive / CleanupStale`,**没有** hands-off 出口。
  按裁决须**新增第五变体** `HandsOff`,语义对齐 `CodeAssistantLifecycleAction::HandsOff`
  (lib.rs:467)——「starting 期间 Open 也不该重复发起 start」。`prepare_code_assistant_open`
  的 `match` 须为该变体补一条不发任何生命周期命令的臂(参照
  `attach_code_assistant_terminal` 现有 `HandsOff` 臂 lib.rs:2648「仍在启动,先等启动完成」)。
- **跨 assistant 仲裁(`RejectOtherActive`)照抄** `decide_code_assistant_open`
  (lib.rs:534-566)对 `others` 的处理逻辑,**唯一改动**:判定「其它 assistant 是否 active」
  的判据从布尔 `code_assistant_lifecycle_is_active` 换成**新快照的 `runtime_state == Active`**
  (等价地:对 `others` 逐个 `reconcile_snapshot_lifecycle`,数 `AttachExisting` 的个数)。
  - 已 fix 的活路径对照点:老函数 `decide_code_assistant_open(Some(active), &[active])`
    = `CleanupStale`;`(Some(inactive), &[active])` = `RejectOtherActive`——v2 须保持等价。

### 裁决 3 — `force_cleanup_ah_runtime` 不在本单范围内

归**任务 7**(Close/quit)处理,本单不动它(含它对 `kill_tmux_session` 的直接调用——
那条 design.md:227 违规由任务 7 一并修)。本单只切 Open/Attach 两个入口的决策输入。

> 注:任务 6.1 条目正文把 `force_cleanup_ah_runtime` 也列进切换范围;master 本次裁决
> **收窄**为「本单只切 Open/Attach,Close/quit 归任务 7」,以裁决 3 为准。g2 实施与
> gatekeeper 验收都按本收窄范围执行,避免与任务 7 重复实现。

### 裁决 4 — 编译期 RED 是预期中间态

RED 测试引用尚未建的 `decide_code_assistant_open_v2` 与
`CodeAssistantOpenDecision::HandsOff`,会让整套 `cargo test --lib` 暂时**编译不过(全红)**。
这是标准 TDD 的编译期红灯,**不是问题**;g2 实现新函数 + 新变体后自然变绿。因此本阶段
不做运行期回滚自检(树尚不可编译);回滚自检是 gatekeeper 后续审 g2 GREEN diff 时的动作。

---

## 四、RED 测试契约(本单交付,加在 lib.rs `#[cfg(test)] mod tests` 内)

锚定原则:断言的是**决策函数在契约边界的可观测返回值**——该返回值正是
`prepare_code_assistant_open` 的 `match` 消费的输入,驱动 attach / start / cleanup / reject
四条真实分支,属契约边界行为,非实现内部状态。fixture 复用任务 1 冻结的真实快照
(`SNAPSHOT_ACTIVE` / `SNAPSHOT_INACTIVE` / `SNAPSHOT_DEGRADED` / `SNAPSHOT_STARTING` /
`SNAPSHOT_ACTIVE_CODEX`),不新造。

1. **`test_open_decision_v2_maps_requested_phase`**(仿
   `test_starting_is_hands_off` + `test_degraded_exposes_working_open`):
   单 runtime(`others` 为空)下四相位映射——
   `Active→AttachRequested`、`Inactive→StartFresh`、`Degraded→CleanupStale`、
   `Starting→HandsOff`;starting 分支用 `assert_ne!` 逐一排除
   `StartFresh/AttachRequested/CleanupStale/RejectOtherActive`(证明是独立无动作出口);
   并以 `assert_ne!` 控制项证明四相位输出彼此不同(genuine projection,非常量)。
2. **`test_open_decision_v2_arbitrates_other_active_runtime`**(仿
   `open_decision_enforces_single_ahd_per_workspace`):
   跨 assistant 仲裁——`(Some(inactive), &[active])→RejectOtherActive`、
   `(Some(active), &[active])→CleanupStale`(single-ahd 护栏),与老 `decide_code_assistant_open`
   等价行为对齐。

**范围说明(测试执笔侧诚实标注)**:master 裁决明确固定的是「requested 的四相位映射」
与「inactive/active + 其它 active 的两条仲裁」。「requested 本身为 `Starting` 且其它
assistant active」这一组合,master 未单独裁定(hands-off「无动作」与照抄的
`RejectOtherActive` 存在语义张力),故**不写进硬断言**、留给 g2 实现;若实施期就此产生
契约疑问,按泳道纪律由 gatekeeper(本人)终裁,不上升 master。

---

## 五、g2 实施后的验收锚点(供后续 gatekeeper 审 GREEN diff 用)

- 两条新 RED 测试变绿,且任务 6 既有两测试(`test_starting_is_hands_off` /
  `test_degraded_exposes_working_open`)继续绿。
- **接线证据(任务 6.1 条目要求)**:`decide_code_assistant_open`(旧)、
  `reconcile_code_assistant_lifecycle`、`AhLifecycleSnapshot` 等旧路径被**编译期删除**——
  删不掉即编译报错,即为「活路径已真正改吃 typed 面」的物理证据(无向后兼容,不得双轨)。
- `status_snapshots` 缓存类型已是 `BTreeMap<PathBuf, AhRuntimeSnapshot>`,UI 投影经
  `assistant_status_for_runtime_state`。
- `force_cleanup_ah_runtime` 未被本单改动(归任务 7)。
- CI:Tauri `cargo test --lib` 全绿(除本沙箱既有 root 环境例外
  `native_fs::tests::publish_package_writer_maps_permission_error`,与本改动无关)。
