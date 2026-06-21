---
doc: impl-plan
status: drafted（2026-06-06; 按 Studio MVP1 FROZEN 文档与当前代码热点编排，待拆 WS 任务书后执行）
applies_standard: ../../../development/task-spec-standard.md
binds_design: ../DESIGN_UNITS_INDEX.md · ../README.md · ../01_workflows/INDEX.md · ../../../development/FRONTEND_UI_SPEC.md
---

# Studio MVP1 实施计划(大模块 + 并发分区)

> **原则**: 三轴设计文档是唯一真理，本计划只排**顺序 + 并发 + 文件锁 + 外部依赖**。执行时必须先写失败测试，再改实现；涉及 `apps/studio/frontend` UI 时必须先读 `FRONTEND_UI_SPEC.md` §2、优先使用本地 `@/components/ui/*` wrapper，并在完成前启动 Studio/Tauri 或等价页面做真实点击验证。
> **投递**: 每个 WS 先产独立任务书与测试清单，经用户在聊天窗口明确确认后再动代码；不得把自动审批当确认。

## 一、为什么不是"全并发":Studio 是共享工作台,不是页面拼装

Studio MVP1 的核心不是单个页面补洞，而是把"本地工作区 + 画布编辑 + 编译/运行/追踪 + 设置/LLM + Copilot"接成一个桌面工作台。以下文件是共享热点，不能让多个 WS 同时乱改：

- `apps/studio/frontend/src/components/studio/Workspace.tsx`: shell、Settings overlay、GraphCanvas、panels、Copilot、Predict/Run 入口都在这里汇合。
- `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`、`canvas-authoring.ts`、`build-nodes.ts`: authoring、运行态节点灯、trace 黑板线都会碰。
- `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx`、`phase-frontmatter.ts`、`InputPanel.tsx`: phase 字段白名单、role 快捷 Test、I/O artifact 都共享。
- `apps/studio/frontend/src/components/studio/settings/**`、`apps/studio/frontend/src/api/llm.ts`、`apps/studio/backend/app/routers/llm.py`: Settings/LLM/Copilot HTTP 面高度耦合，`llm.py` 仍是巨型 router。
- `apps/studio/tauri/src/lib.rs`、`apps/studio/tauri/src/sidecar.rs`、`apps/studio/frontend/src/lib/tauri.ts`: D10/D12 决定所有本地写者收口到 Rust，影响几乎所有工作流。

所以真正能并发的是**文件归属清楚、接口已定**的旁路工作；核心工作台链路必须串行推进。

## 二、依赖图

```
WS-0 外部契约/任务书闸门
  ├─→ WS-1 Shell + native-fs 基座(D10/D12, Rust 唯一写者)
  │     ├─→ WS-2 Authoring 工作台(Canvas/Properties/Editor/I/O)
  │     │     └─→ WS-3 Compile/Predict/Run/Trace 接线
  │     │             ├─→ WS-6 Golden/Eval/Publish/Local History
  │     │             └─→ WS-8 Debug Resume(等 engine checkpoint/resume)
  │     └─→ WS-5 Copilot 工作台(session 持久化 + 真 SDK 测试)
  └─→ WS-4 Settings/LLM/Copilot 配置面(依赖 gateway ③b 契约,可旁路并发)

WS-7 UI/i18n/验证横切 ── 跟随各 WS 落地,最后统一扫尾
```

- **WS-1 是关键前置**: D12 要求本地写全量 Rust。Graph save、phase save、test inputs、golden、publish、copilot session 都依赖它；不能等后面各 WS 自己补一套写盘。
- **WS-4 可旁路并发,但不复制 gateway ③b**: 6 态、materialize、endpoint 标准化、draft/probe 策略以 `docs/graph-agent-gateway/mvp1/` 为 SSOT。Studio 只做 HTTP 壳、DTO 投影、UI 编辑和渲染。
- **WS-3 在 WS-2 后**: compile/predict/run/trace 需要 Graph/Properties/I/O 的目标 schema 与保存路径先稳定。
- **WS-6/WS-8 低于主链**: golden/publish/debug-resume 都依赖 run artifacts 和 engine 外部契约；先把 predict/run/trace 真实可达。

## 三、工作流分区(按文件归属,IR1)

