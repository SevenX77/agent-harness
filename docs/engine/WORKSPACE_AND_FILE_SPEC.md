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

## 1. `.workspace` 目录详细结构与 Init 模板

任何在 Studio 中被打开的文件夹，要被系统承认为一个合法的 Agent Skill，必须拥有明确的文件结构。
当新建 Skill 时，系统会初始化如下标准的模板结构：

```text
my_awesome_skill/
├── SKILL.md                 # 【必须】主入口文件，核心的声明式编排拓扑
├── .workspace/              # 【系统生成】存放中间态缓存、临时 Trace 和本地 SQLite DB
│   └── compiler_cache.json
├── script/                  # 【建议】自定义 Python Tool 和 Validator 的存放目录
│   ├── __init__.py
│   ├── my_tools.py
│   └── schema_validators.py
├── references/              # 【建议】静态知识存放（如 Markdown 规则，会被注入系统提示词）
│   └── persona_guide.md
└── golden/                  # 【隔离】持久化的 Golden Baseline 数据隔离存储
    └── 2026-05-19-perfect-run.json
```

## 2. `SKILL.md` 完整语法规范

文件虽然采用 Markdown 后缀，但其核心编排逻辑必须由严格的 XML 标签来包裹，配合可选的 Markdown 文本供人类阅读：

```markdown
<!-- Frontmatter (可选，用于被外部包管理器索引) -->
---
skill_version: 1.0.0
author: PM_Team
---

<metadata>
  <name>ContentSummarizer</name>
  <type>graph</type>
</metadata>

<io>
  <input name="raw_article" type="string" />
  <output name="summary_result" type="json" />
</io>

<phases>
  <!-- 定义一个具体的执行阶段 -->
  <phase id="summarize_step" type="agent">
    <inputs>
      <input source="raw_article" target="article_text" />
    </inputs>
    <prompt>
      <system>You are an expert summarizer. Read the following rules: {file:references/persona_guide.md}</system>
      <user>Please summarize: {article_text}</user>
    </prompt>
    <tools>
      <tool>script.my_tools.fetch_webpage</tool>
    </tools>
    <outputs>
      <output source="agent_reply" target="summary_result" />
    </outputs>
  </phase>
</phases>
```

## 3. Python 工具函数挂载与开发规范

挂载在 `<tools>` 下的自定义 Python 脚本函数，必须遵守极为严格的签名契约。Engine 使用反射和 AST 分析将其注册为大模型工具。

- **必须带 Type Hints**: 每一个参数和返回值，都必须标注清晰的类型（如 `str`, `int`, `pydantic.BaseModel`）。
- **必须带 Docstring**: 引擎会将 Docstring 提取为向大模型解释“工具用途”的 `description`。没有注释的工具会被拒绝。

```python
# 规范的 Tool 开发示例 (位于 script/my_tools.py)
def fetch_webpage(url: str) -> str:
    """
    Fetches the textual content of a given URL.
    Use this tool when you need real-time data from the web.
    
    Args:
        url: The full HTTP URL to fetch.
    """
    return "Content of the webpage..."
```

## 4. 强制 Compile 编译检查范围

**PM 的核心关切**：文件的缺失或结构错误不应该等到运行时才崩溃，必须在 Compile 阶段直接阻断。
当调用 `compile_skill()` 时，检查器 (Compiler) 必须执行以下针对目录和文件的检查项：

1. **必选文件检查**:
   - 检查根目录下是否存在 `SKILL.md`。如果缺失，返回 `ERR_MISSING_ENTRYPOINT`。
2. **外部文件引用检查 (Reference Check)**:
   - 扫描 `SKILL.md` 中诸如 `{file:references/persona_guide.md}` 的标签。
   - 在 OS 层面查验相对路径的文件是否存在，能否正常读取。如果文件不存在，返回 `ERR_BROKEN_REFERENCE_LINK`。
3. **工具函数挂载检查 (Tool Import Check)**:
   - 解析 `<tool>` 标签内的字符串（例如 `script.my_tools.fetch_webpage`）。
   - 尝试动态 Import 该模块，并验证函数签名。如果模块找不到或函数缺少 Docstring，返回 `ERR_INVALID_TOOL_SIGNATURE`。
4. **内部状态流转与拓扑环路校验**:
   - 如果发生未声明变量使用或出现无限死循环，返回 `ERR_TOPOLOGY_VIOLATION`。

通过这套机制，`.workspace` 的目录树合法性被彻底纳入了安全网。

## 相关 Spec
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/README.md)
