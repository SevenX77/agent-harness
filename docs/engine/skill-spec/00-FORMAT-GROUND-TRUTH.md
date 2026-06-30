---
status: FROZEN
ssot: graph_skill_format_templates
updated: 2026-06-29
supersedes:
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md inline templates
  - docs/engine/mvp1/_migration-src/
---

# graph_skill 文件格式模板唯一真相源

本文是 `graph_skill` 源文件格式的唯一真相源。Studio、copilot、测试 fixture、loader/compiler、mvp1 文档中的示例和模板都必须以本文为准。

规则很简单：

- 本文列出的字段是合法字段集合；除非某节明确允许扩展，否则未列字段都是非法字段。
- 本规范只定义当前合法字段。`batch:`、phase frontmatter `mode:`、phase frontmatter `phase_id:`、phase frontmatter `phase_config:`、phase frontmatter `node_type:`、`io_inputs_ref`、`io_outputs_ref`、SUBGRAPH `target_skill`、Agent `subgraphs[].target_skill` 均为非法字段。
- phase 类型由物理文件名决定：`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`。作者不写 `mode`。
- phase id 由目录名决定：`phases/<phase_id>/`。作者不在 frontmatter 里写 `phase_id`。
- `io.inputs` / `io.outputs` 是对黑板数据的读写边界。画布和属性面板只忠实展示/编辑这些声明，compile 负责判断声明是否合法。
- 所有路径默认相对当前 skill 根目录解析；绝对路径若被接受，也必须解析后落在当前 skill 根目录内。

## 1. 物理目录

标准目录是一棵树。它同时展示作者编辑的 skill 源码，以及 Studio 默认同址放置的 `.workspace/` 运行时目录。

`.workspace/` 是约定目录名，使用小写。它属于标准物理目录，但不是 skill 源码，不进入 git，compile 不读取它；run、predict、golden eval 等运行期产物才写入这里。

```text
<skill_root>/
  GRAPH.md
  phases/
    <phase_id>/
      LOGIC.md | SUBGRAPH.md | SKILL.md
      actions/          # only LOGIC.md needs it, when local actions are used
      validator.py      # optional, only when validator: true
  subgraph/
    <child_skill_name>/
      GRAPH.md
      phases/
        ...
  references/
  examples/
  .workspace/
    runs/
      <run_id>/
        trace.jsonl
        result.json
        final_state.json
        metrics.json
        artifacts/
    golden/
      <baseline_id>/
        baseline.json
        report.json
        cases/
          <case_id>.json
    test_inputs/
      <input_id>.json
      index.json
    copilot/
      sessions/
        <skill_id>/
          <session_id>.json
          _active.json
      checkpoints/
        <sha(path)>.json
```

合法 phase 文件三选一：同一个 `phases/<phase_id>/` 下只能存在 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 其中一个作为节点定义文件。

运行时规则：

- Studio 默认可以把 Engine `workspace_dir` 传为 `<skill_root>/.workspace/`。其他 host 也可以传入别的绝对路径，但内部户型仍是同一套 `runs/`、`golden/`、`test_inputs/`。
- `run_skill` / `predict_skill` 的输出统一进入 `<workspace_dir>/runs/<run_id>/`。
- `evaluate_golden_baseline` 读写 `<workspace_dir>/golden/<baseline_id>/`。
- 可复用输入样本放在 `<workspace_dir>/test_inputs/`。
- Predict 没有专属 `predict/` 或 `latest_predict.json`。
- golden 是会失效的临时优化产物，不能写进 `phases/<phase_id>/`，也不能作为 skill 源码字段参与 compile。

- Studio Copilot support files live under `<workspace_dir>/copilot/`: sessions in `sessions/<skill_id>/` and edit checkpoints in `checkpoints/`. They are runtime state, not compile input.

## 2. GRAPH.md

`GRAPH.md` 定义一个完整 skill：根元数据、根 IO、phase 注册表、可选图级迭代，以及 body 中的 DAG 连线。

