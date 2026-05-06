# F1_T2_SKILL_CREATOR_SPEC (Skill Creator Wizard)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在消除 PM 创建新技能时的“冷启动”障碍。当前 PM 必须手动在 OS 层面创建目录并手写复杂的 `SKILL.md` frontmatter，过程低效且易出错。我们将引入一个 **5 步向导式 UI**，通过可视化表单收集基础信息、输入 Schema 及首个 Phase 配置，最终自动生成符合规范的 `SKILL.md` 并落盘。

## 2. PM 痛点与 UX 流程

### 2.1 现状与挑战
*   **高门槛**: 必须记忆 YAML 语法和 `schema_version: "2.0"` 的字段结构。
*   **重复劳动**: 每个新技能都要手动写一遍 `io` 和 `context_mapping`。
*   **缺乏引导**: 面对空白文件，PM 往往不知道从哪里开始。

### 2.2 理想 UX (Wizard 流程)

| 步骤 | 标题 | 用户操作 | 验证规则 |
| :--- | :--- | :--- | :--- |
| **Step 1** | **选择类型** | 选择 `Agent` (单循环) 或 `Graph` (多阶段流水线) | 必选 |
| **Step 2** | **基本信息** | 输入 `Skill ID` (如 `story-generator`)、`名称`、`描述` | ID 符合 `^[a-z][a-z0-9-]+$` |
| **Step 3** | **定义输入** | 添加输入字段（名称、类型如 `str/int`、默认值） | 至少 1 个输入 |
| **Step 4** | **首个阶段** | 设置 `Phase ID`、角色定位 (`llm_role`) 及初始 Prompt | ID 必填 |
| **Step 5** | **预览创建** | 实时渲染 `SKILL.md` 源码预览 | 点击后发起 POST 请求 |

### 2.3 异常处理
*   **ID 冲突**: 后端返回 409 时，前端高亮 Step 2 字段并提示“ID 已被占用”。
*   **断网**: 提交失败弹出 Toast，保留向导状态允许重试。

## 3. 后端 API 契约

### 3.1 改造 `models/skills.py`
需要扩展 `CreateSkillReq` 以接受前端生成的完整内容：
```python
class CreateSkillReq(BaseModel):
    skill_id: str = Field(..., pattern=r"^[a-z][a-z0-9-]+$")
    content: str  # 前端渲染好的 SKILL.md 字符串
```

### 3.2 完善 `routers/skills.py`
将 `create_skill` 实现从 `raise_not_implemented` 替换为调用 service：
```python
@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(
    request: CreateSkillReq,
    user_id: str = Depends(get_auth_user_id),
    storage: StorageBackend = Depends(get_storage),
    metadata: MetadataStore = Depends(get_metadata),
) -> SkillSummary:
    return await create_new_skill(user_id, request.skill_id, request.content, storage, metadata)
```

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/creator/
│   ├── SkillCreatorWizard.tsx  # 主模态框
│   ├── StepIndicator.tsx       # 进度条
│   └── steps/
│       ├── StepTypeChoice.tsx
│       ├── StepBasics.tsx
│       ├── StepInputs.tsx
│       ├── StepFirstPhase.tsx
│       └── StepPreview.tsx
├── templates/
│   └── skillMdGenerator.ts     # 核心渲染逻辑
└── hooks/
    └── useSkillCreator.ts      # 状态管理 (Step, FormData)
```

### 4.2 触发入口
在 `components/SkillSidebar.tsx` 的 "Project Skills" 标题右侧增加 `+` 按钮：
```tsx
<div className="flex items-center justify-between mb-3">
  <h3 className="text-xs font-semibold uppercase text-gray-400">Project Skills</h3>
  <button onClick={onOpenCreator} className="...">
    <Plus className="h-4 w-4" />
  </button>
</div>
```

### 4.3 SKILL.md 生成模板 (`skillMdGenerator.ts`)
```typescript
export function generateSkillMd(data: WizardData): string {
  const frontmatter = {
    schema_version: "2.0",
    name: data.name,
    description: data.description,
    type: data.type,
    io: {
      inputs: data.inputs.map(i => ({ name: i.name, type: i.type, source: "runtime" })),
      outputs: [{ name: "result", type: "dict", target: "file", path: "output/result.json" }]
    },
    phases: data.type === 'graph' ? [{
      name: data.phaseId,
      mode: "llm",
      llm_role: data.llmRole,
      prompt: data.prompt
    }] : undefined
    // ... agent 模式逻辑
  };
  return `---\n${yaml.dump(frontmatter)}---\n\n# ${data.name}\n`;
}
```

## 5. 实施 Sub-steps

### T2.1: 后端基建 (3h)
1.  修改 `app/models/skills.py`: 更新 `CreateSkillReq`。
2.  在 `app/services/skills.py` 增加 `create_new_skill` 函数：
    *   检查 `workspaces/{user_id}/skills/{skill_id}` 是否存在。
    *   写入 `SKILL.md`。
    *   调用 `metadata.save_skill_summary`。
3.  更新 `routers/skills.py`。

### T2.2: 生成器与 Hook (3h)
1.  实现 `skillMdGenerator.ts` 并覆盖测试用例。
2.  编写 `useSkillCreator.ts`: 管理 5 步数据，提供 `next()`, `prev()`, `canNext` 计算逻辑。

### T2.3: UI 实施 (6h)
1.  实现 `SkillCreatorWizard.tsx` (使用 `Dialog` 或 `Modal` 原语)。
2.  逐个实现 5 个 Step 组件，复用已有的 Tailwind 样式。
3.  集成 `js-yaml` 进行预览渲染。

### T2.4: 联调与验证 (2h)
1.  集成到 `SkillSidebar`。
2.  验证创建成功后自动跳转到新技能并触发 `Monaco` 编辑。

## 6. 风险与缓解
*   **数据丢失**: 用户误关向导。
    *   *缓解*: 在 `localStorage` 缓存草稿。
*   **YAML 注入**: 用户输入的描述包含 `--`。
    *   *缓解*: 使用 `js-yaml` 的 `dump` 函数而非手动拼接字符串。

## 7. 验收 Checklist
- [ ] 点击侧边栏 `+` 弹出向导。
- [ ] 第一步选 Agent，第三步自动调整为 Agent 配置。
- [ ] ID 校验拦截非法字符。
- [ ] 创建后，文件出现在 `workspaces/default/skills` 下。
- [ ] `App.tsx` 成功跳转至新技能。
