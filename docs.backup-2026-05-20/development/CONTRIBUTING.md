---
status: Living
target_goal: "定义向本仓库贡献代码的基础准则、起步命令及测试规范"
linked_code_paths:
  - apps/studio/frontend/package.json
  - Makefile
linked_specs: []
last_updated: 2026-05-19
---

# 贡献指南 (Contributing Guide)

## 1. 环境准备与包管理
我们使用 `uv` 维护统一的 Python Monorepo 依赖，使用 `npm` 管理前端。
```bash
# 全局安装 uv (如已安装则跳过)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 在根目录同步并生成虚拟环境
uv sync
```

## 2. 研发端启动命令
对于二次开发者，你通常需要拉起全栈的 Studio：
```bash
# 启动前端 (包含热重载)
cd apps/studio/frontend
npm install
npm run dev

# 启动伴生后端服务
cd apps/studio/backend
uv run uvicorn app.main:app --reload --port 8000
```
> **注意**: 生产环境会由 Tauri 自动把打包好的后端编译成可执行文件拉起。开发期你需要分别在两个 Terminal 跑。

## 3. Git 流与提交规范
- 所有开发请在新分支进行，命名采用 `<type>/<issue-id>-<brief>` (例 `feat/123-add-nudge-trace`)。
- 提交前请确保运行通过 `uv run ruff check .` 和前端的 `npm run lint`。
- Commit message 遵循 Conventional Commits (`feat(engine): ...`)。

## 4. 远程 GUI 测试最佳实践
在跑包含 Tauri 界面 E2E (如 Playwright) 的自动化测试时，针对无头服务器环境：
1. 确保系统安装了 `xvfb`。
2. 使用包裹命令运行，例如：`xvfb-run npm run playwright` 以模拟虚假的 X11 屏幕缓冲，防止崩溃。

## 相关 Spec
本指南无直接的 Active 施工单，请在遵守以上契约的前提下随意发起 PR 完善基建。
