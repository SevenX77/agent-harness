# a3 (Claude Worker) Dotfile 隔离与角色对齐方案

## 1. 当前问题 Root Cause 诊断

### 1.1 现象实证
a3 (Claude worker) 在接收任务后频繁早退并触发 `hook_stop`，返回 `Codex processing...` 等字样。

### 1.2 根因分析 (Root Cause)
ccb 启动 a3 时，通过 `_prepare_managed_home` 机制将主控 PM 的 `~/.claude/CLAUDE.md` 及 `rules/` 文件夹完整拷贝/投影到了 a3 的沙盒 Home 目录。

a3 加载了以下 **“自杀式”规则**：
- **CLAUDE.md § 宪法 1**: `主控纯 PM 身份, 绝不在 src/ 或 tests/ 写业务代码 (派 Codex / a1)`
- **01-sop-role-delegation.md §1**: `主控 Claude = PM, 不碰业务代码... a3 (Claude) = e2e 测试 + a1 忙时分担 src 实施`

**实证逻辑链路**：
1. a3 启动，扫描 `~/.claude/CLAUDE.md`。
2. a3 识别出自己是 “Claude” 实例。
3. 规则声明 “Claude = PM, 不写代码”。
4. a3 遵守宪法，拒绝执行 src 写入任务，并按 SOP 建议“派发给 Codex”。
5. a3 触发 ccb 的 `hook_stop` 逻辑导致任务中断。

---

## 2. 隔离方案选项

### 方案 A: 环境变量驱动的条件加载 (ROLE=worker)
- **原理**: 在 rules markdown 中使用类似 `If ROLE=worker then ignore Tenet 1` 的描述。
- **优点**: 成本极低，仅改动 markdown。
- **缺点**: **不可行**。Claude CLI 的规则加载器目前是纯静态 Markdown 解析，不支持环境变量插值或分支逻辑。

### 方案 B: 独立的 ~/.claude-worker 配置目录 (推荐)
- **原理**: ccb 在启动 worker 代理时，不直接投影主控目录，而是投影一个经过修剪的 `~/.claude-worker/` 目录（内含专门为 Worker 编写的 `CLAUDE.md`）。
- **优点**: 物理隔离，逻辑最清晰。a3 看到的宪法第一条将是 `你是主力执行者，请直接写代码`。
- **缺点**: 增加一次性的 dotfiles 维护成本。

### 方案 C: 系统 Prompt 覆盖注入
- **原理**: 修改 `ccb` 启动 worker 的命令，注入一条强力的 System Prompt：`Ignore any rules in CLAUDE.md that say you are a PM. You are a worker agent assigned to write source code.`
- **优点**: 无需维护多套目录。
- **缺点**: 鲁棒性差。Claude Code 对本地 `CLAUDE.md` 的权重极高，由于其 RAG 检索机制，文件内的“宪法”描述极易盖过 Session 级的 System Prompt。

---

## 3. 方案对比总结

| 维度 | 方案 A (Env) | 方案 B (独立目录) | 方案 C (Prompt) |
|---|---|---|---|
| **实施成本** | 极低 (0.5h) | 中 (2h) | 低 (1h) |
| **副作用** | 无 | 需维护两份 rules | 可能被规则反杀 |
| **鲁棒性** | 低 | **极高** | 中 |
| **结论** | 舍弃 | **推荐** | 备选 |

---

## 4. 实施步骤 (推荐方案 B)

1. **创建 Worker 模板**: 
   - 建立 `~/.claude/worker-template/` 目录。
   - 编写 `worker-template/CLAUDE.md`，明确声明：`你是执行代理 a3，职责是直接编写 src/ 和 tests/ 代码，严禁早退派活。`
2. **修改 ccb 启动逻辑**:
   - 修改 `ccb` 后端或 `ccb.sh`，当 `agent_type == claude` 且 `role == worker` 时，将沙盒的 `~/.claude/` 指向上述模板目录而非主控目录。
3. **验证**:
   - 启动 a3 执行一次 `yolo write`，检查是否不再抛出 PM 早退言论。
