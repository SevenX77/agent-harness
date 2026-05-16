# TOOL_DEVELOPMENT_GUIDE (V2.1)

本指南说明如何为 V2.1 版本的 `graph_agent` 编写工具 (Tools) 跟 actions。V2.1 引入 **Tools vs Actions 物理隔离** (R1.5) — 两类脚本职责不同、物理路径不同、context 访问权限不同, 编译期静态扫描 enforce, 不允许混用。

适用版本: **V2.1**。schema 2.0 (V1) 时代的"工具函数接 `ctx` 参数读写黑板"这种写法在 V2.1 是**违规**, 必须按本指南拆 Action / Tool。

## 0. V2.1 关键变化: Tools vs Actions 物理隔离

| 维度 | Tools | Logic Actions |
|---|---|---|
| **直觉**: 谁调? | LLM 在 ReAct 循环里调 | 框架在 LOGIC phase 里 import + 调 |
| **物理位置** | `<root>/tools/*.py` (跨 phase) 或 `<root>/phases/<id>/tools/*.py` (phase local) | `<root>/phases/<id>/actions/*.py` (绑定 LOGIC phase) |
| **绑定标签** | `SKILL.md` frontmatter `tools:` | `LOGIC.md` `<execute>` 标签 `<ref function="...">` |
| **包装机制** | LangChain `StructuredTool.from_function` (type-hint binding) | 直接 Python import + 调用 |
| **Context 访问** | **不接 context** — 函数签名不许出现 `context` / `ctx` / `state` / `blackboard` | **必接** `context: Context` 作为第一参数 |
| **黑板读写** | **不允许** — Tool 看不到黑板, 也写不进去 | **专属权限** — `context.get(key)` / `context.set(key, value)` |
| **可见 schema** | LLM 看到函数业务参数 (LangChain 自动从 type-hint 生成 JSON Schema) | LLM 看不到 — Action 是后台脚本 |
| **副作用文件 IO** | **禁止本地写盘** (Axiom 6) | 同样**禁止本地写盘** (Axiom 6) |
| **典型用例** | 查询外部 API / 文件读取 / 文本搜索 / 计算 / 子代理 Critic 调用 (R1.6) | 数据预处理 / 切块 / 索引建立 / 跨 phase 状态传递 |

**核心区别**: Tools 是给 LLM 的"业务能力外延", Actions 是给框架的"黑板读写专属脚本"。两者职责正交, 不允许越界。

## 1. Tools (LangChain StructuredTool)

### 1.1 设计原则

1. **Tool 是 framework 跟业务之间的最小接缝** — 单一职责, 不在 Tool 里做"准备数据 + 调外部 + 写黑板 + 总结"四件事
2. **Tool 看不到黑板** — 这是 V2.1 物理隔离的核心, 不要绕过 (绕过 = `[F-v21-purity]` FATAL)
3. **业务 Tool 放 skill 本地** (`<skill_root>/tools/` 或 `<skill_root>/phases/<id>/tools/`), 不污染 framework
4. **framework 自带 Tools** (`packages/graph-agent/src/graph_agent/tools/`) 只保留**跨 skill 通用能力** (多模态调用 / web search / 通用文本工具)

### 1.2 函数签名约定 (V2.1 硬约束)

```python
# phases/draft/tools/collect_reference.py

def collect_reference(scene_id: str, depth: int = 2, language: str = "zh-CN") -> str:
    """收集 scene 的上下文参考片段。

    Args:
        scene_id: 场景 ID
        depth: 上下文深度 (默认 2 层)
        language: 输出语言 (默认中文)

    Returns:
        Markdown 格式的参考片段
    """
    # 业务逻辑
    return "已收集 N 个片段..."
```

**硬约束** (违反 → `[F-v21-purity]` FATAL):

- **不接** `context` / `ctx` / `state` / `blackboard` 参数 — 这些参数名命中编译期静态扫描即拒绝
- 函数签名**只暴露业务参数** — 这些参数会通过 LangChain `StructuredTool.from_function` 的 type-hint binding 自动转成 LLM 可见的 JSON Schema
- 参数类型必须是 JSON 可序列化的 Python 类型 (`str` / `int` / `float` / `bool` / `list[str]` / `dict[str, Any]`)
- **返回值** 推荐 `str` (LLM 直接消费); 如果返回 dict, LangChain 会序列化为 JSON 字符串

