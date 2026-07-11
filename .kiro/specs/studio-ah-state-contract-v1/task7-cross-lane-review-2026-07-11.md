# 跨泳道审计:5cb62744 task7 Close/quit cleanup 事件驱动重做

- **审计人**:g2-claude(泳道2 gatekeeper),跨泳道审 g1-claude 实施的生产代码(自审禁忌:本单生产代码由 g1 落地,g2 审)
- **被审 commit**:`5cb6274492afcda4bc01b47613b35149ce3acf98`
  `feat(studio): task7 Close/quit cleanup 事件驱动重做`
- **红测试 commit(g2 执笔,先行)**:`b44fa176d3af0a490713b63d897e82257a4e117d`
  (`test_cleanup_targets_only_cleanup_required_sessions` + `test_quit_leaves_workspace_owned_config_untouched`)
- **spec 依据**:tasks.md 任务 7(把 Close/app-quit cleanup 从 `ah ps`+tmux kill 老路切到事件驱动 typed 快照决策面);
  requirements Req 4.1-4.6/5.5/5.9;design.md:137-152(Close cleanup 流)/215-229(Cleanup orchestrator)
- **日期**:2026-07-11
- **裁定**:**✅ 通过(ACCEPT)** — 逐条达标;附一条**必须跟进的设计回写项**(design.md:226 措辞与实现存在已知 drift,已被诚实标注、非静默稀释,须在 task10 收口时收紧)

---

## 一、任务背景

task6.1(432bad03)把 typed 决策面接进 Open/Attach 活路径并退役老布尔面,但按 `task6.1-seam-decision-2026-07-10.md`
裁决 3,**Close/quit 的 `force_cleanup_ah_runtime` 清理链留给任务 7**。task7 要把 Close 与 app-quit 的 cleanup
从老决策路径(`ah ps` 文本解析 + 直接 kill tmux session,违反 design.md:178/227)整体切到事件驱动 typed 快照面:

1. session kill 目标改由 ah 自己的 per-session `cleanup_required` 判断驱动,不再由 Studio 推导「非终态即 kill」(Req 4.2/5.5);
2. 强清只走 `ah kill --session <id> --force`,彻底移除直接 kill tmux 的分支(design.md:227);
3. workspace-owned config 在 quit 清理里**透明跳过**而非让所有权 guard 的 `Err` 中止整个 quit(Req 5.9/4.6)。

g2 先写两个 RED 测试(b44fa176)锚定 ①新纯 seam `cleanup_target_session_ids` 的选择契约(编译期 RED),
②真实 app-quit 编排 `cleanup_workspace_code_assistants` 对 workspace-owned config 的透明跳过(行为 RED)。
g1 对着红测试实现(5cb62744),commit 只动一个文件 `apps/studio/tauri/src/lib.rs`(`+99 / -212`)。

---

## 二、Diff 合规核对(逐条对 brief 六项审计点)

### 1) 5cb62744 只改生产代码,未动 b44fa176 两个 RED 测试的断言本体 —— ✅

- **逐字节比对**:抽出两版本(b44fa176 / 5cb62744)`lib.rs` 中 task-7 RED 测试整段
  (从 `fn test_cleanup_targets_only_cleanup_required_sessions` 到下一个既有测试
  `ah_ps_probe_extracts_tmux_socket_label_and_session_ids`,含 `SNAPSHOT_MULTI_SESSION_MIXED_CLEANUP`
  fixture、两个测试函数体、全部 doc 注释)`diff` **零差异(137 行,完全一致)**——两个 RED 测试的
  fixture 与全部 `assert!`/`assert_eq!` 断言原样保留,未被实现悄改迁就。
- **5cb62744 的 diff 内 `#[cfg(test)] mod tests` 零改动**:diff 最末一个 hunk(`@@ -3464,6 +3305,52 @@`)是在
  `#[cfg(test)]\nmod tests {` **之前**追加两个新生产函数(`cleanup_target_session_ids`、`resolve_cleanup_snapshot`),
  没有任何 hunk 落进测试模块。本 commit 是**纯生产代码提交**。
