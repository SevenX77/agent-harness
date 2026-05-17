# Domain B · Studio 工作台 (`apps/studio/`)

> Studio = 让 PM 不开终端、不写 YAML 就能可视化编写/改/跑 V2.1 skill 的 GUI。
>
> 由 3 部分组成:
> - **frontend** (`apps/studio/frontend/`): React + Vite + Monaco + React Flow + Zustand
> - **backend** (`apps/studio/backend/`): FastAPI sidecar, 14 routers + 13 services, 把 GUI 操作翻译给 Engine
> - **tauri** (`apps/studio/tauri/`): Rust 桌面壳, 把 frontend + backend 装成原生 app

← 回 [docs/](../README.md) | 当前基线: [STUDIO-BASELINE-2026-05-17.md](../STUDIO-BASELINE-2026-05-17.md)

---

## Living 文档清单

| 文档 | 描述 | Status |
|---|---|---|
| [STUDIO_PROJECT_INTRO.md](./STUDIO_PROJECT_INTRO.md) | Studio 起点文档 (graph skill 概念 + PM 视角介绍, 给新人和开发都该读) | ⚠️ 需 sync (写于早期 MVP 阶段, 跟现在能力有差距) |
| [TAURI_MIGRATION_PLAN.md](./TAURI_MIGRATION_PLAN.md) | Tauri 集成历史路径图 | ⚠️ 需 sync (T2 ship 后未更新) |
| [remote_gui_testing_guide.md](./remote_gui_testing_guide.md) | 远程访问 Studio GUI 的测试指南 (cloudflare tunnel 类) | ⚠️ 需 verify |

**当前缺什么 (待 baseline 阶段 Playwright 实测后写入)**:

- 前端组件树总览 (App.tsx + 30+ 组件实测描述)
- Backend 14 routers 的能力清单 (skills/templates/lint/runs/runs.batch/terminal/test_inputs/golden/compare/copilot/audit/debug/websockets/system)
- WebSocket event payload schema (event_bus.py 实际 event types)
- API key 管理 + tunnel 安全 (parent master 此前 spec 工作, 落地状态待 verify)

---

## 关键代码入口 (PM 看代码时按这个路径走)

| 想看 | 去哪 |
|---|---|
| 用户在浏览器看到什么 | `apps/studio/frontend/src/App.tsx` (顶层组件树) |
| 前端 30+ 组件 | `apps/studio/frontend/src/components/` |
| 前端调 backend 的 API client | `apps/studio/frontend/src/api/{client.ts,types.ts}` |
| Zustand store | `apps/studio/frontend/src/stores/{canvas.ts,workspace.ts}` |
| Backend API endpoints | `apps/studio/backend/app/routers/*.py` |
| Backend 业务逻辑 | `apps/studio/backend/app/services/*.py` |
| Pydantic 数据模型 (跨前后端共享 schema 真相) | `apps/studio/backend/app/models/*.py` |
| Tauri 桌面壳 | `apps/studio/tauri/src/{lib.rs,main.rs,sidecar.rs}` |
