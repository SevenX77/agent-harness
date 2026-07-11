---
spec: studio-ah-state-contract-v1
status: Draft (round 1 per operator-review-findings.md F1-F8; round 2 per d1-review.md NF1/NF2 + o1-review.md 坑洞 3.1-3.5, 2026-07-10)
target_goal: "按 ah v1.4.0+ 状态合约重做 Studio ah 状态检测与清理"
last_updated: 2026-07-10
revision_source: operator-review-findings.md; d1-review.md; o1-review.md
revision_trace: REVISION-TRACE.md
---

# Implementation Plan

本文档执行 `.kiro/specs/studio-ah-state-contract-v1/design.md`。实现目标是让 Studio 的 ah 状态检测、Open/Attach、Close、app quit cleanup 全部通过 ah v1.4.0+ 的结构化状态合约完成，并显式覆盖 `starting`/`degraded` 相位与所有权安全边界。

## 实现约束

- 先写能复现当前漂移问题的失败测试，再改生产代码。
- 不读取 ah sqlite。
- 不解析 `ah ps` 文本来决定 active/attach/cleanup。
- 不直接用 tmux session name 推断 master 或 worker 是否活着。
- 普通 cleanup 不直接 kill tmux，必须走 ah ownership guard。
- `starting` 相位一律 hands-off；`degraded` 相位必须有可用的 cleanup-then-open 路径，不允许三个按钮全灭。
- 生命周期命令（start/stop/kill）只对 Studio-managed temp config 生效；workspace 自带 config 只读。
- **护栏先行**：所有权分类 + env clamp（任务 5）必须在任何会发出 `ah start`/`stop`/`kill` 的任务（任务 6/7）之前落地，绝不出现"能发命令但护栏未接"的中间态。
- **身份判据（第二轮修订）**：快照身份以 `state_dir` + 会话身份（`session_id`/`path`/`project_id`）为权威，`config_path` 仅诊断；路径比对一律 Windows↔WSL 归一，绝不 raw string。
- **sequence 作用域（第二轮修订）**：`sequence` 单调仅限单订阅流/同 `session_id` 生命周期；`reason:"initial"`、新订阅、`session_id` 变化时无条件重置缓存，不得用旧序号挡新帧。
- **env clamp 机制（第二轮修订）**：钳制注入 bash `-c` 字符串（`export AH_STATE_DIR="";…`），不是仅 `Command::env`；且它不保证 1.5.0 读面 daemon 隔离，读面隔离靠身份校验。
- 不假设未验证的 CLI 行为——任何"预期 ah 应该这样做"的断言，先用真实 ah CLI 复现记录，再写 fixture 和生产代码。

- [x] 0. 前置 CLI 行为验证（不写生产代码，先拿真实证据）
  - 用已安装的 ah（1.4.0 与 1.5.0）验证 `ah start` 对一个已有 active stack 的同 config 是否真的拒绝／如何拒绝，记录退出码/stderr/snapshot 形状，供 Requirement 3.4 使用。
  - 用真实 CLI 复现 F1：daemon 不存在时 `ah status --json`（无 JSON，exit 1，stderr 文本）与 `ah events --format json`（结构化 `daemon_absent` 快照）的输出差异，作为 fixture 的原始来源。**前置条件（NF-caveat）**：daemon-absent 分支必须在**零 ahd 运行**的干净机器/环境上采集——在有活跃编队的机器上 `ah status`/`ah events` 会经全局机制连上任何正在跑的 daemon，采到的是残留编队快照而非 daemon-absent（2026-07-10 实测：本机有活编队时无法独立复现 F1 分支）。
  - 复现 F8 新增证据：同一含 `ah.toml` 的 cwd、无 `--config` 时，`status`/`ps` 落 default state dir、`events` 走 project discovery，记录具体输出用于 Requirement 2.7/4.8 的 fixture。
  - **复现 NF1（身份击穿）**：`ah --config <隔离空项目> events --format json` 首帧快照的 `config_path` 是否被原样回显成请求路径，而 `state_dir`/`sessions` 却指向另一套活 daemon；同时记录 live daemon 顶层 `config_path` 可为 `null`。用于 Requirement 2.7/4.8 的"`config_path` 匹配但 `state_dir`/会话身份不匹配即丢弃"fixture（2026-07-10 已在 1.5.0 观测到）。
  - **复现 NF2（读面忽略 env clamp）**：`env AH_STATE_DIR=<新空目录> ah status --json`（及 `ah events`）是否仍返回活编队的 `state_dir`。用于坐实 Requirement 4.7a 的作用域限定，并说明 env clamp 不能作为读面隔离承重手段（2026-07-10 已在 1.5.0 观测到仍连活编队）。
  - **复现坑洞 3.2（sequence 恒为 1）**：多次 `ah status --json` 的 `sequence`/`reason` 是否恒为 `1`/`"initial"`，events 流首帧是否同为 `sequence:1/reason:"initial"`。用于 Requirement 2.1 的 sequence-reset fixture（2026-07-10 已在 1.5.0 观测到恒为 1/initial）。
  - 采集一份真实 `degraded` 快照（`active:false, runtime_state:"degraded"`，某 session `status:"ACTIVE"`、`live_agents`、`cleanup_required:true`、master tmux 死）与一份 `starting` 快照，作为 Requirement 3.6/3.7 的 fixture 来源。
  - 产出：本任务的证据落盘到 fixture 目录旁的 raw-capture 文件，供任务 1 直接消费，不允许凭 README 示例或印象编造。
  - _Requirements: 2.1, 2.7, 3.4, 4.7a, 4.8, 5.8, 5.10, 5.13; 证据来源 F1, F2, F8, NF1, NF2, o1 坑洞 3.2_

