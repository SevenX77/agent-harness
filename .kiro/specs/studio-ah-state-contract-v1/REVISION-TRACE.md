---
spec: studio-ah-state-contract-v1
doc: revision-trace
date: 2026-07-10
purpose: "operator-review-findings.md F1-F9 逐条 → 修订版 requirements/design/tasks/research/INDEX 的具体落点，供 a4 审计对照"
---

# Revision Trace (F1–F9 → 修订位置)

| # | 发现摘要 | requirements.md | design.md | tasks.md | research.md / 其他 |
|---|---|---|---|---|---|
| F1 | `status --json` daemon-absent 非结构化，无 JSON；`events` 同场景给结构化 `daemon_absent` | Req 2.2, 2.3（events 为主决策面，status 仅 bootstrap/fallback，不信 stderr 文本）；Req 5.11（回归测试） | Overview 第 1 点；Architecture flowchart（`STATUS` 标注 bootstrap/fallback）；System Flows "One-shot open decision" 的 daemon-absent 分支；Error Handling 第 4 条；Testing Strategy 集成测试第 2 条 | 任务 0（复现 F1 真实输出作为 fixture 来源）；任务 1（daemon-absent fixture 来源）；任务 4（events-primary + daemon-absent 处理） | research.md 2026-07-10 节 "F1" 段 |
| F2 | `runtime_state` 有 `starting`/`degraded`，degraded 下用户无任何可用操作；1.3.4 CHANGELOG 原文引用 | Req 3.6（starting hands-off）、3.7（degraded cleanup-then-open）、3.8；Req 5.6、5.7（对应测试） | Overview 第 2 点；System Flows "One-shot open decision" 的 starting/degraded 分支；Cleanup orchestrator 末条（degraded 清理仍限四个用户触发时机）；Testing Strategy 集成/回归测试 degraded 相关条 | 任务 0（采集真实 degraded/starting 快照）；任务 1（对应 fixture）；任务 5（Open/Attach 覆盖 starting/degraded）；任务 9（按钮投影覆盖 starting/degraded） | research.md 2026-07-10 节 "F2" 段 |
| F3 | payload `{claude,codex}` 表达力不足；design 自相矛盾（既要 error/starting/unsupported 又说保持现形状）；claude-wins 抑制与前端双活分支冲突 | Requirement 6（新增）：6.1 per-assistant 枚举、6.2 删 claude-wins、6.3 显式回答"单 workspace 单 ahd"不变量保留；Req 5.12（测试） | Data Models 新增 "Frontend event payload" 小节，直接替换旧 TS 形状并删除"保持现有事件形状"的自相矛盾表述；Testing Strategy 集成测试双活跃条 | 任务 8（重做 payload + 删抑制逻辑 + 前端投影更新） | research.md 2026-07-10 节 "F3" 段 |
| F4a | `find_ah_config` 向上爬目录且优先于 temp config；本仓根 `ah.toml`（PR #478）会被 Close/quit 当作目标误杀 operator 自己的编队 | Req 4.6（config 所有权二分类：workspace-owned 只读 / Studio-managed 全生命周期）；Req 5.9（测试） | Architecture "Config ownership classifier" 组件；Cleanup orchestrator 责任第 1、5 条；Testing Strategy 集成/回归测试所有权条 | 任务 6（实现所有权分类器，改写 `ah_config_for_status` 逻辑）；任务 7（Close/quit 确认目标是 Studio-managed） | research.md 2026-07-10 节 "F4a" 段 |
| F4b | `AH_STATE_DIR` 优先于 `--config`；Windows 登录 shell 吃用户 profile；1.5.0 复验 state-dir 解析口径不一致（status/ps 落 default、events 走 project discovery） | Req 2.7（快照身份校验）、4.7（env var 钳制）、4.8（身份校验落地条款，含 1.5.0 新证据引用）；Req 5.10（测试） | Architecture "Env clamp" 组件 + flowchart `ENV`/`IDCHECK` 节点；Runtime snapshot parser 不变量第 4 条；Testing Strategy 集成测试身份校验/env clamp 条 | 任务 0（复现 1.5.0 state-dir 不一致证据）；任务 1（身份不匹配 fixture）；任务 3（身份校验实现）；任务 6（env var 钳制实现） | research.md 2026-07-10 节 "F4b" 段；`upstream-issues-draft.md` issue #2 |
| F5 | events 常驻流 + status 一次性读，无仲裁语义；快照有 `sequence` | Req 2.1（events 为主，按 sequence 单调应用）、2.6 | Overview（events-primary 定位贯穿全文）；System Flows "Live status subscription" 显式画出 sequence 应用规则；Data Models `sequence` 字段；Testing Strategy 单元测试 sequence 仲裁条 | 任务 1（同 config 不同 sequence 的 fixture）；任务 4（仲裁实现） | research.md 2026-07-10 节 "F5" 段 |
| F6 | launcher shell 里已有 4 份独立 `>= 1.3.4` awk 门；版本门未覆盖 events 订阅（老 ah 无 events，3 秒一轮重生）；`ah version`/`ah --version` 输出格式不同 | Req 1.5（版本常量单源）、1.6（覆盖 events 订阅）、1.7（按 session 缓存）、1.8（两种版本输出格式解析） | Components "Tauri ah adapter" 职责第 1 条；Requirements Traceability 表 1.1-1.8 行 | 任务 2（单源常量 + 覆盖 events 订阅 + 缓存）；任务 1（两种版本输出 fixture） | research.md 2026-07-10 节 "F6" 段 |
| F7 | `ah-orchestration-design.md:185-193/629-644/553/644` 与 `lib.rs:550` moirai-intro 文本钉死旧模型，与本 spec 打架；未提回写任务 | （无独立 Requirement——回写属于交付纪律，落在 tasks.md） | Supporting References 末条注明"设计回写在同 PR" | 任务 10（新增：逐锚点回写设计文档 + moirai-intro 文本，注明与 moirai spec 的排序） | — |
| F8 | `activeAgents` 应为 `live_agents`+`db_tracked_agents`；缺 `ahd_alive`；`configPath` 可为 null；漏 `safe_to_cleanup`/`cleanup_required`；`ah start` 拒绝重复启动是未验证假设 | Req 3.4（duplicate-start 假设需前置验证，标注为待验证）、4.2（消费 `safe_to_cleanup`/`cleanup_required` 而非自行推导）；Req 5.8（前置验证测试项） | Data Models "Normalized runtime snapshot" 全量字段修订 + "Changes from the prior draft" 清单；Components "Runtime snapshot parser" state model；Cleanup orchestrator 职责第 3 条 | 任务 0（前置验证 `ah start` 真实行为）；任务 1（真实字段 fixture）；任务 3（typed parser 按修订字段实现）；任务 7（cleanup 消费 `cleanup_required`/`safe_to_cleanup`） | research.md 2026-07-10 节 "F8" 段 |
| F9 | INDEX 未登记本 spec；INDEX 阶段规则要求 design/tasks 由 PM 解锁，本 spec 四件套一日生成需补票 | — | — | — | `.kiro/specs/INDEX.md` 新增本 spec 一行（只加这一行，不动其他行）；PM（用户）终审本次修订视为补票，记录在 `.operator-report` |

