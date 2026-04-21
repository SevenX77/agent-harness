---
name: graph-agent-compiler
description: >
  严格检查、自动修复和生成 GraphAgent Skills 与 Tool scripts。
  当用户创建、修改或审查 skills/**/SKILL.md 或 script/*.py 时使用。
  当遇到 SkillLoadError、SkillCompilationError、模板渲染失败等运行时错误时使用。
  当用户说"检查 skill"、"lint skill"、"fix skill"、"创建新 skill"时使用。
type: graph
io:
  inputs:
    - name: target_skill_path
      type: str
      source: runtime
  outputs:
    - name: compilation_report
      type: dict
      target: file
context_mapping:
  skill_path: "{input.target_skill_path}"
---

# GraphAgent Skill Compiler & Auto-Fixer

一套统一的规则与知识库，既可作为 IDE 助手的知识被 Cursor / Claude Code 加载，
也可作为 GraphAgent 的 LLM 修复 Skill 运行。

## 部署方式

```
# 作为 Claude Code Skill（已通过 symlink 部署）
ln -s src/core/graph_agent/skills/compiler .claude/skills/graph-agent-compiler

# 作为 Cursor IDE Skill
cp -r src/core/graph_agent/skills/compiler/ .cursor/skills/graph-agent-compiler/

# 作为 GraphAgent 内部 Skill（Python 引擎调用）
from src.core.graph_agent.runner import run_skill
result = run_skill("src/core/graph_agent/skills/compiler/SKILL.md", target_skill_path="path/to/SKILL.md")
```

---

## 核心职责

1. **严格审查**：对照 `data/rules.yaml` 中定义的规则，检查目标 Skill 的每一个配置和引用。
2. **主动修复**：发现问题后直接修复文件，输出修复报告。
3. **生成模板**：创建新 Skill 时，使用 `references/` 中的完美模板。

## 规则来源

**唯一数据源**: `data/rules.yaml` — 定义所有 FATAL 和 WARNING 规则的 ID、作用域、描述。

**深度参考**（按需查阅）:
- `references/rules_spec.md` — 每条规则的失效机制、检查方法、修复策略和示例
- `references/skill_template.md` — 完美 SKILL.md 模板（Graph 模式）
- `references/tool_spec.md` — 工具函数编写规范

## 检查流程

1. 读取 `data/rules.yaml` 获取完整规则列表。
2. 解析目标 Skill 的 frontmatter、phase/node 配置、工具文件、目录结构。
3. 逐条执行规则检查，区分 FATAL（阻断）和 WARNING（建议）。
4. FATAL 存在时必须修复后才能运行；WARNING 记录但不阻断。
5. 修复时参考 `references/rules_spec.md` 中的修复策略。

## 创建新 Skill 的工作流

1. 确认用户的业务需求（输入/输出、阶段数、工具列表）。
2. 读取 `references/skill_template.md` 作为骨架。
3. 读取 `references/tool_spec.md` 作为工具骨架。
4. 按照 `data/rules.yaml` 中的规则逐项检查生成结果。
5. 输出完整的 Skill 目录结构。

---

<node id="compile_check">
<ref path="nodes/01_compile_check.md" />
</node>

<node id="auto_fix" depends_on="compile_check">
<ref path="nodes/02_auto_fix.md" />
</node>
