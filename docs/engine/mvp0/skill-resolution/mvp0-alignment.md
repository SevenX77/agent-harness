# skill-resolution (engine) — MVP0 Alignment

> **Status**: Updated by a1 (Codex), 2026-05-25  
> **Scope**: PR δ / round-12 skill-resolution hard cutover ship 后状态。  
> **Truth source**: current `packages/graph-agent/src/graph_agent/core/*` and `apps/studio/backend/app/services/skill_resolver.py`.

## 1. V0.3.0 结论

PR δ 已完成 A 模块 skill-resolution hard cutover。

当前 Engine 不再把 child skill 身份写成父 skill 下的相对路径。跨 skill 寻址统一为：

```text
target_skill -> SkillResolverProtocol.resolve_skill(skill_id) -> local skill root Path
```

这个 cutover 覆盖：

- Agent / Skill phase 的 `phase_config.subagents[].target_skill`
- `SUBGRAPH.md` 的 `target_skill`
- compile / assemble / run 入口显式 `skill_resolver`
- nested tool 调用中的 resolver 透传
- Studio backend resolver 注入

PR-5 追加完成了同一领域的 shipped 健壮性补强：`ModuleSandbox` 的两条 `sys.modules` 临时注册路径都已从“加载后常驻”切换为“同步 exec/rebuild 窗口内可见，结束后清理或恢复”。这不是新 feature，而是把 skill-local Python 对象加载的隔离边界补齐。

## 2. 已完成的 [BREAKING] 字段切换

| 旧字段 / 旧函数 | 当前状态 | 当前替代 |
|---|---|---|
| `SubagentSpec.path` | 已移除 | `SubagentSpec.target_skill: str` |
| `phase_config.subagents[].path` | active schema 拒绝 | `phase_config.subagents[].target_skill` |
| `_resolve_subagent_root` | 已删除 | `resolve_skill_root(skill_resolver, target_skill)` |
| `SubgraphNodeAST` 旧 child 引用字段 | 已退役 | `SubgraphNodeAST.target_skill: str` |
| `_resolve_sub_skill_path` | 已删除 | `resolve_skill_root(skill_resolver, phase_ast.target_skill)` |
| Engine default resolver / fallback resolver | 不存在 | 调用方必须 DI |
| `ModuleSandbox` 沙盒 module 常驻 `sys.modules` | 已移除 | 临时注册 + `try/finally` 清理 / 恢复 |

这符合 SOP-06 breaking cutover：不保 alias，不保 fallback，不把旧字段继续当兼容输入。

### PR-5 shipped: ModuleSandbox sys.modules 隔离

字段 / 机制级状态：

| 机制 | 当前行为 | 作用 |
|---|---|---|
| `search_paths` 命中路径 | `_load_from_file` 使用 `_graph_agent_sandbox_<digest>_<module>` 名短暂注册 | 同名 skill-local 文件不串台 |
| importlib fallback 路径 | `_load_module` 使用 `spec.name` 真模块名短暂注册 | 支持环境中可 import 模块 |
| 临时注册窗口 | `sys.modules[name] = module` 后执行 `exec_module` 与 `_rebuild_pydantic_models` | 让 Pydantic forward-ref / `from __future__ import annotations` 可解析 |
| 清理策略 | `finally` 中按 `previous_module` 快照判断：原来不存在则 `pop`，原来存在则恢复原对象 | 不留下 sandbox 残留，也不误删宿主已 import 的合法模块 |
| 异常路径 | `exec_module` 或 `model_rebuild` 抛错仍进入 `finally` | 防止半加载模块污染全局 registry |

清理必须发生在 `model_rebuild` 之后。此时 Pydantic 已经把 forward-ref 解析进模型类，后续 `model_validate` 不再依赖临时 `sys.modules` 条目。

## 3. Protocol 当前实现

文件：`packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`