| WS | 名 | 设计单元 | owns_files(并发锁) | 依赖 | 并发性 | 优先级 |
|---|---|---|---|---|---|---|
| **WS-0** | 外部契约/任务书闸门 | 全局 | `docs/studio/mvp1/_impl/WS*.md` · `.kiro/specs/studio-mvp1-*`(如启用) | 无 | 文档可并发,执行前串行确认 | P0 |
| **WS-1** | Shell + native-fs 基座 | `native-rust-writer` · `workspace-open-folder-mru` · `shell-runtime-gate` | `apps/studio/tauri/src/lib.rs` · `sidecar.rs` · `apps/studio/frontend/src/lib/tauri.ts` · `config/runtime.ts` · `App.tsx` · `Workspace.tsx` · `Header.tsx` · `components/welcome/**` · `backend/app/routers/skills.py` · `services/skills.py` | WS-0 | **内部串行** | P0 关键路径 |
| **WS-2** | Authoring 工作台 | `subgraph-path-inline-drilldown` · `phase-field-whitelist` · `conflict-overwrite-resolution` · `io-panel-artifacts-test-inputs` | `components/GraphCanvas/**` · `components/nodes/SkillNode.tsx` · `components/edges/ContextEdge.tsx` · `components/studio/panels/**` · `SplitEditor.tsx` · `LazyMonacoPanel.tsx` · `api/client.ts` | WS-1 writer 契约 | 与 WS-4/5 可并发,自身串行 | P0 |
| **WS-3** | Compile/Predict/Run/Trace 接线 | `compile-stage-gate` · `predict-execution` · `run-execution-node-status` · `trace-dot-blackboard` | `Workspace.tsx` · `center-action-bar.tsx` · `components/TracePanel.tsx` · `components/trace/**` · `hooks/useRunStream*` · `components/history/**` · `backend/app/routers/runs.py` · `services/run_manager.py` · `services/predictor.py` | WS-2 + engine contract | 内部串行;后端 fixture 可先行 | P0 |
| **WS-4** | Settings / LLM / Model Roles | `settings-six-state-provider-health` · `model-group-role-materialization` · `node-properties-role-test` | `components/studio/settings/**` · `components/studio/api-keys/**` · `api/llm.ts` · `api/types.ts` · `backend/app/routers/llm.py` · `services/llm_*.py` · `models/llm_config.py` | gateway ③b 契约; WS-2 的 Properties 快捷 Test 落点 | 可与 WS-1/2 并发,但 `llm.py` 单锁 | P0 |
| **WS-5** | Copilot 工作台 | `copilot-session-persistence` · `copilot-sdk-test-parity` | `components/copilot/**` · `store/copilotStore.ts` · `hooks/useCopilot.ts` · `backend/app/services/copilot.py` · `routers/copilot.py` · `routers/llm.py`(test-sdk 段) · `settings/copilot/**` | WS-1 writer + gateway route API | 与 WS-2/4 可并发,碰 `llm.py` 时排队 | P1 |
| **WS-6** | Golden/Eval/Publish/History | `golden-per-agent-node` · `publish-artifact-autocommit` · `local-history-snapshot` | `services/golden_diff.py` · `services/artifact_registry.py` · `routers/golden.py` · `routers/compare.py` · `routers/skills.py` publish 段 · `components/diff/**` · `components/history/**` · `Header.tsx` release 段 | WS-3 run artifacts + WS-1 writer | 可在 WS-3 后并发拆小块 | P2 |
| **WS-7** | UI/i18n/验证横切 | `i18n-error-code-ui-copy` · frontend NFR | `index.css` · `lib/llm-error-messages.ts` · 共享 save-status badge · `components/ui/*` 新 wrapper | 随各 UI WS | 跟随执行,最后统一扫尾 | P1 |
| **WS-8** | Debug Resume | `debug-resume-checkpoint` | `routers/debug.py` · `routers/runs.py` resume 段 · `components/history/**` · `components/trace/**` · `Workspace.tsx` resume actions | engine checkpoint/resume API pinned | 外部依赖未稳前不启动 | P2/Blocked |

## 四、WS-1 内部子步骤(关键路径,严格串行)

> 这是整个 Studio 的地基。后续 WS 不允许绕过它临时写 FastAPI/Python 本地写盘。

0. **任务书 + 红测先行**: 为 native writer、workspace open/MRU、RuntimeGate 局部化各写失败测试；未见失败测试前不改实现。
1. **Rust writer contract**: 在 Tauri 层定义并测试本地文件命令: workspace open/MRU、read/write skill file、serialize graph、mutate phase body、hash conflict、workspace `.workspace` 路径。保留 `reveal_in_file_manager`，清理未挂 UI 的 Cursor/Codex/Terminal dead command。
2. **前端 Tauri wrapper**: `src/lib/tauri.ts` 收口所有本地 I/O；浏览器态只做明确 fallback，不白屏。UI 使用本地 shadcn/Radix wrapper，状态反馈用 Sonner/Badge。
3. **Home/Workspace 模型迁移**: Home 从注册表聚合转为打开文件夹 + Recent(MRU)；删除 import 校验门语义，任意文件夹可进入，不合规交 compile/copilot 修。
4. **RuntimeGate 退役**: shell/file surfaces 立即渲染，engine/gateway sidecar 失败只在调用点显示 scoped error/skeleton，不再全屏挡住 Studio。
5. **Python 写者退场**: `skills.py` 等 Python 端保留 engine/gateway 计算和只读装配；本地落盘统一经 Rust-mediated path。完成后 WS-2/3/6 才能接真实保存。

