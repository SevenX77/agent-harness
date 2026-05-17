# Studio Baseline · 2026-05-17

> **唯一事实来源 (Single Source of Truth)**: 项目当前的现状 + 目标 + 离目标多远, 一切以本文为准。
>
> 跟本文冲突的旧文档 (`docs/archive/` 以下任何) 都不算数。

---

## 0. 锁定目标 (2026-05-17 user lock)

> **Studio 的目标 = 让 PM (user 自己, 未来扩到团队) 可用 — 不开终端、不写 YAML、不拼目录, 在 Studio 里可视化地写 / 改 / 跑 V2.1 skill, 跑完能看到每个 phase 的输入输出。**

**这一句话是后续所有 spec 的总绳**。任何 spec / feature / 优化, 实施前必须先回答"它服务这句话的哪一段"。回答不出来 → 砍掉或推迟。

---

## 1. 系统宏观架构

### 1.1 4 层拓扑

```
┌────────────────────────────────────────────────────┐
│  Tauri 桌面壳 (apps/studio/tauri/)                  │  ← PM 的入口 (期望状态, t3 未完)
│  • Rust shell, 装 frontend + 启 backend sidecar     │
└──────────┬─────────────────────────────────────────┘
           │ (HTTP + WS)
┌──────────▼─────────────────────────────────────────┐
│  Studio Frontend (apps/studio/frontend/)            │  ← PM 实际看到的 GUI
│  • React + Vite + Monaco + React Flow + Zustand     │
│  • App.tsx 顶层 + 30+ 组件                          │
└──────────┬─────────────────────────────────────────┘
           │ (HTTP REST + WebSocket)
┌──────────▼─────────────────────────────────────────┐
│  Studio Backend (apps/studio/backend/)              │  ← GUI 操作翻译给 Engine
│  • FastAPI, 14 routers + 13 services                │
│  • routers/{skills,runs,terminal,websockets,...}    │
└──────────┬─────────────────────────────────────────┘
           │ (in-process import)
┌──────────▼─────────────────────────────────────────┐
│  Graph Agent Engine (packages/graph-agent/)         │  ← V2.1 SDK 内核
│  • Loader → Compiler → Executor                     │
│  • 13 公开 API exports                              │
└────────────────────────────────────────────────────┘
                     │
                     ▼
              skills/ (fixture corpus)
              • 7 个真 V2.1 skill (含 phases/<phase>/)
              • _v2_pending/ V1 待迁
              • text-segmentation/versions/ 版本归档样板
```

### 1.2 PM 用 Studio 的数据流 (期望全链路)

> ⚠️ **本节 placeholder**, 下一步 Playwright 实测填 (现在不知道实际从哪屏到哪屏怎么操作)

```
PM 开 Studio → 选 skill → 看 canvas → 改 phase → save → 跑 run → 看 trace → 看输出
   [待实测]      [待实测]   [待实测]   [待实测]    [待实测] [待实测]  [待实测]  [待实测]
```

---

## 2. 领域 A · Engine 现状

详见 [`engine/README.md`](./engine/README.md)。

