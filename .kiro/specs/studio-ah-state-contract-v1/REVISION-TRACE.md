---
spec: studio-ah-state-contract-v1
doc: revision-trace
date: 2026-07-10
purpose: "operator-review-findings.md F1-F9 逐条 → 修订版 requirements/design/tasks/research/INDEX 的具体落点，供 a4 审计对照"
---

# Revision Trace (F1–F9 → 修订位置)

| # | 发现摘要 | requirements.md | design.md | tasks.md | research.md / 其他 |
|---|---|---|---|---|---|
| F1 | `status --json` daemon-absent 非结构化，无 JSON；`events` 同场景给结构化 `daemon_absent` | Req 2.2, 2.3（events 为主决策面，status 仅 bootstrap/fallback，不信 stderr 文本）；Req 5.11（回归测试） | Overview 引言段/第 2 点（events-primary、status 为 bootstrap/fallback）；Architecture flowchart（`STATUS` 标注 bootstrap/fallback）；System Flows "One-shot open decision" 的 daemon-absent 分支；Error Handling 第 4 条；Testing Strategy 集成测试第 2 条 | 任务 0（复现 F1 真实输出作为 fixture 来源）；任务 1（daemon-absent fixture 来源）；任务 4（events-primary + daemon-absent 处理） | research.md 2026-07-10 节 "F1" 段 |
| F2 | `runtime_state` 有 `starting`/`degraded`，degraded 下用户无任何可用操作；1.3.4 CHANGELOG 原文引用 | Req 3.6（starting hands-off）、3.7（degraded cleanup-then-open）、3.8；Req 5.6、5.7（对应测试） | Overview 第 2 点；System Flows "One-shot open decision" 的 starting/degraded 分支；Cleanup orchestrator 末条（degraded 清理仍限四个用户触发时机）；Testing Strategy 集成/回归测试 degraded 相关条 | 任务 0（采集真实 degraded/starting 快照）；任务 1（对应 fixture）；任务 6（Open/Attach 覆盖 starting/degraded，第二轮 swap 后由原任务 5 变为任务 6）；任务 9（按钮投影覆盖 starting/degraded） | research.md 2026-07-10 节 "F2" 段 |
| F3 | payload `{claude,codex}` 表达力不足；design 自相矛盾（既要 error/starting/unsupported 又说保持现形状）；claude-wins 抑制与前端双活分支冲突 | Requirement 6（新增）：6.1 per-assistant 枚举、6.2 删 claude-wins、6.3 显式回答"单 workspace 单 ahd"不变量保留；Req 5.12（测试） | Data Models 新增 "Frontend event payload" 小节，直接替换旧 TS 形状并删除"保持现有事件形状"的自相矛盾表述；Testing Strategy 集成测试双活跃条 | 任务 8（重做 payload + 删抑制逻辑 + 前端投影更新） | research.md 2026-07-10 节 "F3" 段 |
| F4a | `find_ah_config` 向上爬目录且优先于 temp config；本仓根 `ah.toml`（PR #478）会被 Close/quit 当作目标误杀 operator 自己的编队 | Req 4.6（config 所有权二分类：workspace-owned 只读 / Studio-managed 全生命周期）；Req 5.9（测试） | Architecture "Config ownership classifier" 组件；Cleanup orchestrator 责任第 1、5 条；Testing Strategy 集成/回归测试所有权条 | 任务 5（实现所有权分类器，改写 `ah_config_for_status` 逻辑，第二轮 swap 后由原任务 6 前移为任务 5 以护栏先行）；任务 7（Close/quit 确认目标是 Studio-managed） | research.md 2026-07-10 节 "F4a" 段 |
| F4b | `AH_STATE_DIR` 优先于 `--config`；Windows 登录 shell 吃用户 profile；1.5.0 复验 state-dir 解析口径不一致（status/ps 落 default、events 走 project discovery） | Req 2.7（快照身份校验）、4.7（env var 钳制）、4.8（身份校验落地条款，含 1.5.0 新证据引用）；Req 5.10（测试） | Architecture "Env clamp" 组件 + flowchart `ENV`/`IDCHECK` 节点；Runtime snapshot parser 不变量第 4 条；Testing Strategy 集成测试身份校验/env clamp 条 | 任务 0（复现 1.5.0 state-dir 不一致证据）；任务 1（身份不匹配 fixture）；任务 3（身份校验实现）；任务 5（env var 钳制实现，第二轮 swap 后由原任务 6 前移为任务 5） | research.md 2026-07-10 节 "F4b" 段；`upstream-issues-draft.md` issue #2 |
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

