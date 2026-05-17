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

### 1.2 PM 用 Studio 的数据流 (2026-05-17 Playwright 实测)

```
1. 启动:  Tauri 壳 (或 vite dev :5173) → 加载 Welcome 屏
          左侧栏: 7 个 V2.1 skill (batch-analysis / event-extraction / global-synthesis /
                  hello-world / producer / product-manual / text-segmentation)
                  + Recent 项 (上次打开的 skill) + Settings 按钮 + 黑暗模式切换
          中央: Start (Open/Import Skill Folder) + Recent 列表
2. 选 skill: 点左侧某 skill → 进 Workspace 三栏布局
3. Workspace 三栏:
   ┌─────────┬──────────────────────────────┬──────────────────────────────────┐
   │ Sidebar │ Center (Canvas + Header)     │ Right Panel (6 tab)               │
   ├─────────┼──────────────────────────────┼──────────────────────────────────┤
   │ skill   │ Header:                      │ Files: 多文件树 + Monaco editor    │
   │ 列表    │  [Artifacts ▼] Inputs/Mode   │       (io/, phases/, LOGIC, GRAPH) │
   │ + Fork  │  [Lint✓] [Save] [Open CLI]   │ Trace: WS run 事件 (Waiting...)    │
   │ 按钮    │  [Run ▶]                     │ Diff: Golden 比对 + Promote        │
   │         │                              │ History: Run 历史 + 分页            │
   │         │ Canvas (React Flow + Dagre): │ Batch: 多 test_inputs 一起跑       │
   │         │  Input(runtime) ▼            │ CLI: 内嵌 terminal session         │
   │         │  Phase Node (可编辑 persona) │                                  │
   │         │  Output(result)              │                                  │
   │         │  入边橙 / 出边红 fan-coloring │                                  │
   │         │  Mini-map + 缩放/锁定 + Reset │                                  │
   └─────────┴──────────────────────────────┴──────────────────────────────────┘
4. 改 phase: 双击 phase 节点 → 触发 canvas:open-phase-file 事件 → 右栏 Files tab
            打开对应 phases/<name>/SKILL.md → Monaco 编辑器改 → 改完 Save
5. 配 input: 点 Header 的 [Artifacts ▼] → 弹出 Run Input 面板
            Raw JSON 编辑 + Load preset / 保存 preset / Reset → "Inputs valid" 状态
6. 跑 run:  点 [Run] → 触发 POST /api/runs → 切到 Right Panel Trace tab
            (WS /ws/runs/{run_id} 推 phase 事件 — 待 e2e verify)
7. 看输出: Trace 看完整时间线; History 看历史 run; Diff vs Golden 对比

PM 期望路径上还**缺**:
- 多 skill 一起跑 (Batch tab 有, 但需先有 test_inputs presets)
- Run 中途看到 phase 部分输出 (Trace 待 verify)
- Subgraph 下钻看子图执行 (T3.3 已 ship, drill-down 实装, 但 user 业务流要 verify)
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

### 3.1 Frontend 实测能力清单 (2026-05-17 Playwright)

**Welcome 屏**:
- 左侧栏: skill 列表 (7 V2.1 真 skill, 各带 Fork 按钮) + "Create new skill" + Recent skill 列表 + Settings + 黑暗模式切换
- 中央: "Start" + "Open / Import Skill Folder..." + "Recent" 历史 skill 入口

**Workspace 三栏**:

| 区 | 组件 | 实测状态 |
|---|---|---|
| Sidebar | `SkillSidebar` (skill 列表 + Fork + Settings) | ✅ 完整 |
| Header | `HeaderBar`: [Artifacts ▼] [Inputs: raw JSON] [Mode: Playground] [Lint✓] [Save] [Open CLI] [Run ▶] | ✅ 完整 |
| Center Canvas | `GraphCanvas` (React Flow): Dagre 自动布局 + I/O 边框节点 + Phase 节点 (含可编辑 persona 输入框) + 入边橙/出边红 fan-coloring + Mini-map + 缩放/Reset Layout/锁定 + 顶部 breadcrumb (subgraph drill-down) | ✅ 完整 |
| Right Panel Files | 多文件树 (io/{inputs,outputs}.json + phases/<name>/{SKILL.md, actions/}+ LOGIC.md + GRAPH.md) + Monaco 编辑器 | ✅ 完整 |
| Right Panel Trace | "Waiting for run events" 空状态 + WS 接 `/ws/runs/{run_id}` 推事件 (空 run 时) | ⚠️ 框架在, e2e 待 verify |
| Right Panel Diff | "Golden Diff" + [Compare to Golden] + [Promote to Golden] | ✅ 完整 |
| Right Panel History | "Run History / 0 runs tracked" + 分页 | ✅ 完整 |
| Right Panel Batch | "Batch Runner" + "No JSON test inputs found" 空状态 + Run Batch | ✅ 完整 (依赖 test_inputs) |
| Right Panel CLI | "No CLI session / Open a CLI session for the active skill" + 上方 [Open CLI] | ✅ 完整 |
| Artifacts 弹出面板 | `Run Input` 浮层: Raw JSON + Load preset (test_inputs) + 保存 preset + Reset + Show JSON preview + Run inline | ✅ 完整 |
| Settings | LLM API Keys: OpenAI / Anthropic / Google Gemini (`SettingsPanel`) | ✅ 完整 (api-keys-v1 ship 一部分) |
| Welcome 屏 | `WelcomePage` | ✅ 完整 |

**实测发现的小缺陷** (非 blocker, 在 baseline 之上跟踪):

1. **启动时 Save conflict + GRAPH.md changed externally 两 modal 误渲染** 在 welcome 屏 (状态泄漏 / WS 启动 race condition)
2. **Skill 切换时 "Skill changed: <name>" toast 不去重**, 堆 15+ 条遮右栏 (file watcher emit 没 coalescing)
3. **"Studio event stream disconnected"** 持续显示在 footer (WS 长连接启动失败 / 自动重连缺失)
4. **节点 / 弹窗内中文 CJK 字符显示为方框** (字体 fallback 问题, Save conflict modal 中文文案可重现)

**结论**: PM 角度看, 主要 UI 表面都在 (创建 / 看 / 改 / 跑 / 看 trace / 看 diff / 看 history / 批量跑). 占位居多的是 **执行态** (Trace / History / Diff 是空 — 需要真实 run 数据填充). 当前 baseline 阶段 **不是缺 feature, 是缺 e2e run 可信路径 + 上述 4 个 polish**.

### 3.2 Backend 13 routers 实测能力 (2026-05-17 grep)

> 注: 之前 baseline 写 "14 routers" 实际是 13 (`__init__.py` 不算)。`runs` router 含 batch-run / predict 子路径, 不是独立 router。

| Router | 端点数 | 关键路径 |
|---|---|---|
| `skills` | 8 | GET/POST `""` (列表+创建), GET/PUT/DELETE `/{id}`, POST `/{id}/graph/serialize` (canvas serialize), POST `/{id}/fork`, POST `/{id}/validate_input` |
| `runs` | 7 | POST `""` (新 run), POST `/predict`, GET `""`/`/{id}` (列表/详情), DELETE `/{id}`, POST `/batch-run`, POST `/{id}/...` (resume 类) |
| `templates` | 1 | GET `""` (列模板) |
| `lint` | 1 | POST `/lint` (静态校验) |
| `terminal` | 1 | POST `/terminal` (创 session) |
| `test_inputs` | 3 | GET/POST/DELETE (CRUD test inputs) |
| `golden` | 3 | GET/POST/DELETE (CRUD golden) |
| `compare` | 2 | POST/GET (golden diff) |
| `copilot` | 1 | POST (api-keys-v1 周边, parent master 在做) |
| `audit` | 1 | GET (审计 log) |
| `debug` | 1 | GET `/value-error` (开发调试) |
| `websockets` | 3 | `/ws/runs/{run_id}` + `/ws/terminal/{term_id}` + `/ws/events` |
| `system` | 2 | GET `/health`, POST `/shutdown` |

**合计**: 13 routers, 34 HTTP/WS endpoints (实测命中)。

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

1. ✅ Playwright 实测填 §1.2 + §3.1 (2026-05-17 done)
2. ✅ Backend routers 端点数实测填 §3.2 (2026-05-17 done)
3. Tauri t3 spec tasks 起草后填 §3.3
4. 加 frontmatter (target_goal / linked_code_paths / linked_specs) 给每份 Living 文档
5. **§3.1 实测发现的 4 个 polish 缺陷需 spec 跟进**:
   - 启动时 Save conflict / GRAPH.md changed externally modal 状态泄漏
   - skill 切换 toast 不去重
   - footer "Studio event stream disconnected" 持续显示
   - CJK 字体 fallback
6. e2e 验证 Trace tab + WS `/ws/runs/{run_id}` 真实推 phase 事件 (当前看到的是空 run 占位)
