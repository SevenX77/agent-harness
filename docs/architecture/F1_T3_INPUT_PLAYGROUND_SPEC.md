# F1_T3_INPUT_PLAYGROUND_SPEC (Input Playground)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 🔴 **OBSOLETE** (2026-05-06)

> ## ⚠️ 这份 spec 已废弃
>
> User 在 2026-05-06 PM 工作流校正中明确表态: **测试输入用文件, 不是表单**。
> 这份 spec 整篇是"按 io.inputs schema 动态生成表单"的设计, 跟 user 真实意图根本冲突。
>
> 替代 spec: `docs/architecture/F1_T3_FILE_INPUT_SPEC.md` (Gemini 起草中, 2026-05-06)
> 决策上下文: `docs/architecture/POST_PLAN_C_FINAL_DECISIONS.md` 第 5 节
> Tech debt 跟踪: `.kiro/specs/graph-agent-optimizations/deferred-items.md` TD-S2
>
> 当前 `apps/studio/frontend/src/components/playground/InputPlayground.tsx` 实现仍是按本 spec 的表单设计落地的。**改造任务**已经登记到 deferred-items, 等新 spec ship 后由 a1 codex 实施。
>
> 本文件保留作为**历史参考** (展示 PM 表单 vs 文件输入两种设计的取舍), 内容**不要再继续按这个推进**。

## 1. Executive Summary

本任务旨在彻底改变 PM 运行技能测试的方式。目前 PM 需要在“Artifacts”菜单中手动粘贴 JSON 字符串，这种方式不仅难以记忆字段名，还极易产生语法错误。我们将引入 **Input Playground**：一个基于 `SKILL.md` 中 `io.inputs` 声明自动生成的动态表单。它支持类型映射、实时校验，并提供本地预设（Presets）管理，实现“表单填入-一键运行”的丝滑体验。

## 2. PM 痛点

### 2.1 现状
*   **黑盒输入**: 必须时刻翻阅 `SKILL.md` 源码才能确定需要哪些输入参数。
*   **语法地狱**: JSON 遗漏逗号或引号导致运行失败，浪费调试时间。
*   **重复录入**: 每次测试相同场景都需要重新粘贴 JSON。
*   **类型不直观**: `int` 被写成 `string` 只有到后端运行期才会报错。

### 2.2 理想 UX
*   **自动表单**: 选定技能后，系统解析 Manifest 自动生成带有描述和默认值的表单控件。
*   **强类型校验**: 前端拦截类型错误（如在数字框输入文字）。
*   **预设系统**: 支持为不同测试用例保存“预设”，支持一键加载。
*   **运行反馈**: 点击 Run 直接触发执行，并自动跳转至 Trace 视图。

## 3. 现有契约分析

### 3.1 SDK 契约 (`graph_agent.core.manifest`)
当前 `IoInput` 模型定义如下：
*   `name`: 字段名（Key）
*   `type`: 类型标识（如 "str", "int", "list[str]", "dict"）
*   `default`: 默认值（Any）

**建议扩展**: 为了更好的 UI 体验，建议在 `IoInput` 中增加 `description: str | None` 和 `enum: list[Any] | None` 字段。本任务中若 SDK 尚未更新，前端将先适配现有字段。

### 3.2 后端 API (`POST /api/skills/{id}/runs`)
*   接受 `RunRequest` 负载。
*   `input_data`: 一个 `JsonObject`。这正是我们 Playground 表单产出的目标格式。

## 4. 类型映射表

| InputSpec `type` | 前端控件 | 行为 |
| :--- | :--- | :--- |
| `str` | `Input (type="text")` | 基础文本输入 |
| `str` (有 `enum`) | `Select` | 下拉选择器 |
| `int` / `float` | `Input (type="number")` | 数值输入，支持步长 |
| `bool` | `Checkbox` | 开关/勾选框 |
| `list[str]` | `Multi-Value Input` | 类似标签组或多行文本框 |
| `dict` | `Nested Form` | 递归渲染子字段，若无子 Schema 则显示简易 JSON 编辑器 |

## 5. 前端组件设计

### 5.1 目录结构
```
apps/studio/frontend/src/components/playground/
├── InputPlayground.tsx        # 主入口，取代 HeaderBar 中的旧弹出内容
├── FieldRenderer.tsx          # 调度器，根据类型选择字段组件
├── fields/
│   ├── StringField.tsx
│   ├── NumberField.tsx
│   ├── BoolField.tsx
│   ├── ListField.tsx
│   └── DictField.tsx          # 递归支持
└── PresetToolbar.tsx          # 预设保存/加载
```

### 5.2 状态管理 (`useInputPlayground.ts`)
```typescript
interface InputState {
  values: Record<string, any>;
  errors: Record<string, string>;
  isValid: boolean;
}

export function useInputPlayground(inputs: IoInput[]) {
  // 1. 初始化 values 为 default 值
  // 2. 提供 setValue(name, val) 并触发校验
  // 3. 实时计算 isValid
}
```

### 5.3 预设持久化
使用 `localStorage`，Key 格式为 `studio:presets:{skill_id}`。
每个预设包含：`{ id: string, name: string, data: Record<string, any>, createdAt: string }`。

---

## 6. 实施 Sub-steps (a1 指南)

### T3.1: 核心逻辑与 Hook (4h)
1.  根据 `api/types.ts` 中的 `IoInput` 定义完善类型声明。
2.  实现 `useInputPlayground` hook：处理默认值注入、类型转换及 `required` 验证。
3.  实现 `PresetManager` 工具类：封装 `localStorage` 的 CRUD。

### T3.2: 基础字段组件 (5h)
1.  实现 `StringField`, `NumberField`, `BoolField`：适配 Tailwind 样式与暗色模式。
2.  实现 `ListField`：支持添加/删除项。
3.  实现 `FieldWrapper`：统一显示字段标签、描述（如果有）及错误信息。

### T3.3: 递归与高级组件 (4h)
1.  实现 `DictField`：对于 `type: "dict"` 的字段，支持折叠展开，内部提供一个受控的微型 JSON 编辑器（或二级表单）。
2.  实现 `InputPlayground` 主容器：循环遍历 `manifest.io.inputs` 调用渲染器。

### T3.4: UI 集成与替换 (3h)
1.  **HeaderBar 改动**: 移除 `Artifacts` 按钮中的旧 `textarea`，改为点击后弹出包含 `InputPlayground` 的侧边栏或更大的 Popover。
2.  **Run 逻辑**: 将 `InputPlayground` 产出的 `values` 传给 `App.tsx` 的 `handleRun`。
3.  **Preset 交互**: 在 Playground 顶部增加预设下拉框。

---

## 7. 风险点与缓解
*   **嵌套过深**: 极其复杂的 `dict` 结构。
    *   *缓解*: 第一版对 `dict` 采用 Monaco-lite 嵌入，确保基本可用。
*   **Schema 缺失**: 旧的 `SKILL.md` 可能没有定义 `io.inputs`。
    *   *缓解*: 若 `inputs` 为空，自动降级为原始的 JSON Paste 模式。
*   **性能问题**: 字段过多导致重绘。
    *   *缓解*: 使用 `memo` 包装字段组件，仅在自身值变动时更新。

## 8. 验收 Checklist
- [ ] 选择不同技能时，表单字段能够自动更新。
- [ ] 必填字段未填时，`Run` 按钮处于禁用状态。
- [ ] 填写完数据后点击“Save Preset”，刷新页面后能从下拉框找回。
- [ ] 点击 `Run` 能够将表单内容正确转化为 JSON 并发送至后端。
- [ ] 暗色模式下表单外观正常。
