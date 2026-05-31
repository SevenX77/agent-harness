# Canvas Authoring V1 Tasks

本文档执行 `.kiro/specs/canvas-authoring-v1/design.md`。实现目标是让 Studio canvas 成为文件驱动的编辑入口：属性表单改 phase frontmatter，canvas 菜单新建 phase 文件，节点连线反写 `GRAPH.md` 的 `depends_on`。

## 实现约束

- 修改 `apps/studio/frontend` UI 前必须遵守 `docs/development/FRONTEND_UI_SPEC.md` §2 和 §3。
- 业务 UI 复用本地 shadcn wrapper：`Field`、`Input`、`Textarea`、`Select`、`ContextMenu`、`Button`、`Badge`、`ScrollArea`。
- 不新增 canvas 专用后端 mutation API；优先复用 `writeSkillFile`、`/api/skills/{skill_id}/graph/serialize`、`mutateSkillDetail()`。
- canvas 不渲染前端假节点。新建、编辑、连线必须先写文件，再刷新 `SkillDetail` 重新渲染。
- 不实现任意 YAML key/value 动态编辑；只支持设计文档列出的白名单字段，未支持字段保存时保留。

## Phase 1: Frontmatter 编辑内核

**目标**: 建立可测试的 markdown frontmatter 读写层，先保证文件内容不会被表单保存破坏。

- [x] 1.1 新增 phase frontmatter helper。
  - Create: `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts`
  - 支持解析 `---` YAML frontmatter 与正文。
  - 支持按 phase 类型读取白名单字段：
    - common: `name`, `mode`, `validator`
    - logic: `execute_steps`
    - skill/agent: `llm_role`, `model_override`, `prompt`, `user_prompt_template`, `agent_tools`
    - subgraph: `sub_skill_ref`
  - Acceptance: helper 对缺失 frontmatter、非法 YAML、空正文返回明确状态，不直接覆盖原文件。

- [x] 1.2 先写 frontmatter helper 单元测试。
  - Create: `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.test.ts`
  - 覆盖：
    - 保存支持字段时保留未支持字段。
    - 保存支持字段时保留 markdown 正文。
    - list 字段 `execute_steps` / `agent_tools` 能从 textarea 行文本转回数组。
    - subgraph 字段 `sub_skill_ref` 能正确更新。
    - 非法 YAML 不生成新内容。
  - Run: `npm test -- src/components/studio/panels/phase-frontmatter.test.ts`

- [x] 1.3 实现 helper 到测试通过。
  - 使用 `js-yaml`，不要用正则拼接 YAML 字段。
  - YAML dump 输出保持稳定顺序：原有未支持字段保留，白名单字段按表单值覆盖。
  - Acceptance: `npm test -- src/components/studio/panels/phase-frontmatter.test.ts` 通过。

## Phase 2: Properties 可编辑表单

**目标**: 单击 node 后的 `Properties` 面板根据 phase 文件 frontmatter 渲染可编辑表单，并能保存到对应 phase 文件。

- [x] 2.1 扩展 `PropertiesPanel` props 和保存回调。
  - Modify: `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx`
  - Modify: `apps/studio/frontend/src/components/studio/Panels.tsx`
  - 新增从 panel 到 workspace 的保存入口，签名以 `filePath + content + expectedHash` 为核心。
  - 找不到 `selectedNode.data.filePath` 或文件内容时保留只读错误态和打开文件入口。

- [x] 2.2 改造 `PropertiesPanel` 表单 UI。
  - 使用 `FieldSet` / `FieldGroup` / `Field` / `FieldLabel` / `FieldDescription`。
  - 使用 `Input` 编辑短文本，`Textarea` 编辑多行字段，`Select` 编辑 `mode`。
  - 使用 `Button` 提供保存和重置动作。
  - 保留现有 phase metadata，如 Phase ID、File、Depends On。
  - Acceptance: 不使用硬编码 hex 或一次性 Tailwind palette。