---

## 第二轮修订（2026-07-10）

第一轮修订（PR #483, commit 880164ad）合入后，跑了两份独立评审并落盘本目录：
`d1-review.md`（commit d8682df8，严谨只读审，verdict「有条件批准」，核心是实测出的
NF1/NF2）与 `o1-review.md`（对抗审，verdict「不批准/细节返工」，5 条坑洞 + 忠实度审计）。
两份评审**都不质疑 events-primary + typed snapshot 状态合约这个方向本身**（o1 质疑 2.1
只打「所有权二分类」这条支路，且其前提已被 NF2 证伪）——不构成架构级推翻，由 d1 执笔
第二轮修订。本节记录逐条核实结论 + 修订落点。

### A. o1 独有断言的核实结论（先核实后采纳，附证据）

所有核实均为 2026-07-10 在 ah 1.5.0 上的只读实测（从不对当前编队 start/stop/kill；
隔离用 `/tmp/ah-fixture-*`，用完清理）。

| o1 断言 | 核实结论 | 直接证据 | 处置 |
|---|---|---|---|
| 坑洞 3.1（Windows-WSL 路径 raw string 比对 100% 失配） | **部分证实（并入 NF1 同处条款）** | 当前 Req 2.7/4.8 只说 `config_path`/`state_dir` "match"，未定义比对方式，naive 实现会 raw string 比对；且 live 快照顶层 `config_path:null`、`state_dir` 是 WSL Linux 路径 `/root/.local/state/ah/f2647adf` | **采纳** → Req 2.7/4.8：路径比对跨平台归一、`project_id` 为平台中立锚点、`config_path` 降级 |
| 坑洞 3.2（`status --json` sequence 恒为 1、reason 恒 initial；daemon 重启 sequence 复位挡新帧） | **证实** | 三次 `ah status --json` 全 `sequence=1/reason=initial`；`ah events` 首帧亦 `sequence=1/reason=initial`（稳定编队 8s 只发首帧，无法直接观测 >1 递增，但「全局单调」前提本身即被 sequence=1/reason=initial 基线否证） | **采纳** → Req 2.1：仲裁限定单流/`session_id` 生命周期，`reason:"initial"`/新流/`session_id` 变化无条件重置 |
| 坑洞 3.3（payload 缺只读标志 → 只读 inactive Open 可点但后端拒绝，UI 死锁） | **证实** | Req 6.1 payload 无 ownership 字段；Req 4.6 又要求观察/attach 只读 config 并投影 UI | **采纳** → Req 6.1 加 `readOnly`、新增 Req 6.4 只读 inactive Open 置灰 |
| 坑洞 3.4（只读 active Close 无效 → events 立即重渲染 active，永远关不掉） | **证实** | 同上：只读 config 被投影为 active + Close 按钮，但 Req 4.6 禁止对其发 stop | **采纳** → 新增 Req 6.4：只读 active 的 Close 语义改为 Detach（仅断本地观察，不发 stop） |
| 坑洞 3.5（`bash -lc` 登录 shell source profile 覆盖 `Command::env` 的钳制） | **证实（机制）** | `HOME=<fixture> AH_STATE_DIR=/inherited bash -lc 'echo $AH_STATE_DIR'` → profile 的 `/from-profile` 覆盖继承值；改注入 `-c` 字符串 `export AH_STATE_DIR=/instring` → `/instring` 胜出 | **采纳** → Req 4.7：钳制注入 bash `-c` 字符串，非仅 `Command::env` |
| 质疑 2.1（删掉 workspace config 只读规则，靠 env clamp 隔离即可安全 start/stop） | **证伪（不采纳）** | 其前提「Req 4.7 已隔离 AH_STATE_DIR」被 NF2 直接推翻：`env AH_STATE_DIR=/tmp/空目录 ah status` 仍返回活编队 `state_dir=f2647adf`。读面根本不隔离 → 只读规则是承重安全，不能删 | **不采纳**，保留 Req 4.6 只读边界；只读 UX 死锁改在只读模型内解（Detach），见 Req 4.7a 说明 |
| 质疑 2.2（用 `stderr.contains("not running")` 识别 daemon-absent，避开 events 启动延迟） | **不采纳（会重蹈 ah ps 文本解析覆辙）** | 这正是本 spec Req 2.2 要消灭的文本嗅探反模式；延迟顾虑用 Req 2.3 的量化超时（默认 3s）+ 回落态解决，不靠 sniff stderr | **不采纳**；改为量化 Req 2.3 的「wait briefly」→ 具名超时 + inconclusive 回落态 |
| 质疑 2.3（版本探测双格式解析多余，标准化 `ah version` 裸格式即可） | **采纳** | `ah version`→`1.5.0`（裸）、`ah --version`→`ah 1.5.0`，1.4.0+ 全系 `ah version` 稳定裸输出；双格式解析违背 KISS/DRY | **采纳** → Req 1.8 简化为单一 `ah version`+trim，Req 1.5 launcher 一并统一 |

