# 跨泳道审计:432bad03 task6.1 events-primary 决策面接入活路径

- **审计人**:g1-claude(泳道1 gatekeeper),跨泳道审 g2-claude 实施的生产代码
- **被审 commit**:`432bad037f9ca0e39d1da459219c16766ac67bd8`
  `feat(studio): task6.1 events-primary 决策面接入活路径`
- **红测试 commit(g1 执笔,先行,非本会话实例)**:`04d788d79bf666b78c57e49b131b9eaac3631734`
  (`test_open_decision_v2_maps_requested_phase` + `test_open_decision_v2_arbitrates_other_active_runtime`)
- **决策档案**:`task6.1-seam-decision-2026-07-10.md`(commit `1188a29a`,架构 A 四条裁决 + RED 契约)
- **spec 依据**:tasks.md 任务 6.1(把 typed 决策面接到 Open/Attach 活路径,退役老布尔面);
  requirements Req 3.5/3.6/3.7/5.6/5.7;design.md:27/178/325(禁 `ah ps` 文本/tmux 探测)
- **日期**:2026-07-11
- **裁定**:**✅ 通过(ACCEPT)** — 逐条达标,无附带缺陷,前一单(task6 §五)的承重接线 gap 已闭合

---

## 一、任务背景

task6(af0833d1)把 typed 决策面(`reconcile_snapshot_lifecycle` / `assistant_status_for_runtime_state`)
建好并测试锚定,但 task6 审计 §五 亲验发现:**这套 typed 面只被单测消费、零生产调用点**,
shipping UI 的 Open/Attach 活路径仍跑老布尔面(`inspect_ah_runtime` 解析 `ah ps` 文本 + 探测 tmux),
违反 design.md:27/178/325。master 据此补收尾单 task6.1,并在 `task6.1-seam-decision-2026-07-10.md`
下四条裁决:①架构 A(events 流成 typed 单一真相源,缓存改 typed);②新增 `decide_code_assistant_open_v2`
替代老 `decide_code_assistant_open`;③`force_cleanup_ah_runtime` 归任务 7、本单不动;④编译期 RED 是预期中间态。

g1 先写两个 RED 测试(04d788d7)锚定新决策函数的契约边界返回值。g2 对着红测试实现(432bad03),
commit 只动一个文件 `apps/studio/tauri/src/lib.rs`(`+178 / -193`)。

---

## 二、Diff 合规核对(逐条对 brief 六项审计点)

### 1) 432bad03 只改生产代码,未动 04d788d7 两个 RED 测试的断言本体 —— ✅

- 逐字节比对:抽出两版本(04d788d7 / 432bad03)`lib.rs` 中
  `test_open_decision_v2_maps_requested_phase`(起)到下一个测试
  `claude_wsl_payload_links_windows_credentials`(止)之间的完整区段,`diff` **零差异**——
  两个 RED 测试函数体(含全部 `assert_eq!`/`assert_ne!` 断言与诊断文案)原样保留,未被实现悄改迁就。
- 432bad03 对 `#[cfg(test)] mod tests` 的改动只有三类,**均不碰这两个 RED 测试**:
  4 个旧测试删除(见 §6)、3 个既有测试 retype(见 §6)。
- `git show 432bad03 --stat`:**单文件** `apps/studio/tauri/src/lib.rs`(178 insertions / 193 deletions),
  **无 `ah.toml`、无 vendor、无其它测试文件**;工作树里游离的 `M ah.toml`、`.operator-report.phase1`、
  `vendor/` 均未被本 commit 吸入(非 `git add -A`)。

### 2) `decide_code_assistant_open_v2` 四相位映射符合裁决 2,跨 assistant 仲裁与老函数行为等价 —— ✅

- 四相位映射经 `reconcile_snapshot_lifecycle`(lib.rs:3245-3252)完成,与决策档案裁决 2 的表一致:
  ```rust
  Active   => AttachExisting  // → AttachRequested
  Inactive => StartFresh
  Starting => HandsOff        // Req 3.6
  Degraded => CleanupStale
  ```
