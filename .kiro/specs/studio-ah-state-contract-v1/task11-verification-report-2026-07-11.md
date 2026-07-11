# Task 11 · Focused Verification 收口报告

- **日期**:2026-07-11
- **执笔**:g1-claude(泳道1 质量门 / gatekeeper)
- **spec**:studio-ah-state-contract-v1
- **分支**:feat/studio-ah-state-contract-impl
- **本 spec 改动范围**(vs `origin/main`,`git diff --name-only`):
  - Rust:`apps/studio/tauri/src/lib.rs`、`apps/studio/tauri/src/ah_contract_fixtures.rs`(新增 fixture)
  - 前端:`apps/studio/frontend/src/components/copilot/copilot-panel.tsx`(+ `.test.ts`)、
    `apps/studio/frontend/src/lib/tauri.ts`(+ `.test.ts`)
  - 文档/spec:`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`、`.kiro/specs/...`、`.ah/VERIFY.md`
  - **未触碰** `packages/graph-agent`、`packages/graph-agent-gateway`、`apps/studio/backend` 的 Python 源码,
    也**未触碰** `apps/studio/tauri/src/native_fs.rs`(下述唯一失败项就在此文件,故与本 spec 无关)。

## 环境实测(本轮与 VERIFY.md 2026-07-10 记录的差异)

- **系统库已就绪**(operator 已在地基安装):2026-07-11 `pkg-config --exists` 实测
  `dbus-1 / gtk+-3.0 / glib-2.0 / gdk-3.0 / gio-2.0 / webkit2gtk-4.1 / javascriptcoregtk-4.1 /
  libsoup-3.0 / cairo / pango / atk / gdk-pixbuf-2.0` **全部 OK**(VERIFY.md 记录的 2026-07-10
  全 MISS 态已解锁)。→ **Rust crate 本轮可真机编译并跑测试**。
- **无图形显示服务**:`DISPLAY` 为空、无 Wayland、`Xvfb` 未安装。→ 桌面 GUI 无处渲染,
  交互式手工 smoke 无法在此环境真机执行(详见 §4)。
- **工具链**:cargo 1.96.1(`RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo`)、uv 0.11.28、
  ah **1.5.0**(满足版本门 v1.4.0+)。

---

## §1. Rust / Tauri crate 测试(本 spec 核心改动所在)

命令(在 `apps/studio/tauri`):
```
RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo cargo test --lib
```

- **退出码**:101(因下述唯一失败项;见结论)
- **结果**:`test result: FAILED. 166 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out`
- **唯一失败**:`native_fs::tests::publish_package_writer_maps_permission_error`
  - panic:`src/native_fs.rs:1947` — 期望向只读父目录写入映射为 PermissionDenied,但实际
    `bytes_written: 432`(写成功)。**根因**:以 root 身份跑,root 绕过文件权限位,只读父目录写入不会
    被拒 → 断言落空。这是 **root 沙箱假象**,与本 spec 无关。
  - **既有红判定(VERIFY §4 证伪)**:`native_fs.rs` 未被本分支触碰
    (`git diff --name-only origin/main...HEAD -- apps/studio/tauri/src/native_fs.rs` 输出为空),
    即该文件与 `origin/main` 逐字节相同,测试行为对 main 必然一致 → **既有红/环境性,非本次引入**。
    (与 task 11 brief 声明的"已知唯一允许的既有失败"一致。)
- **本 spec 相关测试全绿**(节选,全部 `... ok`):
  - 版本门:`test_version_gate_rejects_below_1_4_0`、`test_version_parse_uses_bare_ah_version`
  - 身份校验:`test_identity_rejects_config_path_match_state_dir_mismatch`、`test_identity_canonicalizes_windows_wsl_path`
  - typed 决策面:`test_typed_snapshot_parser_projects_phase_sessions_and_health`、
    `test_decision_plane_consumes_typed_snapshot_not_ps_text`、
    `test_open_decision_v2_arbitrates_other_active_runtime`、`test_open_decision_v2_maps_requested_phase`
  - sequence 仲裁:`test_sequence_reset_on_reason_initial`、`test_sequence_guard_within_stream`、
    `test_daemon_absent_prefers_events_over_status_stderr`
  - ownership + env clamp:`test_lifecycle_only_on_studio_managed_config`、`test_env_clamp_in_bash_string`
  - 相位:`test_starting_is_hands_off`、`test_degraded_exposes_working_open`
  - Close/quit:`test_cleanup_targets_only_cleanup_required_sessions`、`test_quit_leaves_workspace_owned_config_untouched`
  - payload:`test_payload_reports_claude_codex_independently`、`test_payload_carries_readonly_flag`
  - fixture 自校验:`ah_contract_fixtures::self_validation::*`(17 项全 ok)