```markdown
---
schema_version: "v0.3.0"
name: story_deconstruction
description: Recursive story deconstruction pipeline.
llm_role: analyst

io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters:
        type: array
        items: {type: object}
  outputs:
    type: object
    required: [report]
    properties:
      report: {type: string}

phases:
  - segmentation
  - event_timeline
  - story_analysis
  - global_synthesis

iterate:
  mode: batch
  over: chapters
  item_var: chapter
  range: [1, 1]
  concurrency: 4
---

<phase depends_on="input">segmentation</phase>
<phase depends_on="segmentation">event_timeline</phase>
<phase depends_on="event_timeline">story_analysis</phase>
<phase depends_on="story_analysis" output>global_synthesis</phase>
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `schema_version` | yes | string, exactly `"v0.3.0"` | 文件格式版本 |
| `name` | yes | string | skill 名称 |
| `description` | no | string | 给人看的说明 |
| `llm_role` | no | string | 整图默认 LLM 角色，Agent phase 可覆盖 |
| `io.inputs` | yes | JSON Schema object | 图入口黑板字段 |
| `io.outputs` | yes | JSON Schema object | 图最终输出字段 |
| `phases` | yes | list[string] | phase id 注册表，必须与 `phases/<phase_id>/` 目录和 body `<phase>` 节点一致 |
| `iterate` | no | IterateSpec | 图级迭代声明，格式见第 7 节 |

body `<phase>` 规则：

| syntax | required | purpose |
| --- | --- | --- |
| `<phase depends_on="input">phase_id</phase>` | yes | 从根 input 连到入口节点 |
| `<phase depends_on="upstream">phase_id</phase>` | yes | 普通依赖边 |
| `<phase depends_on="upstream" output>phase_id</phase>` | no | 标记输出节点 |

`depends_on` 可写 `input` 或已注册 phase id。多依赖用逗号分隔，例如 `depends_on="a,b"`。

## 3. LOGIC.md

`LOGIC.md` 定义确定性代码节点。它声明 IO、action 注册表、validator、可选节点级迭代；body 用 `<action>` 排列执行顺序。

```markdown
---
name: normalize_text

io:
  inputs:
    type: object
    required: [raw_text]
    properties:
      raw_text: {type: string}
  outputs:
    type: object
    required: [normalized_text]
    properties:
      normalized_text: {type: string}

actions:
  - strip_noise
  - normalize_whitespace

validator: false

iterate:
  mode: batch
  over: documents
  item_var: document
  range: [1, 10]
  concurrency: 4
---

<action>strip_noise</action>
<action>normalize_whitespace</action>
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `name` | yes | string | 节点展示名。默认应等于目录 phase id；改名/重命名由 Studio 同步目录完成 |
| `io.inputs` | yes | JSON Schema object | 从黑板切给 action 链的输入字段 |
| `io.outputs` | yes | JSON Schema object | action 链允许写回黑板的输出字段 |
| `actions` | yes | list[string] | action 名注册表 |
| `validator` | no | boolean, default `false` | 是否运行同级 `validator.py` |
| `allow_sequential_overwrite` | no | list[string], default `[]` | 允许本 phase 顺序覆盖上游同名输出字段的白名单，格式见第 10 节 |
| `iterate` | no | IterateSpec | 节点级迭代声明，格式见第 7 节 |

body `<action>` 必须与 frontmatter `actions` 完全一致，并决定实际执行顺序。

LOGIC action 源文件位于 `phases/<phase_id>/actions/<action_name>.py`。文件必须导出同名函数，签名严格为 `def <action_name>(inputs) -> dict`。`inputs` 是只读的 phase-local 输入快照：action 不接收 `context` / `ctx`，不得通过修改 `inputs` 或任何 context 对象写黑板；唯一输出通道是 `return dict`。返回 dict 的 key 必须属于本 phase 的 `io.outputs.properties`。编译期导入 action 不得在 skill 源码目录生成 `__pycache__`。