- `decide_code_assistant_open_v2`(lib.rs:3269-3300)结构:
  1. `requested_action = requested.map(reconcile_snapshot_lifecycle).unwrap_or(StartFresh)`(3273-3275)——
     `unwrap_or(StartFresh)` 与老函数同,保留 `None → StartFresh`。
  2. **`HandsOff` 无条件早返回**(3277-3279):starting 的 requested 不进入仲裁,直接 `HandsOff`。
     合决策档案裁决 2 与 §四「留给本泳道的 `Starting`+other-active 组合,此处裁定 hands-off 优先」——
     doc comment(lib.rs:3265-3268)诚实标注了这条本泳道裁决。
  3. 其后 `has_stale` / `other_active_count` / 四分支 `if…else` **逐字照抄**老
     `decide_code_assistant_open`(见被删 diff),**唯一改动**:`others` 的判据从
     `reconcile_code_assistant_lifecycle`(布尔面)换成 `reconcile_snapshot_lifecycle`(按 `runtime_state`)——
     即「其它 assistant 是否 active」= `runtime_state == Active`(等价于 reconcile 出 `AttachExisting`)。
- 等价性锚点:RED 测试 `test_open_decision_v2_arbitrates_other_active_runtime`(04d788d7)显式对齐老
  `open_decision_enforces_single_ahd_per_workspace` 的两条护栏——
  `(Some(inactive), &[active]) → RejectOtherActive`、`(Some(active), &[active]) → CleanupStale`、
  `(None, &[]) → StartFresh`——**实机全绿**(见 §3)。single-ahd-per-workspace 护栏未在 cutover 中丢失。
- 附:老布尔面只有 3 个布尔无 `Starting`;新面下若某 `other` 为 `Starting`,其 reconcile 出 `HandsOff`,
  既不计入 `has_stale`(≠CleanupStale)也不计入 `other_active_count`(≠AttachExisting),即「starting 的
  他者不阻塞」——与判据「仅 active 他者阻塞」自洽,非缺陷。

### 3) `prepare_code_assistant_open` / `attach_code_assistant_terminal` 真的改吃 typed 快照,函数体零 `inspect_ah_runtime` —— ✅

- `prepare_code_assistant_open`(lib.rs:2481-2553):`requested_runtime` 与 `other_runtimes` 均经
  **`resolve_open_snapshot(cached_snapshot(&config), &config, workspace_root)`**(2498/2510)取 typed 快照,
  再 `decide_code_assistant_open_v2`(2521)决策;`RejectOtherActive` 臂用
  `snapshot.runtime_state == AhRuntimeState::Active`(2533)选活跃他者;`HandsOff` 臂(2548-2551)返回
  「仍在启动,先等」诊断,不发任何生命周期命令。**函数体内无 `inspect_ah_runtime`**。
- `attach_code_assistant_terminal`(lib.rs:2584-2628):读缓存 → `resolve_open_snapshot`(2600)→
  `reconcile_snapshot_lifecycle`(2603)决策,穷尽 match 四臂(AttachExisting/CleanupStale/StartFresh/HandsOff,
  2606-2622)。**函数体内无 `inspect_ah_runtime`**。
- `resolve_open_snapshot`(lib.rs:3444-3469)本身:先取 events-primary 缓存帧(`cached`);缓存无帧才
  `ah status --json` fallback 经 `resolve_bootstrap_snapshot` 解析 + `verify_snapshot_identity` 身份校验;
  **绝不解析 `ah ps` 文本、不探测 tmux**(design.md:27/178/325)。`None` = 无 runtime 信息,caller 视为 start-fresh。
- 物理实证(全文件 grep `\binspect_ah_runtime\b`):调用点仅 1179 / 1187 / 1198,**全部落在任务 7 清理链**
  (`wait_for_code_assistant_shutdown` 1175-1195 / `cleanup_code_assistant_config` 1195+),
  Open/Attach 两入口区间(2481-2628)内 **0 命中**;4203 为测试模块注释。

### 4) 老布尔路径按「无向后兼容」删除,非双轨并存 —— ✅

被删函数(432bad03 diff 中带 `-` 整段移除)+ 全文件 grep 复核残留:
| 符号 | 当前 grep 命中 | 结论 |
|---|---|---|
| `decide_code_assistant_open`(老) | 4(均为注释/字符串引用旧名;`\b…\b` 已排除 `_v2` 新函数) | 无真实定义/调用,已删 |
| `reconcile_code_assistant_lifecycle` | 0 | 已删 |
| `code_assistant_lifecycle_is_active` | 0 | 已删 |
| `lifecycle_snapshot_from_ah_event` | 0 | 已删 |
| `AhRuntimeEventLine` | 0 | 已删 |

