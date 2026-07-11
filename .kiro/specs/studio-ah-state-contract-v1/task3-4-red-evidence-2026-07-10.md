# task3(剩余)+ task4 RED 证据(机器验证)— 2026-07-10

任务 3 与任务 4 是**同一批**(tasks.md:57/66「须与任务 X 同批落地」):task3 的 typed
parser + 快照决策面,离开 task4 的 events-primary + sequence 仲裁没有意义;task3 单独落地
会把 `status` 留成中间决策面(spec 禁止)。故本单把 task3 剩余范围 + task4 全部写成一批红,
只写测试、不写生产代码(typed parser / 决策函数 / 仲裁器本体是 g1-m1 的活)。

本次在 worktree 用 `RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo` 真跑
`cargo test --lib`,记录实际 RED。

- worktree 分支:`feat/studio-ah-state-contract-impl`
- 工具链:`cargo 1.96.1`(与 task2/task3 证据同机同链)
- 命令:`cd apps/studio/tauri && cargo test --lib --no-run`
- 基线核对(真跑,非缓存):加测试**前**先 `git stash push -- apps/studio/tauri/src/lib.rs`
  只回退 lib.rs(**绝不碰 ah.toml**——它是 operator 本机注入,始终保持 `M`),再
  `cargo test --lib --no-run` → 真编译(`Compiling skill-studio-tauri ... / Finished ... in
  1.65s / Executable unittests src/lib.rs`),exit 0、干净编译。随后 `git stash pop` 恢复本单
  测试。证明本次 RED **唯一归因**于新加测试引用的缺失 seam,而非既有代码破坏。

## 五条新测试(全部复用任务 1 已冻结 fixture,不新造、不改 fixture)

task3 剩余(tasks.md:57-63):

- `test_typed_snapshot_parser_projects_phase_sessions_and_health`(Req 2.4→2.5/3.5/3.8):
  用 `SNAPSHOT_ACTIVE`/`SNAPSHOT_STARTING`/`SNAPSHOT_DEGRADED`/`SNAPSHOT_TERMINAL_CLOSED`/
  `SNAPSHOT_UNSUPPORTED_SCHEMA`,断言 typed parser 正确产出 `active`/`runtime_state`(typed
  phase 枚举)/session 列表/master-worker health;**unsupported schema 必须 Err,不得默认放行**。
  断言 `live_agents==10`(锁死 design F8「是 live_agents 不是 active_agents」)。
- `test_decision_plane_consumes_typed_snapshot_not_ps_text`(tasks.md:63):新决策函数
  `reconcile_snapshot_lifecycle(&AhRuntimeSnapshot)` 签名只吃 typed snapshot,**结构上无法**
  再依赖 `ah_ps_output_has_inventory`/`extract_ah_session_ids` 或 tmux 探测;active→AttachExisting、
  terminal→StartFresh,两态相异做常量控制。

task4(tasks.md:67,函数名按 spec 原样):

- `test_sequence_reset_on_reason_initial`(Req 2.1/5.13):流内升到 seq3 后,`reason:"initial"`/
  `sequence:1` 帧**无条件重置并应用**——同 session(`SEQUENCE_RESET_FRAME_SAME_SESSION`,更新态
  已 CLOSED)与变更 session(`SEQUENCE_RESET_FRAME_NEW_SESSION`)两分支。naive 全局 max-guard
  (1≤3 丢弃)会红。
- `test_sequence_guard_within_stream`(Req 5.13 后半):同一未变流内真正的旧序号
  (`SEQUENCE_STREAM_FRAMES[1]`,seq2/reason:"tmux_changed")仍被丢弃——重置测试的控制。
- `test_daemon_absent_prefers_events_over_status_stderr`(Req 5.11):`status --json` 非结构化失败
  (`Err(stderr)`)时,结构化 events `daemon_absent` 快照(`SNAPSHOT_DAEMON_ABSENT`)优先于 stderr
  被当权威错误态;控制用 `SNAPSHOT_INACTIVE`(ahd_alive:true)证明仲裁器转发真实 events 内容、
  非硬编码 daemon_absent 常量。

