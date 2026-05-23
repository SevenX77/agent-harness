# skill-resolution V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `skill-resolution` 子模块具体做什么、为什么这样做、每个字段如何校验。它不是 V2.1 baseline 的现状盘点, 也不是 mvp0-alignment 的改造路线; 它把 `SkillResolverProtocol` 这条小但关键的 DI 边界翻译成自然语言。

核心源码锚点:

- `SkillResolverProtocol`, `SkillResolutionError`, `validate_skill_id()`, `resolve_skill_root()` 定义在 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:15`.
- 编译入口 `compile_skill(..., skill_resolver=...)` 接收 resolver, 有 resolver 时跳过 cache, 再透传给 loader: `packages/graph-agent/src/graph_agent/core/compiler.py:41`.
- loader 在 Agent/subagent metadata 编译时, 对 `target_skill` 调 `resolve_skill_root()`: `packages/graph-agent/src/graph_agent/core/loader.py:359`.
- runtime 入口 `run_skill()` / `_run_v21_skill_dict()` 接收并透传 `skill_resolver`: `packages/graph-agent/src/graph_agent/core/runner.py:162`, `packages/graph-agent/src/graph_agent/core/runner.py:456`.
- LangGraph 装配 `assemble_graph()` 接收 resolver, 继续传给 subgraph / Agent / subagent runtime 装配: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:68`.

## 这个模块只回答一个问题

`skill-resolution` 只回答: 给定一个稳定的 `skill_id`, Engine 如何通过外部注入的 resolver 找到对应 graph skill 根目录, 并确认这个目录真的能作为 skill root 编译。

它不解析 `GRAPH.md`, 不读取 Studio settings, 不弹出文件选择器, 不解析 reference/example 路径, 不把 LLM role 变成模型。对应边界是:

| 事项 | 归属 |
|---|---|
| `target_skill -> skill root Path` | skill-resolution |
| `llm_role -> BaseChatModel` | graph-agent-gateway / ModelResolverProtocol |
| `references[].path` / `examples[].path` | 当前 skill root 内资源校验 |
| `GRAPH.md` / `SKILL.md` / `SUBGRAPH.md` AST | skill-compilation |
| 未注册 skill 导入 UI | Studio frontend/backend |

难点 1: **边界锁**。resolver 是 Engine 与 Studio registry 之间的边界锁: Engine 只拿 `skill_id` 和返回的本地 root, 不知道 registry 存在哪、不知道用户如何导入、不知道权限模型怎么实现。

## Protocol 层: Engine 只依赖单方法

`SkillResolverProtocol` 是 `@runtime_checkable` 的 `Protocol`, 只有一个方法: `resolve_skill(self, skill_id: str) -> str | Path`: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:31`. 单方法设计是刻意的: 跨 skill 寻址只允许查 graph skill root, 不允许把 resource、tool、任意路径选择混进同一个接口。

### Protocol 字段

| 字段 / 对象 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `SkillResolverProtocol` | 定义 Engine 可依赖的 resolver 形状 | 没有协议边界, Engine 会重新硬编码 Studio registry 或本地路径猜测 | 对象必须暴露 `resolve_skill(skill_id)` 语义; spec 禁止 `resolve_resource()` / `resolve_skill_path()` | `[F-v3-resolver-interface-invalid]` |
| `resolve_skill` | 把稳定 skill id 解析为本地 skill root | 子图和子 Agent 只能通过注册 id 寻址, 不能让 LLM 或 skill 作者报路径 | 方法签名当前允许返回 `str | Path`; spec 目标写作 `Path`; helper 统一转 `Path` | `[F-v3-resolver-interface-invalid]` |
| `skill_id` 参数 | registry 查询 key | 非法 id 会让 Studio registry、cache、trace 之间无法稳定对齐 | 当前代码使用 `SKILL_ID_PATTERN`; 不是 string 或不匹配正则就抛 `SkillResolutionError` | 当前 `[F-v3-invalid-skill-id]`; spec `[F-v3-resolver-skill-id-invalid]` |
| return `str | Path` | resolver 返回的本地 skill root | Engine 后续要读 `GRAPH.md` 并递归编译 | `resolve_skill_root()` 用 `Path(resolver.resolve_skill(skill_id))` 规整 | `[F-v3-resolver-path-invalid]` / `[F-v3-skill-not-registered]` |

## skill id 语法和 validate_skill_id()

源码里的公共语法是 `SKILL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"`: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:11`. `validate_skill_id()` 用这个正则做第一道检查: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:39`.

