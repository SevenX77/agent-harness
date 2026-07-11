# task3 结构化 snapshot 身份校验 RED 证据(机器验证)— 2026-07-10

任务 3「先写红」半程:只写身份校验红测试,不写生产代码(typed parser + 身份校验函数
本体是 g1-m1 的活)。环境已解锁,本次在 worktree 用
`RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo` 真跑 `cargo test --lib`,记录实际 RED。

- worktree 分支:`feat/studio-ah-state-contract-impl`
- 工具链:`cargo 1.96.1 (356927216 2026-06-26)`
- 命令:`cd apps/studio/tauri && cargo test --lib`
- 基线核对:加测试**前**先 `cargo test --lib --no-run` 真跑,exit 0、干净编译
  (`Finished test profile ... / Executable unittests src/lib.rs`),证明本次 RED
  唯一归因于新加的两条测试引用的缺失 seam,而非既有代码破坏。

## 两条新测试(均复用任务 1 已建 fixture,不新造)

- `test_identity_rejects_config_path_match_state_dir_mismatch`(Req 5.10a):
  喂任务 1 的 `IDENTITY_NF1_ECHO_MISMATCH`(CAPTURED 真机 NF1 回显击穿:snapshot 把
  请求的 `config_path` 原样回显,但 `state_dir`/session 身份属另一套活 daemon)→
  断言身份校验**丢弃**该快照并给非空诊断。config_path-only 或无条件接受的实现会红。
- `test_identity_canonicalizes_windows_wsl_path`(Req 5.10b):
  喂任务 1 的 `IDENTITY_WINDOWS_WSL_CANONICAL_MATCH`(`C:\Users\dev\myproj` 请求 vs
  `/mnt/c/Users/dev/myproj` WSL 快照,同一 canonical 目标)→ 断言**接受**。测试内先
  断言 raw string 比对不相等(前置条件),故接受只能来自跨平台归一 + project_id 锚点,
  raw string 比对的实现会红。

## RED(编译期,E0425)— 真实终端输出

生产 seam `verify_snapshot_identity` 尚不存在,整个 lib-test 目标编译失败 2 条 E0425:

```
error[E0425]: cannot find function `verify_snapshot_identity` in this scope
    --> src/lib.rs:3616:23
     |
3616 |         let verdict = verify_snapshot_identity(
     |                       ^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `verify_snapshot_identity` in this scope
    --> src/lib.rs:3661:23
     |
3661 |         let verdict = verify_snapshot_identity(
     |                       ^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

For more information about this error, try `rustc --explain E0425`.
error: could not compile `skill-studio-tauri` (lib test) due to 2 previous errors
```

RED 属实且落在预期符号上(与任务 3 tasks.md 第 57-64 行声明一致,同任务 2
`ah_version_gate` 的编译期 RED 机制)。两处 3616/3661 分别是两条测试对该 seam 的调用点。

## g1-m1 待实现的契约 seam(测试注释里已立,g1-m1 不得改测试)

```rust
/// 身份判据以 state_dir + 会话身份(sessions[].session_id/path/project_id)为权威;
/// config_path 仅诊断(无 config daemon 上为 null、且被 --config 原样回显 → 零鉴别力,NF1)。
/// Studio 从 requested_workspace_dir 独立推导期望身份(basename ⇒ project_id 锚点;
/// 目录本身 ⇒ 期望 worktree 路径)。所有路径比对经 windows_path_to_wsl 跨平台归一,
/// 绝不 raw string。Ok(())=身份匹配可采信;Err(diagnostic)=不匹配,须丢弃并给诊断。
fn verify_snapshot_identity(
    snapshot_json: &str,
    requested_config_path: &Path,
    requested_workspace_dir: &Path,
) -> Result<(), String>
```

## 锚定说明(gatekeeper 自查)

- 契约边界输入:两条测试均喂**真实 ah CLI 快照形状**(NF1 为任务 0 CAPTURED 逐字采集),
  非实现内部状态;断言的是**接受/丢弃这一可观测决策**(Ok/Err),非内部字段。
- 交叉对照:两条测试互为控制——"永远 Err"会红归一测试,"永远 Ok"或 config_path-only
  会红 NF1 测试,任何常量实现都无法把这对测试同时糊绿。
- 回滚自检(留给 g1-m1 变绿后复核):归一逻辑回退成 raw string 比对 → 归一测试转红;
  身份判据回退成信任 config_path → NF1 测试转红。断言穿过本次待落地的生产真实路径。

## 结论

两条测试 RED 属实:身份校验 seam 缺失导致 lib-test 编译期硬红(命中预期符号
`verify_snapshot_identity`,src/lib.rs:3616/3661)。符合任务 3「先写红」半程状态,
等待 g1-m1 纯实施(typed parser + 身份校验函数)变绿——g1-m1 不得改动本测试文件。