## 验收标准逐条核对（对照 operator-review-findings.md 末尾"修订完成的验收标准"）

1. **F1-F8 每条有可指认的对应改动** — 见上表，每行至少落在 requirements.md 或 design.md 或 tasks.md 之一，且注明具体章节/条款号。
2. **不再含与真实 CLI 冲突的字段/行为断言** — design.md Data Models 已按 F8 修正字段名（`liveAgents`/`dbTrackedAgents`/`ahdAlive`/`sequence`/可空 `configPath`/`safeToCleanup`/`cleanupRequired`）；requirements.md Req 3.4 把"`ah start` 拒绝重复启动"从既定行为降级为"待前置验证的假设"，不再断言未验证事实。
3. **degraded/starting 全生命周期闭环** — Req 3.6/3.7（UI 语义）、design.md Cleanup orchestrator（清理资格，仅四个用户触发时机）、tasks.md 任务 0/1/5/9（fixture + 实现 + 测试）三层都有对应条目。
4. **每个新增声明都有出处** — requirements.md/design.md 正文内联标注 `(F1)`.. `(F8)` 及具体证据（行号/CLI 实测/CHANGELOG 引文）；research.md 2026-07-10 节汇总同一批证据。
5. **tasks.md 保持 TDD 顺序，含 F7 回写任务与 F8 前置验证项** — 任务 0 是前置验证（先于 fixture）；任务 1 fixture 先于任务 2+ 生产代码改动；任务 10 是 F7 设计回写任务。