### skill id 字段

| 字段 / 常量 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `SKILL_ID_PATTERN` | 定义当前代码接受的 skill id 字符集和长度 | resolver 输入必须稳定, 不能把路径、空串或复杂表达式当 id | 首字符 `[A-Za-z0-9]`, 后续最多 127 个 `[A-Za-z0-9_.-]` | 当前 `[F-v3-invalid-skill-id]`; spec `[F-v3-resolver-skill-id-invalid]` |
| `SKILL_ID_RE` | 编译后的 regex | 每次校验重新编译会浪费且容易不一致 | `re.compile(SKILL_ID_PATTERN)` | 同上 |
| `skill_id` 值 | 具体 registry key, 来自 `target_skill` 等字段 | 如果允许 `../foo` 或空值, resolver 可能越过 registry 进入任意路径语义 | `isinstance(skill_id, str)` 且 `SKILL_ID_RE.fullmatch(skill_id)` | 同上 |

这里有一个完成态差异需要读者注意: spec 文档写的是小写 `^[a-z][a-z0-9_-]*$`, 当前源码允许大小写、点和短横线。logic-explained 按源码说明真实行为, 同时标明 spec 目标错误码, 避免把未来契约误认为当前代码已经完成。

## SkillResolutionError: 失败必须带 skill_id、reason、code

`SkillResolutionError` 继承 `SkillLoadError`, 因此会被 load/compile 边界当成 graph-agent 的加载错误处理: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:15`. 它保存三个字段: `skill_id`, `reason`, `code`, 并把它们渲染进异常消息: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:18`.

### SkillResolutionError 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `skill_id` | 记录哪个 target skill 解析失败 | Studio 需要标红具体 subgraph/subagent id | 构造异常时必传; 非法输入会先转成 `str(skill_id)` 再报错 | `[F-v3-resolver-skill-id-invalid]` / 当前 `[F-v3-invalid-skill-id]` |
| `reason` | 保存人类可读失败原因 | 只有 code 不足以指导修复 registry/path | resolver miss、resolver 抛错、路径非目录、缺 `GRAPH.md` 都会写 reason | 与具体失败 code 一起使用 |
| `code` | 稳定机器可读错误码 | Studio 不能靠字符串截取判断失败类型 | 默认 `[F-v3-skill-not-registered]`; `validate_skill_id()` 可传自定义 code | `[F-v3-skill-not-registered]` / `[F-v3-invalid-skill-id]` |
| 异常消息 | CLI / log 展示 | 开发者需要直接看到失败摘要 | 格式为 `"{code} skill {skill_id!r}: {reason}"` | 同 `code` 字段 |

## resolve_skill_root(): 把外部 resolver 输出收口成可编译目录

