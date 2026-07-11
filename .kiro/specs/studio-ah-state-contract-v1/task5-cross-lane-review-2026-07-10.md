# 跨泳道审计:bc415f21 task5 所有权守卫 + env clamp

- **审计人**:g1-claude(泳道1 gatekeeper),跨泳道审 g2-claude 实施的生产代码
- **被审 commit**:`bc415f214ecfb576d1d05f5b8b7dc831e8de5d01`
  `feat(studio): task5 所有权守卫+bash env clamp 实现`
- **红测试 commit(g1 执笔,先行)**:`1359a5d60b46272f0fe0abc93ad9df022201ff65`
  (`test_lifecycle_only_on_studio_managed_config` + `test_env_clamp_in_bash_string`)
- **spec 依据**:tasks.md:77-83(task 5,护栏先行);requirements Req 4.6 / 4.7 / 5.9
- **日期**:2026-07-10
- **裁定**:**✅ 通过(ACCEPT)**

---

## 一、任务背景

task 5 是「护栏先行」(tasks.md:77):所有权分类器 + env 钳制必须在任务 6/7 发出
`ah start`/`stop`/`kill` 之前落地,否则会出现「能发生命周期命令但守卫没接线」的
中间态。g2 对着 g1 先写的两个红测试实现了两个纯生产缝:

- `ensure_lifecycle_command_allowed`(生命周期命令守卫,Req 5.9)
- `build_ah_bash_script`(Windows `wsl.exe -e bash -lc` 的 script 纯拼接函数 +
  三行 state-dir env 钳制,Req 4.7 / 坑洞 3.5)

commit 只动一个文件 `apps/studio/tauri/src/lib.rs`(`+54 / -14`)。

---

## 二、Diff 合规核对(逐条对本单交付第 1 项 a–f)

### a) 守卫判据是否唯一来源于 `classify_config_ownership` —— ✅

`ensure_lifecycle_command_allowed`(lib.rs:375-385)函数体只有一句判断:

```rust
fn ensure_lifecycle_command_allowed(config_path: &Path) -> Result<(), String> {
    if classify_config_ownership(config_path).read_only {
        return Err(format!(...(Req 5.9)...));
    }
    Ok(())
}
```

判据 `read_only` 完全取自单一所有权权威 `classify_config_ownership`(lib.rs:363-366:
`!config_path.starts_with(studio_ah_temp_root())`),**没有另写一套所有权判断**(没有
自己 re-check 路径前缀、没有第二个 env 开关)。底座一/SSOT 守住。红测试
`test_lifecycle_only_on_studio_managed_config` 用 `ALL_CONFIG_OWNERSHIP_FIXTURES`
逐类断言 `allowed ⇔ !classify_config_ownership(path).read_only`,把「必须同源」这条
钉进契约。

### b) 是否真接线到全部三个生命周期入口、且 Err 时提前返回不发子进程 —— ✅

逐个确认守卫在**发子进程之前**调用,且返回值被真正处置(不是调了忽略):

| 入口 | 生命周期命令 | 守卫位置 | Err 处置 | 被守卫的子进程点 |
| --- | --- | --- | --- | --- |
| `cleanup_code_assistant_config`(1257) | stop + kill | 1258 `ensure_..._allowed(config_path)?;` 在函数第一行 | `?` 直接向上抛,提前返回 | `stop_ah_config`(1265)→`ah stop`;`force_cleanup_ah_runtime`(1272)→`ah kill` |
| `force_cleanup_ah_runtime`(1191) | kill | 1192-1198 `if let Err(error) = ...{ log::warn!; return; }` 函数第一块 | 记 warn 后 `return`,提前退出 | `run_ah_config_command(&["kill",...])`(1200)、`kill_tmux_session`(1222) |
| `open_code_assistant` 的 `StartFresh`(2612) | start | 2614 `ensure_..._allowed(&config_path)?;` 紧跟在解析出 config_path 之后 | `?` 提前返回 | `write_code_assistant_launcher_script`(2615)+`spawn_terminal_with_launcher`(2618),launcher 模板里的 `ah --config "$CFG" start --wait`(1969 / 2138) |

