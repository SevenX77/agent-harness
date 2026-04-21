# GraphAgent Skill 规则详细说明

本文档是 Compiler Skill 的深度参考。规则 ID 和定义见 `data/rules.yaml`（唯一数据源）。
本文档补充每条规则的**失效机制、检查方法、修复策略和示例**。

---

## 1. Frontmatter 规则 (F系列)

### F001: name 必须存在且符合 kebab-case

**检查逻辑**: `re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name)`

**错误示例**:
```yaml
name: My_Cool_Skill    # ❌ 含大写和下划线
name: visual extract v3 # ❌ 含空格
```

**正确示例**:
```yaml
name: visual-extract-v3 # ✅
```

### F002: description 必须存在，≤1024 字符

description 是 IDE 路由（Anthropic Skill 触发条件）和文档说明的关键字段。

### F005: context_mapping 表达式语法

支持三种语法：
- `{dot.path}` — 深度取值
- `$func({args})` / `$func('literal')` — 辅助函数调用
- 纯字符串 — 直接传递

**常见错误**:
```yaml
context_mapping:
  bad_expr: "${input.scene}"    # ❌ $ 和 {} 混用
  bad_quote: $func("arg")      # ❌ YAML 中双引号需要外层引号包裹
```

**正确写法**:
```yaml
context_mapping:
  good_path: "{input.scene.id}"
  good_func: "$format_data({input.scene})"
  good_literal: "$get_protocols('my_phase')"
```

### F006: context_mapping 禁止 $func() 语法（已废弃）

**失效机制**:
`$func()` 语法要求 framework 层（context_resolver）加载并执行 skill 专属业务代码（helpers.py）。
这违反了 framework/skill 分层原则：framework 层不应感知或执行 skill 的业务逻辑。

**正确模式：setup phase + script/ tools**

```
❌ 旧写法（已废弃）：
context_mapping:
  entities: "$format_entities({input.entity_registry})"
  hints: "$compute_continuity_hints({input.visual_assets}, ...)"

✅ 新写法：在 setup phase 中用 tool 准备 context
```

**SKILL.md 新写法：**
```yaml
# frontmatter - context_mapping 只做路径取值
context_mapping:
  scene_id: "{input.scene.scene_id}"
  scene_text: "{input.scene.raw_text}"
  # entity_registry 整体传入，由 setup phase 格式化
  entity_registry: "{input.entity_registry}"
  visual_assets: "{input.visual_assets}"
```

```xml
<node id="setup" depends_on="">
<phase_config>
name: setup
requires_llm: false
tools:
  - script.setup.prepare_visual_context
</phase_config>
</node>

<node id="scene_annotation" depends_on="setup">
<phase_config>
name: scene_annotation
tier: balanced
</phase_config>
<system_prompt>
已知实体：
{entity_summary}

连续性提示：
{continuity_hints}
</system_prompt>
</node>
```

**script/setup.py：**
```python
def prepare_visual_context(context: dict) -> str:
    """准备 scene_annotation 阶段所需的格式化上下文。"""
    registry = context.get("entity_registry") or {}
    assets = context.get("visual_assets") or {}
    nc = context.get("narrative_context") or {}

    # 格式化实体列表
    lines = []
    for eid, info in registry.items():
        if isinstance(info, dict):
            lines.append(f"- {eid}: {info.get('name', eid)} ({info.get('type', '')})")
    context["entity_summary"] = "\n".join(lines) or "（无已有实体）"

    # 提取连续性提示
    context["continuity_hints"] = _extract_continuity_hints(assets, nc)
    return "setup complete"
```

**双重职责（setup tool 同时供 agent 按需调用）：**

setup phase 中的 tool 函数同时应暴露给后续 LLM 阶段，供 agent 发现信息不足时主动补充数据：

```yaml
# scene_annotation 节点也注册相同工具
<phase_config>
name: scene_annotation
tier: balanced
tools:
  - script.setup.prepare_visual_context   # agent 若需重新获取可主动调用
  - script.analysis.get_entity_detail
</phase_config>
```

