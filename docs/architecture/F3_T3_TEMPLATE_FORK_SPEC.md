# F3_T3_TEMPLATE_FORK_SPEC (模板库与 Fork)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在通过“脚手架”机制降低 PM 研发新技能的起步门槛。我们将建立一个内置模板库，提供数据提取、多步流水线及对话机器人等典型场景的 `SKILL.md` 模板。同时，通过引入“Fork”功能，支持 PM 一键克隆现有的成熟技能至自己的工作区进行二次开发，实现研发资产的高效复用。

## 2. PM 痛点

### 2.1 现状
*   **冷启动困难**: PM 创建新技能时往往面对一个近乎空白的 `SkillCreatorWizard`，需要从头构思 `io` 定义和 `phases` 结构，心智负担重。
*   **复用门槛高**: 看到同事做了一个优秀的技能，想学习或在其基础上修改，目前需要手动在文件系统复制目录、改名、并全局搜索替换 ID，过程繁琐。

### 2.2 理想 UX
*   **开箱即用**: 点击“New Skill”后，第一步即展示丰富的模板卡片。选中模板后，Wizard 会自动预填描述、输入输出和初始阶段。
*   **一键克隆**: 在侧边栏技能列表或详情页，点击 [Fork] 图标，仅需输入一个新 ID，即可瞬间获得一个完整的副本。

## 3. 设计决策

### 3.1 模板库实现
*   **存放路径**: 后端在 `apps/studio/backend/app/templates/` 维护一批静态模板。
*   **预设模板清单**:
    1.  `blank-agent`: 极简单阶段 Agent 模板。
    2.  `blank-graph`: 带有基础 `io` 声明的多阶段 Graph 模板。
    3.  `data-extractor`: 专门用于从非结构化文本提取 JSON 的 Graph 模板（含 `output_schema` 配置）。
    4.  `chained-reasoning`: 演示 A Phase 输出作为 B Phase 输入的逻辑链模板。
*   **API**: `GET /api/templates` 返回模板 ID、名称、描述及预览内容。

### 3.2 Fork 逻辑
*   **路径**: `POST /api/skills/{skill_id}/fork`。
*   **后端行为**: 
    1.  物理复制目录：`workspaces/{user_id}/skills/{old_id}` -> `{new_id}`。
    2.  读取新目录下的 `SKILL.md`。
    3.  通过正则表达式或 YAML 解析，将 frontmatter 中的 `id` (若有) 替换为新 ID。
    4.  重新 Lint 并加载至 Metadata。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/templates/
│   ├── TemplatePicker.tsx      # 向导 Step 1 替换组件
│   └── TemplateCard.tsx        # 模板预览卡片
├── hooks/
│   └── useTemplates.ts         # 获取与缓存模板列表
└── components/history/         # 放置在技能标题旁
    └── ForkButton.tsx          # 触发 Fork 流程的图标
```

### 4.2 向导集成 (SkillCreatorWizard)
*   **Step 1**: 变为“选择起点”。用户可以选择“从空白开始”或从下方网格中的模板选择。
*   **状态联动**: 选中模板后，`useSkillCreator` 的 `formData` 将自动被模板内容覆盖，PM 仅需在后续步骤微调即可。

---

## 5. 实施 Sub-steps (a1 指南)

### T3.1: 后端模板与 Fork API (3h)
1.  建立模板目录并写入 4 个初始 `SKILL.md` 模板。
2.  实现 `GET /api/templates` 路由。
3.  在 `app/services/skills.py` 增加 `fork_skill` 函数，确保文件 I/O 异常处理稳健。
4.  在 `routers/skills.py` 暴露 `POST /api/skills/{id}/fork`。

### T3.2: 模板选择器 UI (3h)
1.  实现 `useTemplates.ts` Hook。
2.  开发 `TemplateCard`：包含模板 Icon (Lucide)、标题、简短描述。
3.  改造 `SkillCreatorWizard`：第一步引入 `TemplatePicker` 网格布局。

### T3.3: Fork 按钮与联动 (1.5h)
1.  在 `SkillSidebar` 的技能列表项 Hover 状态下显示 [Copy/Fork] 图标。
2.  点击后弹出精简版 Modal（仅输入 New ID）。
3.  请求成功后调用 `mutateSkills()` 刷新列表并自动跳转。

### T3.4: 验证与验收 (0.5h)
1.  验证从“Data Extractor”模板创建出的技能是否包含正确的 `io.outputs` 预设。
2.  验证 Fork 一个复杂的 `text-segmentation` 技能是否保留了所有的脚本引用和 golden 目录。

---

## 6. 风险点与缓解
*   **模板版本漂移**: 未来 SDK schema 2.1 发布，模板需同步更新。
    *   *缓解*: 在后端实现简单的模板自检逻辑，确保所有模板均能通过 `compile_skill` 校验。
*   **Fork 路径安全**: 恶意构造的 `new_id` 可能导致目录遍历。
    *   *缓解*: 严格执行 `^[a-z][a-z0-9-]+$` 的正则校验。

## 7. 验收 Checklist
- [ ] “New Skill”向导的第一步能看到 4 个以上的场景模板。
- [ ] 选中模板后，后续步骤的默认描述和初始 Phase 已自动填好。
- [ ] 侧边栏点击 Fork 图标能成功克隆技能并自动打开新副本。
- [ ] 克隆后的技能 `SKILL.md` 内部 ID 已与目录名保持一致。
- [ ] 暗色模式下模板卡片展示美观。
