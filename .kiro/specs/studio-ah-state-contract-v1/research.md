---
spec: studio-ah-state-contract-v1
status: Draft
target_goal: "Studio 接入 ah v1.4.0 状态合约，消除 Open/Attach/Cleanup 状态漂移"
linked_code_paths:
  - apps/studio/tauri/src/lib.rs
  - apps/studio/frontend/src/components/copilot/copilot-panel.tsx
  - apps/studio/frontend/src/lib/tauri.ts
last_updated: 2026-07-10
revision_note: "历史 Research Log / Design Decisions 原样保留；2026-07-10 追加实测证据节，见文末"
---

# Research: Studio ah v1.4.0 状态合约接入

## Summary

- **Feature**: Studio ah State Contract V1
- **Discovery Scope**: Complex Integration
- **Key Findings**:
  - ah 最新版本为 `v1.4.0 - 2026-07-09`，官方称其为 state-contract release。
  - v1.4.0 新增 `ah status --json`、snapshot schema v2、`CLOSED` session lifecycle、`ah ps --all` 与 status column、bare-start guard、kill ownership guard。
  - Studio 当前风险不在 UI 本身，而在 Tauri 层同时使用 `ah events`、`ah ps` 文本解析、tmux 探测来推断同一件事，导致状态来源不唯一。

## Research Log

### ah v1.4.0 状态合约