**修复策略：**
1. 删除 `context_mapping` 中所有 `$func()` 条目
2. 如只需路径取值（`{input.x.y}`），直接保留路径表达式
3. 需要数据变换的，在 graph 开头新增 `setup` 节点（`requires_llm: false`）
4. 把原 helpers.py 中的变换函数迁移到 `script/setup.py`（标准 tool 函数格式）
5. setup 函数写入 `context["key"]`，后续节点通过 `{key}` 占位符读取

---

## 2. Phase/Node 规则 (P系列)

### P003: 工具引用路径必须可解析

格式：`module.submodule.function_name`，最后一个 `.` 分隔模块路径和函数名。

解析步骤：
1. `script.continuity.set_directive` → 拆分为 `script.continuity` + `set_directive`
2. 转为文件路径 `{skill_dir}/script/continuity.py`
3. `importlib` 动态加载，取 `set_directive` 属性

**常见错误**:
```yaml
tools:
  - script/continuity/set_directive  # ❌ 用了斜杠
  - set_directive                    # ❌ 缺少模块路径
  - script.continuity                # ❌ 缺少函数名
```

### P006: 占位符必须在 context_mapping 中定义（最危险的静默失效）

**失效机制**:
引擎使用 `_safe_render_template` 进行正则替换 `\{(\w+)\}`。
如果 `{key}` 在 context 中不存在，它会被**原样保留**——用户看到的 Prompt 里会
出现字面量 `{protocols_entity}` 而不是实际的协议文本。
Agent 会把它当作普通文本处理，导致整个阶段的业务逻辑形同虚设。

**检查方法**:
1. 提取 `<system_prompt>` 和 `<user_prompt>` 中所有 `\{(\w+)\}` 匹配。
2. 过滤掉 JSON 模式（`{"` 开头的不算）。
3. 对比 `context_mapping` 的 key 集合。
4. 差集即为"未定义变量"。

**修复策略**:
1. 扫描 `<system_prompt>` 和 `<user_prompt>` 中所有 `{key}` 占位符。
2. 对比 `context_mapping` 已定义的 key。
3. 对于缺失的 key，根据名称推断其数据来源：
   - 以 `protocols_` 开头 → 添加 `$get_protocols_for_phase('phase_name')` 映射。
   - 以 `input.` 开头 → 确认 `io.inputs` 中是否有对应声明。
   - 其他 → 标记为需要开发者确认。

### P007: 严禁 JSON 与模板共存

**失效机制**:
虽然 `_safe_render_template` 不会匹配 `{"name": ...}`（因为 `"name"` 不是 `\w+`），
但以下情况仍然危险：
- `{name}` 在 JSON 上下文中出现（如 `[{name}, {age}]`）
- context 中恰好有 `name` 或 `age` 这种通用 key

**修复策略**:
1. 定位 `<system_prompt>` 中的 JSON 代码块（匹配 `{"` 模式）。
2. 将 JSON 内容抽离到 `data/` 目录下的独立文件。
3. 在 `context_mapping` 中新增映射：`json_example: "$load_file('data/xxx.md')"`。
4. 将原 Prompt 中的 JSON 替换为占位符。

### P008/P009: Graph 拓扑完整性

**P008 检查**: 所有 `depends_on` 引用必须指向已定义的 `<node id="...">`.
**P009 检查**: 对 `depends_on` 关系做拓扑排序，检测环。

### P010: LLM 阶段必须提及 finish_task

所有 LLM 阶段自动启用认知循环，引擎自动注入 `finish_task` 和 `update_working_memory` 工具。
但如果 prompt 中未明确要求 Agent 调用 `finish_task`，Agent 大概率会忽略它。

**最佳实践**: 在 `<system_prompt>` 的执行步骤最后一步写：
```
5. 完成后**必须调用 finish_task**，提供自检结论和证据。
```

---

## 3. Tool 规则 (T系列)

### T002/T003: docstring 即 Prompt 工程

LLM 决定是否调用一个工具，完全依赖 docstring 的第一段（映射为 tool description）。
Args 段的每个参数描述映射为 schema 中的参数 description。

详细规范和完整示例见 `tool_spec.md`。

---

