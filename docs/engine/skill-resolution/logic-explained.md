# skill-resolution 运行逻辑人话版

署名：Codex  
日期：2026-05-25  
定位：把当前 V0.3.0 PR δ ship 后的 skill-resolution 代码翻译成自然语言。这里描述的是 src 真实行为，不是概念草图。

## 1. 模块一句话

`skill-resolution` 只负责一件事：把文档里声明的稳定 `target_skill` id 交给外部注入的 resolver，拿回本地 skill root，并确认这个 root 可以被 Engine 编译。

当前实现的核心文件是 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py` 和 `packages/graph-agent/src/graph_agent/core/local_workspace_resolver.py`。Engine 不再用父 skill 下的相对路径找 child skill；`subagents[].path` 和 `SUBGRAPH.md` 里的旧相对引用字段都已经退出 active schema。

## 2. Protocol 和字段

### `SKILL_ID_PATTERN`

位置：`skill_resolver_protocol.py:11`

值：

```text
^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$
```

含义：

- 第一个字符必须是字母或数字。
- 后续最多 127 个字符。
- 后续字符允许字母、数字、下划线、点和短横线。

决策：`skill_id` 是 registry key，不是文件路径。它允许 `demo.child` 这种命名空间风格，但不允许 `../child`、`/tmp/child`、带空格的路径串。

### `SkillResolutionError`

位置：`skill_resolver_protocol.py:15-28`

字段：

- `skill_id: str`：失败时正在解析的 id。缺 resolver 时 caller 名也会放在这里，例如 `run_skill`。
- `reason: str`：失败原因的短文本。
- `code: str`：错误码，默认是 `[F-v3-skill-not-registered]`。

异常 message 统一拼成：

```text
skill {skill_id!r}: {reason}
```

决策：Engine 内部 resolver 域的失败仍 raise `SkillResolutionError` leaf。这个 leaf 现在是 `ResourceNotFoundError` family，不再是 compile family；调用方跨 public 边界时 catch `ResourceNotFoundError`，再从 `exc.payload.code`、`exc.skill_id`、`exc.reason` 或 `exc.code` 拿到原 resolver 颗粒度。

### `SkillResolverProtocol.resolve_skill`

位置：`skill_resolver_protocol.py:31-36`

签名：

```python
def resolve_skill(self, skill_id: str) -> str | Path
```

含义：resolver 接收一个稳定 `skill_id`，返回本机可读的 skill root 路径。返回值可以是 `str`，也可以是 `Path`。

决策：Engine 只依赖这一件事，不知道 Studio registry、生产 registry、用户 workspace、只读资源目录怎么组织。谁拥有 registry，谁实现 resolver。

## 3. 三个 helper 怎么跑

### `validate_skill_id(skill_id)`

位置：`skill_resolver_protocol.py:39-47`

流程：

1. 检查 `skill_id` 是不是字符串。
2. 用 `SKILL_ID_RE.fullmatch` 匹配 `SKILL_ID_PATTERN`。
3. 不通过就抛 `SkillResolutionError`，错误码是 `[F-v3-resolver-skill-id-invalid]`。

这个 helper 只检查 id 语法，不访问磁盘，也不调用 registry。

### `resolve_skill_root(resolver, skill_id)`

位置：`skill_resolver_protocol.py:50-76`

流程：

1. 先调用 `validate_skill_id(skill_id)`。
2. 调用 `resolver.resolve_skill(skill_id)`。
3. 如果 resolver 自己抛 `SkillResolutionError`，原样往外抛。
4. 如果 resolver 抛了其他异常，把它包成 `SkillResolutionError`，默认错误码是 `[F-v3-skill-not-registered]`。
5. 把返回值转成 `Path`。
6. 如果路径不是目录，抛 `[F-v3-resolver-path-invalid]`。
7. 如果目录里没有 `GRAPH.md`，也抛 `[F-v3-resolver-path-invalid]`。
8. 通过后返回 root `Path`。

决策：resolver 负责“这个 id 对应哪里”，Engine 负责“这个返回结果是不是一个可编译的 graph skill root”。这避免 Studio resolver 漏掉路径校验时把坏路径继续送进 loader。

### `require_skill_resolver(resolver, caller=...)`

位置：`skill_resolver_protocol.py:79-92`

流程：

1. 如果 `resolver is None`，抛 `SkillResolutionError`。
2. 错误码是 `[F-v3-resolver-missing]`。
3. `skill_id` 字段写 caller 名，例如 `compile_skill`、`assemble_graph`、`run_skill`。
4. resolver 存在就原样返回。

决策：PR δ 后入口不再容忍隐式 resolver。测试里可以用测试 resolver，Studio 用 `StudioSkillResolver`，CLI 和独立工具用 `LocalWorkspaceResolver`，生产宿主也必须显式提供 resolver；Engine 的 compile/assemble/run 层不 new 默认 resolver。

## 4. LocalWorkspaceResolver 本地实现

位置：`local_workspace_resolver.py:15-51`

`LocalWorkspaceResolver` 是 PR-1 新增的本地文件系统 resolver。它不是协议的一部分，而是 CLI、README 示例、独立工具和简单宿主项目可复用的 concrete implementation。

构造字段：

- `search_paths: Iterable[str | Path] | None = None`：可选构造参数。这里的可选只属于 resolver 对象自身，不代表 Engine 入口的 `skill_resolver` 可选。
- 当 `search_paths is None` 时，默认搜索两个根：`Path.cwd()` 和 `Path.cwd() / "skills"`。
- 传入 `search_paths` 时，构造函数只把每项转成 `Path` 并按顺序保存，不扫描全局临时目录，也不读取 Studio registry。

`resolve_skill(skill_id)` 流程：

1. 先调用 `validate_skill_id(skill_id)`。非法 id 直接抛 `[F-v3-resolver-skill-id-invalid]`。
2. 为同一个 id 生成两个相对候选：
   - literal：`Path(skill_id)`，例如 `acme.echo` -> `acme.echo`
   - dotted-id path：`Path(*skill_id.split("."))`，例如 `acme.echo` -> `acme/echo`
3. 对每个 `base` 和每个候选相对路径拼出 `candidate = base / relative`。
4. 命中条件必须同时满足：
   - `candidate.is_dir()`
   - `(candidate / "GRAPH.md").is_file()`
5. 收集所有命中，并用 `path.resolve()` 去重。
6. 唯一命中时返回这个 root `Path`。
7. 多个不同 root 命中时抛 `[F-v3-skill-id-ambiguous]`，message 包含所有匹配路径。
8. 没有命中时抛 `[F-v3-skill-not-registered]`，message 包含 search paths，方便 CLI 诊断。

为什么多命中 fail-loud：如果 literal 目录 `acme.echo/` 和 dotted 目录 `acme/echo/` 同时存在，silent first-match 会让 search path 顺序决定实际调用哪个 child skill。这种行为很难在 trace 里看出来，也违反零静默失败原则；因此 resolver 必须要求用户收窄 search paths 或删除重复注册。

## 4.5 ModuleSandbox 的 sys.modules 隔离

位置：`module_sandbox.py`

`ModuleSandbox` 负责把 skill 本地 Python 对象加载成 class / callable。它维护实例内私有缓存，避免不同 skill 里的同名 `schemas.py`、`tools.py` 通过 Python 全局 import registry 串台。

### 两条加载路径

`_load_module(module_path)` 先查显式 `search_paths`，再回退到 Python importlib：

1. `search_paths` 命中时走 `_load_from_file(module_path, module_file)`。这里会把真实文件名转成 sandbox hash 模块名，例如 `_graph_agent_sandbox_<digest>_schemas`。这个名字带文件路径 digest，目标是让两个 skill 都有 `schemas.py` 时仍得到不同 module identity。
2. `search_paths` 没命中时走 `importlib.util.find_spec(module_path)`。这里使用 `spec.name`，也就是 Python 正常 import machinery 能解析的真实模块名。这个路径用于加载环境里本来就可 import 的模块。

这两条路径都短暂写入 `sys.modules`，但写入只存在于同步加载窗口内。

### 为什么还要临时写 sys.modules

Pydantic model 如果使用 `from __future__ import annotations`，字段注解会先以字符串形式保存。`_rebuild_pydantic_models(module, module_name)` 调 `model_rebuild()` 时，Pydantic 需要能按模块名找到该 module，才能解析 `Literal[...]` 或同模块前向引用。

所以加载窗口是：

```text
sys.modules[name] = module
exec_module(module)
_rebuild_pydantic_models(module, name)
finally: 清理 / 恢复 sys.modules
```

可以把这理解为“把钥匙临时挂到门口，让 Pydantic 完成登记；登记完立刻收回”。模型类 rebuild 后，运行期 `model_validate()` 已经不再需要这个临时全局入口。

### PR-5 隔离机制

两条路径都用 `try/finally` 包住 `exec_module + model_rebuild`。`finally` 里不是无条件 `pop`，而是先在覆盖前做快照：

```python
previous_module = sys.modules.get(name, _MISSING)
sys.modules[name] = module
try:
    ...