- **Context**: 用户遇到 master `/exit` 后 UI 显示 Open，但 ahd 仍在；另有 ahd 未清干净但按钮已恢复可打开的状态，需要判断 ah 与 Studio 的责任边界。
- **Sources Consulted**:
  - [ah v1.4.0 release](https://github.com/SevenX77/ah/releases/tag/v1.4.0)
  - [ah v1.4.0 CHANGELOG](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/CHANGELOG.md)
  - [ah v1.4.0 README](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/README.md)
- **Findings**:
  - `ahd` owns state, sessions, workers, recovery, and event streams; `ah` CLI drives it over JSON-RPC.
  - `ah status --json` 是面向集成方的一次性机器可读 runtime snapshot。
  - `ah events --format json` 输出完整 JSONL snapshot；消费者不需要合并 delta，也不需要自行探测 tmux。
  - `active` 只有在 ahd inventory 有活动 session、master tmux session/pane 活着、所有非终态 worker/agent tmux session 活着时才为 true。
  - v1.4.0 引入 schema v2 与 `CLOSED` session lifecycle，关闭语义应由 ah 明确表达。
  - bare-start guard 会让未配置目录中的 `ah start` 直接报错，避免污染默认 state。
  - kill-safety hardening 将 cleanup 约束到 daemon 自己的 marker，避免误杀其他 stack。
- **Implications**:
  - Studio 应把 ah 结构化 snapshot 作为唯一状态来源。
  - Studio 不应读 ah sqlite、解析 `ah ps` 文本、按 tmux 名称猜测 master/worker 是否活着。
  - `ahd alive && active=false` 是合法状态，不应被 Studio 自动解释成清理失败。

### README 与 release note 的 schema 版本差异

- **Context**: release/changelog 明确说 v1.4.0 是 schema v2；README 的 runtime events 示例仍显示 `schema_version: 1`。
- **Sources Consulted**:
  - [ah v1.4.0 release](https://github.com/SevenX77/ah/releases/tag/v1.4.0)
  - [ah v1.4.0 README](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/README.md)
- **Findings**:
  - 这是外部文档之间的暂时不一致。
  - 集成实现不能硬编码 README 示例，而应使用安装后的 `ah status --json` 与 `ah events --format json` 实际输出建立 fixture。
- **Implications**:
  - Studio parser 必须显式检查 `schema_version`。
  - 未支持的 schema 版本必须 fail fast，而不是静默降级到旧推断逻辑。

### Studio 当前状态来源

- **Context**: 用户截图显示 UI 可 Open，但 WSL 中仍有 ahd service；此前现场检查显示 dead master pane 和历史 session 容易混淆。
- **Findings**:
  - 当前 UI 通过 Tauri event 投影按钮状态，本身只是消费 `active`。
  - Tauri 层同时有独立 probe：调用 `ah ps`、解析 `sess_*`、列 tmux sessions，并把 `master_*` session name 当作活性证据。
  - 这种 probe 会把历史 inventory 或 dead pane 误判成可 attach 的 runtime。
- **Implications**:
  - 主要修复点在 Tauri ah adapter。
  - Frontend 应继续保持薄投影，不增加第二套状态机。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Studio 自行探测 | `ah ps` + tmux + sqlite 拼出状态 | 短期不依赖新 ah | 状态来源多，容易和 ahd 漂移 | 应废弃 |
| 读取 ah sqlite | 直接查 `sessions` / `agents` 表 | 字段丰富 | 越过 ah 公共边界，schema 易变 | 不符合边界纪律 |
| ah structured contract | `ah status --json` + `ah events --format json` | 单一状态来源，符合 v1.4.0 合约 | 需要最低版本门槛 | 选定方案 |

## Design Decisions

### Decision: ah structured snapshot 是 lifecycle SSOT

- **Context**: Studio 不能同时相信 events、ps、tmux 和 sqlite。
- **Alternatives Considered**:
  1. 保留现有 probe，只修 dead pane 判断。
  2. 读取 ah sqlite 表。
  3. 使用 v1.4.0 的 `ah status --json` 与 `ah events --format json`。
- **Selected Approach**: 选 3。一次性状态走 `ah status --json`，实时状态走 `ah events --format json`。
- **Rationale**: v1.4.0 已把该能力定义为正式集成合约。
- **Trade-offs**: Studio 需要强制 `ah >= 1.4.0`。
- **Follow-up**: 实现前用本机 v1.4.0 采集真实 JSON fixture。

### Decision: Cleanup 走 ah ownership guard，不直接 kill tmux

- **Context**: 直接 `tmux kill-session` 绕过 ah 的所有权模型。
- **Alternatives Considered**:
  1. Studio 继续直接杀 tmux。
  2. Studio 只调用 `ah stop`。
  3. Studio 先 `ah stop`，必要时只对 selected snapshot 中的 session id 调 `ah kill --session ... --force`。
- **Selected Approach**: 选 3。
- **Rationale**: 保留强制清理能力，同时让 ah 的 marker / ownership guard 生效。
- **Trade-offs**: 如果 ah 自身 cleanup 有 bug，Studio 不再绕过它，需要把问题反馈到 ah。
- **Follow-up**: 为 app quit、手动 Close、Open 前清理分别建测试 fixture。

## Risks & Mitigations

- ah README 示例和 release note schema 版本不一致：实现以真实 v1.4.0 CLI 输出为准，并对 schema 做显式门禁。
- 用户本机仍是旧 ah：启动/打开入口先做版本检查，提供升级说明。
- ahd alive 但 inactive 被误解为异常：需求中明确这是合法状态，UI 显示 Open。

## References

- [SevenX77/ah v1.4.0 release](https://github.com/SevenX77/ah/releases/tag/v1.4.0)
- [SevenX77/ah v1.4.0 CHANGELOG](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/CHANGELOG.md)
- [SevenX77/ah v1.4.0 README](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/README.md)

## 2026-07-10 实测证据补充（operator review, F1-F8）

本节只追加 operator 评审期间用真实 ah CLI（WSL，评审时 1.4.0，标注处已在 1.5.0 复验）实测到的、与上面历史结论不一致或历史结论未覆盖的事实。**不改写上面的历史 Research Log / Design Decisions**——上面记录的是当时基于 release/CHANGELOG/README 调研得出的判断，其中一部分被下面的真实 CLI 行为证伪或补完，处置方式记录在 `requirements.md`/`design.md` 的修订里，不在本节倒填历史结论。完整发现文本见 `operator-review-findings.md`（F1-F9），逐条落地位置见 `REVISION-TRACE.md`。

- **F1 — `status --json` 与 `events --format json` 在 daemon-absent 时行为不对称**：daemon 不存在时，`ah status --json` exit 1、stderr 为人话文本 `"ahd daemon is not running at ..."`、无 JSON 输出；同场景 `ah events --format json` 输出结构化快照 `{"reason":"daemon_absent","runtime_state":"inactive","ahd_alive":false,...}`。历史 Research Log 只调研了两个命令“各自输出结构化数据”，未发现两者在这个具体状态下不对称。1.4.0 与 1.5.0 表现一致。
- **F2 — `runtime_state` 有 `starting`/`degraded` 两个此前调研未落地的相位**：真实观测到 `active:false, runtime_state:"degraded"` 快照，一条 session `status:"ACTIVE"`（`live_agents=10`、master tmux 死、`cleanup_required:true`）。上游 ah 1.3.4 CHANGELOG 原文："Consumers such as Studio should clean up only `degraded` runtimes; `starting` means startup is still in progress and must be left alone." 历史调研的 "Findings" 小节完全未提 starting/degraded，`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md:185-193` 甚至写了"runtime_state 只有 Active/Degraded/Inactive、没有 Starting"——这句在 1.3.4 之后已经不成立。
- **F3 — 前端事件 payload 实测为 `{claude: bool, codex: bool}` 且存在 claude-wins 抑制**：`lib.rs:63-73` 定义 payload 形状，`lib.rs:1244-1246` 在 claude 为 true 时强制把 codex 置 false；而 `copilot-panel.tsx:303-306` 已有面向双活跃的 "Close assistants" 分支。两者不一致，说明前端已经准备好消费更丰富的状态，是后端 payload 落后。
- **F4a — workspace 自带 `ah.toml` 会被 Studio 的 `find_ah_config` 向上发现并优先使用**：本仓根自 PR #478 起有 `ah.toml`；`find_ah_config`（`lib.rs:203-218`）向上爬目录且优先于 temp config（`ah_config_for_status`，`lib.rs:828-833`）。在本仓任意子目录打开 Studio，Close/quit today 会对该 config 执行 `ah stop` + 强杀，而这个 config 可能就是 operator 自己在跑的 ah 编队。
- **F4b — `AH_STATE_DIR` 优先级 + Windows 登录 shell 会吃用户 profile**：ah README + 1.4.0 CHANGELOG #117 明文 `AH_STATE_DIR` 优先级高于显式 `--config`；Studio 在 Windows 上用 `wsl.exe -e bash -lc`（`lib.rs:858/879/927`）是登录 shell，会 source 用户 WSL profile。用户若 pin 过 `AH_STATE_DIR`，Studio 所有本应隔离的 temp config 会塌缩到同一个 state dir。
- **F4b 新增（2026-07-10，1.5.0 复验）— state-dir 解析口径不一致，且换了一边**：同一个含 `ah.toml` 的 cwd 下、不带 `--config` 时，`ah status` 与 `ah ps` 落到 default state dir，而 `ah events` 走 project discovery，落到不同的 state dir。这直接佐证 F4b 提出的"收到的 snapshot 必须做身份校验（`config_path`/`state_dir` 匹配所请求 config）"不是防御性冗余，而是两个读取面在真实环境下就是会给出不同答案。已列入 `upstream-issues-draft.md` 的第二条上游 issue。
- **F5 — 快照确有 `sequence` 字段**：真实快照里存在 `sequence`，可支撑"events 为主决策面、按 sequence 单调仲裁"的设计，K8s `resourceVersion` 是可类比的既有解法。
- **F6 — 版本门槛已有旧实现、版本解析两种格式并存**：生成的 launcher shell 脚本里已有 4 处独立 `awk` 版本门（`lib.rs:1754/1836/1903/1960`，门槛 `>= 1.3.4`），且该门未覆盖 events 订阅路径（`lib.rs:1355` 起）。实测 `ah version` 输出裸 `"1.4.0"`，`ah --version` 输出 `"ah 1.4.0"`，解析需分别处理。
- **F8 — 真实 v2 快照字段与 README 示例/既有 design 草案不一致**：`activeAgents` 不存在，实际字段是 `live_agents`（另有 `db_tracked_agents`）；顶层缺 `ahd_alive` 时无法实现 Requirement 3.3/测试 5.1；`configPath` 实测可为 `null`（daemon 无 config 启动时）；`sessions[]` 有 `safe_to_cleanup`/`cleanup_required`，ah 已经算好每个 session 的清理资格，不需要 Studio 自己用"非终态即 kill"这种推导重新造一遍。

以上事实已经收进 `requirements.md`（Req 1.5-1.8、2.1-2.7、3.4/3.6/3.7、4.6-4.8、Requirement 6）、`design.md`（Architecture、Data Models、Error Handling、Testing Strategy）与 `tasks.md`（任务 0/2/3/4/5/6/8/10）。