- [x] 1. 建立 ah v1.4.0+ contract fixtures
  - 添加 active、inactive、starting、degraded、daemon absent、`CLOSED`、`FAILED`、unsupported schema 的 snapshot fixture，全部来自任务 0 采集的真实输出（含 `ahd_alive`、`sequence`、`reason`、`live_agents`、`db_tracked_agents`、`safe_to_cleanup`、`cleanup_required`、可空 `config_path`、`sessions[].session_id`/`path`/`project_id` 等真实字段，不是 README 示例字段）。
  - 添加 supported / unsupported / unparsable ah version fixture，只覆盖 `ah version` 裸版本号一种格式（Req 1.8 已简化为单一 `ah version` + trim，不再解析 `ah --version` 前缀格式）。
  - 添加 sequence-reset fixture（Req 2.1 / 坑洞 3.2）：同一流内 `sequence` 递增到 >1 后，再来一帧 `reason:"initial"`/`sequence:1`（新订阅、one-shot `status`、daemon 重启、或 `session_id` 变化）——用于验证"无条件重置后应用，而非按旧序号丢弃"。
  - 添加 workspace-owned config（如本仓根 `ah.toml`）与 Studio temp config 并存的 fixture，用于验证所有权分类；并为 workspace-owned 项加 `readOnly:true`、Studio temp 项加 `readOnly:false`，供 payload 与只读 UI 语义测试使用。
  - 添加身份校验 fixture（Req 2.7/4.8 / NF1 / 坑洞 3.1）：(a) `config_path` **匹配请求路径但 `state_dir`/会话身份不匹配**（NF1 回显击穿形态，须被丢弃）；(b) Windows 请求路径（`C:\...`）对 WSL 快照路径（`/mnt/c/...`）同一 canonical 目标——用于验证跨平台归一比对成功、raw string 比对会失败。
  - _Requirements: 1.1, 1.2, 1.8, 2.1, 2.4→2.5, 2.7, 4.8, 5.1, 5.3, 5.4, 5.6, 5.7, 5.9, 5.10, 5.12, 5.13, 5.14_

- [x] 2. 接入 ah version gate（单源 + 覆盖 events 订阅）
  - **先写红测试**：`test_version_gate_rejects_below_1_4_0`（< 1.4.0 fixture → 断言 block 且不发起 events 订阅，Req 5.4/1.6）；`test_version_parse_uses_bare_ah_version`（断言只调 `ah version` bare + trim，无 `ah --version` 第二 token 解析路径，Req 1.8）。
  - 在 Rust 层定义唯一的最低版本常量；把 launcher shell 脚本模板中现有 4 处独立 `awk >= 1.3.4` 检查（lib.rs:1754/1836/1903/1960）改为引用同一个值，并统一改用单一 `ah version` 命令（去掉 `ah --version | awk '{print $2}'` 的第二 token 解析），全代码库只保留一条版本探测规则（Req 1.5/1.8）。
  - 在 start、attach、status、cleanup、**events 订阅**前统一检查 ah 最低版本；events 订阅同样必须先过版本门，不允许对 < 1.4.0 的 ah 发起订阅并无限重生（lib.rs:1355 起）。
  - 版本检查结果按 app session 缓存，不对每次 ah 调用重新执行（Windows 下每次是一次 wsl.exe 往返）。
  - 旧版本、无法解析版本、缺少 ah binary 都要 fail fast，并返回可操作诊断。
  - 保持已有安装/provisioning 入口，不让旧版本继续进入生命周期命令。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 5.4_

