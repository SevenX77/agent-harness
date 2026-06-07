---
ws_id: WS-4-settings-llm-model-roles
modules: [02_capabilities/studio-settings, 03_regions/settings, 04_platform/llm-copilot-http-api, graph-agent-gateway]
depends_on: [WS-0]
blocks: []
owns_files:
  - apps/studio/frontend/src/components/studio/settings/
  - apps/studio/frontend/src/components/studio/api-keys/
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/frontend/src/api/types.ts
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/services/llm_roles.py
  - apps/studio/backend/app/models/llm_config.py
spec_ssot:
  - docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/settings/mvp1-alignment.md
  - docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
  - docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
status: drafted
---

# WS-4 Settings / LLM / Model Roles — 需求书

本需求书是 WS-4 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

把 Settings 中 API Keys、LLM Roles、Model Bundles 和后端 LLM registry / role materialization 契约对齐，让 Studio 只编辑和展示用户意图，最终状态与测试事实来自后端和 gateway 绑定。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 中 Studio `mvp1-alignment.md`、`01_workflows/00_settings-ux-spec.md` 和 gateway role/test SSOT。
- 现状起点：`docs/studio/mvp1/02_capabilities/studio-settings/baseline.md`、`docs/studio/mvp1/03_regions/settings/baseline.md`、`docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md`，以及 gateway 相关 `baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `settings-six-state-provider-health`、`model-group-role-materialization`、`node-properties-role-test`。
- 外部契约状态：gateway ③b role resolution、registry schema、test status 当前按 floating-draft 消费；Studio 不复制 gateway 内核。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2；实现前先查 `apps/studio/frontend/src/components/ui/`，Settings 表单使用本地 wrapper 和语义 token。
- 必读源码：frontmatter `owns_files` 中 Settings、API Keys、LLM API、`llm.py`、`llm_roles.py` 和 `llm_config.py`。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/backend/app/routers/llm.py` 与 WS-5 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 排队：WS-4 只处理 Settings/roles/model/provider HTTP 壳，WS-5 的 copilot SDK test 段等 WS-4 释放后接入。若 Properties role shortcut 需要 `components/studio/panels/`，必须等 WS-2 文件锁释放。

禁止触碰 Copilot chat/session、Canvas/Properties 业务文件、Tauri lifecycle、gateway package 和 engine package。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

baseline 显示后端已有部分 LLM registry、role materializer 和测试接口，前端 Settings 也有 API Keys/LLM Roles UI，但状态、证据、role test 和 model bundle 语义仍存在 drift。

## 5. 目标行为(可测的契约)

- API Keys 与 LLM Roles 展示同一后端投影，不以本地字符串启发式作为最终事实。
- provider/model/route 健康状态、reason、capability state 与 gateway SSOT 对齐，失败路由可见但不会默认进入可执行 fallback。
- Role Test 先 flush autosave，再走后端 persisted test job，最终状态可从 registry/evidence 重读。
- Role Settings 保存用户 intent，不在前端物化最终执行链。
- Model Bundle 作为引用参与 role materialization，状态和测试规则与 role 一致。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、Playwright/浏览器验证、窄宽度检查和语义 token。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖六态或 SSOT 状态投影、API Keys provider health、Available Models、Role Test autosave flush、Role Settings intent、Model Bundle 引用、backend registry/materialization 和错误文案。至少一条真实 e2e 或手动验证必须在 Settings 中完成 provider 配置、role 保存、role test 成功或失败路径；不许 fake mock 到绿。

## 7. 硬依赖约束

gateway ③b 契约未 frozen 的部分只能作为 floating-draft 绑定；不得在 Studio 中复制角色解析、capability 判定或 fallback 内核。修改后端 Python 后必须重启 Studio App 或重新拉起 `cargo tauri dev`。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] API Keys 和 LLM Roles 对同一路由展示一致状态和诊断。
- [ ] Role Test 覆盖所有候选路由，刷新后仍能从后端投影看到结果。
- [ ] Playwright 或浏览器真实 e2e 覆盖成功、失败、取消/删除和窄宽度。
- [ ] 后端、前端相关测试通过并记录命令。

## 9. 不做(范围锁定,IR7)

不实现 Copilot chat/session，不修改 Canvas/Properties，除非 WS-2 串行释放；不重写 gateway 内核，不暴露 MVP1 不要求的复杂策略。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码回写 studio-settings、settings、llm-copilot-http-api 的 `baseline.md`；若 Properties shortcut 串行接入，再回写 phase-editing/properties baseline。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖后端投影、role test、model bundle 和 no-fake 边界。Codex 审查退出以 §8 为准。PM 终审检查 baseline 诚实和 gateway 边界未被复制。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws4-settings-llm-model-roles.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