## 4. SUBGRAPH.md

`SUBGRAPH.md` 定义一个调用子图的普通 phase 节点。它和其他节点一样有 name、IO、validator、iterate；区别只是它用 `path` 指向另一个完整 graph skill 根目录。

```markdown
---
name: producer_review
path: subgraph/producer_reviewer

io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items: {type: object}
  outputs:
    type: object
    required: [review_score]
    properties:
      review_score: {type: number}

validator: false

iterate:
  mode: batch
  over: segments
  item_var: segment
  range: [1, 20]
  concurrency: 4
---
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `name` | yes | string | 节点展示名。默认应等于目录 phase id；改名/重命名由 Studio 同步目录完成 |
| `path` | yes | string path | 子图 skill 根目录，目录内必须有 `GRAPH.md` |
| `io.inputs` | yes | JSON Schema object | 从父图黑板切给子图的输入字段 |
| `io.outputs` | yes | JSON Schema object | 子图返回后允许合并回父图黑板的输出字段 |
| `validator` | no | boolean, default `false` | 是否运行同级 `validator.py` |
| `allow_sequential_overwrite` | no | list[string], default `[]` | 允许本 phase 顺序覆盖上游同名输出字段的白名单，格式见第 10 节 |
| `iterate` | no | IterateSpec | 父图调用这个子图节点时的节点级迭代声明 |

SUBGRAPH 没有 body XML。

`path` 规则：

- 推荐写相对 skill 根目录的路径，例如 `subgraph/producer_reviewer`。
- 绝对路径如果被使用，解析后仍必须在当前 skill 根目录内。
- `target_skill` 不是 SUBGRAPH 新规范字段。
- 父图和子图 IO 不要求字段全集一一相等；只要求各自声明的 `io.inputs` / `io.outputs` 与黑板读写边界一致。

## 5. SKILL.md

`SKILL.md` 定义 Agent phase。frontmatter 声明 IO、角色、工具、可委托子 agent、可引用子图、资料和样例；body 声明 role/goal/steps/protocols/examples。

```markdown
---
name: review_chapter
llm_role: analyst
validator: false
max_iterations: 10

io:
  inputs:
    type: object
    required: [chapter]
    properties:
      chapter: {type: object}
  outputs:
    type: object
    required: [review]
    properties:
      review: {type: string}

tools:
  - read_reference

subagents:
  - name: producer_reviewer
    target_skill: producer_review_skill
    description: Review producer-facing quality.

subgraphs:
  - name: evidence_pipeline
    path: subgraph/evidence_pipeline
    description: Extract supporting evidence before review.

references:
  - id: R1
    path: references/style.md
    summary: Style and scoring rules.

examples:
  - id: E2
    path: examples/boundary_case.md
    summary: Boundary case example.

iterate:
  mode: loop
  over: chapters
  item_var: chapter
  range: [1, 10]
  accumulate:
    var: previous_reviews
    init: []
    from: review
    merge: append
---

<role>你是负责章节审查的分析员。</role>
<goal>产出结构化 review，并解释关键依据。</goal>

<step id="S1" name="read">阅读章节输入。</step>
<step id="S2" name="review">根据协议输出 review。</step>

<protocol id="P1">所有结论必须引用输入证据。</protocol>

<example id="E1">如果证据不足，明确写出不确定性。</example>
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `name` | yes | string | 节点展示名。默认应等于目录 phase id；改名/重命名由 Studio 同步目录完成 |
| `llm_role` | no | string | 覆盖整图默认 LLM 角色 |
| `validator` | no | boolean, default `false` | 是否运行同级 `validator.py` |
| `max_iterations` | no | integer, default `10` | Agent 内层最多轮数 |
| `io.inputs` | yes | JSON Schema object | Agent 可读黑板字段 |
| `io.outputs` | yes | JSON Schema object | Agent 必须通过 `finish_task` 写出的业务字段 |
| `tools` | no | list[string] | 可由 Agent 主动调用的工具名 |
| `subagents` | no | list[SubagentRef] | 运行期由 Agent 委托的子 agent |
| `subgraphs` | no | list[SubgraphRef] | Agent 可引用的子图资源 |
| `references` | no | list[ReferenceRef] | 可查阅资料 |
| `examples` | no | list[ExampleRef] | 可查阅样例文件 |
| `allow_sequential_overwrite` | no | list[string], default `[]` | 允许本 phase 顺序覆盖上游同名输出字段的白名单，格式见第 10 节 |
| `iterate` | no | IterateSpec | 节点级迭代声明，格式见第 7 节 |

