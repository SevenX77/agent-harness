# workspace-file-system (studio system-level) — Baseline (Round 31 收缩版)

> **Status**: Updated by a1 (Codex), 2026-05-30
> **Scope**: Studio 如何决定 skill workspace 根目录；Engine 子结构不在本文件定义。
> **配套**: Engine 子目录规范见 [workspace-spec](../../../engine/workspace-spec/baseline.md)。

## 1. 范围收缩

Studio 负责回答一个问题：当前 skill 的 workspace 根目录在哪里。

Engine 负责回答另一个问题：传入的 `workspace_dir: Path` 下面应该有哪些子目录、哪些文件、由哪些 SDK verb 写入。

因此，`.workspace` 子目录结构规范由 Engine 定义，见 `docs/engine/workspace-spec/baseline.md`。Studio 只负责 workspace 根目录定位，例如：

`~/.studio/projects/<skill>/.workspace/`

本文件不再维护 runs / golden / test_inputs 的字段级结构，避免 Studio 文档和 Engine 文档双写漂移。

## 2. Studio 现有文件系统入口

用户在 Welcome 页面有两个文件系统入口：

- New skill
- Import skill

现状实证：

- New skill / Import skill UI 入口：`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:174-197`
- Import skill 调系统目录选择器并把目录交给后端：`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:127-137`
- Tauri 侧只提供目录选择、Reveal、打开外部工具等桌面能力；不是 Engine workspace 子结构 owner：`apps/studio/frontend/src/lib/tauri.ts:64-74`

## 3. Studio 现有 workspace root 定位

Studio backend 当前以 skill 目录下的 `.workspace` 作为 workspace root。

现状实证：

- `workspace_dir_for(skill_dir)` 返回 `skill_dir / ".workspace"`：`apps/studio/backend/app/services/skills.py:734-735`
- 新建 skill 时当前只确保 `.workspace` 本身存在：`apps/studio/backend/app/services/skills.py:476-477`
- `resolve_skill_dir()` 负责把 `skill_id` 定位到实际 skill 目录：`apps/studio/backend/app/services/skills.py:708-726`

Round 31 后，Studio 将这个 root 作为 `workspace_dir: Path` 传给 SDK。Engine 绝对不知道 Studio 默认目录、用户目录、导入目录或 `~/.studio` 约定。

## 4. Engine 子目录规范迁出

`.workspace` 子目录结构规范由 Engine 定义。

见：

`docs/engine/workspace-spec/baseline.md`

Studio 文档只保留 root 责任：

- Studio 决定 `<workspace_dir>` 是哪个绝对路径。
- Studio 把 `<workspace_dir>` 传给 `run_skill` / `predict_skill` / `evaluate_golden_baseline`。
- Studio 不定义 `<workspace_dir>` 下面的 Engine 子目录字段。

## 5. 当前遗留点

当前 Studio backend 仍保留通用 workspace helper；Predict 专用 helper 已清理：

- `runs_dir_for(skill_dir)`：`apps/studio/backend/app/services/skills.py:738-739`
- `golden_dir_for(skill_dir)`：`apps/studio/backend/app/services/skills.py:742-743`

`predict_dir_for()` 已被 Engine workspace spec 明确废除；Predict 结果和日志进入 `<workspace_dir>/runs/<run_id>/`，Studio skill detail response 不再返回 `file_paths.predict_dir`。

当前 `STUDIO_GITIGNORE` template 不再放行旧 Predict 子目录：

- `apps/studio/backend/app/services/git_local.py:21-26`
- template 由 `write_studio_gitignore()` 写入每个 skill 项目目录的 `.gitignore`：`apps/studio/backend/app/services/git_local.py:320-323`

## 6. 与 Engine workspace spec 的协同铁律

- 本文件不写 Engine 子目录字段级清单。
- 推演结果与日志只引用 `<workspace_dir>/runs/<run_id>/`。
- SDK 动作只写 `run_skill` / `predict_skill` / `evaluate_golden_baseline`。
- 旧 Predict 子目录只在“遗留清理”语境出现，不作为目标结构。
