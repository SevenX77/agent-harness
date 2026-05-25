# skill-resolution 运行逻辑人话版

署名：Codex  
日期：2026-05-25  
定位：把当前 V0.3.0 PR δ ship 后的 skill-resolution 代码翻译成自然语言。这里描述的是 src 真实行为，不是概念草图。

## 1. 模块一句话

`skill-resolution` 只负责一件事：把文档里声明的稳定 `target_skill` id 交给外部注入的 resolver，拿回本地 skill root，并确认这个 root 可以被 Engine 编译。

当前实现的核心文件是 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`。Engine 不再用父 skill 下的相对路径找 child skill；`subagents[].path` 和 `SUBGRAPH.md` 里的旧相对引用字段都已经退出 active schema。

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
{code} skill {skill_id!r}: {reason}
```

决策：resolver 域的失败都用同一种异常承载，调用方可以从 message 看到错误码，也可以从对象字段拿到 `skill_id`、`reason`、`code`。

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

决策：PR δ 后入口不再容忍隐式 resolver。测试里可以用测试 resolver，Studio 用 `StudioSkillResolver`，生产用生产 resolver；Engine 不 new 默认 resolver。

## 4. 入口 DI 边界

所有 engine 入口都显式接收 `skill_resolver: SkillResolverProtocol`。

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

位置：`loader.py:149-199`

字段：

- `skill_root: str | Path`：skill root 目录。
- `skill_resolver: SkillResolverProtocol`：必填 resolver。
- `validate_context_writes: bool`：构造 `SkillLoader` 时传入，控制 LOGIC action 写出校验。

流程：

1. `require_skill_resolver(..., caller="SkillLoader.compile_skill")`。
2. 校验 root 是 V2.1/V0.3.0 skill root。
3. 解析 root `GRAPH.md`、io schema、phase document。
4. 加载 actions/tools。
5. 调 `_compile_subagent_metadata(phase_docs, skill_resolver=resolver)`。
6. 把 subagent 动态工具注入 phase tools。

### `assemble_graph`

位置：`graph_assembler.py:73-103`

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

### `run_skill` / `_run_skill_dict` / `_run_v21_skill_dict`

位置：`runner.py:173`、`runner.py:244`、`runner.py:474`

字段：

- `skill_resolver: SkillResolverProtocol`：三个入口都必填。
- `model_resolver: Any | None`：LLM role 到模型实例的 Gateway resolver，和 skill resolver 是不同边界。

流程：

1. `run_skill` 先用 `require_skill_resolver(..., caller="run_skill")`。
2. `_run_skill_dict` 再用 `require_skill_resolver(..., caller="_run_skill_dict")`。
3. V2.1/V0.3.0 root 走 `_run_v21_skill_dict`。
4. `_run_v21_skill_dict` 调 `compile_skill(..., skill_resolver=resolver)`，再调 `assemble_graph(..., skill_resolver=resolver)`。

决策：编译、装配、运行三层都不允许掉 resolver。这样 child skill 解析不会在某一层偷偷回退到路径扫描。

## 5. nested tool 调用

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

位置：`md_to_json.py:505-570`

字段：

- `skill_resolver: SkillResolverProtocol`：patch agent 路径需要调用 `run_skill`，所以必填。

流程：happy path 只 parse/validate；error path 调 `_PATCH_SKILL_MD` 时传 `skill_resolver`。

## 6. AST 字段 cutover

### `SubagentSpec`

位置：`manifest.py:97-104`

字段：

- `name: str`：动态工具名的一部分，必须匹配 Python 标识符风格。
- `target_skill: str`：必填，匹配 `SKILL_ID_PATTERN`。
- `description: str`：必填，用于动态 tool 描述。

已移除：`path` 字段。

当前 `_compile_subagent_metadata` 位于 `loader.py:373-422`。它不再接收 `skill_root`，也不拼相对路径。每个 subagent 都执行：

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

已退役：旧 child 相对引用字段。`loader.py:1050-1073` 只从 frontmatter/body 构建 `SubgraphNodeAST`，不会再把旧 child ref block 注入 AST。

当前 `_build_subgraph_node` 位于 `graph_assembler.py:196-213`。它直接用：

```text
resolve_skill_root(skill_resolver, phase_ast.target_skill)
```

拿到 child root，再 compile + assemble child graph。

## 7. legacy 已移除

已删除的 active 行为：

- `SubagentSpec.path`
- `_resolve_subagent_root`
- `SUBGRAPH` 的旧 child ref 字段
- `_resolve_sub_skill_path`
- engine 内部默认 resolver / fallback resolver

当前 grep guard 期望在 active src/test/backend 中没有这些旧依赖。测试里如果要验证旧字段被拒绝，会通过字符串拼接避免让 grep guard 误判成 active 依赖。

## 8. 错误码字典

当前 resolver 相关错误码共 5 个：

| 错误码 | 当前触发点 | 当前行为 |
|---|---|---|
| `[F-v3-resolver-missing]` | `require_skill_resolver` 收到 `None` | 入口缺 resolver，直接失败 |
| `[F-v3-resolver-skill-id-invalid]` | `validate_skill_id` 正则不匹配 | 拒绝路径串、空格、非法 id |
| `[F-v3-resolver-path-invalid]` | resolver 返回非目录或无 `GRAPH.md` 目录 | registry 返回了坏 root |
| `[F-v3-skill-not-registered]` | resolver miss 或 resolver 普通异常被包装 | skill id 没有注册或不可解析 |
| `[F-v3-resolver-interface-invalid]` | 当前 src 无 runtime trigger | spec 保留项，PR δ 未实现主动接口探测 |

## 9. Studio backend 实现

Studio resolver 文件：`apps/studio/backend/app/services/skill_resolver.py`

### `StudioSkillResolver.resolve_skill`

位置：`skill_resolver.py:13-36`

解析顺序：

1. 查 `config.SKILL_INDEX_PATH`，如果 entry 存在且 `absolute_path` 是 skill root，返回它。
2. entry 存在但路径不是 skill root，抛 `[F-v3-resolver-path-invalid]`。
3. 查默认 workspace：`config.default_workspace_skills_dir() / skill_id`。
4. 查 bundled skills：`config.SKILLS_DIR / skill_id`。
5. 都没找到，抛 `SkillResolutionError(skill_id, "skill is not registered in Studio")`，错误码默认 `[F-v3-skill-not-registered]`。

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