`resolve_skill_root(resolver, skill_id) -> Path` 是本模块真正被 loader 调用的 helper: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:50`. 它做四步:

1. 先调用 `validate_skill_id(skill_id)`;
2. 调 `resolver.resolve_skill(skill_id)` 并规整成 `Path`;
3. 把非 `SkillResolutionError` 的任意异常包装为 `SkillResolutionError`;
4. 校验返回路径是目录且含 `GRAPH.md`。

### resolve_skill_root 字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `resolver` | 外部注入的 resolver 实例 | Engine 不拥有 Studio registry, 必须由调用方注入 | 需要有 `resolve_skill()`; 当前 Python 调用时缺方法会进入包装异常 | `[F-v3-resolver-interface-invalid]` / 当前默认包装为 `[F-v3-skill-not-registered]` |
| `skill_id` | resolver 查询 key | 先校验 id 可避免把非法路径语义传进 resolver | 调 `validate_skill_id()`; 不通过立即抛 | 当前 `[F-v3-invalid-skill-id]`; spec `[F-v3-resolver-skill-id-invalid]` |
| `resolver.resolve_skill(skill_id)` | 查 registry 并返回 root | 这是唯一允许跨 skill 找目录的动作 | 成功返回 `str | Path`; 抛 `SkillResolutionError` 原样透出; 其他异常包装 | `[F-v3-skill-not-registered]` |
| `Path(...)` 规整 | 把返回值变成 Engine 内部可用路径对象 | 协议允许 `str | Path`, 后续文件校验需要 Path API | `Path(return_value)` 成功 | 包装为 `[F-v3-skill-not-registered]` |
| `root.is_dir()` | 确认返回值是目录 | 文件或不存在路径不能作为 skill root | false 时抛 `SkillResolutionError(skill_id, "resolved path is not a directory: ...")` | 当前 `[F-v3-skill-not-registered]`; spec 可细分 `[F-v3-resolver-path-invalid]` |
| `(root / "GRAPH.md").is_file()` | 确认目录是 graph skill root | 没有 `GRAPH.md` 就无法进入 skill-compilation | false 时抛 `SkillResolutionError(skill_id, "resolved path has no GRAPH.md: ...")` | 当前 `[F-v3-skill-not-registered]`; spec `[F-v3-resolver-path-invalid]` |
| return `Path` | 给 loader / runtime 递归编译使用 | 下游只应拿已校验 root, 不再重复猜测路径 | 目录存在且含 `GRAPH.md` 后返回 | 无 |

难点 2: **窄口**。`resolve_skill_root()` 把所有外部差异收窄成一个结果: 要么是可编译 root, 要么是带 code 的解析失败。Studio、本地 sandbox、生产 registry 可以完全不同, 但 Engine 后面只面对这一个窄口。

## 注入链: resolver 从入口一路传到需要它的地方

当前源码已经把 `skill_resolver` 参数穿过多层入口:

- `compile_skill(..., skill_resolver=None)` 接收参数, 有 resolver 时跳过 cache, 然后传给 `SkillLoader().compile_skill()`: `packages/graph-agent/src/graph_agent/core/compiler.py:41`.
- `SkillLoader.compile_skill(..., skill_resolver=None)` 接收参数, 传给 `_compile_subagent_metadata()`: `packages/graph-agent/src/graph_agent/core/loader.py:146`.
- `run_skill(..., skill_resolver=None)` 传给 `_run_skill_dict()`: `packages/graph-agent/src/graph_agent/core/runner.py:162`.
- `_run_v21_skill_dict(..., skill_resolver=None)` 传给 `compile_skill()` 和 `assemble_graph()`: `packages/graph-agent/src/graph_agent/core/runner.py:456`.
- `assemble_graph(..., skill_resolver=None)` 传给 `_build_phase_node()`, 再传给 subgraph / Agent / subagent runtime builders: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:68`.

### 注入字段

| 注入点 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `compile_skill.skill_resolver` | 编译期解析 Agent subagent `target_skill` | 编译时要知道子 Agent 根 IO, 才能生成 tool schema | 若存在 `target_skill` 且参数是 `None`, loader 当前报 fatal | `[F-v3-resolver-missing]` / 当前 `[F-v3-route]` |
| `SkillLoader.compile_skill.skill_resolver` | loader 内部依赖注入入口 | 不应让 loader 从 cwd 或父目录猜 registry | 传给 `_compile_subagent_metadata()` | 同上 |
| `run_skill.skill_resolver` | public runtime 入口 | 用户 / Studio 应在运行入口注入 registry 能力 | 透传到 `_run_skill_dict()` | `[F-v3-resolver-missing]` |
| `_run_v21_skill_dict.skill_resolver` | V2.1 runner 到 compile/assembly 的桥 | 子图和子 Agent runtime 递归调用也需要同一 resolver | 传给 `compile_skill()` 和 `assemble_graph()` | `[F-v3-resolver-missing]` |
| `assemble_graph.skill_resolver` | graph assembly 递归构建 child graph / subagent runtime | runtime 子图调用不能丢 resolver, 否则下层 target skill 解析失败 | 传给 `_build_subgraph_node()`, `_build_skill_node()`, `_subagent_runtime_map()` | `[F-v3-resolver-missing]` |

## 调用点: 当前 target_skill 主要在 subagent metadata 编译时解析

当前代码里真正调用 `resolve_skill_root()` 的位置是 `_compile_subagent_metadata()`: `packages/graph-agent/src/graph_agent/core/loader.py:359`. 当 `SubagentSpec.target_skill` 不为 `None`, loader 要求 `skill_resolver` 必须存在, 然后调 `resolve_skill_root(skill_resolver, spec.target_skill)`: `packages/graph-agent/src/graph_agent/core/loader.py:371`.

