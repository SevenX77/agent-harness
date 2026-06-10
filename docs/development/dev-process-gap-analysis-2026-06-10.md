# 开发流程差距分析与优化路线（2026-06-10）

> 状态：**已评审、未执行**。优化项全部待 PM 启动指令，本文先作记录。
> 背景：基于 2026-06-10 整天的一手事故素材（CI hang 解堵、Wave 4A 收口、#117 冲突灾难、Sonar 质量门治理）+ 前沿流程网络调研。
> 读者：PM（非程序员背景）+ 后续 PM session。

## 一、当前流程画像（PM 已确认）

- **角色**：人类 PM 做决策与验收（亲自读全部汇报/闸门）；Claude session 做架构/计划/审查/git；**代码编写最终派给 Gemini 执行**；CCB 多 AI 桥已弃用。
- **设计层**：`docs/<域>/mvp1/` 设计文档树为唯一目标真相（SSOT），mvp1-alignment（目标态）+ baseline（现状）成对；文档 hash 锁/锁态快照测试钉死设计状态。
- **计划层**：`_impl/IMPL_PLAN.md` 按文件归属拆 WS（工作流），共享热点文件串行、其余并发，WS 按依赖排 Wave。
- **任务书层**：`task-spec-standard.md` 12 章节需求书 + RED-first + PM 契约门（用户聊天窗确认）+ 实现只许 RED→GREEN + baseline 回写 + 终审。实际操作中需求书会写**非常完整的操作流程**（注：这一点与标准第一条"需求书不写逐步改法"存在自相矛盾，见差距④）。
- **执行层**：每 WS 一个 worktree + 分支 → draft PR → 七道 CI（三档 Python 测试 / quality-gates / frontend-gates / CodeQL / SonarCloud 自动分析 / Scorecard）→ 终审 → squash 合并。
- **防回归层**：特征锁测试（配置逐键锁、文档 hash 锁）、错误码 registry、decision log、deferred-items、治理留痕。

## 二、前沿调研结论（2025H2–2026，来源见 §五）

行业已从 vibe coding 收敛到 **agentic engineering**：瓶颈从"生成代码"转移到"审查与集成代码"。

1. **并行分两种**：并行 A（一人管 3–5 个 agent，各做**文件不重叠**的独立任务，worktree/sandbox 隔离）被广泛验证；并行 B（多 agent 写同一片代码）被 Cognition 明确劝退——"写操作单线程，额外 agent 贡献智能不贡献动作"。
2. **Spec-driven 是主流但有成熟度警告**：Spec→Plan→Tasks→Implement 四阶段（GitHub Spec Kit ~9 万 star、AWS Kiro）；Thoughtworks 雷达置于 Assess 档，批评"繁琐且过度规定"——应按任务复杂度分级。
3. **集成铁律：小步快合**。trunk-based + merge queue 为标配；stacked PR（每层 <200 行、自洽）成为 agent 原生原语（GitHub 2026-04 官方 gh-stack）；大批次 PR 是 agent 时代分支腐烂之源。
4. **验证器质量决定一切**（Anthropic C 编译器项目头号教训）；AI code review 已是标配（~60% 有 CI 团队每 PR 跑），**审查 agent 不与写码 agent 共享上下文**效果最好（每 PR 平均抓 2 bug、58% 严重；Anthropic 内部实质审查意见率 16%→54%）。
5. **人类三个高杠杆审查点**：spec 入口（最高杠杆）、高风险任务 plan 批准（可选）、行为验收出口。人不当人肉代码审查器、不当过程监工。

## 三、差距分析（按严重度）

### 差距①（最大）：大批次长寿分支 vs 小步快合
- **证据**：wave2 分支 21 提交 / 净增 1 万行 / 落后 main 147 提交 / 47 文件冲突，最终只能重切（#117）；15 个分支比 main 超前，多数腐烂；`first-batch`、`gateway-mvp1-optimization` 等僵尸 PR。
- **根因**：Wave 被用作"攒批次"容器（baseline 大分支），而非仅排依赖序。
- **对策**：一 WS = 一分支 = 一 PR，≤400 行，合完即删；禁 baseline 容器分支。

### 差距②：合并协调靠人肉 vs 机器排队
- **证据**：E1-io 与 E4 在 `graph_assembler.py` 重叠靠人调度合并顺序；多 session 并行合并无防竞态机制；合并后分支不自动删（`docs/sonar-governance-record` 残留）。
- **对策**：branch protection（checks 全绿方可合）+ auto-delete branch + GitHub 原生 merge queue（公开仓库免费）。

