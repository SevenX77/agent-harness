---
spec: studio-ah-state-contract-v1
status: Draft (revised per operator-review-findings.md F1-F8, 2026-07-09 review / 2026-07-10 revision)
target_goal: "按 ah v1.4.0+ 状态合约重做 Studio ah 状态检测与清理"
last_updated: 2026-07-10
revision_source: operator-review-findings.md
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
- 不假设未验证的 CLI 行为——任何"预期 ah 应该这样做"的断言，先用真实 ah CLI 复现记录，再写 fixture 和生产代码。

- [ ] 0. 前置 CLI 行为验证（不写生产代码，先拿真实证据）
  - 用已安装的 ah（1.4.0 与 1.5.0）验证 `ah start` 对一个已有 active stack 的同 config 是否真的拒绝／如何拒绝，记录退出码/stderr/snapshot 形状，供 Requirement 3.4 使用。
  - 用真实 CLI 复现 F1：daemon 不存在时 `ah status --json`（无 JSON，exit 1，stderr 文本）与 `ah events --format json`（结构化 `daemon_absent` 快照）的输出差异，作为 fixture 的原始来源。
  - 复现 F8 新增证据：同一含 `ah.toml` 的 cwd、无 `--config` 时，`status`/`ps` 落 default state dir、`events` 走 project discovery，记录具体输出用于 Requirement 2.7/4.8 的 fixture。
  - 采集一份真实 `degraded` 快照（`active:false, runtime_state:"degraded"`，某 session `status:"ACTIVE"`、`live_agents`、`cleanup_required:true`、master tmux 死）与一份 `starting` 快照，作为 Requirement 3.6/3.7 的 fixture 来源。
  - 产出：本任务的证据落盘到 fixture 目录旁的 raw-capture 文件，供任务 1 直接消费，不允许凭 README 示例或印象编造。
  - _Requirements: 3.4, 5.8; 证据来源 F1, F2, F8_

- [ ] 1. 建立 ah v1.4.0+ contract fixtures
  - 添加 active、inactive、starting、degraded、daemon absent、`CLOSED`、`FAILED`、unsupported schema 的 snapshot fixture，全部来自任务 0 采集的真实输出（含 `ahd_alive`、`sequence`、`live_agents`、`db_tracked_agents`、`safe_to_cleanup`、`cleanup_required`、可空 `config_path` 等真实字段，不是 README 示例字段）。
  - 添加 supported / unsupported / unparsable ah version fixture，覆盖 `ah version` 裸版本号与 `ah --version` 带前缀两种输出格式。
  - 添加"同一 config，events 与 status 同时给出不同 sequence 快照"的 fixture，用于验证仲裁规则。
  - 添加 workspace-owned config（如本仓根 `ah.toml`）与 Studio temp config 并存的 fixture，用于验证所有权分类。
  - 添加 `configPath`/`stateDir` 与请求 config 不匹配的 fixture，用于验证快照身份校验拒绝逻辑。
  - _Requirements: 1.1, 1.2, 1.8, 2.4→2.5, 2.7, 4.8, 5.1, 5.3, 5.4, 5.6, 5.7, 5.9, 5.10_

- [ ] 2. 接入 ah version gate（单源 + 覆盖 events 订阅）
  - 在 Rust 层定义唯一的最低版本常量；把 launcher shell 脚本模板中现有 4 处独立 `awk >= 1.3.4` 检查（lib.rs:1754/1836/1903/1960）改为引用同一个值。
  - 在 start、attach、status、cleanup、**events 订阅**前统一检查 ah 最低版本；events 订阅同样必须先过版本门，不允许对 < 1.4.0 的 ah 发起订阅并无限重生（lib.rs:1355 起）。
  - 版本检查结果按 app session 缓存，不对每次 ah 调用重新执行（Windows 下每次是一次 wsl.exe 往返）。
  - 旧版本、无法解析版本、缺少 ah binary 都要 fail fast，并返回可操作诊断。
  - 保持已有安装/provisioning 入口，不让旧版本继续进入生命周期命令。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 5.4_