无一处保留老决策/老事件解析作为 fallback,不存在双轨。事件订阅流(`start_code_assistant_status_stream`)
改用 `parse_ah_runtime_snapshot`(typed v2);`status_snapshots` 缓存类型改
`BTreeMap<PathBuf, AhRuntimeSnapshot>`(lib.rs:141);UI 投影链(`snapshots_for_configs` /
`code_assistant_status_from_snapshots` / `handle_code_assistant_status_snapshot`)一并 retype,
经 `assistant_status_for_runtime_state` 投影(inactive/starting/active/degraded 各自可辨,不再塌成布尔)。

### 5) `inspect_ah_runtime` + `ah ps` 辅助保留给任务 7 清理链,本单不动 —— ✅

- `inspect_ah_runtime`(lib.rs:1093)及 `ah ps` 文本辅助
  (`extract_tmux_socket_label` / `ah_ps_output_has_inventory` / `extract_ah_session_ids`)、
  `code_assistant_shutdown_is_complete`、`AhLifecycleSnapshot` 均**保留**,仍被
  `force_cleanup_ah_runtime`(1129,收 `&AhRuntimeProbe` 参数)/ `wait_for_code_assistant_shutdown`(1175)/
  `cleanup_code_assistant_config`(1195)的 Close/quit 清理链使用——归任务 7,本单未触碰(合裁决 3)。
- 编译通过即证这批保留代码仍被合法引用、无「删一半」的悬空引用。

### 6) 4 个删除的旧测试合理(测的函数确被删,非删测绕过);3 个 retype 测试语义未削弱 —— ✅

**删除的 4 个旧测试**——逐一对到被删函数,是「函数没了测试跟着走」,非「删测试绕过失败」:
| 删除测试 | 所测(已删)函数 |
|---|---|
| `code_assistant_status_requires_ahd_and_master_tmux` | `code_assistant_lifecycle_is_active` |
| `stale_ahd_without_master_requires_cleanup_before_reopen` | `reconcile_code_assistant_lifecycle` |
| `open_decision_enforces_single_ahd_per_workspace` | `decide_code_assistant_open`(老) |
| `ah_events_snapshot_maps_open_state_from_inventory_and_master_not_worker` | `lifecycle_snapshot_from_ah_event` |

其中 `open_decision_enforces_single_ahd_per_workspace` 的仲裁覆盖已由新
`test_open_decision_v2_arbitrates_other_active_runtime` 等价承接,护栏未失守。

**retype 的 3 个既有测试**——只换输入 fixture 类型(`AhLifecycleSnapshot::new(bool,bool,bool)` →
`parse_snapshot_or_panic(SNAPSHOT_*)` 冻结 typed fixture),wire 断言语义核对:
- `test_payload_reports_claude_codex_independently`:断言(both active / claude-only→codex inactive)**未动**。
- `test_payload_carries_readonly_flag`:readOnly 断言**未动**。
- `ah_events_status_aggregation_is_display_only`:`claude active` / `codex inactive` 断言未动;**唯一变更**是
  启动窗口一处断言 `v_starting["claude"]["status"]` 由 `"inactive"` 改为 `"starting"`。
  **此为对齐设计的精化、非稀释**:`assistant_status_for_runtime_state(Starting) => Starting`
  是 design.md:132-133 / Req 5.6 的 SSOT 投影(lib.rs:3312-3319 穷尽 match),老布尔面把 starting 塌成
  inactive 本就是 drift;retype 后 typed 面让 starting 相位可辨,断言随之更严。display-only 契约本体
  (快照只驱动显示、永不触发 cleanup)完好。

---

## 三、独立重跑验证(brief 第 7 项,g1 自跑不信 commit message 数字)

```
cd apps/studio/tauri
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib
```

结果:**164 passed;1 failed**。

- 唯一失败:`native_fs::tests::publish_package_writer_maps_permission_error`
  (panic 于 `src/native_fs.rs:1947`,"read-only parent maps to permission")——
  本沙箱 **root 环境既有失败**(root 可写只读父目录,权限断言不成立),与本改动无关,brief 明确允许的例外。
