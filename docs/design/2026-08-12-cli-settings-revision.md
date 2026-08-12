# CLI 设置区修订：版本检查 / 更新与登录按钮 / 全称文案 / codex effort 修正 / 模型下拉 / worker effort

- **日期**: 2026-08-12
- **状态**: 已批（用户口头批准「其他先实施」，同日）
- **范围**: Settings → Copilot →「CLI」区（设计源 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.9）
- **来源**: 用户对该区的七条实测反馈（2026-08-12）。第 1 条（本机 ah 缺失）是机器环境问题不改代码，
  其余六条按本文实施。

## 决策

1. **依赖行文案写产品全称**：`Claude CLI → Claude Code CLI`、`Claude 登录 → Claude Code 登录`
   （en: `Claude Code sign-in`）。"Claude" 与 "Claude Code" 是两个东西，UI 不得用简称。
2. **codex effort 档位修正**为 `light / medium / high / xhigh / ultra`。
   证据：本机 codex-cli 0.147.0 TUI 五档 Light/Medium/High/Extra High/Ultra（用户截图）；
   `~/.codex/config.toml` 中 Extra High 持久化为 `model_reasoning_effort = "xhigh"`；
   codex 二进制 strings 含 `light`/`xhigh`/`ultra` 与 Ultra 档副标题
   "Consumes usage limits faster"。旧档位 `minimal/low/medium/high` 是过时词表，删除。
   claude 档位 `low/medium/high/xhigh/max` 经 `claude --help` 复核仍正确，不动。
3. **会话默认模型从自由输入改为下拉**（选择而非填写）：
   - Claude Code：`fable / opus / sonnet / haiku`（官方别名，`--help` 原文举例
     'fable', 'opus', 'sonnet'；二进制 strings 四个别名俱在。别名指向 latest，目录不随小版本过期）。
   - Codex CLI：`gpt-5.6 / gpt-5.6-sol / gpt-5.6-luna / gpt-5.6-terra / gpt-5.6-pro`
     （codex 0.147.0 二进制 strings 挖出的当前 gpt-5.6 家族）。
   - 目录是 UI 选择目录（常量，放 CliSection 内 effort 档位旁、带证据注释），**不是** gateway
     的凭据/route 真相；CLI 订阅模型与 API 模型两个世界，不进 gateway registry。
   - 首项恒为「跟随 CLI 默认」（空串哨兵语义不变，settings schema 不动）。
4. **MoirAI worker 三行（clotho/lachesis/atropos）改为 模型下拉 + effort 下拉**，
   默认项均为「跟随 provider 默认」。模型目录/effort 档位与 Claude Code 相同（worker 仅
   claude provider 生效，既有边界不变）。
   - 注入通道：模型沿用 `[agents.X].env` 的 `ANTHROPIC_MODEL`；effort 新增
     `CLAUDE_CODE_EFFORT_LEVEL`（证据：claude 2.1.228 二进制 strings 含该环境变量名）。
     原设计「worker 级 effort 无环境变量证据,不注入」的前提已被推翻，据此更新 §3.9。
   - 数据形状：`CliSessionLaunchConfig.agent_models: Map<String,String>` 替换为
     `agent_overrides: Map<String, {model, effort}>`（pre-release 直接替换，无兼容层）。
     backend `AppSettings.cli_sessions.agents` 本就存 `{model, effort}`，schema 零改动。
5. **版本自动检查**并入现有探测动作（进区冷加载 + 手动「重新检测」，不加定时器，守
   SSOT revalidation 边界）。探测脚本内用 `curl --max-time 4` 后台并行查三个最新版：
   claude → npm `@anthropic-ai/claude-code`，codex → npm `@openai/codex`，
   ah → GitHub `SevenX77/ah` releases/latest（三源本机实测可达且版本号与已装可比）。
   已装 < 最新 → 该行转 `outdated`（黄）+ detail 标注最新版号；**查询失败（断网/超时）只显示
   已装版本，绝不据此标 outdated**。ah 低于 `AH_VERSION_MIN` 的既有判定优先级更高（那是
   "Studio 没法用"，不是"有新版"）。
6. **行内动作按钮**（可见控制台承载，理由与已批安装设计相同：更新/登录有进度与交互，后台
   静默失败不可见）：
   - `claude` / `codex` 行 `outdated` → 「更新」→ 控制台跑 `claude update` / `codex update`
     （两 CLI 自带的检查+安装一体命令，help 实测在案）。
   - `claude_auth` / `codex_auth` 行 `missing|broken` → 「登录」→ 控制台跑
     `claude auth login` / `codex login`（与 launcher login-doorman、安装脚本 B2 步同款命令）。
   - `ah` 行继续走既有「安装 / 修复」控制台（安装脚本幂等，兼任 ah 升级）。
   - 命令在 Rust 侧按 provider 枚举定死，前端只传 provider 标识，不传任意字符串。
   - 非 Windows 平台与安装按钮同策略：明确报错引导手动命令，不猜终端。

## 不做什么

- 不改 backend settings schema；不把 CLI 模型目录挂进 gateway；不加定时轮询/自动更新；
- 不代填任何凭据（登录控制台里的 OAuth 由用户完成）；
- 本机 `wsl.conf default=ahe2e` 的环境修复是机器操作，不属本修订（另行处理）。

## 验收判据（逐项点验用）

1. CLI 区五行文案含全称（zh/en 两份 locale）。
2. codex effort 下拉恰为 light/medium/high/xhigh/ultra；claude 档位不变。
3. 两个 provider 的模型为下拉（含「跟随 CLI 默认」首项），选择后 autosave 生效并注入
   启动命令（`--model` / `-m`）。
4. worker 三行为 模型+effort 双下拉；选择后 ah.toml `[agents.X].env` 同时含
   `ANTHROPIC_MODEL` 与 `CLAUDE_CODE_EFFORT_LEVEL`（单元测试 + 真机会话 `/status` 复核）。
   实测遗留点：worker env 的 `ANTHROPIC_MODEL` 是否吃别名——不吃则 worker 模型目录换全名。
5. 本机三行（ah/claude/codex）在"已装=最新"时不出现更新按钮；人为构造旧版本数据时
   行转黄、detail 带最新版号、更新按钮出现并能拉起控制台。
6. 登录行 missing/broken 时出现登录按钮，点击拉起控制台跑对应登录命令；完成后
   「重新检测」转绿。
7. 前端四门禁 + `cargo test` 全绿。