- **结论**:**GREEN(扣除既有环境红 1 项)**。失败集合仅含允许项,无其它。
  - 注:`.ah/VERIFY.md` 明确"泳道1 gatekeeper 本地的 `cargo test`(在 `apps/studio/tauri`)是该 crate
    唯一的机器验证门"(CI 5 个必过 check 不含任何 cargo/rust 门)。本门本轮真机跑通。

---

## §2. 前端(Copilot 面板投影 + 全量前端门)

命令(在 `apps/studio/frontend`,`node_modules` 已装):

| 命令 | 退出码 | 结果 |
|---|---|---|
| `npm run lint` | 0 | 绿 |
| `npm run typecheck` | 0 | 绿 |
| `npm test`(vitest run) | 0 | **Test Files 189 passed (189) · Tests 1851 passed (1851)** |
| `npm run build`(tsc -b && vite build) | 0 | `✓ built in 664ms`(仅 chunk>500kB 的告警,非错误) |

- **本 spec 前端投影测试(定向复跑)**:
  `npx vitest run src/components/copilot/copilot-panel.test.ts src/lib/tauri.test.ts`
  → **Test Files 2 passed · Tests 56 passed**。覆盖 per-assistant 5 态枚举、claude/codex 独立状态、
  `readOnly` flag、只读 Detach/置灰 Open、starting/degraded 分支等 task 8/9 投影行为。
- **结论**:**全绿**。

---

## §3. `.ah/VERIFY.md` §1 收口全量清单 · Python 后端(证明未引入回归)

即使本 spec 未碰 Python 源码,仍按 VERIFY §1 跑满 8 条:

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv run ruff check packages/graph-agent packages/graph-agent-gateway apps/studio/backend` | 0 | All checks passed! |
| `uv run mypy --strict packages/graph-agent/src` | 0 | 绿 |
| `uv run mypy --strict packages/graph-agent-gateway/src` | 0 | 绿 |
| `uv run mypy apps/studio/backend/app` | 0 | 绿 |
| `uv run pytest apps/studio/backend/tests` | 0 | **1395 passed, 1 skipped, 2 warnings** in 94.57s |
| `uv run pytest packages/graph-agent-gateway/tests` | 0 | **309 passed, 1 xfailed** in 2.34s |
| `uv run pytest packages/graph-agent/tests` | 0 | **1450 passed, 2 skipped, 4 xfailed, 2 xpassed** in 24.63s |
| `uv run --with pip-audit pip-audit` | 0 | **No known vulnerabilities found**(0 CVE) |

- **结论**:**全绿**。后端三套 pytest 整套跑(非子集),无 full-suite-only 失败模式触发;
  0 CVE。证明本 spec 未对 Python 后端引入任何回归。

---

## §4. 手工 Smoke(Open/Attach/starting/degraded/Close/quit/workspace-owned/只读 Detach)

- **是否真机跑了**:**否**。原因:本沙箱**无图形显示服务**(`DISPLAY` 空、无 Wayland、无 `Xvfb`),
  Tauri 桌面 GUI 无处渲染;且 9 个场景是多步交互 + 真实 ah 编队生命周期,属真机 GUI 人工点验,
  自动化不可替代。系统库虽已就绪(足以让 `cargo test` 编译跑通),但"能编译测试"≠"能拉起交互 GUI"。
- **产出替代**:一份 **operator/PM 真机逐项点验清单**,已落盘
  `.kiro/specs/studio-ah-state-contract-v1/task11-manual-smoke-checklist.md`,
  按 task 11 枚举的全部 9 条场景逐条写清「如何触发 / 预期看到什么 / 对应 Req / 代码锚点 / 勾选栏」。
- 说明:未尝试装系统库或用其它花招硬拉 GUI(遵 task 11 约束);仅按 (a) 实测确认限制成立
  (`DISPLAY` 空 + 无 Xvfb),(b) 改产清单。

---

## 总结论

| 门禁 | 结论 |
|---|---|
| §1 Rust crate `cargo test --lib` | **GREEN**(166 passed;唯一失败 `publish_package_writer_maps_permission_error` = 既有 root 沙箱环境红,`native_fs.rs` 未被本 spec 触碰,证伪为非本次引入) |
| §2 前端 lint / typecheck / test / build | **GREEN**(1851 tests 全过;投影测试 56 过) |
| §3 Python ruff / mypy×3 / pytest×3 / pip-audit | **GREEN**(全 EXIT 0,0 CVE) |
| §4 手工 smoke | **未真机跑**(无显示服务)→ 已产出 operator/PM 点验清单 |

- **无本次引入的新红**。唯一红项为环境性既有红,已证伪并记录,不阻塞。
- tasks.md 的 task 11 checkbox 未改动(留 master 核实后自行勾)。
- 未碰 `ah.toml` / `apps/studio/tauri/vendor/` / `.operator-report.phase1`。