- **失败集合未变**:`failures:` 块只列这一项,无新增红,无新面孔;
  已知 flaky `sidecar::tests::allocate_loopback_port_honors_pinned_env` 本轮在 passed 集内,未触发。
- 计数与先例自洽:task6 审计为 166 passed / 1 failed;task6.1 净删 2 个测试(4 删 − 2 新 RED = −2),
  166 − 2 = **164 passed**,failed 恒为同一 native_fs 项。
- 编译通过(exit 0)本身即证:新增 `CodeAssistantOpenDecision::HandsOff` 变体已正确接入所有穷尽 match
  (`prepare_code_assistant_open` 2548 / 若漏则 Rust 编译期红)。两条新 RED 测试与 task6 两测试单独按名重跑均绿(见 §四)。

---

## 四、回滚自检(锚定硬项实操,证明测试穿过本次 diff)

临时抽掉本 commit 核心新逻辑——`decide_code_assistant_open_v2` 的 `HandsOff` 无条件早返回
(lib.rs:3277-3279),重跑两条新 RED 测试:

```
test tests::test_open_decision_v2_arbitrates_other_active_runtime ... ok
test tests::test_open_decision_v2_maps_requested_phase ... FAILED
  assertion `left == right` failed: starting requested runtime is hands-off — Open takes no action while startup is in progress (Req 3.6)
    left: StartFresh
   right: HandsOff                                                        [lib.rs:4538]
```

`test_open_decision_v2_maps_requested_phase` **精确变红在 starting→HandsOff 断言**(拿到 StartFresh)——
证明它真穿过本次 diff 的核心 HandsOff 逻辑,非空转(未锚在别处已修好的代码上)。
`arbitrates_other_active_runtime` 保持绿属预期:它锚的是 inactive/active 仲裁,不经 HandsOff 分支。
`git checkout -- lib.rs` 复原后:

- 该文件相对 HEAD **零 diff**(`git diff --stat HEAD` 空);
- 两条新 RED 测试 + task6 两测试(`test_starting_is_hands_off` / `test_degraded_exposes_working_open`)
  **全部回绿**。

回滚自检闭合,未污染被审树。

---

## 五、裁定

**✅ ACCEPT** —— 按泳道 TDD 契约,被审实施的验收线是「正确变绿红测试,且不改测试 / 不绕护栏 /
不稀释 spec / 不越 scope」。432bad03 逐条达标:

- 只改生产代码,两条 RED 测试逐字节未动,未碰 ah.toml/vendor,单文件提交(§1);
- `decide_code_assistant_open_v2` 四相位映射合裁决 2,跨 assistant 仲裁逐字照抄老函数、仅判据换
  `runtime_state`,行为等价、single-ahd 护栏保留;`Starting`+other-active 组合按本泳道裁决 hands-off 优先并诚实标注(§2);
- `prepare_code_assistant_open` / `attach_code_assistant_terminal` 真改吃 `resolve_open_snapshot` 的 typed 快照,
  函数体零 `inspect_ah_runtime`;events-primary + `status --json` fallback + 身份校验,绝不解析 `ah ps`/探测 tmux(§3);
- 老布尔面五符号按无向后兼容删净、无双轨(§4);`inspect_ah_runtime` + `ah ps` 辅助仅留给任务 7 清理链、本单不动(§5);
- 4 个删除测试均只测已删函数(非删测绕过),3 个 retype 测试仅换 fixture 类型、断言语义未削弱
  (唯一 `inactive→starting` 变更是对齐 SSOT 设计的精化)(§6);
- 独立重跑 164 passed / 1 failed(唯一失败为既有 root 环境 native_fs 例外,失败集合未变)(§三);
- 回滚自检证明新 RED 测试穿过本次 diff 核心 HandsOff 逻辑、非空转,复原后回绿树净(§四)。

**承接闭合**:task6 审计 §五 提示的「typed 决策面未接入活路径、`ah ps` 文本解析未退役」承重 gap,
本单已在 Open/Attach 两入口闭合(Close/quit 的 `force_cleanup_ah_runtime` 清理链按裁决 3 归任务 7)。