- `git show 5cb62744 --stat`:**单文件** `apps/studio/tauri/src/lib.rs`(99 insertions / 212 deletions),
  **无 `ah.toml`、无 vendor、无其它文件**;工作树里游离的 `M ah.toml`、`.operator-report.phase1`、
  `vendor/` 均未被本 commit 吸入(非 `git add -A`)。

### 2) `cleanup_target_session_ids` 谓词只用 `cleanup_required`——commit 的解释属实且**站得住**,但 design.md:226 有已知 drift —— ✅(附跟进项)

**先坐实 commit message 的三条事实主张,再下独立判断。**

- **fixture 组合属实**:b44fa176 的 `SNAPSHOT_MULTI_SESSION_MIXED_CLEANUP` 里健康 ACTIVE 会话确为
  `"status":"ACTIVE" ... "cleanup_required": false, "safe_to_cleanup": false`(即活栈:有 6 个 live agent、
  master 在跑);另有一个 degraded ACTIVE 会话 `cleanup_required:true`(唯一 kill 目标)、一个 CLOSED 终态会话
  `cleanup_required:false, safe_to_cleanup:true`。
- **测试确实断言活栈必须被放过**:测试前置断言 `assert!(!live.cleanup_required && !live.safe_to_cleanup, ...)`,
  核心断言 `assert!(!targets.contains(&live.session_id), "a live ACTIVE session ah did not flag ... must NOT be killed")`,
  收口断言 `assert_eq!(targets, BTreeSet::from([degraded.session_id.clone()]))` —— 目标集**恰好只含** degraded 一个 id。
- **fixture 形态有真机 CLI 证据背书,非杜撰**:`task0-cli-evidence-2026-07-10.md:166` 记录的真实活编队会话即
  `"status": "ACTIVE", "live_agents": 6, ... "cleanup_required": false, "safe_to_cleanup": false, "master_tmux_alive": true`
  ——健康 ACTIVE = `cleanup_required:false + safe_to_cleanup:false` 是真实 CLI 形态。

**独立判断(不因「听起来合理」放过)——去读 design.md:226 原文核对措辞:**

> design.md:226 原文:「Escalate only with `ah kill --session <id> --force` for session ids from the selected
> config's latest identity-checked snapshot, and only where the snapshot marks that session
> `cleanup_required`**/not** `safe_to_cleanup`.」

原文用 `/` 连 `cleanup_required` 与 `not safe_to_cleanup`,按「OR」读即「`cleanup_required` 或 `!safe_to_cleanup`
其一即 kill」。我不满足于纸面推演,做了**物理实证**(见 §四回滚自检):把生产谓词临时改成 design.md:226
的字面 OR 读法 `session.cleanup_required || !session.safe_to_cleanup`,重跑 test1 →
**精确变红在「a live ACTIVE session ... must NOT be killed」**。即:**字面 OR 读法会真的把活栈
(`safe_to_cleanup:false`,6 个 live agent 在跑)选为 `ah kill --force` 目标**——这是对操作者自有编队的误杀。

语义上也自洽了这个结论:`safe_to_cleanup` 是 **ah 的安全闸(false = 有活工作、清它会毁数据)**,是「能不能清」的
_gate_,**不是「要不要清」的 _trigger_**。把 `!safe_to_cleanup` 当 OR-触发器,等于「专挑 ah 说不安全动的会话去 kill」,
方向反了。生产代码的 doc 注释(lib.rs:3308-3318)已把这层语义写清:「`safe_to_cleanup` is ah's safety gate against
killing live work, NOT a kill trigger, so `!safe_to_cleanup` alone must never escalate a kill」。

因此:**只用 `cleanup_required` 的谓词是对的,不是稀释、更不是放宽 fail-closed**——它在安全轴上比字面 OR 读法**更收紧**
(放过活栈),且正是 Req 4.2「优先 ah 自己的字段、Studio 绝不推导『非终态即 kill』」这条更底层设计原则的直接落实。
design.md:226 的字面 `/not safe_to_cleanup` 与 Req 4.2 本身自相矛盾(把安全闸误用作 kill 触发器),实现选择服从
**深层原则 + 测试契约 + 真机证据**,是正确取舍。