### 1.3 不要使用 `@tool` 装饰器

V2.1 内核继续依赖 `_wrap_tool_for_langchain()` 对普通函数做包装。因此:

- ❌ 不要给 skill 本地工具加 `@tool` 装饰器
- ❌ 不要直接返回 LangChain `BaseTool` 子类
- ❌ 不要在工具层再做一层 schema 包装 (Pydantic Model 等)

直接写 Python 函数 + type-hint 就行, 包装机制是框架的事。

### 1.4 静态扫描 enforce (R1.5 / T1.2)

V2.1 编译期对 `tools/*.py` 做 AST 扫描, 拦截以下违规:

| 违规 | 错误码 | 修复 |
|---|---|---|
| 函数签名含 `context` / `ctx` / `state` / `blackboard` 参数 | `[F-v21-purity]` | 把该 Tool 迁为 Action (§4 示例) |
| 函数体内 `import` 了 `graph_agent.cognitive.context_facade` | `[F-v21-purity]` | 同上 |
| `open(file, 'w' | 'a' | 'x' | 'wb')` / `Path.write_text` / `Path.write_bytes` / `Path.touch` | `[F-v21-stateless]` | 见 §5 (改为 framework 落盘) |

**research §2.5 实证**: 当前 framework 的 Tools 路径 (`packages/graph-agent/src/graph_agent/tools/`) 已经通过 LangChain `StructuredTool.from_function` 天然 tunnel vision, `grep "def.*context.*:" packages/graph-agent/src/graph_agent/tools/` 0 命中。V2.1 把这种天然合规 enforce 化为永久规则, 防止未来回归。

## 2. Logic Actions (黑板读写脚本)

### 2.1 设计原则

1. **Action 是 LOGIC phase 的执行单元** — 一个 LOGIC.md `<execute>` 标签对应一个 Action 函数
2. **Action 专享黑板访问权** — 这是 V2.1 唯一允许跨 phase 显式传数据的 Python 路径
3. **Action 不被 LLM 调** — LLM 看不到 Action, 也不能 invoke; Action 是后台脚本
4. **Action 同样不能本地写盘** — Axiom 6 (Stateless Skills) 同样适用 (§5)

### 2.2 函数签名约定 (V2.1 硬约束)

```python
# phases/prep/actions/prepare_chunks.py

from graph_agent.cognitive.context_facade import Context

def prepare_chunks(context: Context, chunk_size: int = 500) -> None:
    """切块上游传入的章节文本, 写到黑板供下游 phase 消费。

    Args:
        context: 框架提供的黑板门面
        chunk_size: 每块字符数 (默认 500)
    """
    raw_text = context.get("raw_text")
    if not isinstance(raw_text, str):
        raise ValueError("expected raw_text:str in blackboard, got %r" % type(raw_text))

    chunks = [raw_text[i:i+chunk_size] for i in range(0, len(raw_text), chunk_size)]
    context.set("chunks", chunks)
```

**硬约束**:

- **必接** `context: Context` 作为第一参数 — 这是框架提供的黑板门面, 通过 `from graph_agent.cognitive.context_facade import Context` import
- 其他参数可选 (业务参数, 通过 `LOGIC.md` `<execute>` 标签的 `<arg>` 子标签传入)
- 返回值类型不限 — 框架不消费 Action 返回值, 数据流走黑板 (`context.set`)

### 2.3 物理位置

Actions **必须**位于 `<skill_root>/phases/<phase_id>/actions/*.py`, 跟对应的 `LOGIC.md` 同目录。

- ✅ `skills/text-segmentation/phases/prep/actions/prepare_chunks.py` (绑定 `phases/prep/LOGIC.md`)
- ❌ `skills/text-segmentation/actions/*.py` (skill 根 actions, V2.1 不认)
- ❌ `skills/text-segmentation/phases/draft/actions/*.py` (但 draft phase 是 `SKILL.md` 不是 `LOGIC.md`) → 装载时报 FATAL

### 2.4 `Context` 门面 API