| 对象 | 当前位置 | 对齐说明 |
|---|---:|---|
| `SKILL_ID_PATTERN` | line 11 | registry key grammar，允许 `A-Z/a-z/0-9/_.-` |
| `SkillResolutionError` | line 15 | Engine 内部 resolver leaf；IS-A `ResourceNotFoundError` public family |
| `SkillResolverProtocol.resolve_skill` | line 35 | 单方法协议，返回 `str | Path` |
| `validate_skill_id` | line 39 | 失败抛 `[F-v3-resolver-skill-id-invalid]` |
| `resolve_skill_root` | line 50 | 调 resolver 并校验 root 是目录且含 `GRAPH.md` |
| `require_skill_resolver` | line 79 | resolver 缺失抛 `[F-v3-resolver-missing]` |

`[F-v3-resolver-interface-invalid]` 仍是 spec 错误码，但当前 src 没有主动 runtime trigger。PR δ 没有实现 resolver object 结构探测；调用点依赖 Python Protocol / 方法调用失败语义。

PR-A 后，`SkillResolutionError` 不再属于 compile family。内部 helper 仍可 raise 这个 leaf；跨 SDK / Studio 边界的调用方应 catch `ResourceNotFoundError`，并用 `ErrorPayload.code` 区分 `[F-v3-skill-not-registered]`、`[F-v3-resolver-path-invalid]`、`[F-v3-resolver-missing]` 等 resolver 细粒度。

## 4. Engine 入口对齐

| 入口 | 当前签名状态 | 对齐结果 |
|---|---|---|
| `compile_skill` | `compiler.py:41-47` 必填 `skill_resolver` | 编译 facade 不 new resolver |
| `SkillLoader.compile_skill` | `loader.py:146-153` 必填 `skill_resolver` | 解析 phase / subagent metadata 时使用同一 resolver |
| `assemble_graph` | `graph_assembler.py:91-99` 必填 `skill_resolver` | SUBGRAPH runtime 和 subagent runtime 继续透传 |
| `run_skill` | `runner.py:59-73` 必填 `skill_resolver` | public runtime 入口不允许隐式 fallback |
| `_run_skill_dict` | `runner.py:130-144` 必填 `skill_resolver` | 内部执行入口不允许掉 resolver |
| `_run_v030_skill_dict` | `runner.py:217-226` 必填 `skill_resolver` | compile + assemble 都用同一 resolver |

验收重点：无 resolver 的代码路径不是“只在遇到 child skill 时失败”，而是在入口边界通过 `require_skill_resolver` 直接失败。

## 5. 子 skill 编译对齐

文件：`loader.py`

当前 `_compile_subagent_metadata` 位于 `loader.py:593-649`。它只接收 `phase_docs` 和 `skill_resolver`，不再接收 `skill_root`，所以无法拼父目录相对路径。

字段流：

1. `SubagentSpec.target_skill` 从 AST 读出。
2. `resolve_skill_root(skill_resolver, spec.target_skill)` 解析到 child root。
3. `SkillLoader(validate_context_writes=False).compile_skill(sub_root, skill_resolver=skill_resolver)` 编译 child skill。
4. child `io.inputs` 构造成动态 subagent input model。
5. `CompiledSubagent.target_skill` 保存原始 id，`root` 保存解析后的 root。

动态工具 metadata 仍保留 `target_skill`、`subagent_root`、`expected_schema`。旧 path 不再是寻址来源。

## 6. SUBGRAPH 对齐

文件：`manifest.py` 和 `graph_assembler.py`

当前 `SubgraphNodeAST` 字段：

- `mode: Literal["subgraph"]`
- `target_skill: str`
- `io: PhaseIOSchema | None`
- `validator: bool = False`

装配流程：