Agent phase 必须通过 `finish_task` 写出本 phase 的 `io.outputs`。非终端 Agent 也会把自己的 phase output 写回黑板与 `phase_outputs[phase_id]`；终端 phase 完成后，整图还必须满足 `GRAPH.md` 根 `io.outputs`。

`subagents` 与 `subgraphs` 不是一回事：

```yaml
subagents:
  - name: producer_reviewer
    target_skill: producer_review_skill
    description: Review producer-facing quality.

subgraphs:
  - name: evidence_pipeline
    path: subgraph/evidence_pipeline
    description: Extract supporting evidence before review.
```

- `subagents[].target_skill` 是合法字段，因为 subagent 是运行期委托的 agent skill 引用。
- `subgraphs[].path` 是合法字段，因为 subgraph 是编译/装配期解析的子图路径。
- `subgraphs[].target_skill` 不是新规范字段。

body 顶层标签：

| tag | required | cardinality | purpose |
| --- | --- | --- | --- |
| `<role>` | yes | exactly 1 | Agent 角色 |
| `<goal>` | yes | exactly 1 | Agent 目标 |
| `<step id="..." name="...">` | no | 0..N | 建议步骤 |
| `<protocol id="...">` | no | 0..N | 必须遵守的协议 |
| `<example id="...">` | no | 0..N | inline 示例 |

禁止写 `<steps>` / `<protocols>` / `<examples>` 外壳标签；禁止在 `SKILL.md` body 写 `<exit_contract>`。

### Validator runtime contract

`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 的 `validator: true` 表示运行期加载同级 `validator.py`。该文件必须导出 `validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。

- 返回 `None` 表示通过，输出保持不变。
- 返回 `dict` 表示通过并富集/修正输出；该 dict 必须再次通过本 phase 的 `io.outputs` schema gate，且不得写出未声明 key。
- 抛出异常、返回非 `None`/`dict`，或返回 dict 未通过 schema gate，均转成对应节点类型的 `[F-v3-*-validator-failed]` fatal。

## 6. IO Schema

所有 `io.inputs` / `io.outputs` 必须是 JSON Schema object：

```yaml
io:
  inputs:
    type: object
    required: [field_a]
    properties:
      field_a: {type: string}
  outputs:
    type: object
    required: [field_b]
    properties:
      field_b: {type: string}
```

要求：

- 顶层 `type` 必须是 `object`。
- `properties` 必须存在。
- `required` 如果存在，只能引用 `properties` 中已有字段。
- 不再使用外部 `io/inputs.json`、`io/outputs.json`、`io_inputs_ref`、`io_outputs_ref`。

## 7. IterateSpec

`iterate` 是唯一合法的循环声明字段，可出现在 `GRAPH.md` 或任一 phase frontmatter。

### 7.1 batch

```yaml
iterate:
  mode: batch
  over: chapters
  item_var: chapter
  range: [1, 10]
  concurrency: 4
```

### 7.2 loop

