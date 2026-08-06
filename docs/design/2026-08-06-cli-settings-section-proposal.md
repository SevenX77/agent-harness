# 提案：Settings → Copilot 增设「CLI」区(安装/鉴权/配置,分操作系统)

- 状态:**提案待 PM 批准**(2026-08-06)。批准后本文内容写回设计源
  `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`,再开工实施。
- 需求来源(PM 原话,2026-08-06):「加一个与Claude sdk平行的设置,cli的设置,把在
  copilot里面使用open in cli 所需要的所有的包安装、登录鉴权等状态和一键安装功能都
  做上去,还得分不同操作系统。再加上一些配置选项,比如使用的默认模型,effort等配置,
  Moirai的不同角色的不同配置」。

## 一、定位与形态

- **落点**:Settings → Copilot 页内,与现有「Claude Agent SDK」手风琴**并列**新增
  「CLI」手风琴(CatalogAccordion)。理由:copilot 的两条能力面(SDK 聊天面 + Open in
  CLI 编队面)在同一页看全;「与 Claude sdk 平行」按原话直译为同级 section。
  放弃的替代:独立顶层 tab——体量撑得起,但把 copilot 能力拆两处,放弃。
- 「CLI」区含三块:**依赖与鉴权状态**、**一键安装**、**会话配置**。

## 二、依赖与鉴权状态(分操作系统)

- **owner = Tauri 层**。依赖探测/安装是桌面本机事实,不走 FastAPI(sidecar 只管
  HTTP API 域)。新增 tauri 命令:
  - `cli_dependency_status()` → 按当前 OS 返回依赖链逐项状态
    `{name, state: ok|missing|broken|outdated, version?, detail?}`。
  - 探测复用现有基建:`check_ah_version_cached`(AH_VERSION_MIN 门)、
    `install-claude-code-wsl.ps1` 的检查逻辑。
- **依赖链(Windows)**:WSL 可用 → ah(版本 ≥ 门槛) → tmux → claude CLI
  (native、非 /mnt Windows 二进制) → codex CLI。
  **macOS/Linux**:去掉 WSL 层,直接探测本机 ah/tmux/claude/codex。
- **鉴权状态**(读态,不碰凭据明文):
  - claude:host home `.claude/.credentials.json` 存在且未过期(expiresAt)→
    「已登录」;stub/缺失 → 「未登录」+ 引导(打开终端跑 `claude /login`)。
  - codex:`~/.codex/auth.json` 存在 → 「已登录」;缺失 → 引导 codex login。
  - 边界:Studio 只读状态、只引导,**绝不代填凭据**;凭据共享继续走 ah
    `shared_credentials_dir`(#596),本区不新建第二条凭据通道。

## 三、一键安装

- 每个 missing/outdated 依赖项旁一个安装钮;点击 = Tauri 起对应安装流程
  (Windows:wsl + 官方安装脚本;macOS/Linux:brew/官方脚本),输出流式打到一个
  只读终端视图(复用 CLI 终端组件),完成后自动重探。
- 安装进行中该项转 spinner(hands-off 窗口不给可点假按钮,沿用 loading 纪律)。
- 失败显式报错误输出,不静默;不自动重试。

## 四、会话配置(默认模型 / effort / MoirAI 分角色)

- **truth = studio backend settings**(runtime 唯一真相源文件,与「通用」页同一
  存储),前端经 FastAPI 读写;**消费点 = Tauri**:open 时前端把配置随 invoke 传入,
  Tauri 生成 master cmd / ah.toml `[agents.*]` 时注入对应旗标。
  理由:产品配置要进备份/同步域(backend truth),而 ah.toml 生成在 Tauri——
  「前端读 truth → 传参给 launcher」比「Tauri 反向拉 sidecar」链路短、无新耦合。
- **配置面**(第一期只做已确认有对应 CLI 旗标的):
  - claude:默认模型(`--model`)、effort(映射 `MAX_THINKING_TOKENS` 或
    `--effort`,以 claude CLI 实测支持为准)。
  - codex:默认模型(`-c model=`)、reasoning effort(`-c model_reasoning_effort=`)。
  - **MoirAI 分角色覆盖**:moirai(master)/clotho/lachesis/atropos 四行,每行可
    覆盖 model/effort,空 = 继承 provider 默认。落进 ah.toml 各 `[agents.*]` 的
    cmd/env。
- 自动保存沿用 settings autosave 并发语义(防抖期只留最新快照,旧响应不得覆盖新草稿)。

## 五、分期与验收

| 期 | 内容 | 验收 |
|---|---|---|
| PR-1 | 状态面板:依赖链探测 + 鉴权状态显示(双 OS 探测逻辑,UI 一套) | Rust 单测(探测纯函数) + 真机截图 |
| PR-2 | 一键安装 + 流式输出 + 完成重探 | 真机:删一个依赖装回来(或 dry-run 单测 + 现状机截图) |
| PR-3 | claude/codex 默认模型 + effort 配置,进 master cmd | Rust 单测锁 argv + 真机进程表验证 |
| PR-4 | MoirAI 分角色覆盖,进 ah.toml [agents.*] | Rust 单测锁 toml + 真机开编队验证 |

## 六、边界

- 不代填任何凭据/密码;不新建凭据存储;不动 ah 的 shared_credentials_dir 机制。
- 不做「CLI 版本自动升级守护」(升级 = 一键安装的重装,不做后台自动)。
- MoirAI 角色的 prompt/技能配置不在本区(那是 `.ah/` 与 agent-skill-map 的域),
  本区只管 model/effort 这类运行参数。