1. `loader.py:1330-1361` 不再读取旧 child ref block。
2. `_build_subgraph_node` 在 `graph_assembler.py:258-270` 使用 `phase_ast.target_skill`。
3. `resolve_skill_root(skill_resolver, phase_ast.target_skill)` 返回 child root。
4. child graph 编译和 assemble 都复用同一个 resolver。

PR δ 只解决“child root 怎么找到”。它不改变 γ2 负责的 state/IO 隔离策略。

## 7. nested tools 对齐

| 文件 | 当前字段 | 对齐说明 |
|---|---|---|
| `skill_tool_factory.py:78-115` | `build_skill_tool(..., skill_resolver)` | tool 调 `run_skill` 时透传 resolver |
| `parallel_map.py:43-54` | `parallel_map(..., skill_resolver)` | 每个 item 的 child run 复用 resolver |
| `parallel_map.py:230-235` | `_run_one_item` 调 `run_skill(..., skill_resolver=...)` | 并发子运行不掉 resolver |
| `md_to_json.py:505-570` | `md_to_json(..., skill_resolver)` | patch agent run 透传 resolver |

这些不是新的 skill registry 实现，只是防止 nested runtime 调用绕开顶层 DI。

## 8. Studio backend 对齐

文件：`apps/studio/backend/app/services/skill_resolver.py`

`StudioSkillResolver.resolve_skill` 当前解析顺序：

1. `config.SKILL_INDEX_PATH`
2. `config.default_workspace_skills_dir() / skill_id`
3. `config.SKILLS_DIR / skill_id`

如果 index 指向坏 path，抛 `[F-v3-resolver-path-invalid]`。如果三处都找不到，抛默认 `[F-v3-skill-not-registered]`。

注入点：

- Predict：`predictor.py:73-80`
- Predict fallback：`predictor.py:218-224`
- Run worker：`run_manager.py:232-240`
- Validator：`validator.py:78-83`
- Skills lint / compile / load：`skills.py:292-318`、`skills.py:1061-1066`

这保持 Engine 与 Studio 解耦：Engine 只看 Protocol，Studio 负责 registry 查询策略。

## 9. 错误码对齐

| 错误码 | 当前实现状态 | 触发点 |
|---|---|---|
| `[F-v3-resolver-missing]` | active | `require_skill_resolver(None, caller=...)` |
| `[F-v3-resolver-skill-id-invalid]` | active | `validate_skill_id` 正则失败 |
| `[F-v3-resolver-path-invalid]` | active | resolver 返回非目录或无 `GRAPH.md` |
| `[F-v3-skill-not-registered]` | active | resolver miss / 普通异常包装 / Studio miss |
| `[F-v3-resolver-interface-invalid]` | spec-only for now | 当前 src 无主动触发点 |

## 10. 边界：PR δ 不做什么

PR δ 不改这些模块的核心语义：

- **state-and-io-contract / D 模块**：child graph blackboard 隔离、StateMapper 深化、phase_outputs 规范化仍由 γ2/D 负责。
- **tracing-and-observability / E 模块**：resolver failure 只提供稳定错误码，不新增 tracing event 类型。
- **Gateway / ModelResolver**：LLM role 到模型实例仍由 graph-agent-gateway 负责，和 `SkillResolverProtocol` 是两个独立 DI 边界。
- **Studio frontend / Tauri**：PR δ 只完成 backend resolver 注入，不做文件选择 UI。

## 11. 当前验收状态

本轮 docs sync 基于以下本地 gate：

- `pytest packages/graph-agent/tests/`：984 passed, 0 failed
- `pytest apps/studio/backend/tests/`：350 passed, 0 failed
- `ruff check packages/graph-agent/src packages/graph-agent/tests apps/studio/backend`：pass
- `mypy packages/graph-agent/src apps/studio/backend/app`：pass
- `rg "[F-v21-" packages/graph-agent/`：无命中
- `rg "SubagentSpec.path|_resolve_subagent_root|sub_skill_ref|path: subskills" packages/graph-agent/`：无 active 命中
