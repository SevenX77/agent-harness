---
ws_id: WS-5-copilot-workbench
modules: [02_capabilities/copilot-assist, 03_regions/copilot, 04_platform/llm-copilot-http-api]
depends_on: [WS-0, WS-1]
blocks: []
owns_files:
  - apps/studio/frontend/src/components/copilot/
  - apps/studio/frontend/src/store/copilotStore.ts
  - apps/studio/frontend/src/hooks/useCopilot.ts
  - apps/studio/backend/app/services/copilot.py
  - apps/studio/backend/app/routers/copilot.py
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/frontend/src/components/studio/settings/copilot/
spec_ssot:
  - docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md
  - docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
  - docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md
status: drafted
---

# WS-5 Copilot 工作台 — 需求书

本需求书是 WS-5 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

让 Copilot 面板、session 持久化、Settings Copilot runtime 和真实 SDK 测试走同一条可信配置路径，避免 Copilot UI、Settings 和后端测试各自维护不同事实。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 中 Copilot、LLM HTTP API 和 Settings UX 的 `mvp1-alignment.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/copilot-assist/baseline.md`、`docs/studio/mvp1/03_regions/copilot/baseline.md`、`docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `copilot-session-persistence`、`copilot-sdk-test-parity`。
- 外部契约状态：gateway role resolution 当前按 floating-draft 消费；Studio 只消费 route API，不复制 gateway 解析内核。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2；实现前查 `components/ui`，Copilot/Settings 使用语义 token、Playwright 或浏览器验证和窄宽度检查。
- 必读源码：frontmatter `owns_files` 中 Copilot UI、store、hook、backend copilot service/router、`llm.py` test-sdk 段和 Settings Copilot。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/backend/app/routers/llm.py` 与 WS-4 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 排队：WS-5 只处理 copilot SDK test parity 相关段，Settings/roles/model registry 由 WS-4 先行或串行释放。`apps/studio/frontend/src/components/studio/settings/copilot/` 只处理 Copilot runtime 页，不扩散到 LLM Roles。

禁止触碰 Canvas、authoring panels、run/golden/debug、Tauri writer、gateway/engine packages。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

baseline 显示 Copilot 面板和后端 service 已存在，但 session 持久化、ThinkingBlock 翻译、Settings Copilot 和真实 SDK 测试路径仍存在 drift 或 mock 数据。

## 5. 目标行为(可测的契约)

- Copilot session keyed by workspace identity，刷新或切换后不串台。
- Settings Copilot runtime 配置不使用 mock 数据，候选模型和 SDK readiness 来自后端 DTO。
- Copilot SDK Test 与真实 Copilot chat 使用等价 SDK 路径，错误原因可诊断。
- 消息渲染保留 ThinkingBlock、tool call、diff bubble 等结构化块，不把机器码吞掉。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、语义 token、Playwright/浏览器验证和窄宽度检查。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 session 持久化、workspace 切换隔离、Copilot SDK Test parity、Settings Copilot 无 mock 数据、错误展示、ThinkingBlock/tool call 渲染。至少一条真实 e2e 或手动验证必须打开 Copilot 面板和 Settings Copilot，覆盖成功、失败、取消或空态；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-5 依赖 WS-1 writer 和 gateway route API。若 gateway route contract 未 pinned，相关项必须标成 floating-draft 或 blocked，不在 Studio 中发明替代运行时。修改后端 Python 后必须重启 Studio App。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] Copilot session 持久化与 workspace identity 隔离通过测试。
- [ ] Copilot SDK Test 与真实 SDK 路径等价，不再靠 mock 数据宣称可用。
- [ ] Playwright 或浏览器真实 e2e 覆盖 Copilot 和 Settings Copilot 窄宽度。
- [ ] 后端和前端相关测试通过并记录命令。

## 9. 不做(范围锁定,IR7)

不做 Copilot brain 场景，不改 LLM Roles 核心编辑，不接 run/trace/golden，不复制 gateway 内核。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码回写 copilot-assist、copilot region、llm-copilot-http-api 的 `baseline.md`。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖 session、SDK parity、无 mock 数据和 no-fake 边界。Codex 审查退出以 §8 为准。PM 终审检查 baseline 诚实和 gateway 边界。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws5-copilot-workbench.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
