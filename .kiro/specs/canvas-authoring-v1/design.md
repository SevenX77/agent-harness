> ⚠️ **Superseded → `studio-feature-canvas-topology`**（2026-06-01）。本 spec 编辑态能力（连线反写 / 新建节点 / Properties 编辑）已实现并吸收为主文档 REQ-3/9/10，写入侧待迁 Rust。本文件留作已实现代码的设计参考，待物理归档到 `_archive/`。

# Canvas Authoring V1 设计

## 目标

把 Studio canvas 变成真正的“文件驱动编辑入口”，而不是只看图：

- 在 `Properties` 面板里直接编辑当前 phase 文件 frontmatter 中明确支持的字段。
- 在 canvas 菜单里新建 phase node。
- 在 canvas 上连线后，自动反写 `GRAPH.md` 里的 `depends_on`。

核心原则：**canvas 只渲染文件状态的结果**。新建节点、编辑属性、连线都必须先落盘到 phase 文件或 `GRAPH.md`，再通过刷新 `SkillDetail` 让 canvas 重新渲染。

## 范围

本次只做三类能力：

1. `Properties` 面板编辑支持字段。
2. canvas 右键菜单新建三种 phase。
3. node 连线持久化为 `GRAPH.md` 依赖关系。

不做这些事：

- 不渲染只存在于前端 state 的“假节点”。
- 不做任意 YAML key 的动态表单编辑。
- 不新增一套独立于文件系统的 canvas 数据模型。

## 架构方案

本轮优先复用现有 API：

- `writeSkillFile(skillId, path, content, expectedHash?)`
- `/api/skills/{skill_id}/graph/serialize`
- `mutateSkillDetail()`

暂不新增大而全的后端 mutation API。

### Properties 面板

`PropertiesPanel` 根据当前选中 node 找到对应文件：

- `selectedNode.data.filePath`
- 从 `skillDetail.files[filePath]` 读取内容
- 解析 YAML frontmatter
- 渲染白名单字段表单
- 保存时只更新该文件的 frontmatter，正文保持不变
- 保存成功后调用 `mutateSkillDetail()`，让 canvas 从最新文件状态重绘

### Canvas 新建节点

canvas 使用本地 shadcn `ContextMenu`：

- `New Logic Phase`
- `New Agent Phase`
- `New Subgraph Phase`

用户选择一种类型后：

1. 前端生成唯一 phase id。
2. 写入新 phase 文件：
   - logic: `phases/<id>/LOGIC.md`
   - agent/skill: `phases/<id>/SKILL.md`
   - subgraph: `phases/<id>/SUBGRAPH.md`
3. 调用 graph serialize 生成新的 `GRAPH.md`。
4. 写回 `GRAPH.md`。
5. 刷新 `SkillDetail`。
6. canvas 渲染后端返回的新拓扑。

### Node 连线

ReactFlow `onConnect` 不再只改本地边。

连线时：

1. 校验 source/target 都是 phase node。
2. 拒绝重复依赖、自依赖、global input/output 依赖写入。
3. 从当前 `graph_topology` 生成新的 phase refs。
4. 给 target 的 `depends_on` 追加 source。
5. 调用 graph serialize 生成新的 `GRAPH.md`。
6. 写回 `GRAPH.md`。
7. 成功后刷新 `SkillDetail`；失败后撤销本地 optimistic edge，并显示 toast。

## Properties 支持字段

只展示明确支持字段。

通用字段：

- `name`
- `mode`
- `validator`

Logic phase：

- `execute_steps`

Agent/Skill phase：

- `llm_role`
- `model_override`
- `prompt`
- `user_prompt_template`
- `agent_tools`

Subgraph phase：

- `sub_skill_ref`

未支持字段：

- 保存时保留原样。
- 不在表单里展示。
- 不允许通过动态 key/value 表单编辑。

## UI 规则

- 表单使用本地 shadcn wrapper：`Field`、`Input`、`Textarea`、`Select`。
- canvas 菜单使用本地 `ContextMenu`。
- 按钮、badge 继续使用本地 `Button` / `Badge`。
- 不写硬编码 hex 颜色或一次性 Tailwind palette。
- `Properties` 仍然是左侧 panel，不弹 modal。
- 新建 phase 的入口放在 canvas context menu，不做额外浮层。

## 错误处理

Properties：

- 找不到文件：显示只读错误状态，并提供打开文件入口。
- frontmatter 解析失败：显示错误，不覆盖文件内容。
- 保存冲突：toast 提示，保留当前草稿。

新建 node：

- phase 文件写入失败：toast 提示，不更新 canvas。
- `GRAPH.md` 更新失败：toast 提示并刷新最新 `SkillDetail`，让用户看到真实文件状态。

连线：

- 无效连接直接拒绝。
- graph serialize 冲突或校验失败：toast 提示并刷新最新 `SkillDetail`。
- 本地 optimistic edge 必须回滚。

## 测试要求

单元测试：

- frontmatter 解析和保存只修改支持字段，并保留未支持字段。
- `PropertiesPanel` 按 phase 类型展示对应字段。
- canvas context menu 展示三种新建 phase 动作。
- 连线逻辑能生成正确 phase refs，并拒绝重复依赖/自依赖。

E2E：

- 在 Properties 中编辑一个支持字段，保存后刷新并看到变化。
- 从 canvas 菜单分别新建 logic、agent、subgraph phase，并确认 node 出现在 canvas。
- 连接两个 node，刷新后确认 `depends_on` 已持久化。

## 决策

- phase id 生成使用可读 slug：`logic`、`agent`、`subgraph`。
- 如果 id 已存在，追加数字后缀，例如 `logic-2`。
- 本轮不做任意 YAML 字段编辑，只做白名单字段。
