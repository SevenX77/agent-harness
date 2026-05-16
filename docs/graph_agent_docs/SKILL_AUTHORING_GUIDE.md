# SKILL_AUTHORING_GUIDE (V2.1)

本指南说明如何为 V2.1 版本的 `graph_agent` 编写一个可编译、可迁移、可审计的 skill。V2.1 是 schema 大版本升级, 一刀硬切, 不向后兼容 schema 2.0 — 旧根 `SKILL.md` 单文件写法在 V2.1 内核会直接 FATAL 拦截。

适用版本: **V2.1**。如果你在 main 分支看到的还是单文件 `SKILL.md` skill, 那是 schema 2.0, 跟本指南不兼容; V2.1 cutover PR 合并 (T3.3) 后, 仓内 in-scope 11 份 skill 都按本指南布局。

## 0. V2.1 vs schema 2.0 快速对照

| 维度 | schema 2.0 (V1) | V2.1 |
|---|---|---|
| skill 单位 | 单个 `SKILL.md` 文件 | 一个目录树 (`<skill_root>/`) |
| 整图拓扑 | 单文件内 `<node>` 或 `<phase>` 标签 | 独立 `<root>/GRAPH.md` (manifest) |
| 不同 phase 区分 | YAML `mode: agent/logic/subgraph` 字段 | **物理文件名** (`LOGIC.md` / `SUBGRAPH.md` / `SKILL.md`) + `mode` 双校验 |
| IO 声明 | YAML `io:` 字段 | 独立 `<root>/io/inputs.json` + `outputs.json` (JSON Schema) |
| Python 副作用 | `tools/*.py` 接 `ctx` | `phases/<name>/actions/*.py` 读写黑板; `tools/*.py` 不接 context |
| 退出条件 | 静态 `W-FINISH-TASK-VISIBILITY` 告警 | `<exit_contract>` + 每轮 ReAct 末尾 User Message 注入 |
| 兼容路径 | — | 无 (一刀硬切, R0 决策 3) |

## 1. V2.1 skill 物理布局

一个 V2.1 skill 是一个**目录**, 包含以下文件 (路径相对 `<skill_root>/`):

```
<skill_root>/
├── GRAPH.md                          # 必须. 整图 manifest. 一个 skill 有且仅有一份
├── io/
│   ├── inputs.json                   # 必须. JSON Schema, 描述 runtime input 契约
│   └── outputs.json                  # 必须. JSON Schema, 描述 artifact / context 输出契约
└── phases/                           # 必须. 至少含一个 phase 子目录
    ├── <phase_a>/
    │   ├── LOGIC.md                  # 三选一 (LOGIC / SUBGRAPH / SKILL), 决定 phase 角色
    │   ├── actions/*.py              # 可选. 仅 LOGIC phase 有意义 (黑板读写)
    │   └── tools/*.py                # 可选. LangChain StructuredTool (天然 tunnel vision)
    ├── <phase_b>/
    │   └── SUBGRAPH.md               # 子图委派
    └── <phase_c>/
        ├── SKILL.md                  # LLM ReAct
        └── tools/*.py
```

**硬规则** (违反 → 编译期 FATAL):

