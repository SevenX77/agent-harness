# 决议 2026-08-05 — 关闭即清场是产品预期；回到上次对话由显式 Resume 承担

> 本文件落盘两项 PM 裁决（2026-08-05 原话）："studio 关闭应该关掉所有的会话啊，并且应该
> 清掉所有 ah 的残留"；"如果要恢复上次对话应该加一个 resume 的功能和按钮"。
> 前序：`decision-2026-08-05-identity-anchor-and-tmux-server-alive.md`。

## 一、裁决 R1：app 退出的全量清扫是预期行为，不是隐患

`decision-2026-08-05-identity-anchor-and-tmux-server-alive.md` 的范围边界曾把
「退出时 `discover_studio_ah_configs()` 全量清扫会杀掉其它工作区仍在跑的会话」标注为
"独立隐患，另案待用户裁决"。**本裁决关闭该项：这是产品预期。** 所有权模型是：
Studio 启动的 CLI 会话归 Studio 所有，关闭 Studio = 全部会话关干净、残留清零。

已经成立的两条边界保持不变：

- 清扫只覆盖 **Studio 自己生成的临时配置**（`%TEMP%\skill-studio-ah`）；operator 自己的
  workspace `ah.toml` 编队被 `classify_config_ownership` 判为只读，Studio 从不对它发
  生命周期命令。
- 异常退出（launcher 被硬杀）会跳过清扫留下残留——由下一次 Open 的启动前清理兜底
  （2026-08-02 决议 D-A4/D-A5 双保险）。语义自洽：正常退出清场，异常退出的残留下次清。

## 二、缺陷 F：对话记录活不过关闭，「回到上次对话」在今天不可能

裁决 R1 的直接推论：关闭即清场，那"继续上次的对话"就必须是一个**显式功能**，
不能靠残留碰运气。而机制调查表明，今天连显式恢复的前提都不存在：

1. ah 给 claude master 设 `CLAUDE_CONFIG_DIR=<沙箱HOME>/.claude`
   （ah 仓 `src/provider/home_layout.rs:1813`，`provider_home_env`）——
   claude 的对话记录（`projects/<cwd-slug>/*.jsonl`）写进**沙箱 HOME**。
2. `ah stop` 时 ahd 把 master 的沙箱目录整个删除
   （ah 仓 `src/bin/ahd.rs:278`，`remove_agent_sandbox_dir_sync(..., "master")`）。

⇒ 正常关闭 = 对话记录随沙箱蒸发。此后无论怎么 `claude --continue`，都无话可续。

## 三、设计

### D-F1：对话记录经宿主 HOME 持久化（软链，与凭据同一手法）

claude 的启动包装脚本（Studio 生成的 master cmd）已经在把宿主的 `.claude.json` 与
`.claude/.credentials.json` 软链进沙箱；同一手法补一条：

```
$HOME/.claude/projects  →  $STUDIO_AH_HOST_HOME/.claude/projects
```

对话记录经软链写进宿主 WSL home，活过沙箱删除、活过 Studio 重启。

> **修订（2026-08-05 真机复验）**：初版把链段挂在 `STUDIO_AH_HOST_HOME` 守卫后面——
> 照抄了旁边凭据软链段的手法，但真机取证发现那批守卫**已是死代码**：master 环境里该
> 变量不存在（#596 改凭据链路后无人再注入它），`.claude.json` 是 ah 材料化拷的普通
> 文件、`.credentials.json` 不存在——凭据实际由 ah 的 `shared_credentials_dir` 机制
> 接管，那些软链段全部静默跳过。教训与 D-A3 同款：**照抄邻居的手法之前，先验证邻居
> 还活着。** 修正：宿主 home 是 WSL 里可查询的事实，脚本自己 `getent passwd` 派生，
> 零注入依赖；同时处理 ah 材料化预建空目录的坑（`ln -sfn` 对已存在目录会把链建进
> 目录里——先 `rmdir` 空目录再建链，非空则保留跳过，安全降级）。
> 已死的 `STUDIO_AH_HOST_HOME` 段（claude_real 回退、.claude.json/凭据软链、codex
> auth 同步）是 #596 的遗留，涉及凭据面，另案清理。

- **新开与恢复都做这条链**：新开必须写得持久，之后才有得恢复。
- **worker 不受影响**：worker 由 ah 直接拉起、不经 Studio 的包装脚本，无软链——
  worker 的对话留在各自沙箱里随之销毁。这是**特性**：master 的 `--continue` 按
  cwd 找对话，worker 的 cwd 与 master 相同，若共享目录，Resume 可能捞到某个
  worker 的对话；不共享则天然隔离。
- **按工作区隔离免费获得**：claude 本来就按 cwd 分目录存对话
  （`projects/<cwd 的 slug>/`），Resume 恢复的自然是**这个工作区**的上次对话。

### D-F2：Resume = 同一条启动流程，命令尾部分叉

`Open in CLI` 下拉新增 **"Resume Claude code"**。它走与 Open 完全相同的
决策/清理/启动流程（D-A4 的启动前清残留照常），仅 master cmd 的执行尾不同：

```
该工作区的对话目录非空  →  exec claude $mcp_args --continue     (不带初始 prompt)
目录为空/不存在        →  打一行说明,回落到全新启动(带 prompt)
```

- 不带初始 prompt：skill 绑定上下文（P4-E）在上次对话的历史里已经有了，重发是污染。
- 空目录回落而不是报错死掉：`--continue` 在无对话时会失败退出，master 秒死会把
  ah 会话拖进 FAILED——回落到全新启动是唯一不把用户扔在错误屏上的行为，且打印了
  说明，不是静默偷换。
- 对话目录的 slug 规则（路径非字母数字字符替换为 `-`）是 claude 的存储约定，
  Studio 只用它做"有没有得恢复"的预判；判错的最坏后果 = 回落到全新启动（安全降级）。
  真机验证步骤中显式核对该规则。

### D-F3：范围

- 仅 claude。codex 的恢复机制不同（ah manifest 中 codex `resume_args` 为空），
  Tauri 命令边界对 codex + resume 请求 fail fast。
- 已在跑的会话点 Resume 无意义——决策流程会照常走到 Attach（有活会话就 attach），
  resume 标志被忽略；UI 上 Resume 项只出现在 Open 下拉里（有活会话时头部本来就
  不渲染 Open 下拉）。
- 只读（workspace-owned）配置照旧禁用，与 Open 同一条禁用逻辑。

## 四、验收判据

| # | 判据 | 验证方式 |
|---|---|---|
| F-1 | claude master cmd（新开与恢复两种模式）都含 projects 软链 | Rust 单测 |
| F-2 | resume 模式的 cmd 含 `--continue` 且**不含**初始 prompt；fresh 模式反之 | Rust 单测 |
| F-3 | resume 模式含空目录回落分支（说明文案 + 带 prompt 的 exec） | Rust 单测 |
| F-4 | codex + resume 在命令边界被拒 | Rust 单测 |
| F-5 | 前端：Open 下拉含 "Resume Claude code"，点击以 resume 语义调用 | 前端单测 |
| F-6 | 真机：开会话→说一句话→Close→Resume→终端里能看到上次对话被续上 | 操作者实测 |
| F-7 | 真机：从未开过会话的工作区点 Resume→落到全新启动并打印说明 | 操作者实测 |

## 五、边界

不改 ah；不动 codex；不动退出清扫（裁决 R1 已确认现状）；不做"对话列表/多条恢复"
（`--resume <id>` 选单是后续需求，本决议只做"回到最近一次"）。
