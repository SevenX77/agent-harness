# 忠实度复核意见书 (Round 2)：Studio ah 状态合约 V1 Spec

- **Spec 标识**: [studio-ah-state-contract-v1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/)
- **复核目标**: 针对 commit **f4da1164** 的 spec 完整 diff 进行独立第三方对抗验证与忠实度核对
- **复核日期**: 2026-07-10
- **复核人**: Antigravity (设计辩论席)
- **总体结论 (Verdict)**: **通过 (Approved — 可开闸进入实施)**

---

## 1. 必改项逐条核对表 (Round 1 意见落地复核)

本节核对 Round 1 (`o1-review.md`) 提出的 5 条必改项以及 1 条被采纳的质疑项，在 commit `f4da1164` 的 diff 及当前 spec 文件中的落实程度。

### 1.1 坑洞 3.1: Windows-to-WSL 路径比对阻塞
* **必改要求**: 必须支持跨平台路径转换/归一化比较，严禁对 Windows 宿主机请求路径（如 `C:\...`）与 WSL 返回的 snapshot 路径（如 `/mnt/c/...`）进行 raw string 直接比对；config_path 因存在 null 或被 `--config` 原样回显等问题，不可作为身份识别的唯一权威。
* **f4da1164 对应改动**: 
  - [requirements.md: Req 2.7](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L60-L63) 与 [Req 4.8](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L108-L108) 重写了身份判据。明确 `config_path` 降级为 advisory 诊断（在无 config 启动的 daemon 上为 `null`，且会被 `--config` 回显击穿而失去鉴别力），身份校验以 `state_dir` + 会话身份 (`sessions[].session_id`, `sessions[].path`, `sessions[].project_id`) 为唯一权威。
  - 明确规定所有路径比对（`state_dir`, `sessions[].path`）必须在跨 Windows↔WSL 边界时进行 canonicalization，严禁 raw string 比对。引入了平台中立的 `sessions[].project_id`（基于目录 basename）作为跨主机最稳固的锚点。
  - [tasks.md: 任务 3](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L57-L64) 新增先写红测试 `test_identity_canonicalizes_windows_wsl_path` 与 `test_identity_rejects_config_path_match_state_dir_mismatch`。
* **落实程度**: **完整落实**
* **分析与证据**: d1 在采纳该意见的同时，结合了实测新发现（NF1：`ah --config <隔离> events` 回显隔离项目的 `config_path`，但数据指向活编队），将身份校验机制重构得极为彻底。不仅解决了跨平台路径比对不匹配问题，还从源头上封堵了利用 `config_path` 回显漏洞的身份伪造可能。

### 1.2 坑洞 3.2: 仲裁中的“Sequence 1”失效陷阱
* **必改要求**: Sequence 仲裁只能在同一个 events 订阅流或同一 daemon 会话寿命内有效。遇到 session_id 变化、events 订阅流重新建立或 one-shot `status` 读到 `reason: "initial"` 时，必须无条件覆写并重置 sequence 缓存。
* **f4da1164 对应改动**:
  - [requirements.md: Req 2.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L50-L50) 重写了仲裁规则。明确 `sequence` 属于单订阅流与单 `session_id` 生命周期内的 baseline 计数，非全局单调。当观察到：① 重新建立的 events 订阅；② 快照携带 `reason: "initial"`；③ `sessions[].session_id` 改变，Studio 必须**无条件重置** applied-sequence 缓存，不再阻挡新帧。
  - [tasks.md: 任务 4](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L66-L75) 新增先写红测试 `test_sequence_reset_on_reason_initial` 与 `test_sequence_guard_within_stream`。
* **落实程度**: **完整落实**
* **分析与证据**: 完全封锁了 `sequence: 1` 被旧高水位丢弃的问题。在 spec 层面明确指出 K8s 风格 of `resourceVersion` 在此处不适用，并确立了三类触发 sequence 重置的条件，考虑得相当周密。

### 1.3 坑洞 3.3: 前端 status payload 缺失 ownership 信息导致 UI 报错死锁
* **必改要求**: Payload 结构中必须带上所有权只读标志（如 `readOnly: boolean`），使前端能够在只读 inactive 状态下置灰 Open 按钮并提供 tooltip 引导。
* **f4da1164 对应改动**:
  - [requirements.md: Req 6.1](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L150-L150) 中为 `CodeAssistantStatusChangedPayload` 增加了 `readOnly: boolean` 字段。
  - [Req 6.4](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L156-L156) 规定只读 (workspace-owned) assistant 在 `inactive` 时 Open 按钮必须被禁用并提供置灰的引导文案（"此配置由工作区提供且为只读..."）。
  - [tasks.md: 任务 8 与 任务 9](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L104-L118) 分别为 payload 重构与 UI 置灰投影设定了红测试：`test_payload_carries_readonly_flag` 与 `test_readonly_inactive_open_disabled`。
