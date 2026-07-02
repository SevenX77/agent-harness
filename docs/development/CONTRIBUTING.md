---
status: Living
target_goal: "贡献流程入口指路——唯一真相源是根目录 AGENTS.md,本文件不复述其内容"
linked_code_paths: []
linked_specs: []
last_updated: 2026-07-02
---

# 贡献指南 (Contributing Guide)

本仓库的贡献流程只有一份真相源:**根目录 [`AGENTS.md`](../../AGENTS.md)**。
本文件不重复它的内容(重复 = 双份真相,必然漂移),只做入口指路:

- **环境与依赖** → AGENTS.md「Baseline & Working Environment」:Python 是单一 uv
  workspace(`uv sync --all-packages --all-extras --group dev`,单一根 `uv.lock`),
  前端用 npm。
- **启动 app** → AGENTS.md「Studio Tauri Dev」:从仓库根跑
  `scripts/studio-dev.ps1`(Windows)/ `scripts/studio-dev.sh`(macOS/Linux),
  launcher 统一拉起 Tauri + Vite + FastAPI sidecar 并钉住 sidecar 端口。
  **不要**手动分别起 Vite 和 uvicorn,也不要绕过 launcher 直接 `cargo tauri dev`。
- **分支、PR 与合并** → AGENTS.md「Workflow Pipeline」:一任务一 worktree
  (`scripts/wt-new.sh <type>/<short-desc>` 从 `origin/main` 切),`main` 是
  protected、PR-only;`scripts/wt-ship.sh` 推分支 + 开 PR + auto-merge,合并后
  `scripts/wt-clean.sh` 清理。Commit message 遵循 Conventional
  Commits(`feat(engine): ...`)。
- **推送前门禁** → AGENTS.md「CI Gates」:ruff / mypy(SDK 用 `--strict`)/
  pytest×3 / 前端 lint+typecheck+test+build / pip-audit,**全部**本地跑绿再推。
- **Studio 功能开发**(前端驱动、允许全栈)→ 先读
  [`apps/studio/frontend/CLAUDE.md`](../../apps/studio/frontend/CLAUDE.md)
  (单 agent 功能 SOP);交接模板见
  [`FRONTEND_HANDOFF_PROMPT.md`](FRONTEND_HANDOFF_PROMPT.md)。
- **跑 app / worktree 预览 / 无头验证与截图** →
  [`RUN_AND_SCREENSHOT.md`](RUN_AND_SCREENSHOT.md)。
- **跨平台与编码铁律** → [`CROSS_PLATFORM.md`](CROSS_PLATFORM.md)。
