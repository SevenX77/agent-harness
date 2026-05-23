# skill-compilation 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前 skill 编译真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`skill-compilation` 的工作，是把一个磁盘上的 skill 目录变成结构化的 `CompiledSkill`。

它不运行 LLM，不执行 Python action，不调用工具，也不跑 LangGraph。它只做静态工作：

- 确认目录形状像一个 graph skill。
- 读取 `GRAPH.md`。
- 找到每个 phase。
- 把 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 解析成 AST。
- 读取根级 IO schema。
- 发现 actions、tools、subagents。
- 做一部分静态校验。
- 返回一个运行时可以装配的编译产物。

## 2. 编译入口做什么

公开编译入口接收一个 skill root。它会先尝试 cache；但如果传了 `skill_resolver`，当前会跳过 cache，因为 resolver 背后可能代表外部 registry 状态，不能简单认为同一路径的编译结果永远稳定。

编译过程最终交给 loader。loader 返回的不是运行结果，而是 `CompiledSkill`。

可以把它理解成：

```text
skill 目录
  -> 编译器读文件和校验声明
  -> CompiledSkill
  -> execution-runtime 后续再装配和运行
```

## 3. 一个 skill 目录必须长什么样

当前 graph skill 根目录至少需要：

```text
my_skill/
  GRAPH.md
  phases/
    prepare/
      LOGIC.md
    analyze/
      SKILL.md
```

根目录必须存在 `GRAPH.md`，也必须有 `phases/`。phase 子目录下面只能有一种 phase 文件：

- `LOGIC.md`
- `SUBGRAPH.md`
- `SKILL.md`

如果一个 phase 目录里同时出现两种 phase 文件，当前编译器会拒绝，因为它无法把一个 phase 同时当作两种节点运行。

例子：

```text
phases/analyze/
  SKILL.md
  LOGIC.md
```

这会失败。`analyze` 到底是 Agent 还是 LOGIC，必须只有一个答案。

## 4. GRAPH.md 怎么被理解

`GRAPH.md` 是整张图的入口。

当前它可以通过两种方式描述 phase：

1. frontmatter 里的 `phases:` 列表。
2. body 里的 `<phase .../>` 标签。

如果 frontmatter 已经有 `phases:`，编译器会以它为准。否则会从 body 里提取 `<phase />`。

一个 phase 引用最少包含：

```yaml
id: prepare
src: phases/prepare
depends_on: []
```

`id` 是 phase 在图里的名字，`src` 是 phase 目录，`depends_on` 表示它必须等哪些 phase 完成后才能运行。

## 5. DAG 校验做什么

编译器会把 `depends_on` 当成一张图来检查。

它会拒绝三类常见错误：

### 依赖不存在

```yaml
phases:
  - id: analyze
    src: phases/analyze
    depends_on: [prepare]
```

如果没有 `prepare` phase，就失败。

### 依赖成环

```text
A depends_on B
B depends_on A
```

这会失败，因为运行时永远不知道谁先开始。

### 孤岛 phase

如果一个图里有多个互不相连的 phase 组件，也会被当作错误。当前编译器要求整张 graph 是连通的。

## 6. 根级 IO schema 怎么来

当前根级 IO schema 有两种来源：

- `GRAPH.md` frontmatter 里的 inline `io.inputs` / `io.outputs`。
- 如果没有 inline `io`，就读取 `io_inputs_ref` / `io_outputs_ref` 指向的 JSON 文件，默认是 `io/inputs.json` 和 `io/outputs.json`。

也就是说，物理 JSON 文件还没有完全退役。

例子：

```yaml
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      summary:
        type: string
```

这会走 inline schema。

如果没有这段 inline `io`，编译器会去找默认 JSON 文件。

## 7. phase 文件怎么被解析

phase 类型由物理文件名和 frontmatter `mode` 共同决定。

### LOGIC.md

`LOGIC.md` 必须声明 `mode: logic`。它需要能解析出一个 Python callable 名字。

运行时会根据这个 callable 名字，在该 phase 的 actions 里找到真正的函数。

### SUBGRAPH.md

`SUBGRAPH.md` 必须声明 `mode: subgraph`。它当前主要读取 `sub_skill_ref`，也支持 AST 上的 `target_skill` 字段，但 runtime 路径里仍主要用 `sub_skill_ref` 去解析子 skill 路径。

### SKILL.md

`SKILL.md` 当前兼容两种模式：

- `mode: agent`
- `mode: skill`

