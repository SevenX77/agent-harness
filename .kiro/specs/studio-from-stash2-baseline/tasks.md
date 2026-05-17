# Tasks & Execution Waves

> **Status**: Draft v0.1
> **Date**: 2026-05-17
> **Author**: a2 (Gemini)
> **Implementer**: a1 (Codex)
> **Total a1 工时**: ~20.5h (±20%)

## Wave 1 (Tier 1 Base)

- **T1.1**: 基于 `e252fe9` 新建分支 `feat/studio-from-stash2-baseline` 并应用 `stash@{2}`，确保应用可成功启动 (UI 显示 3-tab)。
  - **DoD**: 可通过 `npm run dev` 启动，无严重前端崩溃。
  - **工时估算**: 1.0h

- **T1.2**: Cherry-pick `main` 上对 `packages/graph-agent/` 及 `skills/` 的 V2.1 引擎更新。
  - **DoD**: V2.1 的纯逻辑测试全数通过。
  - **工时估算**: 1.0h

## Wave 2 (Tier 2 Backend Cutover & Save Flow)

- **T2.1**: 拆解并合并 `a53e72c` (V2.1 cutover) 与 `4c9b968` T2 Endpoint (canvas serializer)，全面接驳 V2.1 API 契约与序列化。
  - **DoD**: 前端成功调用 compile 与 run，后端无缝支撑单文件写盘 API。
  - **工时估算**: 3.0h

- **T2.2**: 实现基于 Python `watchfiles` 的文件监听及 Echo 过滤。
  - **DoD**: API 触发不回弹事件；VS Code 手动修改文件能引发后端的 WebSocket `skill_changed` 推送。
  - **工时估算**: 3.5h

## Wave 3 (Tier 3 Direct Copy)

- **T3.1**: 拷入并合并纯逻辑、非侵入式补丁代码 (Lint 负债处理 `37b121e`, Vite proxy dev-tunnel 穿透配置 `e374245`, Terminal cancellation 桥接修复 `83d13f5`)。
  - **DoD**: 终端退出机制稳健，无 Lint/Format 警报。
  - **工时估算**: 0.5h

## Wave 4 (Tier 4 UI Reimplements)

- **T4.1**: `AssetsPanel` 树状层级遍历及 V2.1 layout 兼容化 (改造 `manifestFiles()` 输出 GRAPH.md + phases/<id>/{SKILL.md,LOGIC.md,SUBGRAPH.md} + io/{inputs,outputs}.json)。
  - **DoD**: 完全正确的嵌套展开，展示 `/phases` 及 `/io` 目录数据。
  - **工时估算**: 1.5h

- **T4.2**: `SplitEditor` 双 Monaco 实例封装及 `Workspace.tsx` `activeFiles` 管线连接。
  - **DoD**: 左右分屏顺畅加载异构数据文件。
  - **工时估算**: 1.5h

- **T4.3**: Monaco `1500ms` 防抖实时写本地保存、组件卸载 `flush` 闭环以及静默重试机制 (指数退避, 3 次失败 Toast)。
  - **DoD**: 停顿秒存，卸载必存，失败重试 3 次后 Toast 精准抛出。
  - **工时估算**: 2.5h

- **T4.4**: 跨端冲突阻断验证体系 (Local vs Remote 弹窗逻辑, Keep Local / Use Remote / Diff 三选)。
  - **DoD**: 成功拦截被后端 WS 回流覆盖风险，提供 User 裁决对话框。
  - **工时估算**: 2.0h

- **T4.5**: Canvas 双击直接抛射 `Workspace.tsx` 侧的 `onFileOpen` 调用 (lift state, 跟 AssetsPanel 同管线, 不要 CustomEvent)。
  - **DoD**: 双击 Phase 立即载入内容并由左右任意 Monaco 响应呈现。
  - **工时估算**: 0.5h

- **T4.6**: Subgraph 下钻支持、顶栏 `navStack` 面包屑串联且**撤销 Read-only** (全可编辑, 无横幅警告)。
  - **DoD**: 双击穿透远端 Subgraph 技能，顶部 Breadcrumb 展示正常且退级畅通；引用 skill 全可编辑。
  - **工时估算**: 3.0h

## 依赖关系 (拓扑序)

```
Wave 1 (T1.1, T1.2)
   ↓
Wave 2 (T2.1, T2.2) ←─ T2.2 必须在 T2.1 之后 (file_watcher 接 event_bus)
   ↓
Wave 3 (T3.1) ─── 可与 Wave 2 并行 (无依赖)
   ↓
Wave 4 (T4.x):
   T4.1 → T4.2 → T4.3 → T4.4
              ↘ T4.5 → T4.6 (Canvas 联动依赖 SplitEditor 就位)
```

## 总工时

- Wave 1: 2.0h
- Wave 2: 6.5h
- Wave 3: 0.5h
- Wave 4: 11.0h
- **Total**: ~20.0h ±20% (16.0-24.0h)
