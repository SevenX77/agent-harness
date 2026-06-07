---
ws_id: WS-0-task-spec-red-checklist
modules: [global]
depends_on: []
blocks: [WS-1, WS-2, WS-3, WS-4, WS-5, WS-6, WS-7, WS-8]
owns_files:
  - .kiro/specs/studio-mvp1/requirements-ws0.md
  - apps/studio/backend/tests/test_studio_mvp1_requirements_gate.py
  - .kiro/specs/studio-mvp1/requirements-ws1-shell-native-fs.md
  - .kiro/specs/studio-mvp1/requirements-ws2-authoring-workbench.md
  - .kiro/specs/studio-mvp1/requirements-ws3-compile-predict-run-trace.md
  - .kiro/specs/studio-mvp1/requirements-ws4-settings-llm-model-roles.md
  - .kiro/specs/studio-mvp1/requirements-ws5-copilot-workbench.md
  - .kiro/specs/studio-mvp1/requirements-ws6-golden-eval-publish-history.md
  - .kiro/specs/studio-mvp1/requirements-ws7-ui-i18n-validation.md
  - .kiro/specs/studio-mvp1/requirements-ws8-debug-resume.md
spec_ssot:
  - docs/development/task-spec-standard.md §一/§二/§三/§四
  - docs/studio/mvp1/_impl/IMPL_PLAN.md §二/§三/§七/§八
  - docs/studio/mvp1/README.md §Scope
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md §单元表
status: drafted
created: 2026-06-06
owner: Studio MVP1 PM
related_plan: ../../../../docs/studio/mvp1/_impl/IMPL_PLAN.md
review_flow: PM 写需求书 → Codex 写 RED 文档检查 → PM 契约门 → Codex 写 kiro task.md → Gemini 产 WS1-WS8 需求书/红测清单 → Codex 审 → PM 终审
---

# WS-0 任务书 / 红测清单闸门 — 需求书

> **流水线当前位置**：本文件是 WS-0 的需求书，用来约束后续产出 WS1-WS8 的需求书与 RED 清单。下一步不是改业务代码，而是 Codex 先按 §6 写会失败的文档契约检查；PM 审过这些检查后，才允许进入 WS-0 的实施任务书与实际产出。
>
> **边界提醒**：WS-0 是文档闸门，除本 WS-0 RED 文档契约检查测试外，不改 `apps/studio/**`、`packages/**` 或测试实现文件。任何业务代码、前后端业务测试代码、baseline 实施回写，都属于后续 WS，必须等对应需求书、RED 测试、契约门和用户在聊天窗口明确确认后再动。

## 1. 目标(intent + why)

