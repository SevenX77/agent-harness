# 对抗审意见书：Studio ah 状态合约 V1 修订版 Spec

- **Spec 标识**: [studio-ah-state-contract-v1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/)
- **评审日期**: 2026-07-10
- **评审人**: Antigravity (设计辩论席)
- **总体结论 (Verdict)**: **不批准 (Reject / 细节返工)**

---

## 1. 总体评审说明

修订版 Spec（PR #483 合入后版本）在消除 `ah ps` 文本解析与 tmux 猜测方向上完全正确，并对 [operator-review-findings.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/operator-review-findings.md) 中的大部分 F 级问题作出了表面呼应。

但在第一性架构逻辑与跨平台实施细节上，修订版 Spec 引入了多处**阻塞级新坑洞**。如果按照当前 Spec 实施，Windows 用户将遭遇 **100% 状态订阅失效锁死**、**外部 daemon 重启状态不更新**、以及**只读 assistant 面板无法关闭**的严重缺陷。

必须对 Spec 中的五件套（特别是 [requirements.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md) 与 [design.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/design.md)）进行细节返工后，方可进入代码开发。

---

## 2. 第一性质疑 (First-Principles Critique)

### 质疑 2.1: 混淆了“配置文件所有权”与“运行时实例隔离”的保护边界
- **对应条款**: [requirements.md: Req 4.6](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L100-L100)
- **冲突事实**: Spec 规定 workspace 目录下的 `ah.toml` (class a) 仅允许 Attach (只读观察)，不能在 Studio 内被 Start/Stop/Kill。其初衷是防止 Studio 误杀用户/operator 在终端运行的后台编队。
- **辩论观点**: 
  1. 真正导致“误杀/状态串线”的根本原因并不是使用了相同的 `ah.toml` 文件，而是因为 Studio **继承了用户的 WSL 环境变量，导致使用了同一个状态目录 (`state_dir`) 和同一个 `ahd` 实例**。
  2. 既然 Req 4.7 已经强制隔离了 Studio 运行的 `AH_STATE_DIR`/`CCBD_STATE_DIR`，那么即使 Studio 使用了 workspace 自带的 `ah.toml` 启动，它也是在一个**完全独立、相互隔离的 `ahd` 实例和 tmux 命名空间中运行**，绝不可能干扰到外部 operator 的编队。
  3. 这种“一刀切”将 workspace 配置文件列为只读的规则，直接导致用户无法在 Studio 内启动自己为项目深度定制的环境（必须手动在终端跑 `ah start` 才能在 Studio 观察），剥夺了 Studio 对自定义配置的管理权，属于以不当手段解决环境污染问题的设计妥协。

### 质疑 2.2: 刻板排斥 stderr sniffer 导致同步启动路径高延迟
- **对应条款**: [requirements.md: Req 2.2 / 2.3](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L50-L53)
- **冲突事实**: 当 `status --json` 遭遇 daemon 缺失（F1 场景：exit 1 且输出 `"ahd daemon is not running..."` 文字）时，Spec 严禁通过比对 stderr 文本来识别此状态，而是要求“启动并等待 events 订阅流”直到获得结构化的 `daemon_absent` 快照。
- **辩论观点**: 
  1. 在 WSL 环境下，通过 `wsl.exe -e bash -lc` 启动 events 订阅流（login shell）有**非常明显的时间开销**（实测在一些 Windows 机器上可达 2-5 秒）。
  2. 如果在 synchronous 启动流程中强行“等待 events 流产生第一行数据”，将把 WSL 启动的几秒延迟同步传导给 UI，造成严重的界面卡顿。
  3. 既然 `ah status --json` 的 stderr 在 daemon 缺失时输出 `"ahd daemon is not running..."` 是上游 CLI 极度稳定的错误形式，直接使用 `stderr.contains("not running")` 识别这一特定状态作为 one-shot 临时 fallback，远比阻塞等待 events stream 来得轻量、低延迟且不易出错。