- [ ] 3. 用结构化 snapshot 替换一次性状态检测，并加身份校验
  - 将 one-shot bootstrap 读切到 `ah --config <path> status --json`，但不把它的非结构化失败当作权威"无 runtime"信号（见任务 4 的 events-primary 仲裁）。
  - 引入 typed parser，显式校验 `schema_version`，字段按 design.md 修订后的模型（`ahdAlive`、`sequence`、可空 `configPath`、`liveAgents`/`dbTrackedAgents`、`safeToCleanup`/`cleanupRequired`）。
  - 加入快照身份校验：收到的 snapshot 的 `config_path`/`state_dir` 必须匹配所请求的 config，不匹配则丢弃并给诊断，不采信。
  - 让 `active`、`runtime_state`、terminal session、master/worker health 都来自 parsed snapshot。
  - 移除 normal decision path 对 `ah ps` 文本解析和 tmux 探测的依赖。
  - _Requirements: 2.1, 2.4→2.5(schema), 2.6, 2.7, 3.5, 3.8, 4.8, 5.2, 5.10_

- [ ] 4. 升级 live status subscription 为主决策面 + sequence 仲裁
  - 将 `ah events --format json` 的每一行都按完整 snapshot 解析，设为 open/attach/close 决策的主输入。
  - `status --json` 仅在尚无 events 订阅结果时作为 bootstrap 输入；两者都存在时按 `sequence` 仲裁，旧序号不得覆盖新序号已应用的状态。
  - daemon-absent 场景：`status --json` 非结构化失败时，等待/触发 events 订阅拿到结构化 `daemon_absent` 快照再决策，不直接把 CLI stderr 当作错误态展示。
  - 保持现有 `code-assistant-status-changed` 前端事件边界的语义定位（但 payload 形状按任务 9 重做）。
  - 明确处理 ahd alive 但 `active=false`，UI 应显示 Open。
  - 对 unsupported schema、invalid JSON、stream drop、身份校验失败输出诊断而不是本地猜测。
  - _Requirements: 2.1, 2.2, 2.3, 2.6, 3.1, 3.2, 3.3, 5.1, 5.11_

- [ ] 5. 重做 Open/Attach 决策，覆盖 starting/degraded 相位
  - Open 前读取 selected config 的当前快照（events-primary，status fallback）。
  - `runtime_state=active` 时进入 attach 路径。
  - `runtime_state=inactive` 且所有 session 终态时才允许 start。
  - `runtime_state=starting` 时 hands-off：不清理、不重复启动、UI 显示 starting，不报错。
  - `runtime_state=degraded` 时按 `sessions[].cleanup_required`/`safe_to_cleanup` 先清理再 start，Open 按钮必须可用，不得三态全灭。
  - 同 config 已有 active stack 时的 duplicate-start 处理，必须基于任务 0 记录的真实 `ah start` 行为实现，不得凭假设实现。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 5.6, 5.7, 5.8_

- [ ] 6. 加入 config 所有权分类与环境变量钳制
  - 实现所有权分类器：`find_ah_config` 向上发现的 config 默认判定为 workspace-owned（只读：`status`/`events`/观察性 attach），只有 Studio 自己注册的 temp config 才是 Studio-managed（可执行 start/stop/kill）。
  - `ah_config_for_status`（lib.rs:828-833）的"优先取发现的 config"逻辑改为先过所有权分类器，再决定可执行哪些命令。
  - 在 `run_ah_config_command_output` / `spawn_ah_events_command` 等所有经 `wsl.exe -e bash -lc` 的调用点（lib.rs:858/879/927 一带），显式清除或钳制 `AH_STATE_DIR`、`CCBD_STATE_DIR`、`XDG_STATE_HOME`，不吃用户 WSL 登录 profile 里的 pin 值。
  - _Requirements: 4.6, 4.7, 5.9_