## 4. 目录结构规则 (S系列)

### S001: references/ 中不得存在可执行脚本

`references/` 的定位是**规范文档**（被 Claude 按需加载、被注入提示词）。
可执行脚本（`.py`、`.sh`）必须放在 `script/` 中。

**判断方法**:
- 文件是否定义了可调用函数且被 `<phase_config>` 的 `tools:` 引用？→ 放 `script/`
- 文件是否是编写规范、协议、模板等参考资料？→ 放 `references/`，用 `.md` 或 `.yaml`

**修复策略**:
1. 如果 `.py` 文件内容仅为常量/示例/模板 → 转为 `.md` 文档，代码块用 markdown 包裹。
2. 如果 `.py` 文件包含可执行逻辑 → 移动到 `script/` 目录。

### S002: script/ 中的文件必须包含可调用函数

`script/` 的定位是**可执行代码**（被引擎动态导入）。
如果一个 `.py` 文件中只有常量定义或文档字符串而无任何 `def` 或 `class`，
它本质上是一份规范文档，应该放在 `references/` 中。

### S003: 规则只在 data/rules.yaml 定义一次

SKILL.md 不得内联规则表。如果 SKILL.md 中存在类似 `| F001 | ... |` 的规则表格，
说明规则定义被重复了，应删除 SKILL.md 中的表格，改为指向 `data/rules.yaml`。

### S004: helpers.py 已废弃

**失效机制**:
`helpers.py` 是旧架构（`$func()` 模式）的产物。它在 framework 层被加载执行，
导致 framework 与 skill 业务逻辑耦合。新架构规定：数据变换逻辑必须在 skill 层（setup phase 的 `script/` tools）完成，
framework 层只做纯路径取值。

**检查方法**: 扫描技能目录下 `helpers.py`、`tools/helpers.py`、`script/helpers.py` 是否存在。

**修复策略**:
1. 把 `helpers.py` 中的函数移到 `script/setup.py`（标准 tool 格式：有 docstring，返回 str）
2. 在 SKILL.md graph 开头新增 `setup` 节点（`requires_llm: false`）
3. 删除 `helpers.py` 文件
4. 删除 `context_mapping` 中对应的 `$func()` 条目

---

## 7. Framework/Skill 分层原则

> 核心规则：**framework 层不得包含 skill 专属业务逻辑**。

### 7.1 分层定义

| 层 | 包含 | 不包含 |
|----|------|--------|
| **Framework** (`context_resolver`, `harness`, `loader`, `io_manager`) | 路径取值、文件加载、模板渲染、编排 | 数据格式化、业务变换、领域概念 |
| **Skill** (`script/` tools, SKILL.md) | 所有业务逻辑、数据变换、领域知识 | framework 机制细节 |

### 7.2 context_mapping 规范

`context_mapping` 只允许 **路径表达式**，不允许函数调用：

```yaml
# ✅ 允许：从 io.inputs 做路径取值
context_mapping:
  scene_id: "{input.scene.scene_id}"
  scene_text: "{input.scene.raw_text}"
  entity_registry: "{input.entity_registry}"

# ❌ 禁止：函数调用（$func() 语法已废弃）
context_mapping:
  entities: "$format_entities({input.entity_registry})"
```

**原则**：context_mapping 是"io.inputs → context dict 的路径映射"，不是"数据变换管道"。

### 7.3 setup phase 模式

需要数据预处理时，在 graph 开头新增 `setup` 节点：

```
┌─────────────────────────────────────────────────────────┐
│  setup (requires_llm: false)                             │
│    tools: [script.setup.prepare_context]                 │
│    → 读取 context["entity_registry"]                     │
│    → 写入 context["entity_summary"]（格式化字符串）       │
│    → 写入 context["continuity_hints"]                    │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│  phase_1 (requires_llm: true)                            │
│    system_prompt: "已知实体：\n{entity_summary}"         │
│    → _safe_render_template 直接从 context 填值           │
└─────────────────────────────────────────────────────────┘
```

### 7.4 工具双重职责

setup 阶段的数据获取 tool 应同时注册到 LLM 阶段的 `tools`，供 agent 按需补充数据：