### 差距③：PM 人肉读一切 vs 三点审查
- **证据**：契约门、终审、CI 状态、Sonar 失败、冲突裁决全过 PM 眼睛；PM 非程序员出身，单位审读成本更高。**PM 正在兼任人肉 merge queue + 人肉 code reviewer + 人肉监控大盘，是当前最贵瓶颈。**
- **对策**：PM 收缩到 spec 入口 / plan 批准 / 行为验收三点；每 PR 挂独立 AI code review（与写码 agent 不共享上下文）；汇报纪律改为"行为级摘要 + 待拍板判断"。

### 差距④：流程重量过载（反向差距，比主流更重）
- **证据**：12 章节需求书 + 文档 hash 锁 + 配置逐键锁 + 多轮复核；2026-06-10 一天两次撞锁（sonar 配置锁、scorecard 把不安全的 `read-all` 锁成契约）——**锁钉死"逐字节状态"而非"意图"，正当改进付双倍成本，锁还保护错误状态**；需求书写完整操作流程，撞上 Cognition 反模式（"manager 给死步骤适得其反"）且违反自家 task-spec-standard 第一条。
- **对策**：流程分级（小改动走轻量道：直接做 + PR + AI review；跨文件机制类才走全套）；锁改锁意图（断言"必须最小权限"而非"必须等于字面值"）；需求书删操作步骤，"怎么做"还给实现 agent。

### 差距⑤：无巡检，问题靠爆炸才被发现
- **证据**：Sonar 扫描配置失效 12 天无人察觉（Automatic Analysis 不读 sonar-project.properties）；CI hang 堵塞 runner 队列 52 分钟；僵尸 PR/分支无人清理。
- **对策**：定时巡检 agent（每日：open PR 腐烂度、CI 健康、质量门、待清理分支 → 一页摘要）。

### 已对齐前沿的部分（保持）
SSOT 设计文档树（≈spec-driven Level 1.5，baseline 回写接近 Level 2 活 spec）、RED-first（≈验证器优先）、文件锁并发分区（≈并行 A + 文件不重叠铁律）、worktree 隔离、治理留痕文化。

## 四、优化路线图（全部待启动）

| 优先级 | 动作 | 成本 | 收益 | 状态 |
|---|---|---|---|---|
| P0 | 小步快合纪律：一 WS 一 PR、≤400 行、合完删分支、禁 baseline 容器分支 | 零（纪律） | 根除 47 冲突类灾难 | ⏸ 待启动 |
| P0 | GitHub 三件套：branch protection + auto-delete + merge queue | ~0.5h 配置 | PM 不再人肉协调合并 | ⏸ 待启动 |
| P0 | 每 PR 挂独立 AI code review（Claude Code review action 或 CodeRabbit） | ~0.5h 配置 | PM 不再人肉审代码 | ⏸ 待启动 |
| P1 | PM 角色收缩至三点：spec 入口 / plan 批准 / 行为验收 | 习惯调整 | 解除最贵瓶颈 | ⏸ 待启动 |
| P1 | 流程分级 + 需求书去操作步骤 + 锁改锁意图（修订 task-spec-standard） | 改一份标准 | 每任务省 30–50% 流程开销 | ⏸ 待启动 |
| P1 | 定时巡检 agent | 一次配置 | 问题早发现 | ⏸ 待启动 |
| P2 | 僵尸分支/PR 大扫除（核对 5 月旧分支后关闭；优先核对 docs/mvp1-design-20260604 的 7 个未合提交） | 一次性 | 仓库回干净态 | ⏸ 待启动 |
| P2 | CI 选择性测试、stacked PR 工具链 | 中 | 吞吐再上档 | ⏸ 待启动 |

## 五、调研来源（节选）

- Cognition: Multi-Agents — What's Actually Working（写单线程/审查环/不共享上下文）
- Anthropic: Building a C compiler with parallel Claudes（16 agent 文件锁并行、验证器命门、翻车清单）
- Claude.com: How Anthropic teams use Claude Code（90% AI 写码、非工程团队用法）
- Cognition: Devin's 2025 Performance Review（spec 清晰度是头号成败因素）
- GitHub Spec Kit / AWS Kiro（SDD 四阶段）；Thoughtworks Radar 2025-11（SDD = Assess，过度规定警告）
- InfoQ/InfoWorld: GitHub Stacked PRs（2026-04 官方 gh-stack）；Gitar: merge queue 2026（Shopify +33%）
- DEV: State of AI Code Review 2026（~60% 渗透率）；The New Stack: Anthropic AI review（16%→54%）
- Nx 2026 Roadmap（选择性测试、self-healing CI）