- [x] 2.3 先写 Properties 表单测试。
  - Modify: `apps/studio/frontend/src/components/studio/Panels.test.tsx`
  - 覆盖：
    - logic phase 展示 `execute_steps`，不展示 agent-only 字段。
    - skill/agent phase 展示 `llm_role`、`prompt`、`agent_tools`。
    - subgraph phase 展示 `sub_skill_ref`。
    - 修改字段并保存时调用保存回调，保存内容只更新 frontmatter。
    - 解析错误时保存按钮不可用。
  - Run: `npm test -- src/components/studio/Panels.test.tsx`

- [x] 2.4 接入 `writeSkillFile` 与刷新。
  - Modify: `apps/studio/frontend/src/components/studio/Workspace.tsx`
  - 保存 phase 文件成功后调用 `mutateSkillDetail()`。
  - 保存失败时显示 toast，保留当前草稿。
  - `expectedHash` 使用当前文件内容 hash，避免覆盖并发修改。
  - Acceptance: Properties 保存后 canvas 从刷新后的 `SkillDetail` 渲染。

## Phase 3: GRAPH 序列化客户端与拓扑 helper

**目标**: 把 `GRAPH.md` 更新逻辑收敛为可测试的前端 helper，供新建节点和连线共用。

- [x] 3.1 新增 graph serialize client。
  - Modify: `apps/studio/frontend/src/api/client.ts`
  - Modify: `apps/studio/frontend/src/api/types.ts`
  - 新增 `serializeSkillGraph(skillId, phases, expectedHash?)`，调用 `POST /api/skills/{skill_id}/graph/serialize`。
  - 类型对齐后端 `PhaseRef` / `SerializeGraphReq` / `SerializeGraphRes`。

- [x] 3.2 新增 canvas authoring helper。
  - Create: `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts`
  - 从当前 `SkillDetail` 和 canvas node 生成 phase refs。
  - 支持新增 phase ref，生成唯一 id：`logic`、`agent`、`subgraph`，冲突时追加数字后缀。
  - 支持连接 source → target 时给 target 追加 `depends_on`。
  - 拒绝自依赖、重复依赖、global input/output 依赖写入。

- [x] 3.3 先写 topology helper 测试。
  - Create: `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.test.ts`
  - 覆盖：
    - 从 schema v2.1 `manifest.phases` 生成完整 refs。
    - 新建 logic/skill/subgraph phase 使用正确 `src`。
    - 已存在 `logic` 时生成 `logic-2`。
    - 连线 `draft -> review` 生成 `review.depends_on = ["draft"]`。
    - 重复依赖和自依赖返回 rejected 状态。
  - Run: `npm test -- src/components/GraphCanvas/canvas-authoring.test.ts`

- [x] 3.4 实现 helper 到测试通过。
  - Acceptance: `npm test -- src/components/GraphCanvas/canvas-authoring.test.ts` 通过。

## Phase 4: Canvas 右键新建 phase

**目标**: canvas menu 能创建三种 phase 文件，并通过 `GRAPH.md` 刷新后显示新 node。

- [x] 4.1 为新 phase 生成默认文件内容。
  - 在 authoring helper 中提供默认 markdown：
    - logic: `phases/<id>/LOGIC.md`
    - skill/agent: `phases/<id>/SKILL.md`
    - subgraph: `phases/<id>/SUBGRAPH.md`
  - 默认 frontmatter 只写白名单内必要字段，正文给最小可编辑占位。