- [ ] 3. 用结构化 snapshot 替换一次性状态检测，并加身份校验（须与任务 4 同批落地）
  - **先写红测试**：`test_identity_rejects_config_path_match_state_dir_mismatch`（NF1 回显 fixture → 断言丢弃 + 诊断，Req 5.10a）；`test_identity_canonicalizes_windows_wsl_path`（`C:\...` vs `/mnt/c/...` 同 canonical → 断言接受，raw string 比对会红，Req 5.10b）。
  - 将 one-shot bootstrap 读切到 `ah --config <path> status --json`，但不把它的非结构化失败当作权威"无 runtime"信号（见任务 4 的 events-primary 仲裁）。二者高度耦合，必须同一 PR 落地，避免出现 task 3 单独存在时 status 仍被当主决策面的中间态。
  - 引入 typed parser，显式校验 `schema_version`，字段按 design.md 修订后的模型（`ahdAlive`、`sequence`、`reason`、可空 `configPath`、`liveAgents`/`dbTrackedAgents`、`safeToCleanup`/`cleanupRequired`、`sessions[].sessionId`/`path`/`projectId`）。
  - 加入快照身份校验：以 `state_dir` + 会话身份（`sessions[].session_id`/`path`/`project_id`）为权威判据；`config_path` 仅作诊断辅助，**不得**单独作身份依据（它在无 config 的 daemon 上为 `null`、且被 `--config` 原样回显，匹配零鉴别力——NF1）。所有路径比对先做 Windows↔WSL 归一，绝不 raw string 比对；`project_id`（目录 basename 派生）是最稳的跨平台锚点。Studio 需独立推导所请求 config 的期望身份，不信任回显的 `config_path`。不匹配则丢弃并给诊断，不采信。
  - 让 `active`、`runtime_state`、terminal session、master/worker health 都来自 parsed snapshot。
  - 移除 normal decision path 对 `ah ps` 文本解析和 tmux 探测的依赖。
  - _Requirements: 2.1, 2.4→2.5(schema), 2.6, 2.7, 3.5, 3.8, 4.8, 5.2, 5.10_

- [ ] 4. 升级 live status subscription 为主决策面 + sequence 仲裁（须与任务 3 同批落地）
  - **先写红测试**：`test_sequence_reset_on_reason_initial`（流内升到 >1 后来一帧 `reason:"initial"`/`sequence:1` → 断言无条件重置并应用，而非按旧序号丢弃；含 `session_id` 变化分支，Req 5.13）；`test_sequence_guard_within_stream`（同流内真正的旧序号仍被丢弃）；`test_daemon_absent_prefers_events_over_status_stderr`（Req 5.11）。
  - 将 `ah events --format json` 的每一行都按完整 snapshot 解析，设为 open/attach/close 决策的主输入。
  - `sequence` 仲裁限定在**单订阅流 / 同 `session_id` 生命周期内**：识别到新（重）建订阅、`reason:"initial"` 帧、或 `session_id` 变化时，**无条件重置** applied-sequence 缓存再应用，不得用旧序号挡新帧；重置后同流内旧序号才不覆盖新序号已应用的状态（Req 2.1 / 坑洞 3.2）。
  - `status --json` 仅在尚无 events 订阅结果时作为 bootstrap 输入（其 `sequence` 恒为 1/`reason:"initial"`，属重置信号，不能当"旧序号"挡掉后续 events）。
  - daemon-absent 场景：`status --json` 非结构化失败时，在单一具名超时常量（默认 3s）内等待/触发 events 订阅拿到结构化 `daemon_absent` 快照再决策；超时则回落到 inconclusive `inactive`-可启动态（不是 `error`），不直接把 CLI stderr 当作错误态展示（Req 2.3）。
  - 保持现有 `code-assistant-status-changed` 前端事件边界的语义定位（但 payload 形状按任务 8 重做）。
  - 明确处理 ahd alive 但 `active=false`，UI 应显示 Open。
  - 对 unsupported schema、invalid JSON、stream drop、身份校验失败输出诊断而不是本地猜测。
  - _Requirements: 2.1, 2.2, 2.3, 2.6, 3.1, 3.2, 3.3, 5.1, 5.11, 5.13_