**关键合规点:此 drift 是「诚实标注、非静默」**——(a)commit message 显式写明与 design.md:226 措辞不同及原因;
(b)代码 doc 注释写清语义;(c)**未触碰 design.md**(没有偷改设计文档去迁就代码)。这与我方铁律「实现悄悄放宽
=拒收」的「悄悄」二字正相反。

> **必须跟进项(记入 gate,勿遗忘)**:按 AGENTS.md「MVP1 design = source of truth」,design.md:226 字面措辞与
> 实现存在真实分歧,须在 **task10 设计回写**时把 design.md:226 收紧为「只按 `cleanup_required`;`safe_to_cleanup`
> 是安全闸不是 kill 触发器」,闭合 code↔design 的 drift。本单 ACCEPT 以此跟进项落实为前提。

### 3) `force_cleanup_ah_sessions` 不再直接 kill tmux,改走 `ah kill --session <id> --force` —— ✅

- 重写后的 `force_cleanup_ah_sessions`(lib.rs:1004-1017):对 `cleanup_target_session_ids(snapshot)` 的每个 id
  只发 `run_ah_config_command(config_path, &["kill", "--session", &session_id, "--force"])`,**函数体内已无任何
  tmux 分支**(design.md:227「Do not directly kill tmux sessions during normal cleanup」)。
- 老路的直接 kill tmux 整块(`if let Some(socket_label) ... kill_tmux_session(...)`)在 diff 中带 `-` 整段移除;
  底层 `kill_tmux_session` / `run_tmux_socket_command` / `list_tmux_sessions` / `tmux_session_is_master/worker/ah_managed`
  全部删除,全文件 grep **0 处存活引用**(见 §6)。

### 4) `cleanup_code_assistant_config` 对 workspace-owned config「透明跳过继续」而非「整体 Err 中止」—— ✅

- 重写后的 `cleanup_code_assistant_config(config_path, workspace_dir)`(lib.rs:1042-1061)**首行即所有权分类**:
  `if classify_config_ownership(config_path).read_only { return Ok(false); }`(1046-1048)——workspace-owned
  直接 `Ok(false)` 透明跳过,不发任何生命周期命令;`ensure_lifecycle_command_allowed(config_path)?`(1053)保留在
  跳过之后,作为「Studio-managed 也必过的单一权威闸」的 fail-closed 兜底。
- 老路是 `ensure_lifecycle_command_allowed(config_path)?` 在函数最前,其 `Err` 经 `cleanup_workspace_code_assistants`
  循环里的 `?`(1083)**中止整个 quit**。新路把所有权跳过前置到该 `?` 之前,消除中止。
- 跳过是**所有权选择性**(来自单一权威 `classify_config_ownership`),非「一律 no-op 什么都不清」——第二个测试同时用
  `ensure_lifecycle_command_allowed` 在冻结 fixture 上正断言 Studio-managed temp config 仍允许全生命周期。