- [ ] 7. 重做 Close 和 app quit cleanup
  - Close 先确认目标 config 是 Studio-managed（绝不对 workspace-owned config 发生命周期命令），再调用 `ah stop`。
  - stop 后重新读取当前快照（events-primary，status fallback）。
  - 如需强制清理，只对 selected snapshot 中 `cleanup_required`/非 `safe_to_cleanup` 的 session id 调 `ah kill --session <id> --force`，不再自行推导"非终态即 kill"。
  - app quit 只清理 Studio 注册过或 Studio temp namespace 下的 config；确认不触碰 workspace-owned config（包括本仓根 `ah.toml` 这类操作者自己的编队）。
  - 不清理用户手动在 default state dir 启动的 ahd。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.9_

- [ ] 8. 重做前端事件 payload 为 per-assistant 状态枚举
  - 把 `{claude: bool, codex: bool}`（lib.rs:63-73）改为 per-assistant `{status: inactive|starting|active|degraded|error, reason?}`；直接改，不做双格式兼容层。
  - 删除 claude-wins 抑制逻辑（`if status.claude { status.codex = false; }`，lib.rs:1244-1246）。
  - 更新 `copilot-panel.tsx` 的投影逻辑以消费新 payload，验证既有的双活跃分支（copilot-panel.tsx:303-306）能正确显示 claude/codex 各自真实状态。
  - _Requirements: 6.1, 6.2, 6.3, 5.12_

- [ ] 9. 验证前端按钮投影（含 starting/degraded）
  - 用 fixture 验证 Open/Attach/Close/Starting/Degraded/Error 状态只由 identity-checked normalized snapshot 决定。
  - 覆盖 ahd alive、`active=false`、terminal sessions 时按钮恢复 Open。
  - 覆盖 unsupported contract 时显示错误状态，不显示 Attach。
  - 覆盖 `starting` 时按钮禁用且不报错；`degraded` 时 Open 可用（cleanup-then-open）。
  - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7, 5.1, 5.4, 5.6, 5.7_

- [ ] 10. 设计文档回写（F7，须与实现同 PR）
  - 更新 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md:185-193`：加入 `starting`/`degraded` 相位语义（此前该段写"runtime_state 只有 Active/Degraded/Inactive、没有 Starting"，已被 ah 1.3.4 证伪）。
  - 更新同文件 629-644：把"`ah ps` 输出解析必须提取 tmux session id 供 double-check/兜底"这类内容，从"必须遵守的规则"改写为与本 spec 一致的 events-primary + ownership guard 表述；不再要求解析 `ah ps` 作为决策依据。
  - 更新同文件 553 与 644："`ah status` 不是可用命令"——1.4.0 起为假，需订正为 `status --json` 作为 bootstrap/fallback 读的正确用法（含 F1 的 daemon-absent 注意事项）。
  - 更新 `apps/studio/tauri/src/lib.rs:550` 的 moirai-intro skill 文本中同一句"ah status 不是可用命令"的表述；本 spec 与 moirai spec 都要改这一行，本 spec 先行落地，moirai spec 后续 rebase。
  - _Requirements: 对应 design.md Overview 与本文件任务 5/8 的行为变更_

- [ ] 11. 跑 focused verification
  - 运行 Tauri/Rust ah adapter 相关测试。
  - 如果触及 frontend projection，运行 Copilot panel 相关前端测试。
  - 使用安装后的 ah v1.4.0+ 手工 smoke：Open、Attach、master `/exit` 后回到 Open、`starting` 期间 hands-off、`degraded` 期间 Open 可用、Close、app quit cleanup、workspace-owned config（如本仓根 `ah.toml`）在 Close/quit 时保持不受影响。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10, 5.11, 5.12_