```yaml
iterate:
  mode: loop
  over: chapters
  item_var: chapter
  range: [1, 10]
  accumulate:
    var: previous_result
    init: []
    from: result
    merge: append
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `mode` | yes | `"batch"` or `"loop"` | 并发 map 或串行累积 |
| `over` | yes | string | 黑板中被迭代的数组字段路径 |
| `item_var` | yes | string | 每轮注入当前 item 的字段名 |
| `range` | no | two-item integer list | 闭区间切片，例如 `[1, 10]` |
| `concurrency` | batch only, optional | integer >= 1 | batch 并发上限 |
| `accumulate` | loop required | object | loop 累积声明 |

`accumulate` 字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `var` | yes | string | 每轮注入的累积变量名 |
| `init` | yes | any serializable value | 累积初始值 |
| `from` | yes | string | 从本轮输出的哪个字段取增量 |
| `merge` | yes | `"append"`, `"extend"`, `"merge"`, or `"replace"` | 累积合并策略 |

`batch:` 不是新规范字段。`iterator:` 不是新规范字段，应使用 `over`。

## 8. Mention 与资源引用

Agent body 可以引用已声明资源：

```text
@tool:read_reference
@subagent:producer_reviewer
@subgraph:evidence_pipeline
@reference:R1
@example:E1
@example:E2
@protocol:P1
```

静态可达性：

- `@tool:<name>` 必须存在于 `tools`。
- `@subagent:<name>` 必须存在于 `subagents[].name`。
- `@subgraph:<name>` 必须存在于 `subgraphs[].name`。
- `@reference:<id>` 必须存在于 `references[].id`。
- `@example:<id>` 可以来自 body inline `<example id>` 或 frontmatter `examples[].id`。
- `@protocol:<id>` 必须存在于 body `<protocol id>`。

## 9. Properties Panel 映射

Studio Properties 面板必须从本文模板推导可编辑字段：

- 面板显示的是对应 `.md` 文件 frontmatter YAML 字段，而不是编译后的内部 AST。
- 只展示新规范字段，不展示 `phase_id`、`node_type`、frontmatter `mode` 等内部推导值。
- `name` 可以改，但应通过重命名动作完成，同步目录名与引用，而不是普通文本框直接写。
- `path` 可以改，但应通过选择/重连已有子图目录完成，而不是让用户手输一个可能不存在的路径。
- `io` 属于 Input/Output 专门面板；Properties 可以显示入口或跳转，但不应在普通属性表单里重复维护整块 schema。
- `allow_sequential_overwrite` 在每个 phase 节点（LOGIC / SUBGRAPH / SKILL）的 Properties 表单里编辑，每行一个输出字段名；面板可依据上游 phase 的 `io.outputs` 给出候选勾选。语义见第 10 节。

## 10. allow_sequential_overwrite

`allow_sequential_overwrite` 是 phase frontmatter 字段，可出现在 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`，不是 `GRAPH.md` 根字段。它是一个输出字段名白名单，类型 `list[string]`，默认 `[]`。

compile 会检查每个 phase 的 `io.outputs` 声明字段是否与其**上游祖先 phase**（传递依赖的上游）已声明的输出字段重名。重名意味着本 phase 会顺序覆盖上游写入黑板的同名字段：默认这是非法的，compile 失败并报 `[F-v3-sequential-overwrite-unauthorized]`；只有把该字段名显式列进本 phase 的 `allow_sequential_overwrite`，才放行这次覆盖。

```yaml
# phases/refine/LOGIC.md
name: refine
io:
  outputs:
    type: object
    required: [draft]
    properties:
      draft: {type: string}      # 上游某祖先 phase 也输出 draft
actions:
  - refine_draft
allow_sequential_overwrite:
  - draft                         # 明确允许覆盖上游的 draft
```

字段：

| field | required | type | purpose |
| --- | --- | --- | --- |
| `allow_sequential_overwrite` | no | list[string], default `[]` | 列出本 phase 允许覆盖的上游同名 `io.outputs` 字段名 |

规则：

- 只对与**祖先 phase**输出字段重名的情况触发；与并行/非祖先 phase 同名不触发。
- 列表元素必须是本 phase `io.outputs.properties` 中存在的字段名。
- 不声明就重名 → compile 失败，错误码 `[F-v3-sequential-overwrite-unauthorized]`。
