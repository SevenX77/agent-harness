# F2_T2_PHASE_FORM_SPEC (节点表单化编辑)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在解决 PM 在超长 `SKILL.md` 中手动维护 Phase 逻辑的效率与准确性问题。我们将引入一个 **Phase Drawer (侧边栏表单)**，通过可视化方式展示并编辑 Phase 的全部属性（Prompt, LLM Role, Tools, 校验器等）。核心挑战在于实现 **Monaco ↔ Form 的双向增量同步**，即在不破坏用户 YAML 手动格式的前提下，精准替换特定 Phase 的 YAML 块。

## 2. PM 痛点

### 2.1 现状与挑战
*   **定位难**: 在上千行的 Markdown 中寻找某个特定的 `phase` 耗时耗力。
*   **语法险象**: 手动修改 YAML 极易因缩进（Indent）错误导致 `SkillCompilationError`。
*   **盲目改写**: 修改 Prompt 时缺乏直观的 Token 计数参考。
*   **引用断层**: 难以记住哪些 Tool 已在 Skill 中注册，哪些 LLM Role 可选。

### 2.2 理想 UX
*   **一键滑出**: 双击画布节点，右侧即刻滑出表单。
*   **所见即所得**: 表单修改即时反映到左侧编辑器高亮行，且提供 Prompt Token 实时估算。
*   **智能输入**: 
    *   `Tools`: 下拉多选（基于 Skill 现有的 `agent_tools`）。
    *   `LLM Role`: 预设角色选择（基于 `llm_roles.yaml`）。
*   **安全更新**: 仅点击“Apply”时才将变更提交至 Monaco，防止误操作。

## 3. 关键技术方案

### 3.1 双向增量同步 (Incremental Sync)
不推荐全量重新渲染整个 `SKILL.md`，因为这会丢失用户的空行和注释。
*   **算法**:
    1.  利用正则表达式定位目标 Phase 的 YAML Block（从 `- name: <target>` 到下一个 `- name:` 或文档末尾）。
    2.  解析该 Block 为 JS Object 供 Form 初始化。
    3.  Form 修改后，使用 `js-yaml` 的 `dump` 函数生成新 Block。
    4.  通过 Monaco 的 `executeEdits` API 精准替换特定 Range。

### 3.2 Token 估算器
采用 **4 字符 ≈ 1 Token** 的经验公式（V1 不引入 `tiktoken` 重量级库），在 Prompt 编辑区实时显示字符数与预估 Token。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/phaseform/
│   ├── PhaseDrawer.tsx         # 容器，处理滑出动画与 ESC 逻辑
│   ├── PhaseForm.tsx           # Form 主体，处理校验逻辑
│   └── fields/
│       ├── PromptField.tsx     # 核心编辑器，支持自动高度与 Token 计数
│       ├── ToolSelector.tsx    # 下拉多选
│       └── RoleSelector.tsx    # 角色映射选择
├── hooks/
│   └── usePhaseSync.ts         # 封装 Monaco 查找与替换逻辑
└── utils/
    └── yamlBlockParser.ts      # 负责精准定位 YAML 块的 Offset
```

### 4.2 触发机制
在 `GraphCanvas.tsx` 中绑定 `onNodeDoubleClick`:
```typescript
onNodeDoubleClick={(_, node) => onOpenPhaseDrawer(node.data.label)}
```

---

## 5. 实施 Sub-steps (a1 指南)

### T2.1: YAML 块解析与替换算法 (6h)
1.  实现 `yamlBlockParser.ts`:
    *   `findPhaseRange(md: string, phaseName: string): { startLine, endLine }`
    *   处理 `SKILL.md` 特有的 `---\n frontmatter \n---\n body` 结构。
2.  测试在各种缩进场景下（2 vs 4 spaces）的定位准确性。

### T2.2: 核心字段组件库 (8h)
1.  **PromptField**: 实现具有“高度自适应”的 `Textarea`，并在底部显示“Characters: 1200 | ~300 Tokens”。
2.  **ToolSelector**: 遍历 `manifest.agent_tools` 提供多选 Badge UI。
3.  **RoleSelector**: 提供 `analyst`, `planner`, `critic` 等标准角色下拉。

### T2.3: `usePhaseSync` Hook (4h)
1.  集成 Monaco 的 `IDecorativeRange`，当 Drawer 打开时，在编辑器中高亮显示对应 Phase 所在的行区域。
2.  实现 `applyChanges` 函数：构造 `applyEdits` 事务提交变更。

### T2.4: UI 集成与动画 (4h)
1.  实现 `PhaseDrawer`：右侧滑入，占比 40% 宽度，支持 `Backdrop` 点击拦截（询问是否放弃修改）。
2.  在 `App.tsx` 中分发 `selectedPhaseId` 到各组件。

### T2.5: 最终验证 (2h)
1.  验证修改 Phase Name 时，ReactFlow 连线是否会自动更新（基于依赖关系）。
2.  验证 Logic 模式与 LLM 模式的字段切换（Hidden/Visible）。

---

## 6. 风险点与缓解
*   **定位失败**: 如果用户手动写了两个同名的 `name` 属性（非 Phase 名）。
    *   *缓解*: 严格匹配 YAML 列表项 `- name: <id>` 模式。
*   **格式丢失**: `js-yaml.dump` 可能会改变原有的引号风格（' vs "）。
    *   *缓解*: 配置 `js-yaml` 的 `forceQuotes: false`, `styles: { '!!null': 'empty' }`。
*   **同步冲突**: 当 Drawer 打开时，用户又在 Monaco 侧手动修改。
    *   *缓解*: Drawer 开启期间 Monaco 设为 `readOnly: true` (可选) 或监听 `onDidChangeModelContent` 弹出冲突提示。V1 推荐采用“开启即锁定”策略。

## 7. 验收 Checklist
- [ ] 双击 Phase 节点，Drawer 成功弹出。
- [ ] 修改 Prompt 后，底部 Token 计数实时变化。
- [ ] 点击 Apply，Monaco 编辑器精准定位并替换该 Phase 块，且不影响文档其他部分。
- [ ] 修改 `mode: logic` 后，表单自动隐藏 Prompt 字段，显示 `execute_steps` 字段。
- [ ] 暗色模式适配正常。
