---
status: Living
target_goal: "规范 Tauri 前端对操作系统文件树的渲染逻辑与隐式初始化动作"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/Panels.tsx
linked_specs:
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Workspace 与文件树管理 (Workspace File Management)

## 1. Tauri 端对 OS 文件树的直接渲染
借助 Tauri 的底层桥接，Studio 前端彻底摆脱 Web 沙盒限制：
- 当 PM 选择了一个操作系统路径作为 Skill 后，前端直接调用 Tauri `fs` API 拉取目录快照。
- 在左侧边栏 (AssetsPanel) 中，使用树状折叠组件渲染该目录下的所有 `.py`, `.md`, `.json` 文件。
- 提供原生的右键菜单功能以执行新建、重命名等动作，与 VS Code 体验对齐。

## 2. `.workspace` 隐式初始化机制
当 PM 选择一个空文件夹，或者一个未曾经过 Studio 处理的旧 Skill 目录时：
1. 后端检测当前目录是否拥有 `.workspace/` 和核心的 `SKILL.md`。
2. 若无，立刻在背景（无需打断用户弹窗）隐式创建骨架，生成标准的空白 `SKILL.md` 模板与初始配置目录。
3. 前端树自动收到 FileWatcher 事件并平滑重绘。

## 3. Asset Sidebar 组件标准
- 树状结构必须按照类型排序：文件夹在上，文件在下。
- 特殊标识：`SKILL.md` (总控)、`golden/` (测试基线) 等文件夹在 UI 上配备专属高亮 Icon，强化其在整个产品中的特殊战略地位。
- 点击文件即刻联动右侧的 `SplitEditor` 或 `LazyMonacoPanel` 展示代码内容，避免繁重的 Tab 堆叠。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