- 根目录**只能有** `GRAPH.md`, 不能出现 `SKILL.md` (那是 schema 2.0 残留)
- `phases/*/` 子目录里**只能有** `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 之一, 不能出现 `GRAPH.md` (manifest 不允许嵌套)
- `phases/*/{LOGIC,SUBGRAPH,SKILL}.md` 的 XML body 内**不能出现** `<phase>` / `<depends_on>` / `<edge>` 等整图拓扑标签 (拓扑只活在 `GRAPH.md`)
- `io/inputs.json` 跟 `outputs.json` 缺一不可 (即使没输入也要写 `{"type": "object", "properties": {}}`)

## 2. GRAPH.md (整图 manifest)

`GRAPH.md` 只承载三类信息: **整图元数据** + **IO 契约 reference** + **phase 拓扑**。不写 prompt, 不参与 AST 节点构建。

### 2.1 frontmatter 字段

```yaml
---
name: hello-world                    # 必须. skill 名 (kebab-case)
description: 当 ... 时使用            # 必须. 用途描述
version: 0.1.0                       # 可选. semver
io:
  inputs: io/inputs.json             # 必须. 指向 io/inputs.json 相对路径
  outputs: io/outputs.json           # 必须. 指向 io/outputs.json 相对路径
---
```

### 2.2 XML body: phase 拓扑

`GRAPH.md` 的 XML body **只能有** `<phase>` 标签 (列出所有 phase + 拓扑) 跟 `<ref>` 标签 (指向 phase 子目录里的 LOGIC/SUBGRAPH/SKILL.md):

```xml
<phase id="prep">
<ref path="phases/prep/LOGIC.md" />
</phase>

<phase id="draft" depends_on="prep">
<ref path="phases/draft/SKILL.md" />
</phase>

<phase id="review" depends_on="draft">
<ref path="phases/review/SKILL.md" />
</phase>
```

**`<phase>` 标签字段**:

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | phase 唯一标识 (kebab-case 或 snake\_case), 跟 `phases/<id>/` 目录名一致 |
| `depends_on` | 见 §3 | 上游 phase id 列表 (空白或逗号分隔); 首个 phase 可省略, 额外 entry 必须显式 `depends_on=""` |

**`<ref>` 标签字段**:

| 字段 | 必填 | 说明 |
|---|---|---|
| `path` | 是 | 指向 `phases/<id>/{LOGIC,SUBGRAPH,SKILL}.md` 三选一 |

## 3. `depends_on` DSL 详解 (T0.3 PM 决策)

### 3.1 起点判定规则

1. **首个 `<phase>` 标签**: **可省略** `depends_on` 属性 → 隐式 entry (起点)
2. **额外 entry**: 必须**显式** 写 `depends_on=""` (空字符串) 才被认作 entry
3. **非首个 phase**: 缺 `depends_on` 属性 → `[F-v21-graph]` FATAL (拒绝隐式推导)

### 3.2 分隔符

非起点 phase 的 `depends_on` 可以列**多个**上游, 支持两种分隔符 (混用也 OK):

```xml
<phase id="merge" depends_on="prep_a prep_b">         <!-- 空白分隔 -->
<phase id="merge" depends_on="prep_a,prep_b">         <!-- 逗号分隔 -->
<phase id="merge" depends_on="prep_a, prep_b prep_c"> <!-- 混用 -->
```

### 3.3 拓扑禁区 (全部 FATAL `[F-v21-graph]`)

- **self-loop**: `depends_on` 含自己的 id (`<phase id="a" depends_on="a">`)
- **循环依赖**: a → b → a 这种环
- **孤儿 phase**: 完全跟其他 phase 没有任何无向连通性 (既不依赖任何 phase, 也没被任何 phase 依赖, **且不是起点**)
- **重复 phase id**: 同一个 id 在 `<phase>` 标签里出现两次
- **src 缺失**: `<ref path="phases/foo/SKILL.md">` 但 `phases/foo/` 目录不存在或 SKILL.md 不存在
- **未声明的上游**: `depends_on="x"` 但 manifest 里没有 `<phase id="x">`

### 3.4 示例 (a): 单入口 chain

```
prep → draft → review
```

```xml
<phase id="prep">                                    <!-- 隐式 entry -->
<ref path="phases/prep/LOGIC.md" />
</phase>

<phase id="draft" depends_on="prep">
<ref path="phases/draft/SKILL.md" />
</phase>

<phase id="review" depends_on="draft">
<ref path="phases/review/SKILL.md" />
</phase>
```

### 3.5 示例 (b): 多起点汇合

```
prep ──┐
        ├──→ draft
warmup ─┘
```

```xml
<phase id="prep">                                    <!-- 隐式 entry (首个) -->
<ref path="phases/prep/LOGIC.md" />
</phase>

<phase id="warmup" depends_on="">                    <!-- 必须显式 depends_on="" 才算 entry -->
<ref path="phases/warmup/LOGIC.md" />
</phase>

<phase id="draft" depends_on="prep warmup">          <!-- 汇合 -->
<ref path="phases/draft/SKILL.md" />
</phase>
```

如果 `warmup` 没写 `depends_on=""`, 会被识别为非起点 → 缺 `depends_on` 属性 → FATAL。

## 4. phase 子目录

一个 `phases/<id>/` 目录有且只有 **`LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 三选一** (即 phase 的角色三选一)。

### 4.1 `LOGIC.md` (Python 确定性节点)

```md
---
mode: logic                          # 必须. 文件名 LOGIC.md + mode: logic 双校验
name: prep
description: 准备阶段, 把章节文本切块
---

<execute>
<ref path="actions/prepare_chunks.py" function="prepare_chunks" />
</execute>
```

- `<execute>` 标签声明本 phase 执行的 Python action 函数 (从 `actions/*.py` import)
- **不允许**: `<system_prompt>`, `<role>`, `<user_prompt>`, `<exit_contract>` 等 LLM-only 标签
- 违反 → `[F-v21-purity]` FATAL

### 4.2 `SUBGRAPH.md` (子图委派节点)

```md
---
mode: subgraph                       # 必须. 文件名 SUBGRAPH.md + mode: subgraph 双校验
name: render
description: 委派给独立的渲染 skill
---

<subgraph_target path="../../subskills/render/GRAPH.md" />

<context_bridge>
  <inputs>
    <map from="plan_result" to="render_input" />
  </inputs>
  <outputs>
    <map from="render_output" to="final_render" />
  </outputs>
</context_bridge>
```

- `<subgraph_target>` 指向另一个 skill 的 `GRAPH.md` (绝对路径或相对当前 phase 子目录)
- `<context_bridge>` 显式声明父子 blackboard key 映射 (唯一允许显式 mapping 的地方, Axiom 4)
- **不允许**: `<system_prompt>`, `<role>`, `<python_callable>`, `<execute>` 等
- 违反 → `[F-v21-purity]` FATAL

### 4.3 `SKILL.md` (LLM ReAct 节点)

```md
---
mode: agent                          # 必须. 文件名 SKILL.md + mode: agent (或 llm) 双校验
name: draft
description: 起草段落
tier: balanced                       # 可选. llm_roles.yaml 角色名, 默认 balanced
tools:                               # 可选. phase-local 或 skill-level tools
  - tools.draft.collect_context
  - tools.draft.fetch_reference
max_iterations: 20                   # 可选. ReAct 最大循环次数, 默认 20
max_nudges: 1                        # 可选. 文本偏航提醒次数, 默认 1
---

<role>
你是一名资深内容编辑, 擅长把 outline 扩写成完整段落。
</role>

<system_prompt>
基于上游 `prep` phase 产出的 chunks, 起草本章节的初稿。
要求: 每个 chunk 一段, 段落之间留空行。
完成后调用 finish_task(markdown="...") 提交。
</system_prompt>

<user_prompt>
本章节 chunks:
{chunks}
</user_prompt>

<exit_contract>
当你完成所有 chunk 起草且产出符合下面 schema 时, 调用 finish_task:

```json
{
  "draft_markdown": "string (必填, 完整起草内容, Markdown 格式)",
  "chunk_count": "number (必填, 起草的 chunk 数, 必须等于上游 chunks 长度)"
}
```

不允许跳过任何 chunk; 不允许返回纯文本 (必须 Markdown); 不允许 finish_task 之前调用其他工具。
</exit_contract>
```

- **必须有**: `<role>`, `<system_prompt>`, `<exit_contract>`
- **可选**: `<user_prompt>` (内含 `{key}` 模板会从黑板 / runtime_inputs 注入)
- **不允许**: `<python_callable>` / `<execute>` / Python 副作用块 → `[F-v21-purity]` FATAL

### 4.4 `actions/*.py` (黑板读写 Python 脚本)

仅 `LOGIC.md` phase 的子目录可以有 `actions/`。函数签名约定:

```python
# phases/prep/actions/prepare_chunks.py
from graph_agent.cognitive.context_facade import Context

def prepare_chunks(context: Context, chunk_size: int = 500) -> None:
    """切块上游传入的章节文本, 写到黑板供下游 phase 消费。"""
    raw_text = context.get("raw_text")
    chunks = [raw_text[i:i+chunk_size] for i in range(0, len(raw_text), chunk_size)]
    context.set("chunks", chunks)
```

- **必须**接 `context: Context` 作为第一参数 (框架提供的全局黑板门面)
- 通过 `context.get(key)` / `context.set(key, value)` 读写黑板
- **禁止** 本地写盘 (`open(..., 'w')` / `Path.write_*` / `Path.touch`) — Axiom 6 静态扫描 enforce, 命中 → `[F-v21-stateless]` FATAL
- 所有产出必须通过 `io/outputs.json` 声明 + 框架 `IOManager` 落盘

### 4.5 `tools/*.py` (LangChain StructuredTool, LLM 调)

仅 `SKILL.md` phase 的子目录 (或 `<skill_root>/tools/` 跨 phase 共享) 可以有 `tools/`。函数签名约定:

```python
# phases/draft/tools/collect_context.py
def collect_context(scene_id: str, depth: int = 2) -> str:
    """收集 scene 的上下文片段。LLM 调用工具。"""
    # ... 业务逻辑 ...
    return "已收集 N 个片段..."
```

**关键约束** (R1.5 编译期静态扫描 enforce):

- **不接** `context` / `ctx` / `state` / `blackboard` 参数 — 这些参数名命中即 `[F-v21-purity]` FATAL
- 函数签名只暴露**业务参数** (LLM 看到的 schema)
- 同样**禁止本地写盘** (Axiom 6)

详 `TOOL_DEVELOPMENT_GUIDE.md`。

## 5. `<exit_contract>` 详解 (R1.4)

`<exit_contract>` 是 SKILL phase 的**强制退出条件声明**。V2.1 认知中间件会在每轮 ReAct 后, 把这个标签内的**全部文本**作为一条独立 User Message 追加到 LLM messages 列表末尾, 利用 LLM recency bias 把退出条件钉在 attention 最高位置。

### 5.1 写法

- 写在 `phases/<id>/SKILL.md` XML body 里
- 内容是**自然语言描述退出条件** + (推荐) JSON Schema 形式的产出结构
- 每轮 ReAct 都看得到, 不要怕重复啰嗦

### 5.2 推荐结构

```xml
<exit_contract>
当你 ... (描述任务完成的客观判定标准) 时, 调用 finish_task:

```json
{
  "field_a": "type (描述)",
  "field_b": "type (描述)"
}
```

**禁止**:
- 跳过 ... (列出常见跑偏)
- 在 finish_task 之前调用 ...
- 返回 ...

**允许重试场景**: 如果 ... 你可以 ...
</exit_contract>
```

### 5.3 验收 (T1.1 DoD)

- 每轮 ReAct 发往 LLM 的 `messages` 列表中**最后一条** = `role=user` 且文本末端含 `<exit_contract>` 全文 (机器可断言)
- 长 System Prompt 场景 (>4000 tokens) e2e 不再触发 `W-FINISH-TASK-VISIBILITY` 告警

## 6. `finish_task(markdown="...")` 用法 (R1.7)

V2.1 SKILL phase 的退出工具签名:

```python
finish_task(markdown: str) -> None
```

- LLM 传入 **Markdown 字符串** (不是 dict / JSON)
- 框架内部用 `cognitive/md_to_json.py` 解析 Markdown → Python dict
- 解析后跟 `<exit_contract>` 里声明的 JSON Schema 比对, 验证字段类型 / required
- 解析失败 (残缺标题 / 不闭合代码块 / 字段类型偏差) → **静默拉起** `skills/builtin/md-patch/` agent 修复
- md-patch 修复失败 → 返回结构化错误, ReAct 继续重试

### 6.1 LLM 提交 Markdown 的推荐结构

```markdown
## draft_markdown

第一章 起草内容...

第二章 起草内容...

## chunk_count

3
```

`md_to_json` 会按二级标题 (`## field_name`) 切片, 标题下的内容作为字段值。简单类型 (number / boolean) 直接转换, 复杂类型 (string / object / array) 保留原文或按代码块 JSON 解析。

### 6.2 不要做的事

- 不要在 `finish_task` 之前 / 之后调用其他工具 — `<exit_contract>` 应当声明禁止
- 不要返回纯 dict / 不带 Markdown 包裹的 JSON — V2.1 强制 Markdown 进 md2json 兜底

## 7. `io/inputs.json` + `io/outputs.json` (R1.1)

V2.1 把 IO 契约从 YAML 字段移到独立 JSON Schema 文件, 让 LSP / IDE / studio 前端可以 import schema 校验。

### 7.1 `io/inputs.json`

声明运行时输入 (`run_skill(skill_root, inputs={...})` 的 `inputs` 形状):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "raw_text": {
      "type": "string",
      "description": "章节原文"
    },
    "target_language": {
      "type": "string",
      "enum": ["zh-CN", "en-US"],
      "default": "zh-CN"
    }
  },
  "required": ["raw_text"]
}
```

### 7.2 `io/outputs.json`

声明产出 (写到 artifact 或 context 的 key + 类型):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "draft_markdown": {
      "type": "string",
      "description": "起草内容",
      "x-target": "artifact"
    },
    "chunks": {
      "type": "array",
      "items": {"type": "string"},
      "x-target": "context"
    }
  },
  "required": ["draft_markdown"]
}
```

`x-target` 是 V2.1 扩展, 取值:
- `artifact`: 走 `IOManager` 落盘到 `{workspace_root}/runs/{skill_id}/{run_id}/`
- `context`: 留在 LangGraph state 给下游 skill 消费

### 7.3 校验时机 (T0.2)

- 编译期: `GRAPH.md` 的 `io` 字段引用的 inputs.json / outputs.json 必须存在, 必须是合法 JSON Schema
- 运行期: `run_skill(...)` 入口校验 `inputs` 字典符合 inputs.json schema, 不符 → `[F-v21-io]` 拒绝执行
- 退出期: skill 完成时校验产出 dict 符合 outputs.json schema, 不符 → `[F-v21-io]` 报错

## 8. 完整 hello-world 示例 (T2.8 DoD)

下面这个 hello-world 可以被 V2.1 parser 完整解析, 等价于 `skills/hello-world/` 现役迁移版本。

**目录结构**:

```
skills/hello-world/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    └── greet/
        └── SKILL.md
```

**`skills/hello-world/GRAPH.md`**:

```md
---
name: hello-world
description: 当需要快速验证 V2.1 内核装配链路时使用。
version: 1.0.0
io:
  inputs: io/inputs.json
  outputs: io/outputs.json
---

<phase id="greet">
<ref path="phases/greet/SKILL.md" />
</phase>
```

**`skills/hello-world/io/inputs.json`**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "user_name": {
      "type": "string",
      "description": "要打招呼的用户名"
    }
  },
  "required": ["user_name"]
}
```

**`skills/hello-world/io/outputs.json`**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "greeting": {
      "type": "string",
      "description": "生成的问候语",
      "x-target": "artifact"
    }
  },
  "required": ["greeting"]
}
```

**`skills/hello-world/phases/greet/SKILL.md`**:

```md
---
mode: agent
name: greet
description: 用 LLM 生成一句问候
tier: fast
---

<role>
你是一个友好的助手, 用一句话生成针对特定用户的问候。
</role>

<system_prompt>
基于 user_name, 生成一句不超过 30 字的中文问候语。

完成后调用 finish_task(markdown="...") 提交。
</system_prompt>

<user_prompt>
请给 {user_name} 生成问候语。
</user_prompt>

<exit_contract>
当你生成完整的问候语后, 调用 finish_task, Markdown 内容如下:

```markdown
## greeting

(你生成的中文问候语, 不超过 30 字)
```

**禁止**:
- 返回多于一句
- 超过 30 字
- 在 finish_task 之前调用任何其他工具
</exit_contract>
```

## 9. 提交前 checklist

- [ ] 目录结构: `<root>/GRAPH.md` + `<root>/io/inputs.json` + `<root>/io/outputs.json` + `<root>/phases/<id>/`
- [ ] `GRAPH.md` 的 `io.inputs` / `io.outputs` 字段指向真实存在的 JSON Schema 文件
- [ ] 所有 `<phase id="x">` 引用的 `<ref path="phases/x/{LOGIC,SUBGRAPH,SKILL}.md">` 文件存在
- [ ] 文件名跟 frontmatter `mode` 一致 (LOGIC.md ↔ logic, SUBGRAPH.md ↔ subgraph, SKILL.md ↔ agent/llm)
- [ ] 拓扑无 self-loop / 循环 / 孤儿 / 重复 id
- [ ] 非首个 phase 全部显式声明 `depends_on=...` (或显式 `depends_on=""` 作额外起点)
- [ ] SKILL phase 含 `<role>` + `<system_prompt>` + `<exit_contract>` 三标签
- [ ] LOGIC phase 不含 `<system_prompt>` / `<role>` / `<user_prompt>` / `<exit_contract>`
- [ ] SUBGRAPH phase 不含 `<system_prompt>` / `<role>` / `<execute>`
- [ ] `tools/*.py` 函数签名不含 `context` / `ctx` / `state` / `blackboard` 参数
- [ ] `actions/*.py` 跟 `tools/*.py` 都不写本地文件 (无 `open('w')` / `Path.write_*`)
- [ ] `compile_skill(skill_root)` 无 FATAL
- [ ] `tier` 在 `config/llm_roles.yaml` 有定义

## 10. 从 schema 2.0 迁移

V2.1 cutover 期间, in-scope 11 份现役 skill 走以下流程 (Q-3 决议):

### 10.1 Codemod dry-run (T0.4)

`codemod` 脚本读旧 `SKILL.md` 单文件, 生成 V2.1 雏形:

- 旧 `phases:` 数组 → 每个 phase 生成 `phases/<name>/SKILL.md` (默认 LLM ReAct, 后人工拆 LOGIC/SUBGRAPH)
- 旧顶层 metadata → 写到 `GRAPH.md` frontmatter
- 旧 `io:` 字段 → 拆出 `io/inputs.json` + `io/outputs.json` 雏形
- 旧 `<exit_contract>` (如有) → 保留到对应 SKILL phase

**dry-run 含义**: codemod 只产**候选文件**, 自动注入 `<!--TODO: CODEMOD_REVIEW-->` 注释标记需要人工审查的复杂 XML 节点。CI 扫描 `phases/**/*.md` 命中此标记 → FAIL block T3.3 cutover。

### 10.2 人工审查 (Q-3 决议留人)

复杂 prompt 拆分 (`<role>` / `<system_prompt>` / `<exit_contract>` 等 XML 段) 是人工活儿, codemod 不做。dual-run shadow 比对脚本 (T3.3) 跑迁移前后语义等价性, Tier 1 (`text-segmentation` / `story-deconstruction`) 强制跑。

### 10.3 停摆窗口 (R-6 风险 + Q-5 决议)

cutover 期间 in-scope 11 份 skill 全数 break by design, 用户业务即时停摆。容忍 3-5 天, 高频先迁:

- **Tier 1** (优先): `text-segmentation`, `story-deconstruction`
- **Tier 2**: `batch-analysis`, `event-extraction`, `global-synthesis`, `producer`, `product-manual`
- **Tier 3**: `hello-world`, `producer/review` 内化, `examples/broken-fixtures/...`, `examples/subgraph-sample/...`

迁移过程跟单 skill rollback CI SOP 见 `.kiro/specs/graph-agent-v2.1/tasks.md` T3.3。

## 11. 参考资料

- `ARCHITECTURE.md` — V2.1 架构全貌 + 6 红线映射 + LangGraph 装配链路
- `TOOL_DEVELOPMENT_GUIDE.md` — Tools vs Actions 边界 + 静态扫描规则
- `CORE_ARCH_PRINCIPLES.md` — 6 红线源文档
- `.kiro/specs/graph-agent-v2.1/requirements.md` — R1.1-R1.7 + Q-1..Q-7 决议
- `skills/hello-world/` — V2.1 cutover 后的最小工作样板
- `skills/examples/subgraph-sample/story-deconstruction/` — V2.1 cutover 后的子图样板