- [x] 4.2 接入本地 `ContextMenu`。
  - Modify: `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
  - 右键 canvas 空白区域显示：
    - `New Logic Phase`
    - `New Agent Phase`
    - `New Subgraph Phase`
  - 使用本地 `ContextMenu` wrapper。
  - 新建菜单项触发父级 callback，不在 `GraphCanvas` 里直接写 API。

- [x] 4.3 Workspace 编排新建流程。
  - Modify: `apps/studio/frontend/src/components/studio/Workspace.tsx`
  - 步骤：
    1. 写入新 phase 文件。
    2. 调用 `serializeSkillGraph` 获取新 `GRAPH.md`。
    3. 写回 `GRAPH.md`。
    4. 调用 `mutateSkillDetail()`。
  - 失败时 toast 并刷新最新 `SkillDetail`，避免画布停留在假状态。

- [x] 4.4 新增/更新测试。
  - Modify: `apps/studio/frontend/src/components/GraphCanvas.test.tsx`
  - 覆盖 context menu 存在三种新建动作，并触发正确 callback。
  - Modify: `apps/studio/frontend/src/components/studio/Workspace.test.tsx` 若已有可用测试基建，否则补 authoring helper 层测试覆盖编排输入输出。

## Phase 5: Node 连线持久化 depends_on

**目标**: ReactFlow 连线不再只改本地 edge，而是通过 `GRAPH.md` 保存为真实依赖。

- [x] 5.1 改造 `GraphCanvas` 连线 callback。
  - Modify: `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
  - `onConnect` 校验连接，触发父级 `onPersistConnection`。
  - 成功前可显示 optimistic edge；失败必须回滚到刷新前状态。
  - 无效连接不调用 API。

- [x] 5.2 Workspace 编排连线流程。
  - Modify: `apps/studio/frontend/src/components/studio/Workspace.tsx`
  - 使用 authoring helper 生成更新后的 phase refs。
  - 调用 `serializeSkillGraph`，再 `writeSkillFile("GRAPH.md")`。
  - 成功后刷新 `SkillDetail`。
  - 冲突或校验失败时 toast 并刷新最新 `SkillDetail`。

- [x] 5.3 更新连线单元测试。
  - Modify: `apps/studio/frontend/src/components/GraphCanvas.test.tsx`
  - 覆盖有效连线调用 `onPersistConnection`。
  - 覆盖自依赖、重复依赖、global node 连接被拒绝。
  - 覆盖失败时 edge 回滚。

## Phase 6: E2E 与手动验证

**目标**: 证明三条主路径在真实前端页面里可用。

- [x] 6.1 更新 canvas e2e mock。
  - Modify: `apps/studio/frontend/tests/e2e/canvas-v1.spec.ts`
  - Mock 支持：
    - phase file write
    - graph serialize
    - graph file write
    - skill detail refresh

- [x] 6.2 覆盖 Properties 编辑 e2e。
  - 在 Properties 里修改一个支持字段并保存。
  - 刷新 skill detail 后确认字段仍显示新值。

- [x] 6.3 覆盖新建 node e2e。
  - 从 canvas context menu 新建 logic、agent、subgraph phase。
  - 确认刷新后 canvas 出现对应 node。

- [x] 6.4 覆盖连线 e2e。
  - 连接两个 phase node。
  - 刷新后确认目标 node 的 `depends_on` 持久化。

- [x] 6.5 运行自动验证。
  - Run: `npm test -- src/components/studio/panels/phase-frontmatter.test.ts src/components/studio/Panels.test.tsx src/components/GraphCanvas/canvas-authoring.test.ts src/components/GraphCanvas.test.tsx`
  - Run: `npm run typecheck`
  - Run: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 npx playwright test tests/e2e/canvas-v1.spec.ts`

- [x] 6.6 手动浏览器验证。
  - 使用已有 Vite 或 Tauri dev session。
  - 打开 Studio canvas。
  - 点击 node，编辑 Properties 并保存。
  - 右键 canvas，新建三种 phase。
  - 拖拽连线，确认刷新后边仍存在。
  - 检查窄宽度下 Properties 表单无横向溢出。

## Phase 7: UI Spec 回填

**目标**: 把本轮形成的可复用 canvas authoring 规则沉淀到统一前端规范。

- [x] 7.1 更新 `docs/development/FRONTEND_UI_SPEC.md` §3。
  - 增加规则：
    - canvas authoring 必须文件驱动，禁止前端假节点。
    - Properties 只编辑明确支持 frontmatter 字段，保存保留未知字段。
    - canvas 连线必须持久化到 `GRAPH.md`，不能只停留在 ReactFlow state。
  - Acceptance: 新规则能指导后续 canvas authoring 迭代，不依赖聊天记录。