### subagent target_skill 字段

| 字段 / 对象 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `SubagentSpec.name` | 父 Agent 内的本地 subagent 名 | 动态工具名和 trace 都依赖它 | 正则 `^[A-Za-z_][A-Za-z0-9_]*$` | `[F-v3-agent-subagent-invalid]` |
| `SubagentSpec.target_skill` | V0.3.0 子 Agent skill id | 子 Agent 应通过 registry id 寻址 | 可选字段; 有值时必须匹配 `SKILL_ID_PATTERN` 并走 resolver | `[F-v3-resolver-skill-id-invalid]` / 当前 Pydantic validation 或 `[F-v3-invalid-skill-id]` |
| `SubagentSpec.path` | legacy 相对路径 fallback | 兼容旧数据, 但 V0.3.0 完成态应退役 | `target_skill is None` 时使用; 必须留在父 skill root 内并含 `GRAPH.md` | 当前 `[F-v3-route]`; 完成态不用 |
| `SubagentSpec.description` | 动态 tool 描述 | LLM 调用 subagent 前需要用途说明 | 非空字符串 | `[F-v3-agent-subagent-invalid]` |
| `skill_resolver is None` | 缺少 DI 的状态 | 有 `target_skill` 但无 resolver 时不能猜路径 | 当前 `_fatal(... "no skill_resolver was provided")` | `[F-v3-resolver-missing]` / 当前 `[F-v3-route]` |
| `CompiledSubagent.root` | resolved child skill root | runtime 要递归编译子 graph | 来自 `resolve_skill_root()` 返回的 Path 或 legacy path | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |
| `CompiledSubagent.target_skill` | 保存 provenance | dynamic tool metadata 和 trace 需要知道目标 id | `target_skill` 分支保存 skill id; legacy 分支保存 path 字符串 | 无 |

Agent `subgraphs[]` 目前被 `AgentRegistryItem` 建模, 字段含 `name`, `target_skill`, `description`: `packages/graph-agent/src/graph_agent/core/manifest.py:46`. Loader 的 mention 校验只检查 `@subgraph:NAME` 是否存在于 `ast.subgraphs` 名称集合: `packages/graph-agent/src/graph_agent/core/loader.py:1214`. 完成态还要对 `subgraphs[].target_skill` 走 resolver 可达性校验。

## SUBGRAPH phase: 完成态要走 resolver, 当前 runtime 仍是 legacy path