`mode: agent` 会解析出角色、目标、步骤、协议、资源、示例、subagents 等更结构化的信息。`mode: skill` 仍保留 legacy ReAct 风格的 system prompt / exit contract 形状。

所以，“SKILL.md 只能是 agent，不再接受 skill”还不是当前源码事实。

## 8. actions 和 tools 怎么发现

编译器会扫描 phase 目录下的 `actions/` 和 `tools/`。

规则是：

- LOGIC phase 可以有 `actions/`。
- SKILL phase 可以有 `tools/`。
- SUBGRAPH phase 不能有 `actions/` 或 `tools/`。
- 根目录也可以有 root tools。

例子：

```text
phases/prepare/
  LOGIC.md
  actions/
    normalize.py
```

这是允许的。

反例：

```text
phases/prepare/
  LOGIC.md
  tools/
    search.py
```

这会失败，因为 `tools/` 只允许给 SKILL phase 使用。

## 9. LOGIC action 的静态检查

编译器会检查 LOGIC action 的函数签名：第一个参数必须像 `context` 或 `ctx`。

它还会做一层输出 key 检查。根级 output schema 如果声明了输出字段，action 直接返回 dict 时，返回 key 不能超出根级 output schema。

例子：根级 outputs 只声明：

```json
{
  "properties": {
    "summary": {}
  }
}
```

如果 action 返回：

```json
{
  "summary": "ok"
}
```

通过。

如果 action 返回：

```json
{
  "summary": "ok",
  "debug": true
}
```

编译器会拒绝，因为 `debug` 不是根级 output schema 声明字段。

注意：这不是运行时 `StateMapper`。这是编译期对 action 源码的静态检查。

## 10. subagent metadata 怎么编译

如果 Agent / SKILL phase 声明了 subagents，编译器会为每个 subagent 准备 metadata。

当前有两条路径：

- `target_skill`：通过外部 `skill_resolver` 找到 child skill root。
- legacy `path`：按父 skill 内的相对路径找到 child skill root。

找到 child root 后，编译器会递归编译 child skill，读取它的根级 `io.inputs`，并用这个 schema 生成 subagent tool 的入参模型。

例子：child skill 的 input schema 是：

```json
{
  "type": "object",
  "properties": {
    "scene_text": { "type": "string" }
  },
  "required": ["scene_text"]
}
```

父 Agent 之后会得到一个 `call_subagent_xxx` 工具，它要求调用参数像这样：

```json
{
  "inputs": [
    { "scene_text": "A enters." }
  ]
}
```

## 11. mentions 和资源检查

Agent body 里可以出现 reference、example、tool、subagent 等 mention。

编译器会检查这些 mention 是否能在当前 Agent 声明里找到对应对象。

例子：

```text
正文里用了 @reference:R1
```

如果 Agent 声明里没有 id 为 `R1` 的 reference，就会编译失败。

资源文件路径也会被限制在 skill root 内，防止 reference 或 example 逃逸到任意系统路径。

## 12. 编译产物里有什么

`CompiledSkill` 里主要有：

| 字段 | 人话解释 |
|---|---|
| `manifest` | 根图结构：名字、phase 列表、依赖关系、根级 IO。 |
| `nodes` | 每个 phase 解析后的 AST。 |
| `actions` | LOGIC phase 可调用的 action registry。 |
| `tools` | SKILL phase 可调用的 tool registry。 |
| `subagents_by_phase` | 每个 phase 声明的 subagent metadata。 |
| `raw` | 编译器保留的一些原始解析结果和 schema。 |

它不是运行状态，也不是最终输出。运行时会拿它继续装配 LangGraph。

## 13. 最容易误解的点

### 编译不等于运行

编译只证明“目录和声明大体可装配”。它不会证明某次输入一定能成功，也不会调用 LLM。

### inline IO 不是唯一来源

当前源码优先用 inline `io`，但没有 inline 时仍会读物理 JSON schema 文件。

### `mode: skill` 还没彻底消失

`SKILL.md` 当前仍兼容 `mode: skill`。它不是目标态，但它是当前源码事实。

### resolver 只影响 target_skill

声明 `target_skill` 时需要 resolver。legacy `path` 仍会走相对路径。

## 14. 总图

```text
skill root
  -> 检查 GRAPH.md 和 phases/
  -> 解析 GRAPH.md phase DAG
  -> 读取根级 IO schema
  -> 发现 phase 文件
  -> 解析每个 phase AST
  -> 发现 actions/tools
  -> 编译 subagent metadata
  -> 检查 mentions 和路径边界
  -> 返回 CompiledSkill
```