finally:
    if previous_module is _MISSING:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = previous_module
```

这个快照守卫有两个作用：

- 如果这个名字是本次 sandbox 新加的，加载后把它从 `sys.modules` 移走，避免全局残留。
- 如果这个名字在进程里已经被合法 import 过，加载后恢复原对象，避免把宿主进程已有模块误删或替换。无条件 `pop` 会让后续 import 重新执行模块，产生新对象身份和状态丢失；只 pop 自己新增的条目才是安全边界。

`_load_from_file` 的 sandbox hash 名理论上不应撞已导入模块，但它也使用同一套快照 / 恢复逻辑，保持异常路径和未来改动都一致。

清理发生在 `_rebuild_pydantic_models` 之后，而不是 `exec_module` 之后。原因是 forward-ref 的解析点在 `model_rebuild()`；提前清理会让 Pydantic 找不到模块。失败路径也走 `finally`，因此 `exec_module` 或 `model_rebuild` 抛错时不会留下半加载的全局模块名。

## 5. 入口 DI 边界

所有 engine 入口都显式接收 `skill_resolver: SkillResolverProtocol`。

PR-1 去掉了 pytest `conftest.py` 对函数签名的默认值注入后，真实契约是：`compile_skill` / `SkillLoader.compile_skill` / `load_workflow_from_md` / `assemble_graph` / `run_skill` / `_run_skill_dict` / `_run_v030_skill_dict` 都必须从调用方拿到 resolver。缺失时要么 Python 签名直接报缺必填 keyword-only 参数，要么在内部边界通过 `require_skill_resolver` 抛 `[F-v3-resolver-missing]`。文档、测试和宿主代码都不能再假设 `skill_resolver=None` 会被框架自动补上。

### `compile_skill`

位置：`compiler.py:41-66`

字段：

- `root: str | Path`：要编译的 skill root。
- `chat_model: Any = None`：保留给稳定签名，编译本身不用模型。
- `cache: bool = True`：是否使用 compile cache。
- `skill_resolver: SkillResolverProtocol`：必填 resolver。

流程：

1. `require_skill_resolver(skill_resolver, caller="compile_skill")`。
2. 如果 cache 命中，返回 cached compiled skill。
3. 调 `SkillLoader().compile_skill(skill_root, skill_resolver=resolver)`。
4. cache 开启时保存 compiled result。

### `SkillLoader.compile_skill`

位置：`loader.py:146-215`

字段：

- `skill_root: str | Path`：skill root 目录。
- `skill_resolver: SkillResolverProtocol`：必填 resolver。
- `validate_context_writes: bool`：构造 `SkillLoader` 时传入，控制 LOGIC action 写出校验。

流程：

1. Python 签名要求调用方传入 `skill_resolver`，这里没有 `= None` 默认值。
2. 校验 root 是 V2.1/V0.3.0 skill root。
3. 解析 root `GRAPH.md`、io schema、phase document。
4. `_validate_subgraph_io_contracts(..., skill_resolver=skill_resolver)` 只在遇到 `SubgraphNodeAST` 时调用 `require_skill_resolver(..., caller="SkillLoader.compile_skill")`，再解析 child root。
5. 加载 actions/tools。
6. `_compile_subagent_metadata(..., skill_resolver=skill_resolver)` 只在 Agent phase 声明 subagents 时调用 `require_skill_resolver(..., caller="SkillLoader.compile_skill")`，再解析 child root。
7. 把 subagent 动态工具注入 phase tools。

### `assemble_graph`

位置：`graph_assembler.py:91-103`

字段：

- `compiled: CompiledSkill`：loader 输出。
- `chat_model: Any = None`：Agent/Skill phase 用的模型。
- `max_patch_attempts: int = 3`：md patch retry 上限。
- `skill_resolver: SkillResolverProtocol`：必填 resolver。

流程：

1. `require_skill_resolver(..., caller="assemble_graph")`。
2. 遍历 manifest phases。
3. 每个 phase 构建 runtime node 时把 resolver 往下传。
4. SUBGRAPH 和 subagent runtime 都复用同一个 resolver。

### `run_skill` / `_run_skill_dict` / `_run_v030_skill_dict`

位置：`runner.py:59`、`runner.py:130`、`runner.py:217`

字段：

- `skill_resolver: SkillResolverProtocol`：三个入口都必填。
- `model_resolver: Any | None`：LLM role 到模型实例的 Gateway resolver，和 skill resolver 是不同边界。

流程：

1. `run_skill` 先用 `require_skill_resolver(..., caller="run_skill")`。
2. `_run_skill_dict` 再用 `require_skill_resolver(..., caller="_run_skill_dict")`。
3. `_run_skill_dict` 只接受包含 `GRAPH.md` 的目录。合法目录走 `_run_v030_skill_dict`。
4. 非目录入口、普通 `.md`、单文件 `SKILL.md`、不存在路径、或缺 `GRAPH.md` 的目录，内部仍会抛 `SkillLoadError` leaf；这个 leaf 是 `GraphCompileError` family。payload 和 message 都带 `[F-v3-graph-root-missing]`。公开 `run_skill` 捕获后返回 `WorkflowResult(success=False, context={}, error=ErrorPayload(...))`，调用方应读 `result.error.code`。
5. `_run_v030_skill_dict` 调 `compile_skill(..., skill_resolver=resolver)`，再调 `assemble_graph(..., skill_resolver=resolver)`。

决策：编译、装配、运行三层都不允许掉 resolver。这样 child skill 解析不会在某一层偷偷回退到路径扫描。

### CLI `runner.main`

位置：`runner.py:291-389`

CLI 是 Engine 的调用方，因此它在解析参数后自己构造 resolver，再传给 `run_skill`。

字段和默认搜索根：

- `args.skill`：命令行 `--skill` 传入的 skill root 或 skill 文件路径。
- 固定基础根：`Path.cwd()` 和 `Path.cwd() / "skills"`。
- 如果 `--skill` 是目录，再追加：
  - `skill_path`
  - `skill_path / "registry"`
  - `skill_path.parent`
- 如果 `--skill` 不是目录，再追加：
  - `skill_path.parent`
  - `skill_path.parent / "registry"`

最终调用形态是：

```python
run_skill(..., skill_resolver=LocalWorkspaceResolver(search_paths=resolver_roots), ...)
```

因此用户运行 `python -m graph_agent --skill <root>` 时，CLI 会自动使用 `LocalWorkspaceResolver` 解析这个 root 里或其附近 registry 里的 child skills；这只是 CLI 层的默认接线，不改变 Python API 的强制注入契约。

### `tools/dual_run_shadow.py`

位置：`tools/dual_run_shadow.py:94-118`

独立 shadow 工具也不依赖 pytest fixture。每次 `_run_v21` 会构造：

```python
LocalWorkspaceResolver(
    search_paths=[skill_root, skill_root.parent, skill_root.parent / "registry"]
)
```

然后同一个 resolver 同时传给：

- `compile_skill(skill_root, cache=False, skill_resolver=resolver)`
- `assemble_graph(compiled, chat_model=..., skill_resolver=resolver)`

这样命令行直接运行 shadow 工具时，也不会靠测试环境猴补丁或全局目录扫描解析 child skill。

## 6. nested tool 调用

### `build_skill_tool`

位置：`skill_tool_factory.py:78-115`

字段：

- `skill_resolver: SkillResolverProtocol`：构建 tool 时必填。
- `SubSkillSpec.skill_path`：这个旧 tool factory 仍以 path 调 child run，但调用 `run_skill` 时必须把 resolver 透传。

流程：tool 被调用时构造 thread id 和 trace dir，然后调用 `run_skill(..., skill_resolver=skill_resolver)`。

### `parallel_map`

位置：`parallel_map.py:43-54` 和 `parallel_map.py:230-235`

字段：

- `skill_resolver: SkillResolverProtocol`：`parallel_map` 顶层参数。
- `_run_one_item(..., skill_resolver)`：每个 item 的 child run 都接收同一个 resolver。

流程：每个并发 child run 调 `run_skill(skill_path, ..., skill_resolver=skill_resolver)`。

### `md_to_json`

位置：`md_to_json.py:569-586`

字段：

- `skill_resolver: SkillResolverProtocol`：patch agent 路径需要调用 `run_skill`，所以必填。

流程：happy path 只 parse/validate；error path 调 `_PATCH_SKILL_MD` 时传 `skill_resolver`。如果 patch skill 的 `run_skill(...)` 返回对象有 `success is False`，`md_to_json` 会立刻抛内部 leaf `SkillLoadError("md_to_json md-patch deferred fallback failed ...")`；该 leaf 是 `GraphCompileError` family，并把原始 `result.error`（现在是 `ErrorPayload | None`）接在消息里。这样旧 `md-patch` deferred 路径失败时不会继续读取 `result["context"]["final_results"]`，也不会裸漏 `KeyError("final_results")`。

## 7. AST 字段 cutover

### `SubagentSpec`

位置：`manifest.py:97-104`

字段：

- `name: str`：动态工具名的一部分，必须匹配 Python 标识符风格。
- `target_skill: str`：必填，匹配 `SKILL_ID_PATTERN`。
- `description: str`：必填，用于动态 tool 描述。

已移除：`path` 字段。

当前 `_compile_subagent_metadata` 位于 `loader.py:593`。它不再接收 `skill_root`，也不拼相对路径。每个 subagent 都执行：

```text
resolve_skill_root(skill_resolver, spec.target_skill)
```

然后递归 `SkillLoader(validate_context_writes=False).compile_skill(sub_root, skill_resolver=skill_resolver)`。

### `SubgraphNodeAST`

位置：`manifest.py:139-146`

字段：

- `mode: Literal["subgraph"]`
- `target_skill: str`：必填，匹配 `SKILL_ID_PATTERN`。
- `io: PhaseIOSchema | None`
- `validator: bool = False`

已退役：旧 child 相对引用字段。`loader.py:1361` 通过 `SubgraphNodeAST.model_validate(data)` 从 frontmatter/body 构建 AST，不会再把旧 child ref block 注入 AST。

当前 `_build_subgraph_node` 位于 `graph_assembler.py:258`。它直接用：

```text
resolve_skill_root(skill_resolver, phase_ast.target_skill)
```

拿到 child root，再 compile + assemble child graph。

## 8. legacy 已移除

已删除的 active 行为：

- `SubagentSpec.path`
- `_resolve_subagent_root`
- `SUBGRAPH` 的旧 child ref 字段
- `_resolve_sub_skill_path`
- engine 内部默认 resolver / fallback resolver

当前 grep guard 期望在 active src/test/backend 中没有这些旧依赖。测试里如果要验证旧字段被拒绝，会通过字符串拼接避免让 grep guard 误判成 active 依赖。

## 9. 错误码字典

当前 resolver 相关错误码共 6 个：

| 错误码 | 当前触发点 | 当前行为 |
|---|---|---|
| `[F-v3-resolver-missing]` | `require_skill_resolver` 收到 `None` | 入口缺 resolver，直接失败 |
| `[F-v3-resolver-skill-id-invalid]` | `validate_skill_id` 正则不匹配 | 拒绝路径串、空格、非法 id |
| `[F-v3-skill-id-ambiguous]` | `LocalWorkspaceResolver` 找到多个不同 skill root | 拒绝 silent first-match，要求收窄 search paths 或删除重复注册 |
| `[F-v3-resolver-path-invalid]` | resolver 返回非目录或无 `GRAPH.md` 目录 | registry 返回了坏 root |
| `[F-v3-skill-not-registered]` | resolver miss 或 resolver 普通异常被包装 | skill id 没有注册或不可解析 |
| `[F-v3-resolver-interface-invalid]` | 当前 src 无 runtime trigger | spec 保留项，PR δ 未实现主动接口探测 |

## 10. Studio backend 实现

Studio resolver 文件：`apps/studio/backend/app/services/skill_resolver.py`

### `StudioSkillResolver.resolve_skill`

位置：`skill_resolver.py:13-36`

解析顺序：

1. 查 `config.SKILL_INDEX_PATH`，如果 entry 存在且 `absolute_path` 是 skill root，返回它。
2. entry 存在但路径不是 skill root，抛 `[F-v3-resolver-path-invalid]`。
3. 查默认 workspace：`config.default_workspace_skills_dir() / skill_id`。
4. 查 bundled skills：`config.SKILLS_DIR / skill_id`。
5. 都没找到，Studio 直接抛 public family `ResourceNotFoundError`，payload code 是 `[F-v3-skill-not-registered]`。如果 index 里有 entry 但路径不是 skill root，则同样抛 `ResourceNotFoundError`，payload code 是 `[F-v3-resolver-path-invalid]`。

### `build_studio_skill_resolver`

位置：`skill_resolver.py:39-42`

每次返回一个新的 `StudioSkillResolver`。它不缓存全局状态，只按当前 config 读 index 和目录。

### Studio 注入点

当前注入点：

- Predict 主 run：`predictor.py:73-80`
- Predict fallback compile：`predictor.py:218-224`
- Run subprocess worker：`run_manager.py:232-240`
- Input validator compile：`validator.py:78-83`
- Lint compile：`skills.py:292-296`
- Studio compile endpoint：`skills.py:305-318`
- Skill detail load：`skills.py:1061-1066`

决策：Studio backend 是 Engine 的调用方，所以它负责把 Studio registry 语义注入 Engine。Engine 不 import Studio。