`SubgraphNodeAST` 已经有 `target_skill` 字段: `packages/graph-agent/src/graph_agent/core/manifest.py:146`. 但当前 graph assembly 的 `_build_subgraph_node()` 仍用 `phase_ast.sub_skill_ref` 走 `_resolve_sub_skill_path()` 相对路径: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:190`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:721`. 它只把 `skill_resolver` 继续传给 child compile/assemble, 没有用 resolver 找 subgraph root: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:198`.

完成态语义应该是:

| 字段 / 对象 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `SubgraphNodeAST.target_skill` | 固定 SUBGRAPH phase 指向的 child graph skill id | SUBGRAPH 是主流程固定节点, 不应靠相对路径 include | 必填完成态; 匹配 skill id 语法, resolver 能解析 | `[F-v3-subgraph-target-skill-invalid]` / `[F-v3-skill-not-registered]` |
| `SubgraphNodeAST.sub_skill_ref` | 当前 legacy 子图路径字段 | 旧 runtime 仍需要它找到 child root | 当前必填 `min_length=1`; 完成态退役 | `[F-v3-subgraph-target-skill-invalid]` / 当前 graph error |
| `skill_resolver` | SUBGRAPH phase 的 DI 能力 | 无 resolver 时不应从 phase 目录猜 child skill | 含 SUBGRAPH target_skill 时必须注入 | `[F-v3-resolver-missing]` |
| child root `Path` | 子图编译入口 | 返回路径必须是 graph skill root | 由 `resolve_skill_root()` 校验目录和 `GRAPH.md` | `[F-v3-resolver-path-invalid]` / `[F-v3-skill-not-registered]` |

这里是当前代码与完成态设计的主要差异。本文把它明示出来, 是为了避免读者误以为 `SubgraphNodeAST.target_skill` 已经被 `_build_subgraph_node()` 消费。

## sandbox / Studio / production 三种实现形态

`SkillResolverProtocol` 是 Engine 协议, 不是某一种 resolver 实现。完成态下至少会有三类实现:

| 实现形态 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| test / sandbox resolver | 单测或本地沙箱中用 dict 映射 `skill_id -> temp root` | 测试必须可预测, 不能读用户真实 registry | id 存在则返回 root; 不存在抛 `SkillResolutionError` | `[F-v3-skill-not-registered]` |
| Studio resolver | 从 Studio skill registry 查已导入 skill root | Studio 管导入、权限和本地路径; Engine 不能读 settings | registry miss 抛未注册; path invalid 抛路径错误 | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |
| production resolver | 支持只读 workspace、公共/私有 registry、租户权限 | 生产权限模型不能泄漏到 Engine | 无权限按未注册处理; 返回路径仍需含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |

难点 3: **双态门**。本地 sandbox 和 Studio registry 的实现可以完全不同, 但都必须通过同一个 `resolve_skill()` 门进入 Engine。这样 Engine 的测试路径和真实产品路径共享同一失败语义。

## 错误码全清单

resolver 相关错误码来自 spec 的 resolver domain 和当前源码:

| 错误码 | 阶段 | 触发条件 | 修复方向 | 当前源码状态 |
|---|---|---|---|---|
| `[F-v3-resolver-missing]` | 编译期 / 运行期 | 需要解析 `target_skill` 但调用方没有注入 resolver | 在 `compile_skill` / `run_skill` / `assemble_graph` 入口传入 `SkillResolverProtocol` | spec 已定义; 当前部分路径用 `[F-v3-route]` 文本报错 |
| `[F-v3-resolver-skill-id-invalid]` | 编译期 | `skill_id` / `target_skill` 命名非法 | 修正成合法 registry id | spec 已定义; 当前源码使用 `[F-v3-invalid-skill-id]` |
| `[F-v3-invalid-skill-id]` | 编译期 | 当前 `validate_skill_id()` 发现非法 id | 同上 | 当前源码真实 code, 位于 `skill_resolver_protocol.py:46`; spec 未列为最终 resolver domain 名 |
| `[F-v3-skill-not-registered]` | 编译期 / 装配期 / 运行期 | resolver 查不到 skill、resolver 抛异常、返回不可用路径时的默认 code | 在 Studio 导入 / 注册 skill, 或修 resolver 映射 | spec 已定义; 当前 `SkillResolutionError` 默认 code |
| `[F-v3-resolver-path-invalid]` | 编译期 | resolver 返回路径不存在、不是目录、或缺 `GRAPH.md` | 修 registry 记录或导入目录 | spec 已定义; 当前源码这两类路径错误仍使用默认 `[F-v3-skill-not-registered]` |
| `[F-v3-resolver-interface-invalid]` | 编译期 | resolver 暴露非单方法语义或缺 `resolve_skill` | 实现 `resolve_skill(skill_id)` | spec 已定义; 当前缺方法会被包装成默认 `SkillResolutionError` |

## V0.3.0 四个改造点如何落地

| 改造点 | 完成态代码语义 |
|---|---|
| NEW-RES-1 | `core/skill_resolver_protocol.py` 成为独立协议文件, 导出 `SkillResolverProtocol`, `SkillResolutionError`, `validate_skill_id`, `resolve_skill_root`。 |
| NEW-RES-2 | `compile_skill`, `run_skill`, `assemble_graph` 等顶层入口显式接收并透传 `skill_resolver`, Engine 不创建默认 resolver。 |
| C-RES-1 | `_resolve_subagent_root()` 相对路径扫描退役; 子 Agent root 统一来自 `resolve_skill_root()`。 |
| NEW-RES-3 | `SUBGRAPH.md target_skill`, Agent `subagents[].target_skill`, Agent `subgraphs[].target_skill` 都走同一 resolver, registry miss 统一为 `[F-v3-skill-not-registered]`。 |

读代码时建议从 `skill_resolver_protocol.py` 开始, 再看 `compiler.py` 的 cache/DI 决策, 然后看 `loader.py` 的 `target_skill` 调用点, 最后看 `graph_assembler.py` 中 SUBGRAPH phase 仍待从 `sub_skill_ref` 切到 `target_skill` 的 runtime 装配边界。