* **落实程度**: **完整落实**
* **分析与证据**: `readOnly` 字段的引入将 workspace 文件的读写性质直接透传至前端，配合 Req 6.4 从根本上防止了用户触发无效的后端 write 操作，保护了只读边界。

### 1.4 坑洞 3.4: 观察性 Attach 后的 "Close" 操作死锁
* **必改要求**: 若当前 assistant 为只读，UI 对应的 Close 按钮应该演变为 "Detach"（仅关闭本地终端/观察面板并卸载 UI 状态，决不发送 stop/kill 生命周期指令给后端）。
* **f4da1164 对应改动**:
  - [requirements.md: Req 6.4](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L156-L156) 规定：对于只读 active 状态的 assistant，Close 按钮演变为 **Detach** —— 仅关闭本地 terminal tab 并卸载 UI 状态，永远不向后端发送 `ah stop` / `ah kill`。
  - [tasks.md: 任务 9](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L111-L118) 新增先写红测试 `test_readonly_active_close_is_detach`。
* **落实程度**: **完整落实**
* **分析与证据**: 落实得非常精准。改“Close”为“Detach”解开了由“只读 config 禁止发送 stop 命令”与“前端薄投影 events 重渲染”引发的死循环死锁问题。

### 1.5 坑洞 3.5: WSL 环境钳制被 login shell 绕过风险
* **必改要求**: 环境变量的钳制必须直接写入 bash command 字符串中（如 `export AH_STATE_DIR=""`），以确保其在 login shell 加载 `.bashrc`/`.profile` 之后生效并覆盖它们，而不能仅通过 Rust 的 `Command::env`。
* **f4da1164 对应改动**:
  - [requirements.md: Req 4.7](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L104-L104) 规定：通过 `wsl.exe -e bash -lc` 登录 shell 启动前，必须通过**注入 bash `-c` 命令字符串本身**（如前置 `export AH_STATE_DIR="";`）来进行变量钳制，而不能仅使用 `Command::env(...)`。
  - [tasks.md: 任务 5](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L77-L83) 新增先写红测试 `test_env_clamp_in_bash_string`，断言生成的 bash 命令串中带有前缀。
* **落实程度**: **完整落实**
* **分析与证据**: 机制论证很扎实。为了证明这一点的必要性，d1 在 `tasks.md` 任务 0 中甚至加入了 WSL 登录 shell 环境变量被 profile 覆盖的复现步骤。注入执行串确实是阻断 login shell profile 覆盖的可靠方式。

