# Task 5 RED 证据 — 加入 config 所有权分类与环境变量钳制（护栏先行）

- spec: studio-ah-state-contract-v1
- task: 5「加入 config 所有权分类与环境变量钳制（护栏先行）」
- 执笔: g1-claude（泳道1 gatekeeper，跨泳道 test-first hand-off；GREEN 由 g2 实施，g1 审）
- date: 2026-07-10
- 测试文件: `apps/studio/tauri/src/lib.rs` `#[cfg(test)] mod tests`
- 新增测试: `test_lifecycle_only_on_studio_managed_config` / `test_env_clamp_in_bash_string`
- 只改测试代码，未动任何生产代码（RED 手法同 task 2/3/4/8：声明尚不存在的生产函数签名 →
  编译期 E0425）。

## 验证命令

```
cd apps/studio/tauri && RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib --no-run
```

## 1. 基线（加测试前）— 干净编译

在写入两条 RED 测试之前，`cargo test --lib --no-run` 干净通过（仅一条 **pre-existing**
`dead_code` warning，针对 task 8 的 `AssistantStatus` 变体——它们要到 task 6/9 喂入 typed
snapshot 才被消费，与本任务无关）：

```
warning: `skill-studio-tauri` (lib test) generated 1 warning
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.18s
  Executable unittests src/lib.rs (target/debug/deps/app_lib-b7f80fc054a0890e)
```

即：编译器成功产出 test 可执行文件 → 基线绿、树净。

## 2. 加入两条 RED 测试后 — 真红（编译期 E0425）

写入两条测试后再跑同一命令，编译失败，5 个 `error[E0425]`（4 处
`ensure_lifecycle_command_allowed` + 1 处 `build_ah_bash_script`），全部因为测试调用了
**尚未由 g2 实现的生产函数**。原始报错：

```
error[E0425]: cannot find function `ensure_lifecycle_command_allowed` in this scope
    --> src/lib.rs:4776:13
     |
4776 |             ensure_lifecycle_command_allowed(Path::new(CONFIG_WORKSPACE_OWNED.config_path)).is_err(),
     |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `ensure_lifecycle_command_allowed` in this scope
    --> src/lib.rs:4780:13
     |
4780 |             ensure_lifecycle_command_allowed(Path::new(CONFIG_STUDIO_MANAGED.config_path)).is_ok(),
     |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `ensure_lifecycle_command_allowed` in this scope
    --> src/lib.rs:4788:27
     |
4788 |             let allowed = ensure_lifecycle_command_allowed(path).is_ok();
     |                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `ensure_lifecycle_command_allowed` in this scope
    --> src/lib.rs:4822:13
     |
4822 |             ensure_lifecycle_command_allowed(&status_config).is_err(),
     |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ not found in this scope

error[E0425]: cannot find function `build_ah_bash_script` in this scope
    --> src/lib.rs:4841:22
     |
4841 |         let script = build_ah_bash_script(config, &["status", "--json"]);
     |                      ^^^^^^^^^^^^^^^^^^^^ not found in this scope

error: could not compile `skill-studio-tauri` (lib test) due to 5 previous errors
```

## 3. g2 要实现的两个生产 seam（本 RED 测试锚定的契约）

两者都是**纯函数**（无子进程、不碰活编队），使测试可在 Linux 本机跑、且 RED 期绝不会
误对操作者的 live fleet 发 `ah stop`/`kill`：

1. `fn ensure_lifecycle_command_allowed(config_path: &Path) -> Result<(), String>`
   —— 生命周期命令（start/stop/kill）入口守卫。仅对 Studio-managed temp config 放行
   （`Ok(())`），对向上发现的 workspace-owned config 拒收（`Err(诊断)`）。所有权判据必须
   取自唯一权威 `classify_config_ownership`（底座一/SSOT），不得二次臆断。只读命令
   （status/events/观察性 attach）**不**过此守卫。g2 须把它接到每个 start/stop/kill 入口
   （`cleanup_code_assistant_config` / `force_cleanup_ah_runtime` / start 路径）的**最前面、
   任何子进程之前**——此接线在 GREEN 阶段由 gatekeeper 审 diff 验证。

2. `fn build_ah_bash_script(config_path: &Path, ah_args: &[&str]) -> String`
   —— 从 `run_ah_config_command_output`(lib.rs:965) 抽出、并由
   `spawn_ah_events_command`(lib.rs:995) 复用的 bash `-c` 脚本构造器。必须把
   `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME` 钳制**注入脚本字符串本身**
   （`export AH_STATE_DIR=""; …`），排在 ah 命令之前；不能只用 Rust `Command::env`
   ——`-lc` 登录 shell 在继承 env 后 source 用户 profile 会把 `Command::env` 覆盖掉
   （坑洞 3.5 / Req 4.7）。

## 4. 锚定与回滚自检（每条测试为何不空转）

- `test_lifecycle_only_on_studio_managed_config`：断言 workspace-owned 拒收 /
  Studio-managed 放行 / 守卫判据与 `classify_config_ownership` 全量一致 / 只读 status 发现
  （`ah_config_for_status`）对同一 workspace-owned config 不受影响。always-Ok 守卫会红
  「拒收」断言；always-Err 会红「放行」断言；两个 fixture 互为反类，一致性循环使任何常量
  实现都过不了。
- `test_env_clamp_in_bash_string`：断言构造出的脚本含三条 `export …=""` 钳制、且排在
  ah 命令之前，并保留既有 `SYSTEMD_LOG_LEVEL=err` 与 config/args。去掉 in-string 钳制
  （或改回 `Command::env`）会红 `export …=""` 断言；把钳制放到 ah 命令之后会红 ordering
  断言。

## 5. 复用既有冻结 fixtures（未新造）

两条测试直接消费 `apps/studio/tauri/src/ah_contract_fixtures.rs` 已冻结的
`CONFIG_WORKSPACE_OWNED` / `CONFIG_STUDIO_MANAGED` / `ALL_CONFIG_OWNERSHIP_FIXTURES`
（约 257-276 行），**未改动** fixtures 文件。