### B. d1-review 自审必改项（本席上轮实测所得，直接采纳）

| d1 发现 | 核实结论 | 处置 |
|---|---|---|
| NF1（高）：`config_path` 被 `--config` 原样回显、且 live daemon 上为 null，作身份判据零鉴别力 | 本轮复核证实（顶层 `config_path:null`；NF1 回显形态见 d1-review §1e） | Req 2.7/4.8 改以 `state_dir`+会话身份为权威、`config_path` 降级诊断；测试 5.10 改「config_path 匹配但 state_dir 不匹配即丢弃」 |
| NF2（中-高）：1.5.0 读面 `status`/`events` 忽略 `AH_STATE_DIR`/`--config`，全局连活 daemon | 本轮复验证实（`env AH_STATE_DIR=/tmp/空 ah status` 仍返回 `f2647adf`） | 新增 Req 4.7a：env clamp 不保证读面 daemon 隔离，承重责任移交身份校验；design Testing Strategy 删除不可达成的 env-clamp 集成断言，改为可测的「bash 字符串含 export 前缀」单测 |
| T-2（中）：安全护栏任务排在发 `ah start` 的任务之后，顺序倒置 | 证实 | tasks.md 交换任务 5/6：所有权+env-clamp 护栏（原任务 6）前移为任务 5，Open/Attach（原任务 5）后移为任务 6 |
| NF-caveat（流程）：F1 daemon-absent 在有活 ahd 的机器无法独立复现 | 证实 | 任务 0 补前置条件：daemon-absent 须在零 ahd 环境采集；并补 NF1/NF2/坑洞 3.2 的 1.5.0 证据采集项 |
| A-4（建议）：Req 2.3 "wait briefly" 未量化 | 采纳 | Req 2.3 量化为具名超时（默认 3s）+ inconclusive `inactive`-可启动回落态 |
| T-4（建议）：每个生产任务缺「先写哪条红测试」 | 采纳 | tasks 2-9 每个生产任务补「先写红测试：<测试名> 断言 <目标>」框线 |
| 1a-858/879/927（建议）：Req 4.7 把 tmux 调用点 927 也称作 "invoking ah" 不精确 | 采纳 | Req 4.7 措辞区分 858/879（ah 调用）与 927（tmux 调用） |