- [ ] 5. 加入 config 所有权分类与环境变量钳制（护栏先行：须在任务 6 发出 `ah start` 之前落地）
  - **先写红测试**：`test_lifecycle_only_on_studio_managed_config`（workspace-owned config 只收 read-only 命令、绝不收 start/stop/kill，Req 5.9）；`test_env_clamp_in_bash_string`（断言构造出的 bash `-c` 字符串含 `export AH_STATE_DIR=""; ...` 前缀，而非仅 `Command::env`，Req 4.7）。
  - 实现所有权分类器：`find_ah_config` 向上发现的 config 默认判定为 workspace-owned（只读：`status`/`events`/观察性 attach），只有 Studio 自己注册的 temp config 才是 Studio-managed（可执行 start/stop/kill）。
  - `ah_config_for_status`（lib.rs:828-833）的"优先取发现的 config"逻辑改为先过所有权分类器，再决定可执行哪些命令。
  - 在 `run_ah_config_command_output`（lib.rs:858）/ `spawn_ah_events_command`（lib.rs:879）等所有经 `wsl.exe -e bash -lc` 的 ah 调用点，把 `AH_STATE_DIR`、`CCBD_STATE_DIR`、`XDG_STATE_HOME` 的钳制**注入 bash `-c` 命令字符串本身**（`export AH_STATE_DIR=""; ...`），不是仅用 Rust `Command::env`——登录 shell 会在继承 env 后 source 用户 profile 覆盖掉 `Command::env` 设的值（坑洞 3.5）。（lib.rs:927 是 tmux socket 调用不是 ah，但同样吃登录 profile。）
  - 明确此钳制只防"写面互相污染 state dir"，**不**保证 1.5.0 读面 `status`/`events` 连哪套 daemon（NF2 / Req 4.7a）——读面隔离承重责任在任务 3 的身份校验，不在此钳制。
  - _Requirements: 4.6, 4.7, 4.7a, 5.9_

- [ ] 6. 重做 Open/Attach 决策，覆盖 starting/degraded 相位（依赖任务 5 的所有权护栏已就位）
  - **先写红测试**：`test_starting_is_hands_off`（starting fixture → 无清理/无重复启动/UI 显示 starting 不报错，Req 5.6）；`test_degraded_exposes_working_open`（degraded+`cleanup_required` fixture → Open 可用走 cleanup-then-start，不三态全灭，Req 5.7）。
  - Open 前读取 selected config 的当前快照（events-primary，status fallback）。
  - `runtime_state=active` 时进入 attach 路径。
  - `runtime_state=inactive` 且所有 session 终态时才允许 start——发 `ah start` 前必须先过任务 5 的所有权护栏（只对 Studio-managed config 允许）。
  - `runtime_state=starting` 时 hands-off：不清理、不重复启动、UI 显示 starting，不报错。
  - `runtime_state=degraded` 时按 `sessions[].cleanup_required`/`safe_to_cleanup` 先清理再 start，Open 按钮必须可用，不得三态全灭。
  - 同 config 已有 active stack 时的 duplicate-start 处理，必须基于任务 0 记录的真实 `ah start` 行为实现，不得凭假设实现。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 5.6, 5.7, 5.8_

- [ ] 7. 重做 Close 和 app quit cleanup
  - **先写红测试**：`test_cleanup_targets_only_cleanup_required_sessions`（多 session 快照 → 只对 `cleanup_required`/非 `safe_to_cleanup` 的 session id 发 `ah kill`，Req 5.5）；`test_quit_leaves_workspace_owned_config_untouched`（本仓根 `ah.toml` fixture → Close/quit 不发任何生命周期命令，Req 5.9）。
  - Close 先确认目标 config 是 Studio-managed（绝不对 workspace-owned config 发生命周期命令），再调用 `ah stop`。
  - stop 后重新读取当前快照（events-primary，status fallback）。
  - 如需强制清理，只对 selected snapshot 中 `cleanup_required`/非 `safe_to_cleanup` 的 session id 调 `ah kill --session <id> --force`，不再自行推导"非终态即 kill"。
  - app quit 只清理 Studio 注册过或 Studio temp namespace 下的 config；确认不触碰 workspace-owned config（包括本仓根 `ah.toml` 这类操作者自己的编队）。
  - 不清理用户手动在 default state dir 启动的 ahd。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.9_