## RED(编译期,E0425/E0433)— 真实终端输出(节选)

六个生产 seam 尚不存在,整个 lib-test 目标编译失败 **18** 条错误,全部命中新 seam:

```
error[E0425]: cannot find type `AhRuntimeSnapshot` in this scope
    --> src/lib.rs:3841:47
error[E0425]: cannot find function `parse_ah_runtime_snapshot` in this scope
    --> src/lib.rs:3842:9
error[E0433]: cannot find type `AhRuntimeState` in this scope
    --> src/lib.rs:3862:42
error[E0425]: cannot find function `parse_ah_runtime_snapshot` in this scope
    --> src/lib.rs:3914:27
error[E0425]: cannot find function `reconcile_snapshot_lifecycle` in this scope
    --> src/lib.rs:3938:13
error[E0433]: cannot find type `SequenceArbiter` in this scope
    --> src/lib.rs:3974:23
error[E0425]: cannot find function `resolve_bootstrap_snapshot` in this scope
    --> src/lib.rs:4065:24
...
error: could not compile `skill-studio-tauri` (lib test) due to 18 previous errors
```

按名跑单条 `cargo test --lib test_sequence_reset_on_reason_initial` 同样以
`could not compile ... due to 18 previous errors` 收尾(整 crate 同编译单元,RED 属实)。

缺失的 6 个 seam 及命中行:

| seam | 类别 | 命中行(节选) |
|------|------|----------------|
| `AhRuntimeSnapshot` | type | 3841 |
| `parse_ah_runtime_snapshot` | fn | 3842, 3914 |
| `AhRuntimeState` | enum | 3862, 3882, 3890, 3906, 3988, 4075 |
| `reconcile_snapshot_lifecycle` | fn | 3938, 3945, 3954, 3955 |
| `SequenceArbiter` | struct+impl | 3974, 4004, 4025 |
| `resolve_bootstrap_snapshot` | fn | 4065, 4082 |

RED 属实且落在预期符号上(同任务 2 `ah_version_gate`、任务 3 `verify_snapshot_identity`
的编译期 RED 机制)。测试函数定义行:parse_snapshot_or_panic@3841、
test_typed_snapshot_parser…@3853、test_decision_plane…@3933、
test_sequence_reset_on_reason_initial@3966、test_sequence_guard_within_stream@4021、
test_daemon_absent_prefers_events_over_status_stderr@4056。

## g1-m1 待实现的契约 seam(测试注释里已完整立起,g1-m1 不得改测试)

字段模型 = design.md:237-273(按 F8 对齐真实 1.4.0/1.5.0 CLI 输出),字段清单 tasks.md:60。