- **回滚实证(§四)**:临时禁掉这个所有权跳过 → test2 精确变红在「must skip it and return Ok, not abort ... with the
  ownership guard's Err」,报错正是 guard 的 `refusing lifecycle command ... belongs to the operator's own fleet`——
  证明该跳过就是让 test2 变绿的承重改动,实现与断言完全对齐。

### 5) 删除清单零调用点;保留清单确被既有测试钉住——边界合理,非「图省事没删干净」—— ✅

**删除(全文件 grep,均为 0 处存活引用,残留命中全是注释/测试字符串里的旧名):**

| 删除符号 | 存活引用 | 备注 |
|---|---|---|
| `inspect_ah_runtime` | 0(仅 1 处测试注释) | 老 ps+tmux 探测入口,已删 |
| `wait_for_code_assistant_shutdown` | 0 | 已删 |
| `AhRuntimeProbe` | 0 | 已删 |
| `kill_tmux_session` | 0 | 已删 |
| `list_tmux_sessions` | 0(仅 2 处测试断言文案) | 已删 |
| `run_tmux_socket_command` | 0 | 已删 |
| `tmux_session_is_master/worker/ah_managed` | 0 | 已删 |
| `force_cleanup_ah_runtime`(→`force_cleanup_ah_sessions`) | 0(仅注释旧名) | 已重写更名 |
| `CommandResult::combined_output` | 0 | 已删 |
| `AH_SHUTDOWN_POLL_INTERVAL/ATTEMPTS` | 0 | 已删 |

**保留(仍被既有测试钉住,测试文件不在 task-7 改动范围)——逐个核对钉住的测试真实存在:**

| 保留符号 | 定义 | 钉住它的既有测试引用 |
|---|---|---|
| `extract_tmux_socket_label` | 968 | 测试 5336(`ah_ps_probe_*`) |
| `tmux_socket_label_is_safe` | 961 | 被 `extract_tmux_socket_label`(974)引用 |
| `extract_ah_session_ids` | 981 | 994 + 测试 5340 |
| `ah_ps_output_has_inventory` | 993 | 测试断言 5359/5360 |
| `AhLifecycleSnapshot` | 443 | `code_assistant_shutdown_is_complete`(480)+ 测试 4659-4668 |
| `code_assistant_shutdown_is_complete` | 480 | 测试断言 4658-4667 |

这六个符号构成一个闭合簇:互相引用 + 被 `ah_ps_probe_*` 与 `close_cleanup_requires_master_and_worker_tmux_to_be_gone`
两组**既有**测试(task6/更早引入,非本单)钉住。彻底删除它们**必须同时删掉这些钉住的测试**,那属于 task6/测试文件
范畴,超出 task-7 remit。故本单保留是**真实测试-scope 边界**,不是「图省事没删干净」;编译通过即证无「删一半」的悬空引用。

### 6) 新 seam 接在活路径(非孤儿 shim)—— ✅(RED 测试注释显式把此项留给 gatekeeper diff 审计)

b44fa176 注释明确:「the shim existing but unused would be caught there [gatekeeper diff-audit], not here」。逐链核对:

```
cleanup_target_session_ids (def 3319)
  ← force_cleanup_ah_sessions (调 1006)
  ← cleanup_code_assistant_config.resolve_cleanup_snapshot(...).map(force_cleanup_ah_sessions) (调 1059)
  ← cleanup_workspace_code_assistants (调 1083, 传 Some(workspace_root))     ← Close/quit 活路径 2384 / 2449 / 2568
  ← cleanup_registered_code_assistants (调 1542, 传 None)                    ← app-quit sweep 2928 / 3009
```

新 seam 真正接进 Close 与 app-quit 两条编排,非未接线的孤儿。`resolve_cleanup_snapshot`(3357+)统一 post-stop
快照读取:有 workspace 走 `resolve_open_snapshot`(events-primary + 身份校验),app-quit 无 workspace 走
config-scoped `status --json`,**均不碰 `ah ps` 文本/tmux 探测**(design.md:178)。

---

## 三、独立重跑验证(brief 第 7 项,g2 自跑不信 commit message 数字)

```
cd apps/studio/tauri
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib
```

结果:**165 passed;2 failed**(总 167 恒定)。

- **失败 1**:`native_fs::tests::publish_package_writer_maps_permission_error`
  (panic 于 `src/native_fs.rs:1947`,"read-only parent maps to permission")——本沙箱 **root 环境既有失败**
  (root 可写只读父目录,权限断言不成立),与本改动无关,brief 明确允许的例外。
- **失败 2**:`sidecar::tests::allocate_loopback_port_honors_pinned_env`(`src/sidecar.rs:638`,端口 46119≠49317)——
  **brief 预先声明的已知并行端口争抢 flaky**。我隔离单跑复核:`cargo test --lib -- --test-threads=1
  sidecar::tests::allocate_loopback_port_honors_pinned_env` → **ok**。证明它是并行争抢 flaky,非本改动引入的真回归。
- **失败集合未出现新面孔**:只有以上两项,恰为 brief 两条预授权例外(root native_fs + sidecar flaky),无未知红。
  commit message 报「166 passed / 1 failed」与本轮「165/2」的差值,全部由该 flaky 在并行下翻红解释(总数 167 不变)。
- **两个新验收测试隔离单跑均绿**:`test_cleanup_targets_only_cleanup_required_sessions` ... ok /
  `test_quit_leaves_workspace_owned_config_untouched` ... ok。

---

## 四、回滚自检(锚定硬项实操,证明测试穿过本次 diff、非空转)

临时回滚本次 diff 的**两处核心改动**,重跑两个新 RED 测试:

1. 谓词 `session.cleanup_required` → `session.cleanup_required || !session.safe_to_cleanup`(即 design.md:226 字面 OR 读法);
2. 所有权跳过 `if classify_config_ownership(config_path).read_only { return Ok(false); }` → 用 `if false && ...` 禁用。

```
test tests::test_cleanup_targets_only_cleanup_required_sessions ... FAILED
  panicked at src/lib.rs:5230: a live ACTIVE session ah did not flag (cleanup_required:false) must NOT be killed
                               — no 'non-terminal therefore kill' (Req 5.5/4.2)
