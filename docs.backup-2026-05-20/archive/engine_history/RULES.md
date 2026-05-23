# V2.1 Engine Rules: SKILL Schema 与架构规范

## 1. 目录 Layout 规范
引擎强校验目录完整性：
```text
<skill_name>/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    └── <phase_id>/
        ├── SKILL.md (或 LOGIC.md / SUBGRAPH.md)
        ├── actions/          # (logic 专享)
        │   └── my_actions.py 
        └── subskills/        # (subagent 引用的工作区)
            └── <subagent_name>/
```

## 2. GRAPH.md 顶层规范
`GRAPH.md` frontmatter 与 XML 标签支持字段全集：
```xml
---
schema_version: "2.1"          # 必须为 2.1
name: my-business-skill
description: "Metadata description"
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />

<!-- 拓扑声明区 -->
<phase id="init" src="phases/init" depends_on="" />
<phase id="process" src="phases/process" depends_on="init" />
```

## 3. Phase SKILL.md 三种 Mode 规范

### `mode: logic` (在 LOGIC.md 中)
声明执行 Python callable。
```yaml
---
mode: logic
name: logic-phase
actions:
  - module: actions.helpers
    function: run_logic
---
```

### `mode: skill` (在 SKILL.md 中)
核心驱动器，通过配置连接工具。
```yaml
---
mode: skill
name: llm-agent
phase_config:
  tools: [read_file, write_file]
  tier: 1
  subagent_enabled: false # (废弃的旧开关，不要与 subagents 列表混淆)
  subagents:
    - name: extract_expert
      path: subskills/extract_expert
      description: "Extracts key data from raw text."
---
```

### `mode: subgraph` (在 SUBGRAPH.md 中)
硬链接至其他完整的图拓扑，可相对路径。
```yaml
---
mode: subgraph
name: sub-validator
subgraph: ../../shared/common-validator
---
```

## 4. Subagent 机制 (v2.1-subagent 规范)
作为 V2.1 高级扩展包，使用 Subagent 必须遵循：
- **声明格式**: 必须在 `phase_config.subagents` 列表中显式给出 `[{name, path, description}]`。
- **Schema 强绑定**: 目标 path 指向的 skill 必须存在 `io/inputs.json`。Loader 在编译期将其转换为 Pydantic Model，缺少则 Fatal。
- **Tool 自动生成**: 引擎自动装配出 `call_subagent_<name>` 工具并悄无声息地挂载至此阶段的 Tools 列表中。
- **并发与容错**: 工具签名强制为 `inputs=[N]`。引擎使用 LangGraph `Send` 并发执行。如果 LLM 传参非预期结构，启动 **Informed Retry (上限 10 次)** 给 LLM 错误反馈。
- **嵌套硬锁**: 原型期施加 Max Depth = 1 校验（详情参阅 [[GUIDE]]）。

## 5. IO Schema 
`io/inputs.json` 和 `io/outputs.json` 必须提供标准 JSON Schema（兼容 Draft 7）。如果留空必须提供 `{}`。

## 6. Context (State Flow)
- 默认各阶段的产出数据会自动并入全局 `data` state (字典合并)。
- 阶段之间通过读写 state 共享记忆。如果需要改变映射关系，可通过在代码或配置层面增加 `context_mapping` 来实现强隔离。