```python
class Context:
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def has(self, key: str) -> bool: ...
    def keys(self) -> list[str]: ...
    def delete(self, key: str) -> None: ...

    # 输入只读访问 (runtime_inputs 跟 IO contract)
    @property
    def inputs(self) -> dict: ...

    # 当前 phase 元信息
    @property
    def phase_id(self) -> str: ...
    @property
    def run_id(self) -> str: ...
```

**正确用法**:

```python
# 读上游 phase 写入的数据
chunks = context.get("chunks", default=[])

# 写下游 phase 消费的数据
context.set("processed_chunks", processed)

# 读 runtime inputs (run_skill(...) 传入的 inputs)
user_name = context.inputs["user_name"]

# 当前 phase 上下文 (调试 / 观测用)
print(f"Running {context.phase_id} in run {context.run_id}")
```

**不要做**:

- 不要直接 mutate `context._internal_state` (访问门面的私有属性) — Kitchen-Pass 红线
- 不要 `context.set("output", ...)` 替代 `io/outputs.json` 声明 — 输出必须在 `outputs.json` schema 里声明
- 不要在 Action 里 import 别的 phase 的 Actions — Action 是 phase-local 的, 跨 phase 通过黑板传

## 3. Tool 还是 Action? (决策表)

| 场景 | Tool | Action | 理由 |
|---|---|---|---|
| LLM 想查外部 API (天气 / 维基 / 数据库) | ✅ | ❌ | LLM 调; 不需要黑板 |
| LLM 想读上游 phase 的 chunks 列表然后筛 | 看下表 1 | 看下表 1 | 拆分 |
| 切块章节文本喂给下游 phase | ❌ | ✅ | 框架后台做; 写黑板供下游消费 |
| LLM ReAct 内 Critic 调用 (R1.6) | ✅ | ❌ | LLM 调 Critic Tool (subagent), 不能作为独立 phase |
| 跨 phase 状态传递 (准备 → 起草 → 审阅) | ❌ | ✅ | Action 写黑板, 下游 phase 读 |
| 索引建立 / 数据库 schema migration | ❌ | ✅ | 框架后台做; phase 启动前的准备 |
| 跟 LLM 互动的文本搜索 (LLM 决定搜什么) | ✅ | ❌ | LLM 调, 业务参数化 |
| 跟 LLM 无关的批处理 (固定逻辑切 100 个 scene) | ❌ | ✅ | 确定性逻辑, 没 LLM 决策点 |

**下表 1: LLM 筛 chunks 场景拆分**:

如果业务上 "LLM 看上游 chunks 然后筛掉不相关的", 推荐拆成:

1. **LOGIC phase + Action**: 上游 LOGIC phase 的 `actions/load_chunks.py` 把 chunks 写到黑板
2. **SKILL phase + Tool**: 下游 SKILL phase 的 `tools/get_chunks.py` 让 LLM 通过 Tool 取 chunks (Tool 内部从某个固定来源 / API 读, 不读黑板)
3. **LLM 在 SKILL phase 内** ReAct 思考哪些相关, 调 `tools/filter_chunks.py` 提交筛选结果, 该 Tool 把结果写到 ... 等等, Tool 不能写黑板!

**正确拆法**:

1. LOGIC phase `prep`: action 把 chunks 写黑板
2. SKILL phase `filter`: LLM 看 prompt 里的 `{chunks}` (从黑板模板注入), ReAct 内**只用 Tool 做查询 / 评估**, 最后 `finish_task(markdown="...")` 提交筛选结果
3. LOGIC phase `apply_filter`: action 读 SKILL phase 写到黑板的筛选结果 (经 md2json 转 dict), 应用到 chunks

**关键模式**: SKILL phase 输入靠**黑板 → prompt 模板注入** (单向只读), 输出靠 `finish_task(markdown)` → md2json → 框架自动写黑板; LLM 跟黑板之间**没有 Tool 走读写通道**。

## 4. 现役违规 Tool 迁 Action (T1.2 fix-5 工作清单)

T1.2 任务的 fix-5 部分要求: grep 审计 `tools/*.py` 0 个 ctx/context/state/blackboard 签名, 现存违规 Tool 搬为 Action 并替换调用。

