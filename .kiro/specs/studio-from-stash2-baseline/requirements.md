# Requirements: Studio from Stash Baseline

> **Status**: Draft v0.1
> **Date**: 2026-05-17
> **Author**: a2 (Gemini) primary + PM (sevenx) 决策锁定
> **Baseline**: `feat/copilot-v1-backend` HEAD `e252fe9` + `stash@{2}` applied
> **Implementer**: a1 (Codex)
> **依赖**: V2.1 engine (`packages/graph-agent/` + `skills/` from `main`)

## R0: 范围声明与基线 (Scope & Baseline)

- **When** 启动迁移整合，**the system shall** 严格基于 `/tmp/agent-harness-v1/` 目录下的 `e252fe9` commit 叠加 `stash@{2}` 的物理状态作为基线，并整合 `main` 分支上 V2.1 engine (从 `packages/graph-agent/` 及 `skills/` 获取)，彻底废弃 `main` 上错误的前端基线代码。

## R1: V2.1 文件 Layout 适配 (Asset Enumeration)

- **When** 用户在 Studio 打开 Skill 工作区，**the system shall** 通过现有的 `AssetsPanel` 正确解析并展示 V2.1 标准的目录结构，包括顶层 `GRAPH.md`、`phases/<id>/{SKILL.md, LOGIC.md, SUBGRAPH.md}` 以及 `io/{inputs.json, outputs.json}`。

## R2: Monaco 实时编辑与防抖写盘 (Auto-Save)

- **When** 用户在 Monaco 中敲击修改代码，**the system shall** 触发 1500ms 的防抖 (debounce) 计时，计时结束后直接写回本地物理文件（并非 Git 提交），全程无脏状态和 Save 按钮。
- **When** 用户在 debounce in-flight 期间切换文件或卸载组件，**the system shall** 立即执行 `flush()` 强行写盘，保证最后一笔修改不丢失。
- **When** 实时保存遇阻（断网或文件锁），**the system shall** 开启静默指数退避重试，连续 3 次失败后弹出全局强制警告 (Toast/Banner)。

## R3: Canvas 双击联动加载 (Canvas-to-Editor)

- **When** 用户在 Canvas 画布上双击任意 Phase 节点，**the system shall** 将该节点的文件路径投递给顶层 `Workspace.tsx` 的全局 Context，进而触发与 `AssetsPanel.onFileOpen` 相同的管线，最终在 `SplitEditor` 的双 Monaco 实例之一中加载对应文件。

## R4: 子图下钻与全面编辑 (Subgraph Drill-down)

- **When** 用户双击 Canvas 中的 Subgraph 引用节点（即便跨 skill），**the system shall** 推入下钻导航栈 (navStack) 并刷新画布至子图内容，同时在顶栏渲染面包屑导航 (Breadcrumb)。
- **When** 展现子图及对应源码，**the system shall** 保持全量可编辑状态，取消任何 Read-only 限制或额外警告横幅。

## R5: 多端同步与冲突解决 (Multi-source Sync)

- **When** 外部 IDE 物理修改了 Skill 文件，**the system shall** 通过后端 Python `watchfiles` 监听到变更，过滤掉 Studio API 的 echo 写盘后，经由 WebSocket 向前端下发 `skill_changed` 事件。
- **When** 前端发生本地 Monaco in-flight 且收到 WS `skill_changed`，**the system shall** 暂停自动重载，并弹窗 "Local vs Remote" 提示供用户主动裁决 (Keep Local / Use Remote / Diff)。

## R6: V2.1 Engine API 适配 (API Contract)

- **When** 执行运行或编译时，**the system shall** 全面对接 V2.1 `compile_skill` / `run_skill` 的新签名接口，并正确解析与透传新引擎的错误回传。