- [ ] 8. 重做前端事件 payload 为 per-assistant 状态枚举
  - **先写红测试**：`test_payload_reports_claude_codex_independently`（双活跃 fixture → 两者各自真实状态、无 claude-wins 抑制，Req 5.12）；`test_payload_carries_readonly_flag`（workspace-owned → `readOnly:true`，Studio temp → `readOnly:false`，Req 5.12）。
  - 把 `{claude: bool, codex: bool}`（lib.rs:63-73）改为 per-assistant `{status: inactive|starting|active|degraded|error, reason?, readOnly: bool}`；直接改，不做双格式兼容层。`readOnly` 由任务 5 所有权分类器给出（workspace-owned=true / Studio-managed=false，Req 6.1）。
  - 删除 claude-wins 抑制逻辑（`if status.claude { status.codex = false; }`，lib.rs:1244-1246）。
  - 更新 `copilot-panel.tsx` 的投影逻辑以消费新 payload，验证既有的双活跃分支（copilot-panel.tsx:303-306）能正确显示 claude/codex 各自真实状态。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.12_

- [ ] 9. 验证前端按钮投影（含 starting/degraded + 只读 Detach）
  - **先写红测试**：`test_readonly_active_close_is_detach`（`readOnly:true`+active fixture → Close 呈现为 Detach、只关本地 tab、不发 `ah stop`/`ah kill`，Req 5.14）；`test_readonly_inactive_open_disabled`（`readOnly:true`+inactive → Open 置灰带引导文案、不发任何生命周期命令，Req 5.14）。
  - 用 fixture 验证 Open/Attach/Close/Starting/Degraded/Error 状态只由 identity-checked normalized snapshot 决定。
  - 覆盖 ahd alive、`active=false`、terminal sessions 时按钮恢复 Open。
  - 覆盖 unsupported contract 时显示错误状态，不显示 Attach。
  - 覆盖 `starting` 时按钮禁用且不报错；`degraded` 时 Open 可用（cleanup-then-open）。
  - 覆盖只读（workspace-owned）assistant：active 时 Close→Detach（仅断开本地观察，不发 stop），inactive 时 Open 置灰带引导文案（Req 6.4）。
  - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7, 5.1, 5.4, 5.6, 5.7, 5.14_

- [ ] 10. 设计文档回写（F7，须与实现同 PR）
  - 更新 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md:185-193`：加入 `starting`/`degraded` 相位语义（此前该段写"runtime_state 只有 Active/Degraded/Inactive、没有 Starting"，已被 ah 1.3.4 证伪）。
  - 更新同文件 629-644：把"`ah ps` 输出解析必须提取 tmux session id 供 double-check/兜底"这类内容，从"必须遵守的规则"改写为与本 spec 一致的 events-primary + ownership guard 表述；不再要求解析 `ah ps` 作为决策依据。
  - 更新同文件 553 与 644："`ah status` 不是可用命令"——1.4.0 起为假，需订正为 `status --json` 作为 bootstrap/fallback 读的正确用法（含 F1 的 daemon-absent 注意事项）。
  - 更新 `apps/studio/tauri/src/lib.rs:550` 的 moirai-intro skill 文本中同一句"ah status 不是可用命令"的表述；本 spec 与 moirai spec 都要改这一行，本 spec 先行落地，moirai spec 后续 rebase。
  - _Requirements: 对应 design.md Overview 与本文件任务 5/8 的行为变更_

- [ ] 11. 跑 focused verification
  - 运行 Tauri/Rust ah adapter 相关测试。
  - 如果触及 frontend projection，运行 Copilot panel 相关前端测试。
  - 使用安装后的 ah v1.4.0+ 手工 smoke：Open、Attach、master `/exit` 后回到 Open、`starting` 期间 hands-off、`degraded` 期间 Open 可用、Close、app quit cleanup、workspace-owned config（如本仓根 `ah.toml`）在 Close/quit 时保持不受影响、只读 assistant 的 Close 为 Detach（仅断开观察、编队仍活）。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14_