为 Studio MVP1 建立第一道实施闸门：把 `IMPL_PLAN.md` 中 WS1-WS8 的文件锁、依赖关系、SSOT 指针和 RED 测试要求，落成一组符合 `task-spec-standard.md` 的独立需求书。这样后续每个 WS 都能先用失败测试编码目标，再让实现者按已批准测试推进，避免多人/多 agent 在共享热点文件上边写边猜。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标写法与流水线权威：`docs/development/task-spec-standard.md:16-151`
- WS 切分、依赖、并发锁权威：`docs/studio/mvp1/_impl/IMPL_PLAN.md:25-57`
- 执行波次与完成定义：`docs/studio/mvp1/_impl/IMPL_PLAN.md:86-93`
- 产物落点与当前状态：`docs/studio/mvp1/_impl/IMPL_PLAN.md:95-113`
- Studio 设计总纲与四层边界：`docs/studio/mvp1/README.md:1-32`
- 设计单元、owner、外部绑定状态：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:18-55`
- 用户旅程索引：`docs/studio/mvp1/01_workflows/INDEX.md:5-22`
- 涉及前端 UI 的需求书必须继承的 UI 规范：`docs/development/FRONTEND_UI_SPEC.md:51-172`
- 现状起点：`.kiro/specs/studio-mvp1/` 目录已存在；WS1/WS7 若已有并行草稿，也必须接受本 WS 的命名、结构、文件锁和 RED 清单检查；`IMPL_PLAN.md:104-113` 中 WS1-WS8 任务书状态仍为待产。
- 范本/反例参考：`.kiro/specs/graph-agent-gateway-mvp1/tasks-ws3-six-states.md` 可参考其 grounding 颗粒度，但不要复制其中 implementation phase 写法；本 WS 需求书应停在契约层。

## 3. 文件归属(并发锁,IR1)

- 本 WS owns(可改/建)：frontmatter `owns_files` 中列出的 `.kiro/specs/studio-mvp1/requirements-ws*.md`，以及 WS-0 RED 文档契约检查测试 `apps/studio/backend/tests/test_studio_mvp1_requirements_gate.py`。
- 禁止触碰(后续 WS 或其它任务拥有)：`apps/studio/**`、`apps/studio/tauri/**`、`packages/**`、`docs/studio/mvp1/**/baseline.md`、`docs/studio/mvp1/**/mvp1-alignment.md`、`docs/development/FRONTEND_UI_SPEC.md`、`.kiro/specs/*/tasks*.md`。
- 共享文件协调：WS1-WS8 需求书必须继承 `IMPL_PLAN.md` 的文件锁；若某个源文件在多个 WS 中出现，需求书必须显式写清串行、排队或拆分策略，不能把它伪装成可并发。
- 落点选择：本批需求书使用 `.kiro/specs/studio-mvp1/requirements-wsN-<short-slug>.md` 作为唯一需求书落点，slug 只表达 WS 名称，不承载设计 SSOT；不另建 `docs/studio/mvp1/_impl/WS*.md` 镜像，避免双份 SSOT。

## 4. 现状锚点(baseline)

当前 Studio MVP1 已有设计总纲、设计单元索引和实施计划，但 `.kiro/specs/studio-mvp1/` 尚未形成 WS1-WS8 全量、同一标准的需求书集合；后续实现若现在启动，会缺少逐 WS 的 RED 测试契约、文件归属确认和硬退出条件。

## 5. 目标行为(可测的契约)

- 产物完整性：WS0 完成后，必须存在 WS1-WS8 的独立需求书，文件名采用 frontmatter `owns_files` 列出的稳定 slug；每份需求书都按 `task-spec-standard.md` §三的 12 节结构书写，并带合法 frontmatter。
- 任务边界：每份 WS 需求书只定义目标行为、SSOT 指针、文件归属、测试要求、验收标准和不做范围；不得写 implementation phase、逐行改法、字面代码片段、函数体或把行号当编辑指令。
- 文件锁一致性：每份 WS 需求书的 `owns_files` 必须从 `IMPL_PLAN.md` 的 WS 表推导，并把共享热点文件的排队策略写在 §3；需求书之间不能留下未解释的 owns 冲突。
- SSOT grounding：每份 WS 需求书必须指向对应设计单元的 `mvp1-alignment.md`、`baseline.md`、`DESIGN_UNITS_INDEX.md` 行、相关 workflow 文档，以及实现前必读源码位置；只给指针和增量，不复制设计正文。
- RED 清单：每份 WS 需求书 §6 必须把 Codex 后续要写的失败测试列清楚，覆盖单元/集成/回归/真实 e2e 或手动验证边界；涉及 UI 的 WS 必须点名本地 `@/components/ui/*` wrapper、Playwright/浏览器点击验证和窄宽度检查；涉及 Tauri/native-fs 的 WS 必须点名 Tauri bridge 或等价原生路径验证。
- 外部契约：依赖 gateway 或 engine 的 WS 必须标明外部契约当前是 pinned、floating draft 还是 blocked；不得在 Studio 需求书中复制 gateway ③b 或 engine 内核机制。
- 人工确认：每份需求书都必须保留“用户在聊天窗口明确确认后才可改代码”的闸门语义；系统自动审批不能被当作确认。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 为 WS-0 写 RED 检查时，必须让当前空目录状态先失败，并至少覆盖以下契约：

1. **产物存在性**：断言 frontmatter `owns_files` 中列出的 WS1-WS8 slug 需求书全部存在；当前至少应因 WS2-WS6/WS8 缺失而失败，已有并行草稿也要继续接受后续结构检查。
2. **模板完整性**：每份需求书必须包含 frontmatter、标题、§1-§12，且 frontmatter 至少含 `ws_id`、`modules`、`depends_on`、`blocks`、`owns_files`、`spec_ssot`、`status`。
3. **IR1 文件锁**：从所有需求书解析 `owns_files`，检查未解释的交集为零；允许的共享热点必须在对应需求书 §3 写出串行/排队策略，并指回 `IMPL_PLAN.md`。
4. **IR2/IR5 grounding**：每份需求书必须有完整路径级 SSOT 指针，至少覆盖对应 alignment、baseline、设计单元索引和必读源码；不得把 `.kiro/specs/studio-*` 历史文档当设计 SSOT。
5. **IR3 RED 清单**：每份需求书 §6 必须列出会先失败的测试/验证项，并标注哪些是真实 e2e、哪些不允许 fake mock。
6. **IR4 硬退出**：每份需求书 §8 必须包含测试全绿、验收点、无回归和至少一条真实 e2e 或明确说明为何该 WS 暂时 blocked。
7. **IR7 范围锁定**：每份需求书 §9 必须点名不做范围；发现范围外问题必须登记 deferred，不能顺手扩散。
8. **IR8 PM 边界**：检查需求书不含 implementation phase、逐行改写、字面代码片段、函数体或“按第几行修改”的编辑指令；行号只能出现在 grounding 语境。
9. **Studio 专项规则**：涉及 `apps/studio/frontend` UI 的需求书必须引用 `FRONTEND_UI_SPEC.md` §2，并要求先查 `src/components/ui/` wrapper、使用语义 token、实际点击验证；涉及后端 Python 的需求书必须要求完成后重启 Studio App。
10. **闸门语义**：每份需求书必须明确“RED 测试 → PM 契约门 → Codex task.md → Gemini 实现 → Codex 审 → baseline 回写 → PM 终审”的顺序，且不得把自动审批当成人工确认。

## 7. 硬依赖约束

WS-0 内部只有一个硬顺序：先让 RED 文档检查证明当前缺口，再产 WS1-WS8 需求书和红测清单。WS1-WS8 的业务实现不得与 WS-0 并行启动；WS-8 需求书可以产出，但必须把 engine checkpoint/resume API 未 pin 的状态写成 blocked 或条件放行。

## 8. 验收标准(硬退出,IR4)

- [ ] WS-0 的 RED 文档检查在 WS1-WS8 未产齐或不合规状态下能失败，并在需求书产齐且合规后变绿。
- [ ] frontmatter `owns_files` 列出的 WS1-WS8 slug 需求书均存在，且逐份符合 `task-spec-standard.md` §三。
- [ ] 每份需求书的 `owns_files` 与 `IMPL_PLAN.md` 的 WS 分区一致；所有共享热点文件都有明确串行/排队说明。
- [ ] 每份需求书 §6 都有可执行的 RED 清单，且 UI/Tauri/backend/gateway/engine 相关特殊验证没有遗漏。
- [ ] 没有业务代码、业务测试代码、alignment 或 baseline 被 WS-0 修改。
- [ ] 没有把 implementation phase、逐行实现、字面代码或函数体写进需求书。
- [ ] 至少一条真实端到端验收路径被每个可执行 WS 点名；暂不可执行的 WS 必须写明外部阻塞条件。

## 9. 不做(范围锁定,IR7)

- 不写 WS1-WS8 的实施任务书 `tasks-wsN.md`；那是契约门通过后的 Codex 产物。
- 不写 Gemini prompt；prompt 只在对应 `tasks-wsN.md` 完成后输出。
- 不改任何 Studio 前端、后端、Tauri、gateway、engine 业务代码或业务测试；只允许新增/维护本 WS 的 RED 文档契约检查测试。
- 不重写 Studio alignment/baseline；baseline 只在对应 WS 真实实现落地后按真实代码回写。
- 不在 Studio 需求书中复制 gateway ③b 或 engine 内核机制；只引用外部 SSOT。
- 不把 WS-8 的 debug resume 伪装成已可执行；外部 checkpoint/resume 契约未 pin 前只能作为 blocked/条件项。

## 10. baseline 回写指令(IR6)

WS-0 本身是文档闸门，不回写 Studio 功能 baseline。后续 WS 完成真实实现后，Codex 才能按各自需求书 §10 更新对应 `baseline.md`，并且必须照真实代码状态写，不能把目标态提前写成现状。

## 11. 评审检查点

- 契约门(PM 审测试)：重点查 RED 检查是否真的能抓住“缺需求书、缺红测、文件锁冲突、把实现步骤混进需求书、UI/Tauri 验证遗漏”等问题。
- Codex 审查退出：必须满足 §8 全部验收标准，不能用“文档看起来差不多”替代。
- PM 终审：逐份核对 WS1-WS8 需求书是否忠实承接 `IMPL_PLAN.md`、`DESIGN_UNITS_INDEX.md` 和对应 alignment/baseline；确认没有双份 SSOT、没有越权实现细节、没有自动审批绕过人工确认。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准的 WS-0 RED 检查写 `.kiro/specs/studio-mvp1/tasks-ws0.md`，遵守：

- 来源 = 已批准测试；每个任务项都必须能追到 §6 的某条检查。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: WS0.<契约项>` + 验证命令。
- frontmatter 指回本需求书、`task-spec-standard.md` 和 `IMPL_PLAN.md`；不重写设计。
- 嵌入编排注解：owns_files、实现者、§8 硬退出条件、用户明确确认闸门。
- 行号由 Codex 落地时重新核；不得照抄本需求书里的行号作为编辑坐标。
- 不跑 `/kiro:spec-tasks` 自动生成，避免 clobber。
- WS-0 实施完成后，只产 WS1-WS8 的需求书与红测清单；不顺手开始任何业务代码实现。