```yaml
<node id="phase_1" depends_on="setup">
<phase_config>
name: phase_1
tier: balanced
tools:
  - script.setup.get_entity_summary      # setup 准备的，agent 也可主动再调
  - script.setup.get_continuity_hints    # 同上
  - script.analysis.save_result         # 写操作 tool
</phase_config>
```

这样 agent 在发现 context 不足时，可以主动调用读取工具补充信息，而不是依赖 setup 阶段的一次性注入。

---

本 Skill 同时服务 GraphAgent Python 引擎和 Anthropic IDE 助手。

| 对比项 | GraphAgent | Anthropic | 兼容方式 |
|--------|-----------|-----------|---------|
| Frontmatter `name` | kebab-case | kebab-case | 完全相同 |
| Frontmatter `description` | 功能描述 | 功能 + 触发条件 | 写成 Anthropic 风格（含触发词），GraphAgent 也能用 |
| 额外 frontmatter | `type`, `io`, `context_mapping` | 被忽略 | GraphAgent 专属字段不影响 Anthropic 解析 |
| Body XML 标签 | 引擎正则提取 | Claude 全文阅读理解 | 一份内容两个读者各取所需 |
| `references/` | 引擎忽略 | Claude 按需加载 | Anthropic 的渐进式披露 |
| `script/` | 引擎动态导入执行 | Claude 作为代码上下文阅读 | 各走各的路径 |
| `data/` | 引擎可读取 | Claude 可读取 | 共享的结构化数据源 |

---

## 6. Anthropic Skill 兼容性规则 (A系列)

> 参考: *The Complete Guide to Building Skills for Claude* (Anthropic 2026)
> Skills 可跨 Claude.ai、Claude Code、API 三端运行，以下规则确保兼容性。

### A001: description 必须包含 WHAT + WHEN

**失效机制**:
Anthropic 平台用 `description` 字段决定是否自动加载 Skill。如果 description 只说"做什么"但
不说"什么时候触发"，Skill 可能在用户需要时不被加载。

**好的 description**:
```yaml
description: >
  严格检查、自动修复和生成 GraphAgent Skills 与 Tool scripts。
  当用户创建、修改或审查 skills/**/SKILL.md 或 script/*.py 时使用。
  当遇到 SkillLoadError、SkillCompilationError、模板渲染失败等运行时错误时使用。
  当用户说"检查 skill"、"lint skill"、"fix skill"、"创建新 skill"时使用。
```

**坏的 description**:
```yaml
description: 检查和修复 GraphAgent Skills。  # ❌ 缺少触发条件
description: Helps with skills.              # ❌ 太模糊
```

**检查方法**: description 中应包含"当...时使用"、"Use when"、"Use for" 等触发词模式。

### A002: frontmatter 禁止 XML 角括号

**失效机制**:
Anthropic 平台将 frontmatter 注入 Claude 的 system prompt。`< >` 可能被解释为指令注入。

**检查方法**: 扫描 frontmatter 原始 YAML 文本，检测 `<` 或 `>` 字符。

### A003: Skill 目录内不得包含 README.md

**失效机制**:
Anthropic 规范明确要求：所有文档放在 SKILL.md 或 references/ 中。
README.md 是用于 GitHub 仓库级别的人类可读文档，不应出现在 Skill 目录内。

**修复策略**: 将 README.md 内容合并到 SKILL.md 或移动到 references/。

### A004: name 不得使用保留词

**失效机制**:
Anthropic 保留了 `claude` 和 `anthropic` 命名空间。包含这些词的 Skill 名称会被平台拒绝。

**检查方法**: `"claude" not in name.lower() and "anthropic" not in name.lower()`

### A005: SKILL.md 大小控制

**失效机制**:
Anthropic 使用三级渐进式披露：frontmatter（始终加载）→ SKILL.md body（触发时加载）→ references/（按需加载）。
过大的 SKILL.md 会增加 token 消耗，降低响应速度。官方建议控制在 5000 词以内。

**修复策略**: 将详细参考内容（规则表、修复策略、完整示例等）移到 references/ 目录下。