### 质疑 2.3: 无谓的版本解析兼容性复杂化 (违背 KISS 原则)
- **对应条款**: [requirements.md: Req 1.8](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L40-L41)
- **冲突事实**: Spec 详细设计了如何支持并解析 `ah version` (裸版本号) 和 `ah --version` (带前缀) 两种格式。
- **辩论观点**: 
  1. 既然 Studio 强行要求最低版本必须 `>= 1.4.0`，而在 1.4.0+ 的所有版本中，`ah version` 命令行均已稳定支持且直接返回 bare 版本号（实测输出 `1.5.0`，无任何前缀）。
  2. 既然如此，Studio 的 Rust 适配层在执行版本探测时，**直接单向调用 `ah version` 并做 simple trim** 即可，根本不需要支持两种格式并写复杂的 token 切片代码。Req 1.8 属于典型的过度设计。

---

## 3. 找新坑洞 (New Loopholes / Defects Identified)

### 🚨 坑洞 3.1: Windows-to-WSL 路径比对阻塞 (Blocker 缺陷)
- **细节描述**: [requirements.md: Req 2.7 / 4.8](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L60-L60) 要求对接收到的 snapshot 进行 `config_path` 身份一致性匹配，不匹配则一律丢弃并抛出诊断。
- **失效场景**: 
  - Studio 在 Windows 宿主机运行，其请求的 config 路径是 Windows 格式（例如 `C:\Users\Admin\AppData\Local\Temp\skill-studio-ah\...`）。
  - `ah` 运行在 WSL (Linux) 环境下，返回的 snapshot `config_path` 是 Linux 格式（例如 `/mnt/c/Users/Admin/AppData/Local/Temp/skill-studio-ah/...`）。
  - 如果开发时采用直接字符串匹配（`snapshot.config_path == requested_config_path`），在 Windows 上比对将 **100% 失败**。
  - 这会导致 Studio 丢弃全部有效的 events 状态，UI 永久停留在 `inactive` 或 `error`，无法 attach 也无法进行任何操作。
- **修复方案**: Spec 必须要求比对机制支持**跨平台路径转换**（在 Windows 上必须先将 Windows 路径转换为对应的 WSL 路径，或将 WSL 路径转换回 Windows 路径并标准化斜杠方向后再进行比对）。

### 🚨 坑洞 3.2: 仲裁中的“Sequence 1”失效陷阱 (Blocker 缺陷)
- **细节描述**: [requirements.md: Req 2.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L48-L48) 规定：“never letting an older-or-equal `sequence` value overwrite a newer one”。
- **失效场景**:
  1. **测试事实**: 在当前真实环境下运行 `ah status --json` 发现，不管 daemon 下的 agent 状态如何变化（活跃数从 6 变 2），其返回 of snapshot 的 `"sequence"` 永远是 `1`，`"reason"` 永远是 `"initial"`。
  2. **逻辑坍缩**: 当 live events subscription 开始工作且 sequence 递增到 `> 1` 后，一旦触发 Close、Quit 或手动 Refresh 导致再次调用 `status --json`，拿到的 sequence 永远为 `1`。
  3. 按照“旧 sequence 无法覆盖新 sequence”的规则，这个 `status --json` 结果（代表了关闭后或最新的真实状态）会被 UI 缓存直接丢弃！
  4. 此外，当 `ahd` 重启时，其事件流的 sequence 也会重置为 `1`，这会导致重启后的新流事件无法覆盖旧流在 Studio 中残留的 `sequence > 1` 的状态。
- **修复方案**: 
  - Sequence 的比对只能在**同一个 events 订阅流的生命周期内**生效。
  - 当建立新订阅或进行 one-shot `status` 诊断时，必须重置 `sequence` 缓存。
  - 或者在比对时加入 `session_id` 比对：如果 `session_id` 发生变更，直接覆盖并重置 sequence 计数；如果 `session_id` 相同，才进行 `sequence` 的单调递增比对。