### C. 第二轮改动 → 落点对照

| 收敛必改项 | requirements.md | design.md | tasks.md |
|---|---|---|---|
| 1. 身份校验重做（NF1 + 坑洞 3.1） | Req 2.7 重写（state_dir+会话身份权威、config_path 降级、跨平台归一）、Req 4.8 对齐、Req 5.10 改写 | Data Models `AhSessionSnapshot` 加 `path`/`projectId`、顶层 `configPath` 注释降级；parser 不变量身份条重写；flowchart IDCHECK 节点；Error Handling 身份 mismatch 条；Overview 第二轮硬化段 | 任务 0（NF1 证据采集）、任务 1（身份 fixture 改写）、任务 3（身份校验实现改判据） |
| 2. env clamp 重新定位（NF2 + 坑洞 3.5） | Req 4.7 改 in-string export、新增 Req 4.7a 作用域限定 | Tauri ah adapter 职责 env 条；flowchart ENV 节点；组件 rationale；Testing Strategy 删不可达断言改可测；Overview 硬化段 | 任务 0（NF2 证据）、任务 5（env clamp in-string 实现 + 作用域说明） |
| 3. sequence 仲裁作用域（坑洞 3.2） | Req 2.1 重写（单流/session_id 作用域 + reason:initial 重置）、新增 Req 5.13 | Data Models `sequence`/`reason` 注释；parser 不变量 sequence 条；Overview 硬化段 | 任务 0（sequence 证据）、任务 1（sequence-reset fixture）、任务 4（重置实现） |
| 4. payload ownership + Detach（坑洞 3.3/3.4） | Req 6.1 加 `readOnly`、新增 Req 6.4、Req 5.12 加 readOnly、新增 Req 5.14 | Data Models frontend payload 加 `readOnly`；Error Handling 只读 Detach 条；Testing Strategy 只读语义条；Overview 硬化段 | 任务 1（readOnly fixture）、任务 8（payload 加 readOnly）、任务 9（只读 Detach/置灰 Open 投影） |
| 5. tasks 护栏先行排序（T-2） | — | — | 交换任务 5/6，实现约束加「护栏先行」条 |
| 6. TDD 框线补全（T-4） | — | — | 任务 2-9 每个生产任务加「先写红测试」测试名+断言目标 |
| 7. 版本解析简化（质疑 2.3） | Req 1.8 简化单一 `ah version`、Req 1.7 去 `ah --version`、Req 1.5 launcher 统一 | Tauri ah adapter 职责第 1 条；Testing Strategy 版本单测条 | 任务 1（版本 fixture 只留裸格式）、任务 2（launcher 统一 `ah version`） |
| 8. task 0 daemon-absent 前置条件（NF-caveat） | — | — | 任务 0 补零-ahd 环境前置条件 + NF1/NF2/坑洞3.2 证据采集项 |
| 9. Req 2.3 量化（A-4） | Req 2.3 具名超时 + 回落态 | Error Handling 第 4 条隐含；System Flows daemon-absent 分支 | 任务 4 daemon-absent 超时实现 |

### D. 未升级 operator 的判定依据

按 gate 分工，只有「events-primary 状态合约方向本身站不住」这类架构级分歧才升级 operator。
两份评审的分歧全部落在**具体条款的实现细节/证据缺口**（身份判据用哪个字段、env clamp 保证
什么、sequence 作用域、payload 字段、任务排序、版本解析），无一质疑「用结构化状态合约取代
Studio 第二套弱状态机 + events 为主决策面」这个大方向；o1 质疑 2.1 唯一触及方向的支路（删
只读边界）其前提已被 NF2 实测证伪。故本轮为细节返工，未落 `.operator-question`。