三处都是「先守卫,后子进程」,且都真正短路(`?` 或 `return`),没有一处「调了却
忽略返回值」。

补充链路核对:`force_cleanup_ah_runtime` 除被 cleanup(已守卫)调用外无其它调用点;
`cleanup_code_assistant_config` 的另外两处间接调用方
(`cleanup_workspace_code_assistants`:1302→1308、`cleanup_registered_code_assistants`:1759→1761)
都经这条已守卫的函数发命令,不存在绕过守卫的第四条 stop/kill 通路。

`StartFresh` 的 config 由 `ah_config_for_workspace`(951)解析——它会先
`find_ah_config` 向上发现既有 `ah.toml`,若命中即返回 workspace-owned 路径;此时守卫
正确拒绝(不会对 operator 自己的 fleet 发 `ah start`),这正是护栏的目标场景。

### c) 只读路径(status/events/attach)未被守卫误伤 —— ✅

全仓只有上面三处调用 `ensure_lifecycle_command_allowed`,只读路径一律不经此守卫:

- **status**:`inspect_ah_runtime`(1155)里的 `run_ah_config_command_output(&["ps"])`(1159)
  不过守卫;
- **events**:`spawn_ah_events_command`(1029,被 1538 的状态流用)不过守卫;
- **attach(观察性)**:`open_code_assistant` 的 `AttachExisting`(2602)与
  `attach_code_assistant_terminal`(2624)走 `attach master` launcher(1976 / 2055 /
  2144 / 2199),不过守卫;
- **发现逻辑**:`ah_config_for_status`(970)保持原样,workspace-owned `ah.toml` 仍被
  正常 surface 供观察。

红测试对此有正向锚定:同一个 workspace-owned config 经 `ah_config_for_status` 仍能被
status/events 发现(`status_config == discovered_config`),但对它
`ensure_lifecycle_command_allowed(...).is_err()`——「可观察、不可生命周期操作」两义
同时成立。

### d) 三行 env 钳制是否在 `ah --config ...` 之前 —— ✅

`build_ah_bash_script`(lib.rs:993-1006)拼出的 script 字符串:

```
export AH_STATE_DIR=""; export CCBD_STATE_DIR=""; export XDG_STATE_HOME=""; \
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"; export SYSTEMD_LOG_LEVEL=err; \
ah --config {} {}
```

三行 `AH_STATE_DIR` / `CCBD_STATE_DIR` / `XDG_STATE_HOME` 钳制**位于 `ah --config`
之前**,且是写在 **script 字符串本体内**(不是 Rust `Command::env`)。这符合坑洞 3.5:
`-lc` 登录 shell 在继承 `Command::env` 后会重新 source 用户 profile,Rust 侧钳制会被
覆盖,而 in-string `export` 在 profile 之后执行、能压过。红测试
`test_env_clamp_in_bash_string` 除断言三行 `export …=""` 存在外,还断言
`clamp_at < ah_at`(顺序正确),顺序若倒置即红。

### e) 两个 Windows 分支是否统一走同一纯函数 —— ✅

- `run_ah_config_command_output` 的 Windows 分支(1014):`let script = build_ah_bash_script(config_path, ah_args);`
- `spawn_ah_events_command` 的 Windows 分支(1032):`let script = build_ah_bash_script(config_path, &["events", "--format", "json"]);`

两处旧的各自 `format!` 内联拼接已删除(见 diff 的 `-` 块),统一收束到 `build_ah_bash_script`
这一条缝,钳制不会在两处漂移。

### f) 未碰测试/ah.toml/未用 git add -A —— ✅

