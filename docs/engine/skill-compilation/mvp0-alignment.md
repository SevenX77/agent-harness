# skill-compilation (engine) — MVP0 Alignment (V0.3.0 目标对齐逻辑)

> **Status**: Filled by a1 (Codex) based on a2 framework, 2026-05-20; Q9/Q13 + 死代码清退 + V0.3.0 版本号 升级 2026-05-21
> **Scope**: V0.3.0 技能目录解析、AST 构建、图拓扑校验、静态 IO 数据流校验 (audit A7/A8)、编译缓存策略
> **改造目标 engine 版本**: V0.3.0 (MVP0 落地后, 详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))
> **配套**: 见 [INDEX.md](../../INDEX.md) 三时态模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

这里的 backend Python library 指 `packages/graph-agent` 里的引擎编译层，不是 Studio FastAPI，也不是 React。PM 可以把它理解成“把一个 skill 目录读成可执行说明书”的环节：它不画按钮、不打开面板，但它决定 Studio 之后能不能准确告诉用户“哪条边错了、哪个 phase 缺输入、哪个 schema 不合法”。

当前编译入口是 `compile_skill()`，代码在 `packages/graph-agent/src/graph_agent/core/compiler.py:40`。它最终交出 `CompiledSkill`，字段定义在 `packages/graph-agent/src/graph_agent/core/loader.py:65` 到 `packages/graph-agent/src/graph_agent/core/loader.py:75`。MVP0 对齐后的 UI 价值不是新增一个界面，而是让后续 Studio Canvas、Trace 和 CompileErrorPanel 可以消费结构化错误，而不是只能展示一段不可定位的 Python 异常。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 不会解析 `GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md` 或 `SKILL.md`。这些文件的发现与 AST 构建都发生在 `SkillLoader.compile_skill()`，主流程在 `packages/graph-agent/src/graph_agent/core/loader.py:142` 到 `packages/graph-agent/src/graph_agent/core/loader.py:177`。因此，本文件的“下一步对齐”只规定 Python compiler 将来应该产出什么，不规定 Studio 怎么渲染它。