test tests::test_quit_leaves_workspace_owned_config_untouched ... FAILED
  panicked at src/lib.rs:5313: quit/Close cleanup over a workspace-owned config must skip it and return Ok, not
                               abort the whole cleanup with the ownership guard's Err (Req 5.9/4.6):
                               "refusing lifecycle command (start/stop/kill) on workspace-owned ah config ...
                                belongs to the operator's own fleet (Req 5.9)"
```

- test1 **精确变红在「live 会话必须被放过」**——证明它真穿过本次 diff 的 `cleanup_required`-only 谓词;
  且这一步**顺带物理坐实了 §2 的独立判断**:design.md:226 字面 OR 读法会把活栈(`safe_to_cleanup:false`)选为 kill 目标。
- test2 **精确变红在「所有权 guard 的 Err 中止整个 quit」**——证明它真穿过本次 diff 的所有权跳过早返回。
- `git checkout -- src/lib.rs` 复原后:该文件相对 HEAD **零 diff**(`git diff --stat HEAD` 空);两个新 RED 测试
  **全部回绿**(`test result: ok. 2 passed`)。

回滚自检闭合,未污染被审树。

---

## 五、裁定

**✅ ACCEPT** —— 按泳道 TDD 契约,被审实施的验收线是「正确变绿红测试,且不改测试 / 不绕护栏 / 不稀释 spec /
不越 scope」。5cb62744 逐条达标:

- 只改生产代码,两个 RED 测试整段(fixture+断言)逐字节未动,mod tests 零改动,未碰 ah.toml/vendor,单文件提交(§1);
- `cleanup_target_session_ids` 只用 `cleanup_required` 的谓词**正确**:是 Req 4.2「trust ah 字段、不 Studio 推导非终态即 kill」
  的落实,比 design.md:226 字面 OR 读法更 fail-closed(回滚实证 OR 读法会误杀活栈),drift 已诚实标注、未偷改 design.md(§2);
- `force_cleanup_ah_sessions` 只走 `ah kill --session <id> --force`、tmux 直杀分支删净(§3);
- `cleanup_code_assistant_config` 对 workspace-owned config 透明 `Ok(false)` 跳过、不再 Err 中止 quit,跳过是所有权选择性(§4·§二4);
- 删除清单十余符号零存活引用、保留六符号确被既有测试钉住且属 task6/测试-scope 边界(§5);
- 新 seam 真正接进 Close 与 app-quit 两条活编排,非孤儿 shim(§6);
- 独立重跑 165 passed / 2 failed,两处失败恰为 brief 两条预授权例外(root native_fs + sidecar flaky,后者隔离单跑回绿),
  无新面孔;两个新验收测试隔离单跑全绿(§三);
- 回滚自检证明两个新测试穿过本次 diff 两处核心逻辑、非空转,复原后回绿树净(§四)。

**承接闭合**:task6.1 裁决 3 留给任务 7 的「Close/quit `force_cleanup_ah_runtime` 清理链事件驱动重做」本单已闭合;
`ah ps` 文本解析 + 直接 kill tmux 的老决策链在 Close/quit 路径彻底退役。

**遗留跟进项(ACCEPT 附带条件,须落实)**:design.md:226 字面「`cleanup_required`/not `safe_to_cleanup`」措辞与实现
(只按 `cleanup_required`)存在真实 drift。实现方向正确、已诚实标注,但按「MVP1 design = source of truth」,**task10 设计回写
必须把 design.md:226 收紧**为「只按 `cleanup_required`;`safe_to_cleanup` 是安全闸不是 kill 触发器」,闭合 code↔design 分歧。
此项归 master 跟踪,不在本单生产代码内修。