### 4.1 典型违规 Tool

```python
# ❌ V2.1 违规: tools/store_segments.py
def store_segments(ctx, segments: list[dict]) -> str:
    """把分段结果存到黑板。LLM 调。"""
    ctx.set("segments", segments)
    return f"已存储 {len(segments)} 个分段"
```

问题:
1. 函数签名有 `ctx` → `[F-v21-purity]` FATAL
2. 业务上是"LLM 在 SKILL phase 内把结构化结果写黑板" — 这是 V2.1 禁区 (黑板属于 Action, 不属于 Tool)

### 4.2 迁移路径

**Step 1**: 把 SKILL phase 改用 `finish_task(markdown)` 提交结构化结果, 不要让 LLM 调 Tool 写黑板。

`phases/segment/SKILL.md`:

```xml
<exit_contract>
当所有 chunks 分段完成后, 调用 finish_task, Markdown 格式如下:

```markdown
## segments

```json
[
  {"id": 1, "chunk": "...", "category": "..."},
  {"id": 2, "chunk": "...", "category": "..."}
]
```
</exit_contract>
```

**Step 2**: 框架的 `md_to_json` 中间件 (`cognitive/md_to_json.py`) 自动把 `## segments` 段下的 JSON 解析为 Python list, 写到黑板 `state["segments"]` (R1.7)。

**Step 3**: 下游 LOGIC phase 的 Action 读黑板:

```python
# ✅ V2.1 合规: phases/post_segment/actions/persist_segments.py
def persist_segments(context: Context) -> None:
    segments = context.get("segments", default=[])
    # ... 进一步处理 ...
    context.set("segments_normalized", normalized)
```

### 4.3 迁移检查 (T1.2 grep 审计)

```bash
# 必须 0 命中:
grep -rE "def .*\(.*\b(context|ctx|state|blackboard)\b" packages/graph-agent/src/graph_agent/tools/
grep -rE "def .*\(.*\b(context|ctx|state|blackboard)\b" skills/*/tools/
grep -rE "def .*\(.*\b(context|ctx|state|blackboard)\b" skills/*/phases/*/tools/
```

如果有命中, 按 §4.2 流程迁移到 LOGIC phase + Action。

## 5. Axiom 6 (Stateless Skills): 禁止本地写盘

`<root>/phases/<id>/actions/*.py` + `<root>/phases/<id>/tools/*.py` + `<root>/tools/*.py` **全部禁止本地写盘** — T1.2 fix-7 静态扫描 enforce。

### 5.1 禁止的 API (命中即 `[F-v21-stateless]` FATAL)

```python
# ❌ 禁止
open(path, 'w')
open(path, 'a')
open(path, 'x')
open(path, 'wb')
open(path, 'ab')
open(path, 'r+')
open(path, 'w+')

# ❌ 禁止
Path(path).write_text(content)
Path(path).write_bytes(content)
Path(path).touch()
Path(path).mkdir()       # 创建目录算副作用, 也禁止
Path(path).rename(...)
Path(path).unlink()

# ❌ 禁止
os.remove(path)
os.rename(src, dst)
os.makedirs(path)
shutil.copy(...)
shutil.move(...)
shutil.rmtree(...)
```

### 5.2 允许的 API

```python
# ✅ 允许 (只读)
open(path, 'r')
open(path, 'rb')
Path(path).read_text()
Path(path).read_bytes()
Path(path).exists()
Path(path).is_file()

# ✅ 允许 (临时 buffer, 不落盘)
io.StringIO()
io.BytesIO()
```

### 5.3 怎么落盘? (走框架 `IOManager`)

声明在 `io/outputs.json` 然后通过 `finish_task(markdown)` (SKILL phase) 或 `context.set` (LOGIC phase) 提交:

```json
// io/outputs.json
{
  "type": "object",
  "properties": {
    "draft_markdown": {
      "type": "string",
      "x-target": "artifact"
    }
  },
  "required": ["draft_markdown"]
}
```

框架自动用 `IOManager` / `StorageManager` 写到 `{workspace_root}/runs/{skill_id}/{run_id}/draft_markdown.md`, 保留最新 10 次 run, `.golden` 后缀的 run 永不清理。