- `git show bc415f21 --stat`:仅 `apps/studio/tauri/src/lib.rs` 一个文件,`54 insertions / 14 deletions`,**无 ah.toml、无 `*.test.ts(x)`**。
- 六个 diff hunk 头 `@@` 落在 365 / 981 / 1029 / 1189 / 1255 / 2611 行区间,全部**位于测试模块之上**(`#[cfg(test)] mod tests` 在 3379/3380),未触碰任何 `#[cfg(test)]` 区块——g1 先写的红测试文件原样保留。
- 单文件提交,非 `git add -A`(工作树里 `ah.toml` 的改动、`.operator-report.phase1`、`vendor/` 均未被本 commit 吸入)。

---

## 三、独立重跑验证(本单交付第 2 项,g1 自跑不信自报)

```
cd apps/studio/tauri
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib
```

结果:**164 passed; 1 failed**。唯一失败为
`native_fs::tests::publish_package_writer_maps_permission_error`——本机 root 环境已知
问题(root 可写只读父目录,权限断言不成立),与本次改动无关,是本单明确允许的例外。

两个 task-5 测试单独重跑均绿:

```
test tests::test_env_clamp_in_bash_string ... ok
test tests::test_lifecycle_only_on_studio_managed_config ... ok
test result: ok. 2 passed; 0 failed; ...
```

---

## 四、回滚自检(锚定硬项实操,证明测试穿过本次 diff)

对 g2 的生产改动逐项临时回滚,确认对应测试变红、复原后回绿、树净:

| 临时回滚 | 结果 | 结论 |
| --- | --- | --- |
| 把守卫改成 `if false && classify_config_ownership(...)`(恒 Ok) | `test_lifecycle_only_on_studio_managed_config` **红**(lib.rs:4815「workspace-owned config must refuse start/stop/kill」);env 钳制测试仍绿 | 生命周期测试真锚在守卫生产逻辑上,非空转 |
| 从 `build_ah_bash_script` 删掉三行 `export …=""` 钳制 | `test_env_clamp_in_bash_string` **红**(lib.rs:4887「missing `export AH_STATE_DIR=""`」);守卫测试仍绿 | env 钳制测试真锚在 `build_ah_bash_script` 生产逻辑上,非空转 |
| `git checkout -- lib.rs` 复原 | 两测试均回绿;`git status` 中 lib.rs 干净,与 bc415f21 committed 态零 diff | 回滚自检闭合,未污染被审树 |

两次回滚各自只红各自的测试(另一测试保持绿),说明两个断言互不串扰、各自穿过对应
的 diff 缝。

---

## 五、Scope 观察(非阻断,记录在案)

仓内另有两处 `wsl.exe -e bash -lc` 调用**未**走 `build_ah_bash_script`、未带 state-dir
钳制,已逐一核对确认为正确的 scope 之外,不构成 spec 稀释:

- `run_ah_version`(lib.rs:43):`ah version` 纯版本探测,不读写任何 state dir,钳制对它
  无行为意义;红测试契约亦不要求。
- `run_tmux_socket_command`(tmux `-L <socket>` kill):调用的是 **tmux 不是 ah**,tmux
  不读 `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME`——tasks.md:81 原文即注明
  「lib.rs:927 是 tmux socket 调用不是 ah」。钳制的实质目标(坑洞 3.5「写面互相污染
  state dir」)只落在 ah 的读写面,已由两个 ah 调用点全覆盖。

Req 4.7a(1.5.0 读面 daemon 隔离)按 tasks.md:82 属任务 3 身份校验,不在本 commit
承重范围,未纳入本次断言。

---

## 六、裁定

**✅ ACCEPT** —— 六项 diff 合规(a–f)全部满足;守卫判据同源单一权威、三处生命周期
入口均先守卫后子进程且 Err 短路、只读路径不被误伤;env 钳制在 ah 命令前且在 script
字符串本体内、两个 Windows 分支统一收束;独立重跑除已知 root 例外外全绿;回滚自检
证明两个测试各自穿过本次 diff、非空转。未越界、未稀释 spec、未碰测试文件与 ah.toml。