### 1.6 质疑 2.3: 无谓的版本解析兼容性复杂化 (被采纳项)
* **必改要求**: 探测版本仅通过 `ah version` 命令裸输出格式并 trim，不再处理 `ah --version` 格式。
* **f4da1164 对应改动**:
  - [requirements.md: Req 1.8](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/requirements.md#L42-L42) 规定：探测版本仅通过 `ah version` 命令裸输出格式并 trim，不再处理 `ah --version` 格式。
  - [tasks.md: 任务 2](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md#L49-L55) 新增测试 `test_version_parse_uses_bare_ah_version`，断言无第二 token 分割路径。
* **落实程度**: **完整落实**
* **分析与证据**: 已完全落实，符合 KISS 与 DRY 原则。

---

## 2. 对被驳回项的复核结论 (质疑 2.1 与 2.2)

本节核对 d1 拒绝采纳的 2 条质疑，评估其拒绝理据是否成立。

### 2.1 质疑 2.1 "只读边界一刀切太严格" (被驳回)
* **辩论焦点**: 能否完全依靠 env clamp 隔离 `AH_STATE_DIR`，从而安全地允许对 workspace-owned config (class a) 执行生命周期写入命令（start/stop/kill）？
* **d1 驳回理由**:
  - 在 1.5.0 CLI 实测中发现（NF2 现象），运行 `env AH_STATE_DIR=/tmp/隔离空项目 ah status` 即使使用了空隔离目录，**仍然会返回活编队的信息**。
  - 这表明 ah 1.5.0 本身的读面（`status`/`events`）存在无视 `AH_STATE_DIR` 并通过全局共享机制连接到正在运行的 daemon 的行为。
  - 既然 `AH_STATE_DIR` 不能阻断 daemon 之间的通讯与解析，说明 env clamp **无法作为读写隔离的承重墙**。一旦放开对 workspace-owned config 的 start/stop/kill 限制，将由于 CLI 的全局穿透特性直接停止或误杀外部正在运行 of operator 编队，造成数据丢失灾难。
* **复核结论**: **维持驳回，驳回理由完全成立。**
  - **佐证**: 安全是承重设计的首要追求。既然 1.5.0 在实测中已被证实无法通过 `AH_STATE_DIR` 隔离读面 daemon，那么在 spec 层面将 workspace config 划分在写生命周期（start/stop/kill）之外就是唯一绝对安全的“物理断路器”。因此，保留 workspace-owned 仅读观察是不二法门，只读带来的 UX 死锁也已经在 Req 6.4（Detach）中安全化解。

### 2.2 质疑 2.2 "允许 stderr sniffer 兜底降延迟" (被驳回)
* **辩论焦点**: 在 daemon-absent 时，直接根据 status 的非结构化 stderr (`"ahd daemon is not running..."`) 来 fail-fast，能否有效降低 WSL 启动订阅流造成的 2-5 秒延迟？
* **d1 驳回理由**:
  - 嗅探 stderr 文本是已经被 operator-review 证实的不良反模式（如 `ah ps` 文本解析等），易因 CLI 日志升级而崩溃。
  - 更重要的是，调用 `ah status` 本身在 Windows-to-WSL 下**同样需要启动 `wsl.exe -e bash -lc` 登录 shell**，因此一次 `status` 的失败调用同样伴随着 2-3 秒的 WSL 物理启动延迟，并不能起到降延迟的作用。
  - 如果为了 fail-fast 先调一遍 status 嗅探错误再启动 events 订阅，在 events 正常运行的情况下，反而累积了两次 WSL 往返开销（共 4-6 秒延迟），甚至比“直接走 events 订阅”更慢。
  - spec 已经用 Req 2.3 的具名超时（3s）+ 稳定回落 inconclusive `inactive`-可启动态来消解这个 bootstrap 阻塞问题，保证了界面绝不会卡顿或锁死在 error。
* **复核结论**: **维持驳回，驳回理由完全成立。**
  - **佐证**: 延迟问题属于 WSL 登录 shell 启动的物理开销。d1 准确指出 one-shot status 和 events-primary 均需要付出这段物理开销。因此，“直接走 events 订阅”不仅避免了脆弱的 text match，还在 daemon 存活的长效流程中消除了多次 status 往返的累积开销。量化超时（3s）和 `inactive` 回落对 UX 的平滑处理完全可以闭环。

---

## 3. 第二轮修订新增细节与 TDD 实施规约核对

d1 在第二轮修订中不仅修复了 Round 1 的坑洞，还做到了多项工程设计层面的收拢：

1. **安全护栏先行 (T-2)**:
   - 检查 [tasks.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md) 中的任务排序。
   - `任务 5`（所有权分类与 env clamp 护栏）目前排在 `任务 6`（重做 Open/Attach 决策，含 start 动作）之前，成功消除了“生命周期写命令先落地而所有权护栏悬空”的中间不安全状态。
2. **测试驱动 (TDD) 的细化 (T-4)**:
   - 检查 [tasks.md](file:///root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/.kiro/specs/studio-ah-state-contract-v1/tasks.md) 中 `任务 2` 至 `任务 9`。
   - 每个任务头部均加入了明确的 **“先写红测试”** 块，指定了失败测试名和断言目标（例如 `test_starting_is_hands_off`、`test_readonly_active_close_is_detach` 等），保证了开发人员能完全遵循先红后绿的 TDD 开发规约。
3. **真实 CLI 验证的前置条件与 NF 实测证据 (NF-caveat / Task 0)**:
   - `任务 0` 增加了前置条件：daemon-absent 的快照采集必须在 **零 ahd** 干净环境下采集，因为全局发现机制会污染在跑的 daemon 信息。
   - 增加了 NF1（身份击穿回显）、NF2（环境变量隔离局限）和坑洞 3.2（sequence 恒为 1）在 1.5.0 下的直接采集证据项，产出要求存入 raw-capture 保证测试数据真实度。

---

## 4. 总体 verdict 结论

本次由 d1 执笔的 studio-ah-state-contract-v1 第二轮修订 spec (commit `f4da1164`)：
- **完整、无保留地**落实了 o1 上一次评审中提出的全部 5 条必改项及版本简化项。
- 正确利用实测（NF1/NF2）对身份校验和 env clamp 条款进行了物理安全意义上的重设计，修补了 config_path 被回显绕过和 1.5.0 读面未物理隔离的重大逻辑漏洞。
- 对被驳回项的解释基于物理隔离和延迟的硬性限制，理由十分充分。
- tasks 结构完美，具备严格 TDD 约束和安全护栏防错顺序。

**Verdict**: **通过 (Approved — 可开闸进入实施)**
建议直接推进 PR 合并与任务派单。
