---
status: Living
target_goal: "确立 .workspace 目录结构红线，以及 SKILL.md 语法的 Compile 强校验规则"
linked_code_paths:
  - packages/graph-agent/src/graph_agent/compiler/
linked_specs:
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Workspace 与文件结构规范 (Workspace & File Spec)

## 1. `.workspace` 目录强制结构
任何被 Engine 视为合法 `Skill` 的目录，必须遵循以下结构规范。如果残缺，引擎的 Compile 阶段将直接阻断：
```
{skill_name}/
├── SKILL.md             # 主入口文件，唯一的核心编排逻辑
├── .workspace/          # (系统隐式生成) 存放编译缓存、日志
├── script/              # 自定义的 Python Tool/Validator 脚本存放处
├── references/          # Agent 执行时需要的静态知识 (Markdown/Txt)
└── golden/              # 存放打磨完毕的黄金基线 (Mock 测试标准)
```

## 2. `SKILL.md` 语法规范与 XML 标签大全
文件以 Markdown 形式存在，但内部核心区域使用严格的 XML 标签（用于机器解析）：
- `<metadata>`: 存放 `name`, `version`, `type`。
- `<io>`: 声明全局的输入输出契约。
- `<phases>`: 包含一组 `<phase>` 标签。
  - 每个 `<phase>` 内部必须具有 `id`, `type` (agent/code/subgraph), `<inputs>`, `<outputs>`。
  - agent 类型必须具备 `<prompt>` 标签包围的核心提示词。

## 3. Python 工具函数挂载规范
存放在 `script/` 下的函数，通过 `<tool>module.function</tool>` 语法挂载。
函数必须携带 Type Hints（类型注解）与标准的 Docstring。Engine 的 Compiler 会通过 AST 静态分析，提取这些签名转交大模型。若无 Type Hints，Compile 将报错。

## 4. Compile 强校验规则
Engine 在 `compile_skill()` 调用时会执行极为严苛的静态规则：
1. **类型流验证**: 下游节点请求的入参 `x`，必须能在上游所有前置节点的 `outputs` 中找到，否则报错“断流”。
2. **孤岛检测**: 画布上不能存在无法到达的节点。
3. **依赖循环**: 不允许 A -> B -> A。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
