---
ws_id: WS-7-ui-i18n-validation
modules: [04_platform/i18n, frontend-nfr]
depends_on: [WS-0]
blocks: []
owns_files:
  - apps/studio/frontend/src/index.css
  - apps/studio/frontend/src/lib/llm-error-messages.ts
  - apps/studio/frontend/src/components/ui/save-status-badge.tsx
spec_ssot:
  - docs/studio/mvp1/04_platform/i18n.md
  - docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/settings/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
status: drafted
---

# WS-7 UI/i18n/验证横切 — 需求书

本需求书是 WS-7 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

把 Studio MVP1 前端横切规则收口到轻量基础设施：错误文案入口、共享保存状态 badge、全局 token/utility 和真实 UI 验证纪律，避免各业务 WS 复制一套。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：`docs/studio/mvp1/04_platform/i18n.md`、frontmatter 中 Settings 相关 `mvp1-alignment.md`、`01_workflows/00_settings-ux-spec.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/studio-settings/baseline.md`、`docs/studio/mvp1/03_regions/settings/baseline.md`，以及 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 的 `i18n-error-code-ui-copy`。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2；实现前先查 `apps/studio/frontend/src/components/ui/`，新增 wrapper 必须落在 `components/ui`。
- 外部契约状态：本 WS 不改 engine/gateway；若错误码来自外部，仅按 floating-draft 机器码输入翻译，不复制分类内核。
- 必读源码：frontmatter `owns_files` 中 `index.css`、`llm-error-messages.ts` 和共享 `save-status-badge`。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`，只做横切入口和共享 UI wrapper。业务 Settings 文件不在本 WS owns 内；若某业务 WS 需要迁移消费者，必须在该 WS 文件锁内串行处理，并指回 `docs/studio/mvp1/_impl/IMPL_PLAN.md`。

禁止触碰 API Keys、LLM Roles、Copilot 业务组件、backend 文件、gateway/engine packages。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

现状 baseline 和索引显示 i18n/error copy 是 target-design，`llm-error-messages.ts` 仍是前端英文 catalog，保存状态 badge 存在重复实现，真实 UI 验证纪律依赖各业务 WS 自觉执行。

## 5. 目标行为(可测的契约)

- `llm-error-messages.ts` 的公开行为保持兼容，但错误码和请求包装错误不退化为 raw request error。
- 共享 `SaveStatusBadge` 是 Settings 类页面保存状态的唯一 UI wrapper，业务消费者由对应 WS 串行迁移。
- `index.css` 只沉淀语义 token、主题和可复用 utility，不写业务一次性样式。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、语义 token、Playwright/浏览器验证和窄宽度检查。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 error message fallback、已知错误码、raw request error 禁止、共享 SaveStatusBadge 的 idle/pending/saving/saved/failed 状态、语义 token 约束和新增 wrapper 可访问性。至少一条真实 e2e 或手动验证必须在浏览器中打开触发保存状态或错误文案的页面，并检查窄宽度；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-7 只提供横切基础设施。消费者迁移跟随 WS4/WS5 等业务文件锁，不得为了让横切测试变绿越权修改业务页面。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] `llm-error-messages.ts` 兼容行为和新错误文案测试通过。
- [ ] `SaveStatusBadge` 共享 wrapper 测试通过。
- [ ] 新增 UI 不引入 hardcoded hex 或一次性 palette，遵守语义 token。
- [ ] Playwright 或浏览器真实 e2e/手动验证覆盖保存状态、错误文案和窄宽度。

## 9. 不做(范围锁定,IR7)

不做全应用文案大翻译，不迁移业务 Settings 文件，不修改 backend 中文残留，不复制 engine/gateway 错误分类。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码回写 `docs/studio/mvp1/04_platform/i18n.md`，并在业务 WS 真实迁移消费者后再回写对应 baseline。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖错误 fallback、共享 badge、UI 验证和 no-fake 边界。Codex 审查退出以 §8 为准。PM 终审检查未越权改业务文件和 baseline 诚实。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws7-ui-i18n-validation.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