caller 可通过 `run_skill(skill_root, ..., artifact_saver=my_saver)` 完全接管落盘逻辑, 不破坏 Kitchen-Pass 红线 (Axiom 1)。

## 6. 错误处理 / 异步 / 返回值

### 6.1 错误处理

| 错误性质 | 推荐做法 |
|---|---|
| 输入参数不合法 (类型 / 范围) | 抛 `ValueError` 或 `TypeError`, 让框架捕获并展示给 LLM (Tool) / 报 phase 失败 (Action) |
| 外部 IO 失败 (网络 / 文件不存在) | 抛 `FileNotFoundError` / `ConnectionError` 等具体异常, 让上层 trace 留痕 |
| 非致命 ambiguity (规则不清晰) | Tool: 返回可解释的错误文本, 让 LLM 决策下一步; Action: 调 `context.set("_ambiguity_log", ...)` 把 ambiguity 写到黑板, 让审阅 phase 处理 |
| 静默吃异常 | **永远禁止** — 违反 SOP §3.4 静默失败零容忍 |

### 6.2 异步调用

如果底层实现是 async (比如调外部 API client 是 `async def`):

```python
# ❌ 不要 (会在已有 event loop 内再启 loop 崩溃)
def my_tool(query: str) -> str:
    return asyncio.run(fetch_data_async(query))

# ✅ 用框架提供的 bridge
from graph_agent.tools._providers import run_async

def my_tool(query: str) -> str:
    return run_async(fetch_data_async(query))
```

### 6.3 返回值

| 场景 | 推荐返回 |
|---|---|
| Tool 成功 | 一句中文摘要 (LLM 友好) + 关键结果, 如 "已收集 3 个片段:\n- 片段 A...\n- 片段 B..." |
| Tool 失败 | 抛异常 (框架捕获后塞回 LLM) 或返回明确错误文本 "查询失败: 来源不可达" |
| Action 完成 | `None` (框架不消费 Action 返回值, 数据流走黑板) |
| Action 失败 | 抛异常, phase 算失败, 走重试或 abort |

## 7. checklist (提交前)

### 7.1 Tools

- [ ] 函数签名**不含** `context` / `ctx` / `state` / `blackboard` 参数
- [ ] 参数类型都是 JSON 可序列化 (str / int / float / bool / list / dict)
- [ ] 没有 `@tool` 装饰器, 直接是普通 Python 函数
- [ ] 函数体内**没有** `import graph_agent.cognitive.context_facade`
- [ ] 函数体内**没有**本地写盘调用 (`open('w')` / `Path.write_*` / `Path.touch` / `os.makedirs` 等)
- [ ] 静态扫描 `grep -rE "def .*\(.*\b(context|ctx|state|blackboard)\b" tools/` 0 命中

### 7.2 Actions

- [ ] 函数签名**首参数**是 `context: Context`
- [ ] 函数体只通过 `context.get` / `context.set` 跟黑板交互
- [ ] 没有 `context._internal_*` 私有属性访问
- [ ] 没有本地写盘调用 (同 §5.1)
- [ ] 文件位置在 `<skill_root>/phases/<id>/actions/*.py`, 跟对应 `LOGIC.md` 同目录

### 7.3 决策正确性

- [ ] 这个函数是给 LLM 调? → Tool
- [ ] 还是给框架后台调? → Action
- [ ] LLM 想写黑板? → 改用 `finish_task(markdown)` + md2json (§4 模式)
- [ ] Action 想本地写盘? → 改用 `io/outputs.json` 声明 + framework `IOManager` (§5.3)

## 8. 参考资料

- `ARCHITECTURE.md` — V2.1 架构全貌 + Axiom 6 映射
- `SKILL_AUTHORING_GUIDE.md` — GRAPH.md / phases/ 整体作者指南
- `CORE_ARCH_PRINCIPLES.md` — 6 红线源文档
- `.kiro/specs/graph-agent-v2.1/requirements.md` — R1.5 + Q-7 决议
- `.kiro/specs/graph-agent-v2.1/tasks.md` — T1.2 (Action loader + 静态扫描 + Tools 迁移)