### 🚨 坑洞 3.3: 前端 status payload 缺失 ownership 信息导致 UI 报错死锁 (High)
- **细节描述**: [requirements.md: Req 6.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L142-L142) 定义的 `CodeAssistantStatusChangedPayload` 结构中，只有 status enum，并没有带上所有权类别（read-only / Studio-managed）。
- **失效场景**:
  - 当工作区下存在一个 inactive 的 workspace-owned `ah.toml` 时，因为 frontend 不知道这个 config 是只读的，UI 仍会渲染出可点击的 "Open code assistant" 按钮。
  - 用户点击 "Open"，Tauri 拦截并抛出错误（不予执行），UI 陷入 `error` 状态。
  - 用户只看到一堆莫名的报错，完全不明白为什么点击了可用的 Open 按钮会失败。这违背了 web app 高级美学设计原则。
- **修复方案**: Payload 中必须带上所有权只读标志（如 `isReadOnly: boolean`），让前端可以在只读 inactive 状态下将 Open 按钮置灰，并提供 tooltip 解释说明（“此配置由工作区提供，为只读，请在终端手动运行”）。

### 🚨 坑洞 3.4: 观察性 Attach 后的 "Close" 操作死锁 (High)
- **细节描述**: 用户通过 Attach 观察运行中的只读 (workspace-owned) assistant 编队。
- **失效场景**:
  - 此时 UI 会投影为 `active` 状态，并渲染 "CLI running" / "Close" 按钮。
  - 当用户点击 "Close" 时，Tauri 根据 Req 4.6 判定其为只读，从而拦截并拒绝发送 stop 命令给 daemon。
  - 既然没有发送 stop 命令，daemon 依然保持 active 状态，并通过 `events` 流持续上报 `active=true` 的 snapshot。
  - 由于前端是 events 的薄投影，UI 会瞬间重新渲染为 active。用户会看到点击 "Close" 后没有任何反应，**永远无法从 Studio UI 中关闭或断开对这个只读 assistant 的观察**。
- **修复方案**: 如果当前 assistant 是只读的，UI 对应的 Close 按钮应该演变为 **"Detach"**，其行为只是关闭本地终端连接并卸载 UI 状态，而不是去执行 stop 命令。

### 🚨 坑洞 3.5: WSL 环境钳制被 login shell 绕过风险 (Medium)
- **细节描述**: [requirements.md: Req 4.7](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L102-L102) 规定：在 WSL 命令行调用前显式清除环境变量。
- **失效场景**: 
  - `wsl.exe -e bash -lc` 是以 login shell 启动的。
  - 即使在 Rust 的 `Command` 构建器中调用了 `.env("AH_STATE_DIR", "")`，一旦 `bash` 启动，它会去 source 用户 WSL 里的 `~/.bashrc` 或 `~/.profile`，如果用户在里面 `export AH_STATE_DIR=/foo`，此值会无情覆盖掉进程继承来的环境变量。
  - 这导致 Spec 声明的环境隔离在 login shell 下失效。
- **修复方案**: 环境变量的钳制必须直接写入执行的 `script` 字符串中（如在 `ah` 命令前加上 `export AH_STATE_DIR=\"\"; export CCBD_STATE_DIR=\"\";`），以确保其在 login shell 加载 `.bashrc` 之后运行，从而百分之百覆盖。

---

## 4. 忠实度审 (Fidelity Audit)

根据 [operator-review-findings.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/operator-review-findings.md) (F1-F9) 对照 [REVISION-TRACE.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/REVISION-TRACE.md) 声称的落点进行核对：

