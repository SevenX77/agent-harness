# Node 1: 发现与初始化 (Discovery & Init)

## 1. 业务目标
定义 PM 如何进入 Studio 以及如何开启一个新的任务。本节点确立了 Studio 的顶层导航心智：“主页 (Home)” 与 “专注的工作空间 (Skill Workspace)” 的强隔离。

## 2. 核心范式：强隔离的 Home 与 Workspace

参考 Coze、n8n 等成熟的 Agent/Workflow 编排产品，Studio 采用 **“主页 Dashboard + 沉浸式 Workspace”** 的强隔离模式。当前的“左侧边栏列出所有 Skill”是反模式，一个 Studio 窗口应当专注服务于一个正在开发或调试的 Skill。

### 2.1 主页 (Home / Dashboard)
这是 PM 打开 Studio 时看到的第一屏。它的作用类似于 VS Code 的欢迎页。
- **纯粹的入口**: 提供极简的两个动作：
  1. **新建 Skill 文件夹**
  2. **打开现有 Skill 文件夹**
- **操作心智**: 这里的“打开/新建”在 UI 上只做最简单的事情——在文件系统中选定或创建一个空目录，然后立即发生页面路由跳转，进入沉浸式的 **Skill Workspace**。没有任何复杂的弹窗表单。

### 2.2 沉浸式工作区 (Skill Workspace)
一旦进入某个 Skill 的文件夹，整个窗口的上下文完全锁定在此 Skill 上。
- **去除全局导航**: 左侧边栏不再展示整个 `skills/` 目录树，只展示当前 Skill 内部的相关文件（如 `SKILL.md`, `script/`, `references/`, `golden/`）。
- **返回机制**: 左上角提供明显的 `[ ← Back to Home ]` 按钮退出当前专注模式。

## 3. 界面元素与 Copilot 占位

### 3.1 Copilot 侧边栏 (右侧)
- 遵循行业习惯，Copilot 对话面板固定在 **界面最右侧**。
- **基于对话的创建向导**: 复杂的创建逻辑（确认类型、定义 Schema、生成骨架）不通过 Studio 的 UI 弹窗实现，而是作为 `create-skill` 交给 Copilot。PM 在新建空文件夹后，直接在右侧与 Copilot 对话完成 `SKILL.md` 的初始生成。

### 3.2 外部 IDE 联动快捷键
在 Copilot 侧边栏的顶部或 Workspace 的全局 Navbar 右侧，提供一组极其重要的快捷键/按钮，保证 PM 能够快速在当前 Skill 路径下唤起外部的 AI 辅助工具：
- `[ Open in Cursor ]`：一键在 Cursor IDE 中打开当前专注的 Skill 文件夹。
- `[ Open in Terminal ]`：一键打开终端并 `cd` 到当前目录。
- `[ Open in Codex ]`：唤起关联的 Codex 工具。

## 4. 下游流转
当在 Workspace 中通过 Copilot 或手动初始化了 `SKILL.md` 后，PM 将注意力转移到界面的中左侧，进入 **[02_EDIT_AND_COMPILE](./02_EDIT_AND_COMPILE.md)** 节点。
