---
ws_id: WS-1-shell-native-fs
modules: [04_platform/native-fs, 02_capabilities/skill-workspace, 03_regions/welcome, 03_regions/shell-layout, 04_platform/state-engine]
depends_on: [WS-0]
blocks: [WS-2, WS-3, WS-5, WS-6, WS-8]
owns_files:
  - apps/studio/tauri/src/lib.rs
  - apps/studio/tauri/src/sidecar.rs
  - apps/studio/frontend/src/lib/tauri.ts
  - apps/studio/frontend/src/config/runtime.ts
  - apps/studio/frontend/src/App.tsx
  - apps/studio/frontend/src/components/studio/Workspace.tsx
  - apps/studio/frontend/src/components/studio/Header.tsx
  - apps/studio/frontend/src/components/welcome/
  - apps/studio/backend/app/routers/skills.py
  - apps/studio/backend/app/services/skills.py
spec_ssot:
  - docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/welcome/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md
  - docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/01_init.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
status: drafted
---

# WS-1 Shell + native-fs 基座 — 需求书

本需求书是 WS-1 的契约输入。任何实现代码、业务测试或实施任务书都必须等 RED 测试、PM 契约门和用户在聊天窗口明确确认后再启动。

## 1. 目标(intent + why)

把 Studio 的入口和本地写盘基座切到 MVP1 的 IDE 模型：Tauri/Rust 承担本地工作区写入和 MRU，Home 可以打开本地文件夹，sidecar 失败不再全屏挡住 shell。这样 WS-2 到 WS-8 不需要各自再补一套本地写者。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 所列 `mvp1-alignment.md` 与 `01_workflows/01_init.md`。
- 现状起点：`docs/studio/mvp1/04_platform/native-fs/baseline.md`、`docs/studio/mvp1/02_capabilities/skill-workspace/baseline.md`、`docs/studio/mvp1/03_regions/welcome/baseline.md`、`docs/studio/mvp1/03_regions/shell-layout/baseline.md`、`docs/studio/mvp1/04_platform/state-engine/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `native-rust-writer`、`workspace-open-folder-mru`、`shell-runtime-gate`。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2 和 §2.10；实现前必须先查 `apps/studio/frontend/src/components/ui/` wrapper。
- 启动规则：`apps/studio/tauri/README.md`，修改后端 Python 后必须重启 Studio App，即重新拉起 `cargo tauri dev`。
- 必读源码：frontmatter `owns_files` 中列出的 Tauri、frontend bridge、shell、Home 和 backend skills 文件。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/frontend/src/components/studio/Workspace.tsx` 与 WS-3、WS-8 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 串行：WS-1 只做 shell identity、RuntimeGate 和 native writer 接线；WS-3/WS-8 等 WS-1 释放后再接 run/resume action。`apps/studio/frontend/src/components/studio/Header.tsx` 与 WS-6 共享，WS-1 只处理 shell 基座，release/publish 入口排队到 WS-6。`apps/studio/backend/app/routers/skills.py` 与 WS-6 共享，WS-1 只处理 workspace/open-folder/native writer 兼容，publish 段排队到 WS-6。

禁止触碰 `apps/studio/frontend/src/components/GraphCanvas/`、`apps/studio/frontend/src/components/studio/panels/`、`apps/studio/frontend/src/components/studio/settings/`、`apps/studio/backend/app/routers/llm.py`、`packages/graph-agent-gateway/`、`packages/graph-agent/`。发现范围外问题只登记 deferred。

## 4. 现状锚点(baseline)

当前 baseline 显示 Studio 已有 Tauri sidecar、目录选择和部分 shell，但 Home 仍偏注册表导入模型，部分本地 source 写入仍经 FastAPI/Python，RuntimeGate 仍可能把 shell 级体验挡住。

## 5. 目标行为(可测的契约)

- 本地 source file、workspace `.workspace` 支撑目录和 MRU 写入必须经 Rust/Tauri 或等价 Rust-mediated path。
- Home 主路径是 Open Folder，选择本地目录后进入 Workspace 并写入 path-based MRU；缺少 skill 文件不在 Home 阶段阻塞。
- sidecar 失败只影响 compile/settings/copilot/run 等调用点，不能卸载 Home、Toaster 或本地文件入口。
- browser fallback 必须显式降级，不白屏、不假装 Tauri-only 能力成功。
- Python sidecar 继续承担 compute/read 装配，但不能再成为本地 source file 写入权威。
- UI 必须使用 `FRONTEND_UI_SPEC.md` §2、`components/ui` wrapper、语义 token，并用 Playwright 或浏览器验证窄宽度。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写会失败的 RED 测试，PM 契约门通过后才允许 task.md 和 Gemini 实现。RED 清单至少覆盖：Tauri writer 路径保护、hash conflict、MRU add/list/remove、Open Folder 任意目录进入、RuntimeGate 局部失败、browser fallback、Python writer 退场、Workspace/Monaco 保存不走 FastAPI 写盘、真实 Tauri bridge 或等价原生路径。真实 e2e 或手动验证必须覆盖 Open Folder、Recent reopen、Remove from Studio、Reveal 和 sidecar 失败路径；不许 fake mock 到绿。

## 7. 硬依赖约束

Tauri writer contract 必须先稳定，Home/MRU、Workspace 保存和 Python 写者退场只能消费该 contract。涉及后端 Python 修改时，完成后必须重启 Studio App 再验。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] 所有本地 source file 与 MRU 写入不再以 FastAPI/Python 为权威。
- [ ] Home 能打开任意本地文件夹，MRU path-based，Remove from Studio 不删磁盘。
- [ ] RuntimeGate 不再全屏阻塞 shell。
- [ ] `cargo test`、`cargo check`、frontend 相关测试、backend 相关 pytest 通过。
- [ ] 至少一条真实 e2e 或手动 Tauri 验证通过，并覆盖窄宽度 UI。

## 9. 不做(范围锁定,IR7)

不做 WS-2 authoring schema、WS-3 run/trace、WS-5 Copilot session、WS-6 publish/golden、WS-8 resume，也不迁 Settings 凭证/角色数据到 Rust。范围外问题记入 deferred。

## 10. baseline 回写指令(IR6)

实现落地后按真实代码回写 native-fs、skill-workspace、welcome、shell-layout、state-engine 和 file-editing 的 `baseline.md`。不得把目标态提前写成现状。

## 11. 评审检查点

PM 契约门重点审 RED 是否覆盖唯一写者、Open Folder、RuntimeGate 和真实 Tauri 路径。Codex 审查退出以 §8 为准。PM 终审检查意图、测试非假绿和 baseline 回写是否诚实。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws1-shell-native-fs.md`，再输出给 Gemini 的 prompt。task.md 只能来自已批准测试，必须包含 owns_files、禁止触碰、验证命令、用户明确确认闸门、baseline 回写和 PM 终审顺序。