**简要**:
- V2.1 SDK 已 cutover (PR #45-#52), 9 skills 已迁
- 公开 13 API exports 稳定
- 已知技术债: V1 兼容 test fail; `graph-agent-engine` 空死 legacy package 待 archive
- 多份 doc (`ARCHITECTURE.md` / `IMPLEMENTATION.md` 等) 标 ⚠️ Needs-Sync, 待 audit

---

## 3. 领域 B · Studio 现状

详见 [`studio/README.md`](./studio/README.md)。

### 3.1 Frontend 实测能力清单

> ⚠️ **本节 placeholder**, 下一步 Playwright 实测填
>
> 已知 frontend 至少有 30+ 组件 (`creator/`, `playground/`, `history/`, `diff/` 9 个, `trace/` 5 个, `shortcuts/`, `templates/`, `phaseform/`, `export/`, `draft/`, `TerminalPanel`, `MonacoPanel`, `GraphCanvas`, `SkillSidebar`, `HeaderBar`, `RightPanel`, `WelcomeScreen`, `CommandPalette`, `SettingsPanel`, ...). 实际怎么联动 / 哪些隐藏 / 用户体验割裂在哪 — Playwright 走一遍才知道。

### 3.2 Backend 14 routers 实测能力

| Router | 能力 (推测, 待 verify) | 实际 endpoints 数 |
|---|---|---|
| `skills` | skill CRUD + multi-file 读写 + graph serialize | 待数 |
| `templates` | skill 模板 (5 个 .SKILL.md 已知) | 待数 |
| `lint` | skill 静态校验 | 待数 |
| `runs` | run 创建 / 查 / 删 / batch / predict / resume | 9 个 |
| `terminal` | 内嵌 terminal session 创建 | 1 个 |
| `test_inputs` | run 测试输入管理 | 待数 |
| `golden` | golden run 管理 | 待数 |
| `compare` | golden diff | 待数 |
| `copilot` | (待 verify, 之前 parent master tunnel/api-keys 工作) | 待数 |
| `audit` | 审计 log | 待数 |
| `debug` | 调试接口 | 待数 |
| `websockets` | `/ws/runs/{run_id}` + `/ws/terminal/{term_id}` + `/ws/events` | 3 个 |
| `system` | 系统级 (健康 / 版本) | 待数 |

### 3.3 Tauri 桌面壳

- T2 ship: sidecar runtime + bundle resources + 注入 API config + lifecycle 测试
- T3 待启动: spec 只有 design/requirements, **无 tasks.md**

---

## 4. 领域 C · Skills 库现状

详见 [`skills/README.md`](./skills/README.md)。

**简要**:
- 7 个真 V2.1 skill (text-segmentation / event-extraction / batch-analysis / global-synthesis / hello-world / producer / product-manual) 全有 `phases/<phase>/` 真目录
- `text-segmentation/versions/` 是版本归档 prototype (v0/v1/v2/v3), 推广到其他 skill
- `_v2_pending/` V1 待迁 backlog (story-deconstruction / adaptation_v1)
- **不追求** 全 skill 跑通, broken skill = 反例 corpus

---

## 5. 当前研发过程 (Active Specs + Backlog)

详见 [`process/README.md`](./process/README.md)。

**最近 ship**:
- `studio-canvas-v2` (12 tasks done, 含 Dagre layout / fan-out 着色 / subgraph drill-down / Save 流 / WS reload)
- `studio-frontend-v21-multifile-editor` (T-apps-1 多文件 Monaco editor)
- `graph-agent-v2.1` (V2.1 hard cutover, 9 skills 迁)
- `tauri-t2` (Tauri sidecar runtime 集成)

**Backlog 高优 (服务目标"让 PM 可用")**:
1. **Studio 执行态闭环** — Canvas 接 run 状态 + 现代 trace panel + React Compiler 20 lint 清; 服务目标 "跑完看每 phase 输入输出"
2. **tauri-t3** — spec tasks 起草 + 实施; 服务目标 "不开终端" 完整闭环
3. **studio-mvp1 audit** — 28 pending 实际多数已隐式 ship, 勾上 + 砍掉跟目标不对齐的
4. **V1 → V2.1 harness test 终结** — 修 V1 兼容 stub 或废弃 V1 测试

**已砍掉 / 不在目标内**:
- 跨平台 bundle CI (低优, M2 内事)
- Skill author SDK + 外部贡献者生态 (user 明示删)
- `packages/graph-agent-engine/` (legacy 空 package, archive)

---

## 6. 历史归档

详见 [`archive/README.md`](./archive/README.md)。

历史文档 (v1-reset / architecture-old phase plans / superpowers-plans / 早期 audit reports) **物理隔离**在 `archive/`, 不混进主索引。

---

## 7. 本文档维护规则

- **每次 spec ship 后**, 必须更新本文档对应章节, 把"新增/改变的能力" 提炼一段进来
- 本文档不写"未来 N 周打算做什么" (那是 `process/README.md` 的事), 只写"现在系统是怎样"
- 跟本文冲突的旧文档 = 旧文档错, 立刻 mv 到 archive 或加 ⚠️ Outdated tag
- 文件名带日期戳是为了**强制审视**: 下次大调整时新建 `STUDIO-BASELINE-YYYY-MM-DD.md`, 旧的 mv 到 archive, 不就地改

---

## 8. 待办 (下次迭代填本文档)

1. Playwright 实测填 §1.2 + §3.1
2. Backend 14 routers 实际 endpoints + payload schema 填 §3.2
3. Tauri t3 spec tasks 起草后填 §3.3
4. 加 frontmatter (target_goal / linked_code_paths / linked_specs) 给每份 Living 文档