## 五、WS-2/WS-3 的主链顺序

1. **Authoring schema 先稳**: Canvas/Properties/Input 的目标字段白名单、I/O artifact、subgraph path、conflict overlay 先落地；否则后面的 compile/run 会接到旧 schema。
2. **Stage gate 单一归属**: idle→compile→predict→run 的门控只归 `compile-lint`，Predict/Run 只消费，避免两边重复写 stage 机。
3. **Run stream 接 state-engine**: `useRunStream`/TracePanel/BatchRunner 等孤儿组件先通过 fixture 红测证明不可达，再接到 Workspace、Timeline、Canvas node status。
4. **Trace 黑板和节点灯一起验**: 不只看后端 run 成功，还要验证 Canvas 节点状态、Timeline、edge/dot 黑板 tooltip 同步变化。
5. **Debug resume 延后**: 当前 Studio resume 仍 501，等 engine checkpoint/resume contract pin 住后再从 WS-8 单独开。

## 六、本批不做(范围锁定,避免再发散)

- **不在 Studio 复制 gateway ③b 内核**: 6 态标准投影、model group/materialize、endpoint 标准化、draft/probe 策略、fallback/circuit 归 `docs/graph-agent-gateway/mvp1/`。
- **不在 Studio 重写 engine 契约**: skill syntax、resolver、trace event schema、checkpoint/resume、golden 落点归 `docs/engine/mvp1/`。
- **不做团队协作式发布**: MVP1 publish 是本地 autocommit + Artifact Registry 最小占坑；commit message、confetti、鉴权团队流是 stale/future。
- **不做 Copilot brain 场景**: Settings/Copilot 本批只保证模型配置、真实 SDK 测试、chat/session 持久化；领域脑图技能另立。
- **不做泛化 UI 重设计**: 只按 `FRONTEND_UI_SPEC.md` 修被触碰屏幕；发现可复用规则再回写 spec。

## 七、执行波次建议

- **Wave 0(准备)**: 产 `WS1..WS8` 任务书、每个 WS 的文件锁和红测清单；同步确认 gateway/engine 外部契约当前可用范围。
- **Wave 1(地基 + 旁路)**: WS-1 开跑；WS-4 可先做 Settings API/DTO 边界审计和 UI 红测；WS-7 抽共享 save-status badge / i18n 骨架时不得碰业务逻辑。
- **Wave 2(Authoring)**: WS-2 串行接 Canvas/Properties/I/O/Editor；WS-4 继续 Settings/LLM，但 `PropertiesPanel` 的 role 快捷 Test 要等 WS-2 文件锁释放。
- **Wave 3(Runtime)**: WS-3 接 compile/predict/run/trace；WS-5 在 WS-1 writer 完成后接 Copilot session 持久化和真 SDK test。
- **Wave 4(闭环)**: WS-6 接 golden/eval/publish/local-history；WS-8 仅在 engine resume contract pin 住后启动。
- 每个 WS 完成 = 红测先失败 + 实现后测试绿 + typecheck/build + Studio/Tauri 或 Playwright 实际点击验证 + 更新相关 baseline/alignment/Frontend UI spec(如产生新规则)。

## 八、产物状态(2026-06-06)

- 设计总纲: `docs/studio/mvp1/README.md`
- 设计单元索引: `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`
- UI 规范: `docs/development/FRONTEND_UI_SPEC.md`
- 本实施计划: `docs/studio/mvp1/_impl/IMPL_PLAN.md`
- WS 任务书建议落点: `docs/studio/mvp1/_impl/WSN-*.md`
- Kiro task 建议落点(如需要): `.kiro/specs/studio-mvp1/tasks-wsN.md`

| WS | 任务书 | 实现 | 状态 |
|---|---|---|---|
| WS-0 | 待产 | 无代码 | ⏳ |
| WS-1 | 待产 | 待实现 | ⏳ |
| WS-2 | 待产 | 待实现 | ⏳ |
| WS-3 | 待产 | 待实现 | ⏳ |
| WS-4 | 待产 | 待实现 | ⏳ |
| WS-5 | 待产 | 待实现 | ⏳ |
| WS-6 | 待产 | 待实现 | ⏳ |
| WS-7 | 待产 | 待实现 | ⏳ |
| WS-8 | 待 engine pin | 待实现 | ⏸ |