```rust
enum AhRuntimeState { Active, Inactive, Starting, Degraded }   // derive PartialEq+Eq+Debug

struct AhSessionSnapshot {
    session_id: String, project_id: String, path: String, status: String,
    live_agents: u64, db_tracked_agents: u64,                  // live_agents,非 active_agents(F8)
    cleanup_required: bool, safe_to_cleanup: bool,             // ah 自算,直接消费不再推导
}

struct AhRuntimeSnapshot {
    schema_version: u64, runtime_state: AhRuntimeState,
    active: bool, ahd_alive: bool, sequence: u64,
    reason: Option<String>, config_path: Option<String>,      // config_path 仅诊断(Req 2.7)
    master_tmux_alive: bool, worker_tmux_alive: bool,          // 顶层 tmux-health 须 serde-default:
    sessions: Vec<AhSessionSnapshot>,                         // 精简 SEQUENCE_*/daemon_absent 帧省略这些字段
}

fn parse_ah_runtime_snapshot(snapshot_json: &str) -> Result<AhRuntimeSnapshot, String>
//  schema_version==2 才 Ok;未知 schema / 非法 JSON → Err(诊断),不得默认放行(Req 2.5)

fn reconcile_snapshot_lifecycle(snapshot: &AhRuntimeSnapshot) -> CodeAssistantLifecycleAction
//  active→AttachExisting;inactive/全 terminal→StartFresh;active/terminal 只来自快照字段,
//  绝不来自 ah ps 文本或 tmux 探测(starting/degraded 相位归任务 6)

struct SequenceArbiter { /* 私有 applied-sequence 缓存 */ }
impl SequenceArbiter {
    fn new() -> Self;
    fn accept(&mut self, snapshot: &AhRuntimeSnapshot) -> bool;  // true=已应用,false=丢弃
    //  同一未变流内 older-or-equal seq 丢弃;reason:"initial" / 新订阅 / 变更 session_id
    //  → 无条件重置缓存再应用(Req 2.1/5.13)
}

fn resolve_bootstrap_snapshot(
    status_json_result: Result<&str, &str>,   // Ok=status stdout JSON;Err=非零退出的 stderr
    events_snapshot_json: Option<&str>,       // 可得的 events 快照行
) -> Result<AhRuntimeSnapshot, String>
//  events 快照可得时优先采信;status --json 的 stderr 失败绝不在有结构化 events 时被当权威错误态
//  (Req 2.3/5.11)
```

## 锚定说明(gatekeeper 自查)

- **契约边界输入**:五条测试均喂**真实 ah CLI 快照形状**(active/daemon_absent 为任务 0
  CAPTURED 逐字采集;sequence 递增/重置的 seq/reason 亦 CAPTURED),非实现内部状态;断言的是
  **可观测决策**:解析结果字段、`Ok`/`Err`、应用/丢弃(bool)、AttachExisting/StartFresh。
- **交叉控制,常量实现无法糊绿**:
  - parser:`unsupported schema → Err` 断言杀掉「默认放行」实现;`live_agents==10` 杀掉字段错名。
  - 决策面:active≠terminal 两态相异,杀掉常量返回。
  - sequence:重置测试(必须 applied)与 guard 测试(旧序号必须 dropped)互为控制——「永远
    accept」红 guard,「永远 drop / naive 全局 max」红重置。
  - daemon-absent:主用例杀「status stderr 当权威错误」(会返 Err → `.expect` 红);控制用例
    (events=INACTIVE→ahd_alive:true)杀「硬编码 daemon_absent 常量」。
- **回滚自检(留给 g1-m1 变绿后复核)**:决策面回退去读 `ah ps` 文本 → 决策测试锚在
  typed 签名上不受影响,但 gatekeeper diff 审计查 `inspect_ah_runtime` 是否真删 ps/tmux 依赖;
  仲裁器回退成全局 max-guard → 重置测试转红;parser 放宽 schema 校验 → parser 测试转红。

## 已知 fixture 缺口(如实登记,未自行补 fixture)

- `test_sequence_reset_on_reason_initial` 的变更-session 分支:`SEQUENCE_RESET_FRAME_NEW_SESSION`
  同时带「变更 session_id」+「reason:"initial"/sequence:1」,故该分支**验到**变更-session 重置
  触发器**却无法把它与 reason:"initial" 触发器隔离**(两者同时触发)。要隔离需一条「变更
  session_id 但 reason 非 initial」的 fixture——当前不存在,补 fixture 属任务 1 范围。已在测试
  注释内写明,并按纪律**不自行加 fixture**(必要时走 `.lane-question` 报 master)。

## 结论

五条测试 RED 属实:task3 剩余(typed parser + 快照决策面)+ task4(events-primary + sequence
仲裁 + daemon-absent 仲裁)六个生产 seam 缺失,导致 lib-test 编译期硬红(18 条 E0425/E0433,
命中预期符号)。符合两任务「先写红、同批落地」状态,等待 g1-m1 纯实施变绿——g1-m1 不得改动
本测试文件,亦不得改动 `ah_contract_fixtures.rs`。