| 发现 | 修订声称解决方式 | 忠实度审计 Verdict | 发现/分析 |
|---|---|---|---|
| **F1** | 限制 status 仅在 bootstrap 用，决策以 events 流为主 | **有条件通过** | 已写进要求，但由于刻意规避 stderr sniffer 导致启动流程有性能和高延迟隐患（见质疑 2.2）。 |
| **F2** | 明确定义 starting/degraded 生命周期和 degraded 清理 | **通过** | Req 3.6/3.7/3.8 已对 degraded/starting 作出清晰的按钮语义限定。 |
| **F3** | Payload 拓宽为多状态 assistant 状态枚举 | **有条件通过** | 移除了抑制，定义了新 enum 且单 workspace 单 ahd 仍保留。但缺少只读标志导致前端死锁（见坑洞 3.3）。 |
| **F4a** | 依靠 config 路径二分类划分写 lifecycle 权限 | **有条件通过** | 限制了写 lifecycle，但一刀切地限制让 workspace 配置成了鸡肋，且 Close 操作死锁（见质疑 2.1 与 坑洞 3.4）。 |
| **F4b** | env 钳制与 identity check 机制 | **拒绝 (Fail)** | 缺少跨平台路径转换逻辑，Windows 下 100% 报错（见坑洞 3.1）。WSL login 存在绕过隔离风险（见坑洞 3.5）。 |
| **F5** | events stream 设为主决策面 + sequence 仲裁 | **拒绝 (Fail)** | 忽略了 `status --json` 永远返回 sequence 1 以及 daemon 重启 sequence 复位的事实，比对逻辑存在严重漏洞（见坑洞 3.2）。 |
| **F6** | 常量单源化 + events 订阅受检查限制 | **通过** | 已在 Req 1.5 - 1.8 落实，但 Req 1.8 引入了无谓的代码解析复杂性（见质疑 2.3）。 |
| **F7** | 设计文档与 intro 文本回写任务 | **通过** | [tasks.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md) 任务 10 已经精确注册了全部需回写的文档位置与文本，排序安排合理。 |
| **F8** | 纠正 README 模型字段，duplicate start 前置行为验证 | **通过** | 已经重新建模字段并纠正类型。在 `tasks.md` 安排了 Task 0 前置验证。**[注]**：实测表明 `ah start --config ah.toml` 对活跃 stack **并不报错且退出码为 0**（会重用已有 session），证实前置验证任务非常必要。 |
| **F9** | INDEX 登记与补票规则 | **通过** | INDEX.md 已正确在第 28 行登记该 spec，状态一致。 |

---

## 5. 改进建议与必改项 (Actionable Recommendations)

为使本 Spec 达到**批准 (Approved)**状态，修订方必须对 Spec 文本进行以下二次修订：

1. **解决路径匹配故障 (针对坑洞 3.1)**:
   - 在 [requirements.md: Req 2.7](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L60) 处补充：在比对 snapshot 返回的路径与 Studio 请求的路径时，若处于 Windows 环境，必须调用转换器将 Windows 路径映射为 WSL/Linux 格式路径（或相反）再做 Canonical 比较，严禁对两端环境路径进行 raw string 比较。
2. **重做 Sequence 仲裁规则 (针对坑洞 3.2)**:
   - 在 [requirements.md: Req 2.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L48) 处补充：Sequence 仲裁只在**同一 session_id / 同一订阅流寿命内**有效。当获取到不同的 `session_id`，或 events 订阅流重新建立，或从 `status --json` 中读到 `reason: "initial"` 时，必须无条件覆写并重置 sequence 缓存。
3. **增加只读属性和 Detach 逻辑 (针对坑洞 3.3 与 3.4)**:
   - 在 [requirements.md: Req 6.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L142) 中为 payload 增加 `isReadOnly` 字段。
   - 补充 UI 状态映射规则：对于只读 (workspace-owned) 的 assistant，在其处于 active 状态下，Close 按钮自动蜕变为 **"Detach"**，仅关闭 Studio 的 terminal tab，绝不向 backend 发送 stop 命令。对于 inactive 状态，置灰 Open 按钮并提供引导文案。
4. **修复环境钳制逻辑 (针对坑洞 3.5)**:
   - 修改 [requirements.md: Req 4.7](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L102)，写明隔离环境变量必须注入到 WSL 执行的 bash command 字符串中（如 `export AH_STATE_DIR=""`），而不是在宿主机侧使用 Rust 的 `Command::env` 设置。
5. **极简版本探测逻辑 (针对质疑 2.3)**:
   - 修改 Req 1.8，剔除对 `ah --version` 带前缀格式的解析要求，强行标准化版本命令只使用 `ah version`，从源头消灭解析复杂性。