前端会间接受益。比如 GraphCanvas 双击 phase 后打开文件，用户修完后点 compile；后端如果能返回“phase `summarize` 需要字段 `clean_text`，但上游没有产出”，前端就能标红对应节点或边。这个跨 feature 消费关系放在 [Cross-feature interaction](#cross-feature-interaction) 里说明。

## 后端功能

### 1. 缓存元数据补全与深层对象重建 (P1-1 修复)

MVP0 SHOULD 把编译缓存从“只保存骨架”升级为“命中缓存后与冷编译等价”。当前 `_dehydrate_compiled_skill()` 只保存 `raw`、`manifest` 和 `nodes`，见 `packages/graph-agent/src/graph_agent/core/cache.py:84` 到 `packages/graph-agent/src/graph_agent/core/cache.py:99`；`_rehydrate_compiled_skill()` 恢复时只重建 `actions`、`tools` 并构造 `CompiledSkill(raw, manifest, nodes, actions, tools)`，见 `packages/graph-agent/src/graph_agent/core/cache.py:102` 到 `packages/graph-agent/src/graph_agent/core/cache.py:126`。这会让 dataclass 默认值接管 `subagents_by_phase` 和 `phase_tokens`，而这两个字段本来定义在 `packages/graph-agent/src/graph_agent/core/loader.py:74` 到 `packages/graph-agent/src/graph_agent/core/loader.py:75`。

这里的 dehydrate / rehydrate 可以理解成“存盘压缩”和“从盘上还原”。问题是 subagent 不是一个普通字符串：`CompiledSubagent` 保存了子 skill root、input schema、动态生成的 Pydantic input model 和 expected schema，字段在 `packages/graph-agent/src/graph_agent/core/loader.py:78` 到 `packages/graph-agent/src/graph_agent/core/loader.py:89`。如果缓存只存 nodes，不存 subagent 元数据，冷编译时可用的 `call_subagent_<name>` 动态工具在 cache hit 时就会消失。

MVP0 WILL 在 snapshot 里保存两类额外数据。第一类是 `subagents_by_phase`：每个父 phase 下每个 subagent 的 `parent_phase_id`、`name`、`path`、`description`、`root`、`input_schema` 和 `expected_schema` 都要进入 JSON。第二类是 `phase_tokens`：`GRAPH.md` 中 `<phase />` 标签的位置信息来自 `packages/graph-agent/src/graph_agent/core/loader.py:151`，后续结构化错误要用它定位行号。

恢复时不能把 `input_model` 当 JSON 保存，因为它是动态 Python 类。正确方向是保存 `expected_schema` 或 `input_schema`，再调用现有 `build_subagent_input_model()` 重新生成类型；冷编译路径已经在 `packages/graph-agent/src/graph_agent/core/loader.py:360` 到 `packages/graph-agent/src/graph_agent/core/loader.py:364` 使用这个 helper。换句话说，缓存恢复要复用真实编译路径的建模规则，而不是发明另一套简化对象。

```python
# 拟定的重建逻辑示例，该部分将被插入 _rehydrate_compiled_skill 函数内
subagents_by_phase = {}
for phase, subs in snapshot.get("subagents_by_phase", {}).items():
    restored_subs = []
    for sub in subs:
        # 必须在这里调用 build_subagent_input_model 重新生成类型
        from graph_agent.core.subagents import build_subagent_input_model
        input_model = build_subagent_input_model(sub["name"], sub["expected_schema"])
        restored_subs.append(
            CompiledSubagent(
                parent_phase_id=sub["parent_phase_id"],
                name=sub["name"],
                path=sub["path"],
                description=sub["description"],
                root=Path(sub["root"]),
                input_schema=sub["input_schema"],
                input_model=input_model,
                expected_schema=sub["expected_schema"],
            )
        )
    subagents_by_phase[phase] = restored_subs
```

### 2. 缓存写失败平滑降级机制 (P2-2 修复)

MVP0 SHOULD 把 cache 写入从“编译必要条件”改成“性能优化”。当前 `get_cache_dir()` 固定写 `~/.cache/graph-agent-v21`，见 `packages/graph-agent/src/graph_agent/core/cache.py:18` 到 `packages/graph-agent/src/graph_agent/core/cache.py:19`；`save_to_cache()` 直接 `mkdir` 和 `write_text`，见 `packages/graph-agent/src/graph_agent/core/cache.py:45` 到 `packages/graph-agent/src/graph_agent/core/cache.py:52`。如果 HOME 不可写、容器只读、CI 临时目录权限异常，编译本体明明成功，也会因为保存快照失败而整体失败。

降级机制的产品语义很简单：cache 是加速器，不是发动机。`compile_skill(cache=True)` SHOULD 在写 cache 失败时记录 warning，然后返回内存中的 `CompiledSkill`。读取 cache 已经有容错：`load_from_cache()` 捕获 `OSError`、JSON 错误和类型错误后返回 None，见 `packages/graph-agent/src/graph_agent/core/cache.py:34` 到 `packages/graph-agent/src/graph_agent/core/cache.py:42`。写入侧也应保持同样心智模型。

MVP0 WILL 在 `cache_dir.mkdir()` 和 `cache_file.write_text()` 周围捕获 `OSError | IOError | PermissionError`，记录 cache path 和异常文本。它不应该吞掉编译器本身的错误；只吞“保存缓存失败”这一类辅助 I/O 错误。这样 Studio 或 CLI 仍能运行，只是下次不会命中缓存。

### 3. 编译期 Schema 解析强制增强 (A7 补全)

MVP0 SHOULD 引入 phase-level IO schema。当前根图只有 `GraphManifest.io_inputs_ref` 和 `io_outputs_ref`，默认值在 `packages/graph-agent/src/graph_agent/core/manifest.py:53` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:54`；compiler 会校验这两个 JSON Schema 文件本身，调用点在 `packages/graph-agent/src/graph_agent/core/loader.py:153` 到 `packages/graph-agent/src/graph_agent/core/loader.py:154`，实现见 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。

但根级 schema 只说明整张图的入口和出口，不说明每个 phase 消费什么、产出什么。当前 `SkillNodeAST` 只有 `system_prompt`、`exit_contract`、`tools`、`subagents`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:83` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`；`LogicNodeAST` 也只有 `python_callable`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:69` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:73`。A7 的目标是让每个节点都在 frontmatter 里声明自己的 `io` dict。

第一次出现的术语：phase-level IO schema，就是“单个节点自己的输入输出契约”。例子：`extract` 输出 `{clean_text: string}`，`summarize` 输入要求 `{clean_text: string}`。没有这个契约，compiler 只能知道节点顺序，不能知道数据是否接得上。

MVP0 WILL 在 `_build_phase_document()` 解析 phase frontmatter 时要求 `mode: skill` 与 `mode: logic` 都携带合法 `io`。缺失时 SHOULD 产生结构化 compile issue，例如 `F-v21-io-missing`，并带上 phase 文件路径和 frontmatter 行号。文件解析主循环目前在 `packages/graph-agent/src/graph_agent/core/loader.py:158` 到 `packages/graph-agent/src/graph_agent/core/loader.py:167`，这里是最自然的接入点。

### 4. 静态数据流拓扑连通性校验 (A8 补全)

MVP0 SHOULD 在执行前证明“每个 required input 都有来源”。当前 `_validate_graph_topology()` 已经能检查 phase id/src、重复 id、unknown dependency、自环、环和孤岛，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:730` 到 `packages/graph-agent/src/graph_agent/core/loader.py:771`；环检测在 `packages/graph-agent/src/graph_agent/core/loader.py:774` 到 `packages/graph-agent/src/graph_agent/core/loader.py:805`；孤岛检测在 `packages/graph-agent/src/graph_agent/core/loader.py:807` 到 `packages/graph-agent/src/graph_agent/core/loader.py:837`。这些是“拓扑结构正确”，不是“数据流正确”。

数据流校验的 PM 版解释：如果 `summarize` 声明必须读 `clean_text`，编译器要在运行前确认 `clean_text` 来自全局输入，或者来自它依赖的上游 phase 输出。否则用户不应该等到 LLM 或 Python action 运行时才看到 KeyError。

MVP0 WILL 在 graph manifest 和 phase AST 都构建完之后调用 `_validate_phase_io_dataflow()`。它会按 `depends_on` 做拓扑遍历，维护“当前节点可见字段集合”。入口字段来自 `io/inputs.json` 的 `properties`，当前 helper `_extract_output_schema_keys()` 已能从 schema 顶层 `properties` 提 key，见 `packages/graph-agent/src/graph_agent/core/loader.py:903` 到 `packages/graph-agent/src/graph_agent/core/loader.py:909`。上游字段来自每个上游 phase 的 `io.outputs`。

### 5. 编译期错误信息的规范化结构

MVP0 SHOULD 让 A7/A8 的错误既能给人读，也能给 UI 定位。当前 loader 多数错误通过 `_fatal()`、`_graph_fatal()`、`_io_fatal()` 抛出带 `[F-v21-*]` 前缀的异常，helper 集中在 `packages/graph-agent/src/graph_agent/core/loader.py:232` 到 `packages/graph-agent/src/graph_agent/core/loader.py:253`。这对终端用户有用，但对 Canvas 标红还不够，因为前端需要字段名、phase id、source phase、line 等机器字段。

MVP0 WILL 保留人类可读 message，同时把 compile issue 结构化。一个 A8 缺字段错误 SHOULD 至少包含：`code`、`severity`、`phase_id`、`field_name`、`source_phase_candidates`、`path`、`line`。这让 Studio 后端可以把 `F-v21-io-conflict` 转成 HTTP 422，再让 Canvas 精确定位缺口。

### 6. Subagent / Subgraph 工具的 per-tool 编译 (Q13 决策落地)

**Q13 PM 拍定方案** (2026-05-21, a2 round 5 reply): subagent 跟未来新加的 subgraph 都走 **per-tool 编译路径** — 每个登记的子图在 graph 装配期编译为独立原生 LangChain tool `call_<name>`, schema 从子图 `io.inputs` JSON Schema 直接转, 挂到 `bind_tools`, **完全不占用 system prompt**。

**现状 = 跟决策一致, 文档化即可**:

`_inject_subagent_tools()` (`packages/graph-agent/src/graph_agent/core/loader.py:387-407`) 已经是 per-tool 编译: `tool_name = f"call_subagent_{subagent.name}"` (`:396`); `_subagent_tool_def()` (`:410-437`) 用 `build_subagent_tool_args_model(subagent.input_model.__name__, subagent.input_model)` (`:419-422`) 从 subagent 编译期生成的 Pydantic input model 转成 LangChain Tool args schema。

这条路径已经满足 Q13 决策, MVP0 **不**改 subagent tool 编译入口, 只做 2 件事:

1. **文档化现状**: design.md 明写 "subagent → `call_subagent_<name>` per-tool 是 spec, 不是 implementation detail", 防止后续工程师再次提出"统一入口"方案。
2. **扩展到 subgraph**: 新增 `_inject_subgraph_tools()` 跟 `_compile_subgraph_metadata()`, 跟 subagent 现状完全同构。具体编译路径详见 [execution-runtime/mvp0-alignment.md#3-call_subgraph_name-per-tool-编译路径-q13-决策](../execution-runtime/mvp0-alignment.md#3-call_subgraph_name-per-tool-编译路径-q13-决策)。

**A7 phase-level IO 跟 Q13 的关联**: A7 引入 `PhaseIOSchema` (本文件 Data Model §2) 后, 每个 phase 的 `io.inputs` 都可以直接当 JSON Schema 用; subagent / subgraph 的 root `io/inputs.json` 也是同一种 JSON Schema 格式。编译期统一从 phase 的 `io.inputs` 生成 LangChain Tool args schema, 不需要二次发明 schema DSL。这是 Q13 跟 A7 的协同点 — A7 把 IO 契约带到每个 phase, Q13 把 phase IO 契约编译进 Tool API。

**Token 影响 (a2 round 4 事实 3 估算)**: 5 个 subagent / subgraph schema 序列化后约 500-1250 tokens (假设每个 3-5 个属性), 相对一个完善 SKILL.md system prompt 1000-3000 tokens 而言, 是非常轻量级开销, 完全不影响 prompt cache。

## API

以下为新增或变更的核心公共 API 及其签名定义。它们是整个 compilation feature 中承担核心防御和解析责任的暴露面，未来将被上游调用方紧密依赖。

### 1. 静态数据流校验入口

作为 `compile_skill` 主干流程中的新加入的验证关卡，我们需要提供一个结构化的分析函数。此签名预期为：

```python
from typing import Any

def _validate_phase_io_dataflow(
    manifest: GraphManifest, 
    nodes: list[PhaseAST],
    global_inputs_schema: dict[str, Any]
) -> list[CompileIssue]:
    """Validate dataflow continuity across all compiled phase nodes.

    This static analyzer traverses the declared graph topology in
    `manifest.phases`. It sequentially checks every node's required
    input fields against the output schemas declared by its ancestors
    or the global initialization inputs. This prevents missing keys
    during runtime execution.

    Args:
        manifest: The parsed GraphManifest describing phase sequence.
        nodes: Parsed PhaseAST items containing `io` schemas.
        global_inputs_schema: Evaluated root `io/inputs.json` schema.

    Returns:
        List of CompileIssue containing dataflow or type mismatch errors.
        For example: missing required upstream output mapping.
    """
    issues = []
    # 内部将执行拓扑排序并逐级累加可用字段的集合
    # 若发现 required field 缺失则 append issue 包含了详细的位置信息
    return issues
```

MVP0 SHOULD 把这个函数放在 loader/compiler 内部 API 层，而不是 Studio 层。原因是数据流校验依赖 `GraphManifest`、`PhaseAST` 和 schema 文件，这些对象都已经在 `SkillLoader.compile_skill()` 里可用，见 `packages/graph-agent/src/graph_agent/core/loader.py:150` 到 `packages/graph-agent/src/graph_agent/core/loader.py:176`。

### 2. 扩充的 CompileResult 返回值契约

虽然 `compile_skill()` 当前直接返回 `CompiledSkill`，签名在 `packages/graph-agent/src/graph_agent/core/compiler.py:40` 到 `packages/graph-agent/src/graph_agent/core/compiler.py:45`，MVP0 SHOULD 明确一种可被 Studio 捕捉的结构化 issue 契约。短期可以通过异常携带 `issues`；长期可以让 compile result 明确包含 issue list。关键不是类名，而是信息不能只停留在字符串。

## Data Model / State

### 1. CompiledSkill 缓存序列化 Schema 的深层升级

`CompiledSkill` 当前字段已经包含 MVP0 需要保存的状态，见 `packages/graph-agent/src/graph_agent/core/loader.py:65` 到 `packages/graph-agent/src/graph_agent/core/loader.py:75`；cache snapshot 只是没有完整写出它们。MVP0 的 `DehydratedCompiledSkill` SHOULD 成为“可 JSON 化的 CompiledSkill 子集”，而不是另一个业务模型。

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class DehydratedCompiledSkill:
    """The JSON-serializable representation of a CompiledSkill.
    
    This acts as the canonical data model for saving and loading the
    graph compilation state to and from disk.
    """
    raw: dict[str, Any]
    manifest: dict[str, Any]
    nodes: list[dict[str, Any]]
    
    # 新增字段：完整保留子代理的必要元数据，排除无法序列化的类定义
    # 用于确保运行时缓存命中后能动态重新挂载子执行图
    subagents_by_phase: dict[str, list[dict[str, Any]]] 
    
    # 新增字段：保留 Token 成本消耗等外围计量数据
    phase_tokens: dict[str, dict[str, Any]]             
```

这里的 `raw` 仍要保留 root graph/io/phases 信息，因为 runtime 和 Studio 可能需要原始 schema；`manifest` 继续走 Pydantic `model_dump(mode="json")`，当前实现已在 `packages/graph-agent/src/graph_agent/core/cache.py:85` 到 `packages/graph-agent/src/graph_agent/core/cache.py:98` 做到这部分。新增字段只补齐 P1-1，不改变冷编译产物的语义。

### 2. Node AST 数据结构边界扩展

MVP0 SHOULD 在 AST 层表达 phase-level IO。当前 `_BaseNodeAST` 有 `name`、`raw_blocks`、`metadata`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:59` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:67`。`LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 都继承它，但没有统一 IO 字段。新增 `PhaseIOSchema` 后，compiler 才能在 A7/A8 中以强类型方式读取输入输出。

```python
from pydantic import BaseModel, Field
from typing import Any, Literal

class PhaseIOSchema(BaseModel):
    """Declarative JSONSchema wrapper for node boundary definitions.
    
    This enforces that every phase explicitly states what it consumes
    and what it yields, forming the basis of the IO contract.
    """
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

class SkillNodeAST(_BaseNodeAST):
    """LLM ReAct phase node parsed from ``SKILL.md``."""
    mode: Literal["skill"]
    system_prompt: str = Field(min_length=1)
    exit_contract: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)
    
    # A7 要求的强制绑定结构，在 AST 解析阶段如果该字段无法被 
    # Frontmatter 提供，Pydantic 将直接引发 ValidationError
    io: PhaseIOSchema = Field(...) 
```

MVP0 SHOULD 决定 `SUBGRAPH` 是否强制声明 `io`。如果 SUBGRAPH 继续代表固定子流程，它至少需要声明映射边界，否则 state-and-io-contract 无法完成 A6 子图隔离。这个问题与 [state-and-io-contract 的黑板隔离](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation) 直接相关。

## Cross-feature interaction

本特性的执行作为上游防线，直接影响下游的运行时和前端可视化的体验，属于跨模块的强关联枢纽。

### 1. 与 Studio trace-visualization 及 Canvas 的协同

MVP0 编译错误 SHOULD 成为 Studio Canvas 的静态反馈源。Canvas 不应该等到 `run_skill()` 运行后才知道某条边没有产出字段；A8 的 `_validate_phase_io_dataflow()` 应在 compile 阶段发现它。当前 Canvas/Trace feature 需要展示 phase 与 edge 的可观测状态，具体消费侧见 [Studio trace-visualization mvp0 alignment](../../studio/feature-folders/trace-visualization/mvp0-alignment.md)。

双向关系是：compiler 提供 `phase_id`、`field_name`、`line`；tracing/runtime 后续提供实际运行的 node_start/node_end。前者回答“图还没跑就知道结构错在哪里”，后者回答“图跑起来后每一步实际用了什么”。这两类数据不应该混在同一个错误字符串里。

### 2. 对 State Contract 阶段过滤漏斗的直接支撑

state-and-io-contract 的 Runtime Input Funnel 和 phase-level sandbox 都依赖本文件新增的 `io` schema。编译阶段负责把 frontmatter 和 JSON Schema 变成可查的 AST；运行阶段负责按这些规则过滤输入、构造 `phase_input`、封装 `phase_outputs`。运行侧规划见 [state-and-io-contract mvp0 alignment](../state-and-io-contract/mvp0-alignment.md#后端功能)。

举例：compiler 确认 `summarize.io.inputs.required = ["clean_text"]` 且 `extract.io.outputs.properties.clean_text` 存在；runtime 才能在 `summarize` 执行前只把 `clean_text` 交给它，而不是把整个 `state.data` 全量塞进去。

## MVP0 死代码清退 {#mvp0-死代码清退}

按 a1 (Codex) 2026-05-21 死代码调查 (详见 [baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21](./baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21)) 跟 PM 拍定原则 "把事情做对, 不向后兼容", MVP0 cutover **同 PR** 一并清退以下 skill-compilation 域内的 legacy / 死代码, 不留 deprecated alias:

### 高置信度死 — 直接 `git rm`

- `packages/graph-agent/src/graph_agent/core/skill_builder.py` (991 行) — 旧 schema-2.0 PhaseNode builder, 0 caller。
- `packages/graph-agent/src/graph_agent/core/skill_parser.py` (312 行) — 旧 `parse_skill_md`, 0 caller。
- `packages/graph-agent/src/graph_agent/core/skill_validator.py` (185 行) — 旧 `validate_manifest`, 0 caller。

### 中置信度死 — 删文件 + 同 PR 删测试 (不改测 V2.1)

V2.1 compile 主流程不调用这些 validator, 测试是 dead test 不是 regression 保险:

- `packages/graph-agent/src/graph_agent/core/validators/persona_resolution.py` (84) / `prompt_quality.py` (192) / `template_variables.py` (56) / `tool_paths.py` (269) / `validator_required.py` (83) — 合计 684 行 + 对应 `packages/graph-agent/tests/core/validators/*` 测试目录整删。
- `packages/graph-agent/src/graph_agent/core/skill_tool_factory.py` (127) + `packages/graph-agent/tests/core/test_skill_tool_factory.py`
- `packages/graph-agent/src/graph_agent/core/phase_node.py` (34) + `packages/graph-agent/tests/core/test_phase_node.py` / `test_build_graph_nodes.py`
- `packages/graph-agent/src/graph_agent/codemod/v21_migrator.py` (454) + `packages/graph-agent/tests/core/test_v21_codemod.py` — V2.0 → V2.1 一次性迁移工具, 迁移已完成, 不再需要。

### Legacy 入口直接删

- `load_workflow_from_md()` at `packages/graph-agent/src/graph_agent/core/loader.py:211` 到 `:229` — V2.1 主线 `_run_v21_skill_dict` 不调用。canonical compile API 已是 `compile_skill()` (`compiler.py:40`), 删 `load_workflow_from_md` 同时清掉对它的所有 import (按 SOP-05 cutover discipline 同 PR 改 test)。

### Cutover discipline (按 SOP-05)

清退 PR 必须同 PR 改/删 integration test + e2e test + unit test。**禁止** "skill-compilation 域 1 PR + 测试清退留下一 PR" 这种分拆。

合计本 PR 清退 `~ 2179 行` (高置信度死 1488 + 中置信度死 ~ 1322, validators 测试目录另算), engine 仓库瘦身明显。

### V0.3.0 版本号 cutover (PM 2026-05-21)

MVP0 落地 = engine 版本号从 V2.1 升 V0.3.0 (详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))。同 cutover PR 处理 skill-compilation 域内的版本号 step:

- **错误码前缀** `[F-v21-*]` → `[F-v3-*]`: 现 loader.py / cache.py / actions.py 等 `_fatal()` / `_graph_fatal()` / `_io_fatal()` helper (`packages/graph-agent/src/graph_agent/core/loader.py:232-253`) 抛出的所有 `[F-v21-route]` / `[F-v21-graph]` / `[F-v21-io]` / `[F-v21-actions]` / `[F-v21-actions-keys]` / `[F-v21-purity]` 全部改 `[F-v3-*]`。**不留 alias** (按 "不向后兼容")。
- **cache dir** `~/.cache/graph-agent-v21` → `~/.cache/graph-agent-v3`: `packages/graph-agent/src/graph_agent/core/cache.py:18-19` `get_cache_dir()` 默认路径升级。旧 v21 缓存目录不读取 (V0.3.0 cache 跟 V2.1 cache schema 不兼容, 强制 cache miss 重新编译)。
- **`_guard_v21_root` rename**: `packages/graph-agent/src/graph_agent/core/loader.py:256-272` `_guard_v21_root` 改名 `_guard_v3_root`。`load_workflow_from_md` (`:211-229`) 已经在死代码清退里删, 不再需要。
- **fixture / test 路径**: `packages/graph-agent/tests/core/test_v21_codemod.py` 已经在中置信度死代码清退里删 (跟 codemod/ 一起)。

### MVP0 test 全清重写 (PM 2026-05-21)

PM 原则 (2026-05-21): **不只是 V1/V2.0 dead test, V2.1 现有 test 也全部清掉, MVP0 重新写 test 套**。

- **现状 V2.1 test**: `packages/graph-agent/tests/core/test_compiler*.py` / `test_loader*.py` / `test_cache*.py` / `test_compile_skill_*.py` 等 V2.1 compile 相关 test 全部清退。
- **MVP0 重写覆盖**: 新 test 必须覆盖 V0.3.0 新增能力 — A7 (`PhaseIOSchema` frontmatter 强制) + A8 (静态数据流校验 `_validate_phase_io_dataflow`) + P1-1 (`CompiledSubagent` cache rehydrate) + P2-2 (cache 写失败降级) + Q13 (`_inject_subgraph_tools` per-tool 编译) + V0.3.0 错误码前缀 + 新 cache dir。
- **重写策略**: a1 实施 PR 内, 跟 src 改造同 PR 写新 test (按 SOP-05 cutover discipline 不分拆)。**禁止** "测试随后补" — 测试是 V0.3.0 实施的一部分, 不是 followup。
- **覆盖率**: 测试套必须包括 unit (Pydantic schema / single helper function) + integration (compile_skill 端到端) + e2e (compile + assemble + invoke, 真实 LLM 跑 1 个 reference skill, 用 .env API key)。具体 fixture 设计由 a1 在实施 task spec 阶段写。
