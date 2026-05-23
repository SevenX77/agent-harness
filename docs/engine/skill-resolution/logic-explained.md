# skill-resolution 运行逻辑人话版

署名：Codex  
日期：2026-05-23  
定位：只解释当前 skill 解析边界真实怎么运行，不做源码导览，不讲实现写法。

## 1. 一句话结论

`skill-resolution` 只回答一个问题：

> 给定一个稳定的 `skill_id`，Engine 怎么通过外部注入的 resolver 找到本地 skill 根目录？

它不解析 `GRAPH.md`，不读取 Studio registry，不弹文件选择器，也不决定 phase 怎么运行。它只定义 Engine 和外部 registry 之间的最小协议。

## 2. 核心术语

### skill_id

`skill_id` 是跨 skill 引用用的稳定名字。

例如一个 Agent phase 声明了 subagent：

```yaml
subagents:
  - name: echo
    target_skill: demo.echo_agent
    description: Echo input text.
```

这里的 `demo.echo_agent` 就是 `skill_id`。Engine 不会自己猜它在磁盘哪里，而是把这个 id 交给 resolver。

### SkillResolverProtocol

`SkillResolverProtocol` 是一个很小的接口：外部对象只要提供 `resolve_skill(skill_id)`，就能被 Engine 用来解析 skill。

人话就是：

```text
Engine: demo.echo_agent 在哪？
resolver: 在 /path/to/echo_agent
Engine: 我检查这个目录能不能作为 skill root
```

### SkillResolutionError

解析失败时会抛 `SkillResolutionError`。它会带上 `skill_id`、失败原因和错误码。

常见失败包括：

- `skill_id` 格式不合法。
- resolver 找不到这个 skill。
- resolver 返回的路径不是目录。
- resolver 返回的目录没有 `GRAPH.md`。

## 3. 一次解析怎么走

一次解析大致是这样：

1. 编译或运行遇到 `target_skill`。
2. Engine 检查这个 id 的格式。
3. Engine 调用外部传进来的 resolver。
4. resolver 返回一个本地路径。
5. Engine 确认这个路径是目录。
6. Engine 确认目录里有 `GRAPH.md`。
7. 通过后，把这个目录交给编译器继续编译 child skill。

例子：

```text
target_skill = "demo.echo_agent"
resolver 返回 "/skills/echo_agent"

如果 /skills/echo_agent 是目录，并且里面有 GRAPH.md：
  解析成功

如果 /skills/echo_agent 不存在：
  解析失败
```

## 4. skill_id 怎么校验

当前 `skill_id` 允许字母、数字、下划线、点、短横线。

这些是合法例子：

```text
demo.echo_agent
story-tools.segmenter
team_1.extractor
```

这些会被拒绝：

```text
/absolute/path/to/skill
../escape
demo echo
```

原因很简单：`skill_id` 不是路径。它是 registry key。路径只能由 resolver 返回。

## 5. resolver 返回值怎么校验

resolver 可以返回字符串路径，也可以返回 Path-like 路径。Engine 会把它规整成本地路径，然后做两个检查：

1. 必须是目录。
2. 必须包含 `GRAPH.md`。

例子：

```text
resolver 返回 /skills/echo_agent

/skills/echo_agent/
  GRAPH.md
  phases/
    echo/
      SKILL.md

=> 通过
```

反例：

```text
resolver 返回 /skills/echo_agent/SKILL.md

=> 失败，因为返回的是文件，不是 skill root 目录
```

再一个反例：

```text
resolver 返回 /tmp/some_folder

/tmp/some_folder/
  README.md

=> 失败，因为没有 GRAPH.md
```

## 6. 它在编译和运行里怎么被用到

当前有几条路径会把 `skill_resolver` 继续往下传：

- 公开编译入口接收 `skill_resolver`，并传给 loader。
- 运行入口接收 `skill_resolver`，并传给编译和 graph assembly。
- loader 在编译 Agent subagent metadata 时，如果看到 `target_skill`，会用 resolver 找到 child skill root。
- graph assembly 在装配 subagent runtime 时，也会继续传 resolver，让 child graph 的编译保持同一套解析规则。

这保证了一个原则：父 skill 怎么找到 child skill，不由 skill 文件里的本地路径暗箱决定，而由外部注入的 registry 边界决定。

## 7. 当前仍兼容 legacy path

当前源码里，subagent 声明既可以有 `target_skill`，也保留了 legacy `path`。

如果声明了 `target_skill`，必须传入 resolver。没有 resolver 就会失败。

如果没有 `target_skill`，但有 legacy `path`，当前仍会走相对路径解析。也就是说，“所有跨 skill 引用都必须只用 `target_skill`”还不是完全落地的当前行为。

例子：

```yaml
subagents:
  - name: echo
    path: subskills/echo_agent
    description: Echo text.
```

这种写法当前仍可能被接受，只要路径在父 skill 根目录内，并且目标目录存在 `GRAPH.md`。

## 8. 它不负责什么

`skill-resolution` 不负责这些事：

- 不解析 child skill 的 `GRAPH.md`。
- 不校验 child skill 的 phase DAG。
- 不决定 subagent 是否会被 LLM 调用。
- 不负责 `llm_role` 到模型的解析。
- 不读取 Studio 的 registry 文件。
- 不做 UI 导入、弹窗、路径选择。

它只负责把 `skill_id` 安全地变成本地 skill root。

## 9. 最容易误解的点

### `skill_id` 不是文件路径

`demo.echo_agent` 是 registry key，不是磁盘路径。把 `/home/user/skill` 当成 `skill_id` 会被格式校验挡住。

### resolver 不是编译器

resolver 只返回目录。目录里面是否合法，要交给编译器继续检查。

### 没传 resolver 不一定所有情况都失败

如果 skill 没有用 `target_skill`，或者仍用了 legacy `path`，当前源码可能不需要 resolver。只有遇到 `target_skill` 时，resolver 才是必需边界。

## 10. 总图

```text
target_skill
  -> 校验 skill_id 格式
  -> 调 resolver.resolve_skill(skill_id)
  -> 得到本地路径
  -> 检查是目录
  -> 检查有 GRAPH.md
  -> 交给 loader 编译 child skill
```
