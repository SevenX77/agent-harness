---
module: 01-contract/02-skill-syntax
doc: mvp1-alignment
status: drafted（mvp1 自写=唯一真理；子图 path=绝对路径已写清；GRAPH/LOGIC/SUBGRAPH/AGENT/cognitive/mention/resource(§2.8) 语法已迁入；🚨 iterate/io 切片仍是真空债，见 §2/§8）
binds_baseline: ./baseline.md
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 02-skill-syntax — 契约 A · skill 文件内容/语法

> **Tier**: 契约层 A(声明式,喂 copilot) | **Owns**: skill 文件**里写什么**——四 phase(GRAPH/LOGIC/SUBGRAPH/SKILL)字段 schema + body XML + mention + io/iterate 声明 + cognitive 模板语法 | **现状**: 子图 path 已写清(§2.1);GRAPH/LOGIC/SUBGRAPH/AGENT/cognitive/mention 语法已迁入(§2.2-§2.7);🚨 resource/iterate/io 切片仍待补(§8) | **Related**: `physical-layout`(文件放哪)· `compile-rules`(怎么判)· `02-mechanism/02-resolver`(path 怎么解析)· `02-mechanism/03-assemble`(模板渲染)· `02-iterate`(iterate 执行)

## 1. 定义
定义 skill 文件**内容/语法**:每种文件的 frontmatter 字段、body 格式、`@type:NAME` mention 语法、io/iterate 声明。**只管"写什么"**,不管"放哪"(归 `physical-layout`)、"怎么判"(归 `compile-rules`)、"怎么解析引用"(归 `02-resolver`)。是喂 copilot 生成合法 skill 的核心语言。

> **唯一真理在 mvp1**:本文是 skill 语法的权威定义。旧 `docs/engine/mvp0/skill-spec/*` 已弃用,**不得作为 SSOT(唯一真相源)引用**;mvp1 没写或写错 = 缺陷,按 §2 / §8 🚨 报警、必须在 mvp1 补齐,**不允许回退 mvp0「补全」**。

## 2. 语法部件清单 + mvp1 写入状态
| 语法部件 | mvp1 写入状态 |
|---|---|
| **SUBGRAPH 子图 path 引用** | ✅ 已写清,见 §2.1 |
| GRAPH.md frontmatter + DAG + 根 io | ✅ 已迁入,见 §2.2 |
| LOGIC.md(action 寻址 + validator 生命周期) | ✅ 已迁入,见 §2.3；action 契约按 V4 干净契约反转 |
| SUBGRAPH.md(name/validator/io/path 字段表) | ✅ path 见 §2.1；其余语法见 §2.4 |
| SKILL.md(Agent frontmatter + body XML + 引用注入) | ✅ 已迁入,见 §2.5；其 `subgraphs[]` 引用按 §2.1 用绝对 path |
| cognitive 模板(8 槽布局) | ✅ 已迁入,见 §2.6；仅管模板语法,渲染机制见 `02-mechanism/03-assemble` |
| mention `@type:NAME`(7 类) | ✅ 已迁入,见 §2.7 |
| reference/example 机制 | ✅ 已写清,见 §2.8 |
| iterate 声明(batch/loop/range/accumulate) | 🚨 **真空**(执行见 `04-run-outer/02-iterate`) |
| io 切片声明(从黑板切片) | 🚨 **真空**(切片见 `04-run-outer/01-graph-exec`) |
> 🚨 上述「真空」部件是 **mvp1 的债**:语法正文还没从旧文档迁进 mvp1。mvp0 弃用后这些就是真空,**必须在 mvp1 自写补齐**(这正是"mvp1 没有=错误"的报警点,见 §8)。本批已补 GRAPH/LOGIC/SUBGRAPH/AGENT/cognitive/mention + resource(§2.8);剩余 iterate/io 切片继续报警。
> ❌ **无 golden 声明**:golden 是 `.workspace` 临时产物,不进 skill 源码语法。

## 2.1 子图 path 引用契约(mvp1 权威)
子图 = 一个 phase 委托**另一个完整 graph skill** 执行。引用它用 **path**(直接写子图文件夹的**绝对路径**),无注册表、直接解析。

> **只管子图,不含子代理**:本节是**子图**(SUBGRAPH 节点 + agent `subgraphs[]`,编译期解析的独立 graph skill)。agent 的 **`subagents[]`(子代理)是另一回事**——它与 agent phase 捆绑、运行期由 LLM 委派(生命周期不同),**不在此列、不改 path**(见 §8.3)。

### 字段
- **`SUBGRAPH.md` frontmatter `path`**:`path: <子图文件夹的绝对路径>`,指向含 `GRAPH.md` 的子图根目录。
- **agent `SKILL.md` 的 `subgraphs[].path`**:agent phase 里登记的子图,每项同样写**绝对** `path`。

### path = 绝对路径(物理地址)
path 写**绝对路径**,不是相对路径。原因:
- **要能"随便放哪里"**:绝对路径是确定的物理地址,子图放磁盘任何位置都能被定位;相对路径会把子图**绑死在某个基准目录、一移动就失效**,做不到"随便放"。
- **直接解析**:绝对路径本身就是地址,引擎直接打开,**无需任何 id→路径 的注册表查找**。
- **copilot 可达**:copilot 的工作目录范围**必须包含**这个子图 path,否则 copilot 看不到、也编辑不了该子图。

### io(子图节点像普通节点)
子图节点的 `io.inputs` 从黑板(`WorkflowState.data`,节点间共享状态)按自己声明**切片过滤**取字段,`io.outputs` 合并回黑板——和任何普通节点一样。**不要求**父图与子图的字段集合一一对应。

### 默认落点
新建子图默认放在引用方 skill 根目录的 `subgraph/` 文件夹下(`<skill_root>/subgraph/<name>/`),递归自包含——详见 `01-physical-layout` §2.1。但 `path` 字段始终写**绝对路径**,所以子图也可放工作区内任意位置。

> registry / 逻辑 id 寻址是早期已废弃方案,mvp1 不再使用。解析机制(绝对 path → 校验落在 copilot 工作目录边界内 → 子图 root)写在 `02-mechanism/02-resolver`;默认物理落点写在 `01-physical-layout` §2.1。

## 2.2 GRAPH.md 根语法契约
`GRAPH.md` 是 graph skill 根节点,声明整图元数据、phase 注册表、body DAG 拓扑和根 io。它只允许出现在 skill 根目录；phase 目录内出现 `GRAPH.md` 归 `physical-layout`/`compile-rules` 判错。

### 2.2.1 基础元数据字段
`GRAPH.md` frontmatter 未知字段编译期 FATAL；错误码全集不在本文重复,见 [`03-compile-rules` §4 graph domain](../03-compile-rules/mvp1-alignment.md#graph-domain)。

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`；小写字母开头,仅含 `[a-z0-9_-]` | skill 唯一标识与 trace/展示名基础 |
| `schema_version` | string | 是 | 无 | 精确匹配 `"v0.3.0"`；必须是带 `v` 的字符串 | 引擎版本断言,错版本编译期立即失败 |
| `llm_role` | string | 否 | `"analyst"` | 必须是 `llm_roles.yaml` 内已注册角色 | 整图默认 LLM 角色；Agent phase 可 override |
| `description` | string | 否 | `""` | 自由文本 | 文档说明,不参与执行 |

### 2.2.2 phases 注册 + body DAG 拓扑
GRAPH.md 使用双轨制:
- frontmatter `phases:` 只注册 phase 名字。
- body `<phase>` XML 描述 DAG 拓扑。
- frontmatter、body、物理目录 `phases/<name>/` 三者必须一致。

```yaml
schema_version: "v0.3.0"
phases: [extract_chapter, segment_text, producer_review]
```

```xml
<phase depends_on="input">extract_chapter</phase>
<phase depends_on="extract_chapter">segment_text</phase>
<phase depends_on="segment_text" output>producer_review</phase>
```

| 元素 | 类型 | 必填 | 语法/校验规则 |
|---|---|---|---|
| frontmatter `phases` | list[string] | 是 | 每项同 phase id 规则 `^[a-z][a-z0-9_-]*$`；列表内不能重复；每项必须有对应 `phases/<name>/` 物理目录 |
| body `<phase>` 文本 | string | 是 | 必须等于 frontmatter 注册名,并等于物理目录名 |
| body `depends_on` | string | 是 | 入口节点写保留字 `input`；其他节点引用已注册 phase；多依赖用空格或逗号分隔 |
| body `output` 属性 | flag | 否 | 标记结束节点,可多个；未显式标记时,以无下游节点推导输出候选 |

编译期 DAG 校验必须覆盖:
1. **唯一性**:`phases` 列表和 body `<phase>` name 均不能重复。
2. **双轨一致**:frontmatter `phases` 集合、body `<phase>` name 集合、`phases/<name>/` 目录集合必须相等。
3. **依赖可达**:`depends_on` 只能写 `input` 或已注册 phase。
4. **无环**:按 DAG 做拓扑排序；检测到环必须报出环路径。
5. **无孤岛**:从 `depends_on="input"` 入口不可达的 phase 是孤岛。
6. **物理节点唯一**:每个 `phases/<name>/` 目录下必须在 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 中恰好选择一个节点文件；多选或缺失归 `physical-layout`/`compile-rules`。

### 2.2.3 根 IO 契约
`GRAPH.md` frontmatter `io:` 必填,包含 `inputs` 与 `outputs` 两个子字段,均为 JSON Schema object(Draft 2020-12)。mvp1 只允许 **inline frontmatter IO**；旧物理文件 `io/inputs.json`、`io/outputs.json` 或旧字段 `io_inputs_ref`、`io_outputs_ref` 均已废弃。

```yaml
io:
  inputs:
    type: object
    required: [chapter_path]
    properties:
      chapter_path:
        type: string
        description: 小说章节文件路径
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items: {type: object}
```

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 |
|---|---|---|---|---|
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type` 必须为 `"object"`；必须含 `properties`；Draft 2020-12 解析通过 |
| `io.outputs` | JSON Schema object | 是 | 无 | 同 `io.inputs` |
| `io_inputs_ref` | — | 禁止 | — | 使用即编译期 FATAL；改写为 inline `io.inputs` |
| `io_outputs_ref` | — | 禁止 | — | 使用即编译期 FATAL；改写为 inline `io.outputs` |

### 2.2.4 静态数据流校验
Loader 以根 `io.inputs` 作为 graph 入口字段源,按 DAG 拓扑遍历每个 phase 的 `io.inputs.required`。每个必填字段必须来自:
- 根 `io.inputs.properties`,或
- 任一上游 phase 的 `io.outputs.properties`。

来源缺失时,编译结果必须能定位 `phase_id`、`field_name` 和候选上游。错误码归 [`03-compile-rules` §4 graph domain](../03-compile-rules/mvp1-alignment.md#graph-domain)。

## 2.3 LOGIC.md 语法契约
`LOGIC.md` 表示不进入 ReAct 循环的确定性执行节点。节点类型由物理文件名 `LOGIC.md` 推导,Loader 注入内部 `mode="logic"`；作者不得在 frontmatter 写 `mode:`。未知字段编译期 FATAL；错误码全集见 [`03-compile-rules` §4 logic domain](../03-compile-rules/mvp1-alignment.md#logic-domain)。

### 2.3.1 Frontmatter 字段
```yaml
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
validator: true
---
```

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`；建议与 phase id 一致,不一致只 WARN | Trace、错误定位和 Studio 节点展示名 |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`；含 `properties`；`required` 只能引用已有 properties | 声明从 blackboard 切给 action 链的只读 state slice |
| `io.outputs` | JSON Schema object | 是 | 无 | 同 `io.inputs`；action/validator 返回字段必须是 `properties` 子集 | 声明 action 链最终允许回写 blackboard 的字段边界 |
| `actions` | list[string] | 是 | 无 | 非空；每项正则 `^[a-z][a-z0-9_]*$`；不允许路径分隔符；按列表顺序执行 | 注册确定性 Python action 的执行顺序 |
| `validator` | boolean | 否 | `false` | 必须是 YAML boolean,不能用 `"true"` 字符串 | 开启后置校验钩子,用于阻断脏输出回写 |

`io` 的业务含义不是重复根 IO,而是 StateMapper 的切片尺:运行期只把 `io.inputs.properties` 中声明的字段传给本 Logic phase,并只允许 `io.outputs.properties` 声明的字段写回 blackboard。

### 2.3.2 body `<action>` 拓扑
frontmatter `actions:` 是注册表,body `<action>name</action>` 是调用顺序。两者必须完全一致,包括顺序；未在 frontmatter 注册的 action 不能被 body 调用,frontmatter 注册但 body 未调用也不合法。

```xml
<action>strip_noise</action>
<action>normalize_whitespace</action>
```

### 2.3.3 Action 寻址与 V4 干净执行契约
action 来源支持两类:
1. 当前 logic phase 路径下 `actions/<action_name>.py`。
2. Studio 或 Engine 内注册的通用 action registry。

`actions:` 只能注册一级 action 名字,不允许 `./actions/foo.py`、`pkg.module:function` 或多级目录。

| 项 | mvp1 契约 |
|---|---|
| 解析根 | 当前 logic phase 目录 `<skill_root>/phases/<phase_id>/` + Engine/Studio 通用 action registry |
| 物理目录 | `<skill_root>/phases/<phase_id>/actions/` 可选；当 action 不在通用 registry 时必须存在 |
| 文件名 | `<action_name>.py` |
| 导出函数 | `def <action_name>(inputs) -> dict`；函数名必须等于 action 名 |
| 入参 | `inputs` 是按 `io.inputs` 从 blackboard 切出的浅 dict,对 action 只读 |
| 返回值 | dict；key 必须是 `io.outputs.properties` 子集 |
| 执行顺序 | 严格按 body `<action>` 标签从上到下串行执行；上一个 action 的返回合并进下一次 action 的 `inputs` |
| 纯净性约束 | action 是确定性纯变换；禁止直接写 blackboard、`run_skill` 编排、文件系统读写/变更、`sys.path` hack、import 越界、返回非序列化对象 |

> **V4 反转点**:旧 `run(state_slice/context)` 或可变 `Context` mutation 不是 mvp1 契约。LOGIC 的权威运行决策在 `04-run-outer/01-graph-exec` LE1-3；本文只把该运行决策反写成 skill 语法。

Action 与 Tool 的边界固定:

| 概念 | 谁触发 | 所属节点 | 是否进 ReAct | 业务语义 |
|---|---|---|---|---|
| Action | Engine 静默执行 | `LOGIC.md` | 否 | 确定性代码步骤,适合解析、转换、校验、入库等稳定逻辑 |
| Tool | LLM 主动调用 | Agent `SKILL.md` | 是 | Agent 在推理过程中按需调用的能力,例如 `read_reference` / `read_example` |

### 2.3.4 Validator 生命周期
`validator: true` 表示 action 链全部完成后、结果写回 blackboard 之前,Engine 必须执行同级物理文件 `validator.py`。

```text
<skill_root>/phases/<phase_id>/
  LOGIC.md
  actions/
    strip_noise.py
  validator.py
```

| 字段/文件 | 类型 | 必填条件 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `validator` | boolean | 否 | `false` | `true` 时必须存在同级 `validator.py`；`false` 时忽略同级文件 | 声明是否启用后置强校验 |
| `validator.py` | Python file | `validator: true` | 无 | 必须导出 `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict` | 在回写前检查 action 输出完整性和业务不变量 |

触发顺序:
1. StateMapper 按 `io.inputs` 切出 `state_slice`。
2. Engine 串行执行全部 actions,得到 `candidate_output`。
3. 若 `validator: true`,调用 `validate(candidate_output, state_slice, phase_id=..., trace_id=...)`。
4. validator 成功返回 `None` 时沿用 `candidate_output`;返回 dict 时以该 dict 作为最终输出,仍必须满足 `io.outputs`。
5. validator 抛错或返回非法字段时,本 phase FATAL,`candidate_output` 不写回 blackboard。

## 2.4 SUBGRAPH.md 其余语法契约(path 之外)
`SUBGRAPH.md` 表示当前 phase 委托另一个完整 graph skill 执行。节点类型由物理文件名 `SUBGRAPH.md` 推导,Loader 注入内部 `mode="subgraph"`；作者不得在 frontmatter 写 `mode:`。path 寻址契约见 §2.1,本节只补 `name` / `validator` / `io` 等字段规则。

### 2.4.1 Frontmatter 字段
```yaml
---
name: producer_review
path: /absolute/path/to/producer_reviewer
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [review_score]
    properties:
      review_score: {type: number}
validator: false
---
```

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` | Trace 与 Studio 展示名 |
| `path` | absolute path string | 是 | 无 | 必须是子图 skill 根目录绝对路径；详细寻址见 §2.1 | 指向被调用的 graph skill |
| `validator` | boolean | 否 | `false` | 必须是 YAML boolean,不能用 `"true"` 字符串 | 声明是否对本 subgraph phase 的候选输出启用后置校验 |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`；含 `properties`；`required` 只能引用已有 properties | 声明父图从 blackboard 切给子图调用的字段边界 |
| `io.outputs` | JSON Schema object | 是 | 无 | 同 `io.inputs`；子图返回父图的字段必须是 `properties` 子集 | 声明子图完成后允许合并回父图 blackboard 的字段边界 |

### 2.4.2 Loader 拦截规则
1. 扫描 `phases/<id>/` 时发现 `SUBGRAPH.md`,节点类型锁定为 `subgraph`。
2. Loader 将内部 AST discriminator 注入为 `mode="subgraph"`。
3. 若同目录还存在 `LOGIC.md` 或 `SKILL.md`,由 `physical-layout`/`compile-rules` 报 phase mode ambiguous。
4. `SUBGRAPH.md` 没有 body 拓扑；整图拓扑只能写在根 `GRAPH.md`。

### 2.4.3 IO 切片与合并规则(mvp1 放宽)
SUBGRAPH phase 的 `io` 与普通节点一致,是 blackboard 的切片/回写边界:
- `io.inputs` 只声明父图传入子图调用的字段集合；运行期从父图 blackboard 过滤得到子图初始输入。
- `io.outputs` 只声明子图完成后允许合并回父图 blackboard 的字段集合。
- 父图 `SUBGRAPH.md io` 与子图 `GRAPH.md io` **不要求字段集合 1:1 相等**,也不要求 required 集合或同名 schema 结构完全一致。
- 若子图运行需要的 required 字段在父图切片中不存在,由 StateMapper/运行期 state mapping 报错；不在语法层强制父子镜像。

这条是 mvp1 对旧 `target_skill + 父子 io 1:1` 模型的反转:子图节点像普通节点,只通过 blackboard slice/merge 接入。

## 2.5 AGENT `SKILL.md` 语法契约
Agent `SKILL.md` 是进入 LLM ReAct 循环的 phase 节点。节点类型由物理文件名 `SKILL.md` 推导,Loader 注入内部 `mode="agent"`；作者不得在 frontmatter 写 `mode:`。frontmatter 只放框架装配配置,业务 prompt 内容放在 body XML。未知字段编译期 FATAL；错误码全集不在本文重复,见 [`03-compile-rules` §4 agent domain](../03-compile-rules/mvp1-alignment.md#agent-domain)。

### 2.5.1 Frontmatter 字段
```yaml
---
name: producer_review
llm_role: reviewer
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [review_md]
    properties:
      review_md: {type: string}
tools:
  - read_reference
subagents:
  - name: producer_reviewer
    target_skill: producer_reviewer
    description: Review story production quality
subgraphs:
  - name: review_graph
    path: /absolute/path/to/review_graph
    description: Run the structured review graph
references:
  - id: R1
    path: references/style.md
    summary: Style guide
examples:
  - id: E1
    path: examples/good-review.md
    summary: High quality review example
max_iterations: 10
validator: false
---
```

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` | Trace、Studio 展示和 prompt 诊断名 |
| `llm_role` | string | 否 | 继承 `GRAPH.md llm_role`,再无则 `"analyst"` | 必须存在于 `llm_roles.yaml` | 路由 LLM tier/model policy,不是 prompt 文案 |
| `validator` | boolean | 否 | `false` | 必须是 YAML boolean,不能用 `"true"` 字符串 | 结合 `validator.py` 控制 Agent 输出后置校验 |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`;含 `properties`;`required` 只能引用已有 properties | StateMapper 切给 Agent 的输入边界 |
| `io.outputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`;含 `properties`;finish_task 输出必须满足该 schema | finish_task 输出强校验 schema |
| `tools` | list[string] | 否 | `[]` | 每项正则 `^[a-z][a-z0-9_]*$`;必须是 builtin 或 tool registry 已注册名 | 暴露给 Agent ReAct 循环主动调用 |
| `subagents` | list[object] | 否 | `[]` | 每项含 `name`、`target_skill`、`description`;`name` 供 `@subagent:NAME` 引用 | 注册可委托的 Agent 子技能 |
| `subgraphs` | list[object] | 否 | `[]` | 每项含 `name`、`path`、`description`;`path` 必须是子图 skill 根目录绝对路径,见 §2.1 | 注册 Agent 可引用或说明的子图资产 |
| `references` | list[object] | 否 | `[]` | 每项含 `id`、`path`、`summary`;`id` 正则 `^[A-Z][A-Za-z0-9_-]*$` | 装配期预读 + runtime `read_reference` 索引 |
| `examples` | list[object] | 否 | `[]` | 每项含 `id`、`path`、`summary`;只注册 document 扩展案例库 | runtime `read_example` 索引 |
| `max_iterations` | integer | 否 | `10` | `1 <= max_iterations <= 50` | 限制 ReAct 循环最大轮数,防止失控调用 |

### 2.5.2 `subagents[]` / `subgraphs[]` 子项字段
`subagents[]` 与 `subgraphs[]` 不是同一类生命周期:
- `subagents[]` 是 Agent phase 内层可委派的子 Agent,保持 `target_skill` 逻辑 skill id；它与 agent phase 捆绑,不按子图 path 反转。
- `subgraphs[]` 是 Agent 可引用的子图资产,按 §2.1 使用绝对 `path`,不再使用 mvp0 的 `target_skill`。

`subagents[]` 子项:

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`;同列表内唯一 | Body 中 `@subagent:NAME` 的本地引用名 |
| `target_skill` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`;必须可被 subagent 机制解析 | 指向可委派的 Agent 子技能 |
| `description` | string | 是 | 无 | 非空 | 给 LLM 和 Studio 自动补全展示用途 |

`subgraphs[]` 子项:

| 字段 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`;同列表内唯一 | Body 中 `@subgraph:NAME` 的本地引用名 |
| `path` | absolute path string | 是 | 无 | 必须是子图 skill 根目录绝对路径;解析边界见 §2.1 / `02-resolver` | 指向可引用或说明的子图资产 |
| `description` | string | 是 | 无 | 非空 | 给 LLM 和 Studio 自动补全展示用途 |

### 2.5.3 Body XML 扁平化容器
`SKILL.md` frontmatter 后的 Markdown body 必须是 XML fragment 集合,顶层平铺,不允许 `<steps>`、`<protocols>`、`<skill>` 这类壳节点。允许的顶层标签只有 5 类:

| 标签 | 属性 | 数量 | 是否必填 | AST 去向 |
|---|---|---|---|---|
| `<role>` | 无 | 1 | 是 | `{skill_role}` |
| `<goal>` | 无 | 1 | 是 | `{skill_goal}` |
| `<step>` | `id`, `name` | 0..N | 否 | `{skill_steps_splat}` |
| `<protocol>` | `id` | 0..N | 否 | `{skill_protocols_splat}` 与 `@protocol` 可达域 |
| `<example>` | `id` | 0..N | 否 | `{skill_examples_inline}` |

解析行为:
1. Loader 把 body 当 XML fragment 解析,可通过临时根节点包裹实现解析,但临时根不进入 AST。
2. 顶层标签必须在允许列表内；未知顶层标签 FATAL。`<exit_contract>` 禁止出现在 SKILL.md body,因为 exit contract 只由 cognitive template hardcode。
3. `<step>` 必须有 `id` 与 `name`;`<protocol>` / `<example>` 必须有 `id`;id 正则 `^[A-Z][A-Za-z0-9_-]*$`。
4. `<step>` / `<protocol>` / `<example>` 的 id 在各自命名空间内唯一。
5. 标签正文允许普通 Markdown 文本和 `@type:NAME` mention;不允许嵌套另一个顶层业务标签。

禁止示例:

```xml
<steps>
  <step id="S1" name="parse">...</step>
</steps>
```

禁止 `<steps>` 壳的原因是 cognitive template 已经提供固定容器。SKILL.md body 只提供业务原子块,Loader 直接把 AST splat 到模板插槽,不再猜测壳节点语义。

### 2.5.4 必须持有的业务核心标签
`<role>` 和 `<goal>` 是 Agent prompt 的业务身份与完成目标,不是可选描述。缺任一项时 Loader 不能退化成通用 Agent,必须 FATAL。

| 标签 | 必填 | 数量 | 内容规则 | 业务作用 |
|---|---|---|---|---|
| `<role>` | 是 | 恰好 1 | 去空白后非空;不允许只写占位文本 | 决定 Agent 以什么专业身份判断 |
| `<goal>` | 是 | 恰好 1 | 去空白后非空;必须描述可完成任务 | 决定 Agent 最终要产出什么 |

重复 `<role>` 或 `<goal>` 均为编译期 FATAL；错误码全集见 [`03-compile-rules` §4 agent domain](../03-compile-rules/mvp1-alignment.md#agent-domain)。

### 2.5.5 引用注入校验(Frontmatter ↔ Body)
Body 中出现的 `@type:NAME` 必须能在对应静态域内解析。Loader 不允许把无法解析的 mention 留给 LLM 自行理解。

| Mention | 可达域 | 校验规则 |
|---|---|---|
| `@reference:R1` | frontmatter `references[].id` | id 存在;path 在 skill 根内或合法相对路径 |
| `@example:E1` | body `<example id>` + frontmatter document `examples[].id` | id 存在;document example path/summary 合法 |
| `@subagent:producer_reviewer` | frontmatter `subagents[].name` | name 存在;`target_skill` 字段合法 |
| `@subgraph:review_graph` | frontmatter `subgraphs[].name` | name 存在;`path` 是合法绝对路径且子图 root 可解析 |
| `@protocol:P1` | 本 body `<protocol id="P1">` | id 存在 |
| `@step:S1` | 本 body `<step id="S1">` | id 存在 |
| `@tool:store_segments` | frontmatter `tools[]` + framework builtin | tool 名存在 |

校验顺序:
1. 解析 body XML AST,收集 step/protocol/inline example id。
2. 解析 frontmatter registry,收集 tools/subagents/subgraphs/references/document examples。
3. 用 §2.7 的统一 regex 扫描所有 body 文本节点。
4. 按类型查对应可达域,聚合全部缺失项后一次报错。

## 2.6 cognitive 模板语法(8 槽布局)
cognitive 模板语法定义 Agent prompt 的固定 XML 容器和变量占位。本文只管**模板长什么样、哪些 slot 存在、slot 从哪些语法输入取值**；模板渲染时机、reference-reader 预读、失败降级和 trace 记录归 [`02-mechanism/03-assemble`](../../02-mechanism/03-assemble/mvp1-alignment.md),不在本契约重复。

### 2.6.1 8 大插槽布局拓扑
8 个固定容器为:`role`、`goal`、`thinking_style`、`knowledge_base`、`examples`、`ambiguity_feedback`、`protocol_citation`、`critical_reminders`。`exit_contract` 是末尾固定输出契约 block,不计入 8 大插槽,也不从 SKILL.md body 引用。

```xml
<role>
{skill_role}
</role>

{llm_role_prefix_section}

<goal>
{skill_goal}
</goal>

<thinking_style>
- 行动前先做简短策略思考：目标是什么、输入是否充分、输出标准是什么
- 区分"事实"与"推断"，不要把推断当作事实写入结果
- 对关键判断给出依据，不要无依据臆测
- 先规划后执行：明确步骤，再调用工具
- 思考用于规划；对外输出必须给出可执行结果，而不是只描述计划

建议步骤：
{skill_steps_splat}
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】(系统已为你提前查阅相关资料并提取核心差异)：
{aligned_concepts_and_critical_corrections_markdown}

如果上述提炼不足以支撑判断，或你需要阅读未被精炼的其他原始语料，
可自主调用 read_reference subagent 工具，传入 R-id 从完整 Reference 库获取。
当前可用 Reference 注册清单：{reference_registry_listing}
</knowledge_base>

<examples>
以下案例仅用于辅助理解业务逻辑，你的最终输出格式必须严格遵守 <exit_contract> 的 Schema，不要照搬案例结构。
【内联示范】：{skill_examples_inline}
【扩展案例库】(遇棘手边界可调用 read_example subagent)：{example_registry_listing}
</examples>

<ambiguity_feedback>
当你发现规则不清晰、输入不足或存在多种合理解释时，不要静默跳过：
1. 优先调用 log_ambiguity 记录问题、类型、你的决策和理由
2. 然后继续按"最保守且可解释"的方案执行
这不是阻塞流程的澄清请求，而是用于改进技能定义的反馈回路。
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据，例如 [protocol:P1]。若无明确协议，需在自检说明写明并调用 log_ambiguity。
必须遵守的协议：
{skill_protocols_splat}
</protocol_citation>

<critical_reminders>
- 调用 finish_task 前，先检查关键工具返回值是否与预期一致；不一致先修复再 finish
- 对每个关键结论给出规则依据或数据依据
- 不确定规则边界时，先 log_ambiguity 再继续
- finish_task 必须提供 diagnostics_md（自检诊断）+ business_data_md（业务输出，遵循 output_schema）
- business_data_md 经 md_to_json 强校验，失败会收到错误反馈，按反馈修正后重新 finish_task
</critical_reminders>

<exit_contract>
回答必须调用 finish_task，输出符合下方 Schema 的结构化结果。business_data_md 遵循 output_schema 列业务字段；diagnostics_md 写自检诊断。
强制输出 Schema：
{output_schema}
</exit_contract>
```

### 2.6.2 字段级插槽定义
| 插槽 | 类型 | 必填 | 默认值 | 来源 | 业务作用 |
|---|---|---|---|---|---|
| `{skill_role}` | string | 是 | 无 | SKILL.md body `<role>` | 给 LLM 明确专业身份 |
| `{llm_role_prefix_section}` | string | 否 | `""` | `llm_roles.yaml` 的 `system_prompt_prefix` | 注入模型角色方法论 |
| `{skill_goal}` | string | 是 | 无 | SKILL.md body `<goal>` | 给 LLM 明确完成目标 |
| `{skill_steps_splat}` | string | 否 | `""` | SKILL.md body `<step id name>` | 把业务步骤放入 `thinking_style` |
| `{aligned_concepts_and_critical_corrections_markdown}` | markdown string | 否 | 降级警告 + 原文摘录 | knowledge_base 装载 subagent 输出 | 预先注入领域知识修正报告 |
| `{reference_registry_listing}` | markdown list | 否 | `"无注册 Reference"` | frontmatter `references` | 告诉 Agent 可按需读取哪些资料 |
| `{skill_examples_inline}` | string | 否 | `"无内联示例"` | SKILL.md body `<example id>` | 直接给短案例,不消耗 tool 调用 |
| `{example_registry_listing}` | markdown list | 否 | `"无扩展案例"` | frontmatter document `examples` | 只列 id/summary,鼓励按需读取 |
| `{skill_protocols_splat}` | string | 否 | `"无显式协议"` | SKILL.md body `<protocol id>` | 给判断提供可引用规则 |
| `{output_schema}` | JSON/YAML schema | 是 | 无 | 当前 Agent phase `io.outputs` | 约束 finish_task 输出 |

### 2.6.3 静态组装输入映射(语法侧)
静态输入来自 Loader 已完成的 Agent AST,不调用 LLM。本文只定义 slot 与 AST 的语法映射；具体渲染流程归 `02-mechanism/03-assemble`。

| 模板变量 | 输入 AST | 转换规则 | 空值行为 |
|---|---|---|---|
| `{skill_role}` | `<role>` text | 保留正文 Markdown,trim 外层空白 | 不允许为空 |
| `{skill_goal}` | `<goal>` text | 保留正文 Markdown,trim 外层空白 | 不允许为空 |
| `{skill_steps_splat}` | `<step id name>` list | 按 body 顺序直接拼入 `thinking_style` 建议步骤区域 | 允许为空字符串 |
| `{skill_protocols_splat}` | `<protocol id>` list | 按 body 顺序直接拼入 `protocol_citation` 区域 | 输出 `"无显式协议"` |
| `{skill_examples_inline}` | `<example id>` list | 按 body 顺序直接拼入 `examples` 内联示范区域 | 输出 `"无内联示例"` |

`SKILL.md` body 禁止 `<exit_contract>`。输出契约由模板末尾固定 `<exit_contract>` block 加 `{output_schema}` 生成。错误码全集见 [`03-compile-rules` §4 cognitive/tool/runtime domain](../03-compile-rules/mvp1-alignment.md#cognitive--tool--runtime-domain)。

## 2.7 mention `@type:NAME` 语法契约
mention 是 SKILL.md body 中可静态验证的引用 token。它既给人看,也给 Loader/Studio 自动补全和可达性校验使用。

### 2.7.1 `@type:NAME` 语法规范
全局 regex:

```regex
@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)
```

| 部分 | 类型 | 必填 | 默认值 | 语法/校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `type` | enum string | 是 | 无 | 只能是 `subagent`、`tool`、`subgraph`、`protocol`、`step`、`reference`、`example` | 决定后续查哪个静态 registry |
| `NAME` | string | 是 | 无 | 正则 `^[a-zA-Z0-9_-]+$`;区分大小写 | registry key |
| 完整 token | string | 是 | 无 | 必须无空格,形如 `@reference:R1` | Studio 自动补全和 Loader 静态扫描的共同格式 |

解析行为:
1. Loader 只扫描 Agent `SKILL.md` body XML 的文本节点,不扫描 frontmatter 字符串。
2. 匹配到合法 token 后生成 mention ref,至少包含 `type`、`name`、`source_tag`、`source_id`、`span`。
3. 残缺写法如 `@reference:`、`@tool`、`@ reference:R1` 必须 FATAL,不能当普通文本忽略。
4. Studio 编辑器按同一 7 类提供自动填充；空分类不显示,避免提示不存在资产。

### 2.7.2 7 大分类静态可达性算法
Loader 必须按 mention 类型查对应可达域,不允许跨域 fallback。

| 类型 | 查询域 | 注册来源 | 额外校验 |
|---|---|---|---|
| `subagent` | `frontmatter.subagents[].name` | Agent SKILL.md frontmatter | `target_skill` 字段合法 |
| `tool` | `frontmatter.tools[]` + framework builtin tools | Agent SKILL.md frontmatter + Engine builtin registry | tool 已注册且可暴露给当前 `llm_role` |
| `subgraph` | `frontmatter.subgraphs[].name` | Agent SKILL.md frontmatter | `path` 是绝对路径,并按 §2.1 / `02-resolver` 可解析 |
| `protocol` | body `<protocol id="...">` | 当前 SKILL.md body AST | id 唯一 |
| `step` | body `<step id="...">` | 当前 SKILL.md body AST | id 唯一 |
| `reference` | `frontmatter.references[].id` | Agent SKILL.md frontmatter | path 合法;summary 非空 |
| `example` | body `<example id>` + frontmatter document `examples[].id` | Agent SKILL.md body + frontmatter | inline body example 或 document example 合法 |

算法步骤:
1. 构建本地 registry:`subagents`、`tools`、`subgraphs`、`references`、document `examples`。
2. 构建 body registry:`protocols`、`steps`、inline `examples`。
3. 扫描所有 body 文本节点,得到 mention refs。
4. 对每个 ref 按 type 查域；例如存在 tool `P1` 不能满足 `@protocol:P1`。
5. 聚合全部不可达 ref,一次性报错,payload 带 `type`、`name`、`source_tag`、`source_id`。

### 2.7.3 语法滥用与容错
mention 采用“语法宽入口、语义强校验”:token 字符允许大小写、数字、下划线和短横线,但目标必须静态可达。

| 场景 | 示例 | 等级 | 处理 |
|---|---|---|---|
| 类型不存在 | `@asset:R1` | FATAL | 停止编译 |
| token 残缺 | `@reference:` | FATAL | 停止编译 |
| 目标不存在 | `@reference:R9` | FATAL | 停止编译 |
| 大小写不一致 | `@reference:r1` 但注册 `R1` | FATAL | 要求作者修正 |
| 未使用的注册项 | frontmatter 注册 R2 但 body 未引用 | WARN | 不中断,trace 记录 |
| 普通邮箱/文本误伤 | `user@example.com` | 无 | regex 不匹配,忽略 |

错误码全集见 [`03-compile-rules` §4 mention domain](../03-compile-rules/mvp1-alignment.md#mention-domain)。

## 2.8 resource(reference / example)部件契约
Agent `SKILL.md` 可声明两类**外部资产**供 LLM 查阅:**reference**(领域资料)与 **example**(样例)。声明在 frontmatter(字段表见 §2.5.1),body 用 `@reference:R1` / `@example:E1` 引用(可达校验见 §2.7),装配期注入 cognitive 槽(§2.6),错误码归 [`03-compile-rules` §4 resource domain](../03-compile-rules/mvp1-alignment.md#resource-domain)。本节把散在各节的这套机制收口成一个部件。

### 2.8.1 reference(领域资料)
```yaml
references:
  - id: R1                       # 正则 ^[A-Z][A-Za-z0-9_-]*$;同列表唯一
    path: references/style.md    # skill 根内可读路径
    summary: 风格指南             # 非空
```
- **装配期预读**:内置 reference-reader 子代理把 references 读一遍 → 提炼"领域知识修正报告"注入 `{aligned_concepts_and_critical_corrections_markdown}`(knowledge_base 槽,§2.6);reader 失败只 WARN + 原文摘录降级(`[F-v3-reference-reader-failed]`),不中断装配(装配流见 `compile-rules` §2.2)。
- **运行期按需读**:`{reference_registry_listing}` 列出可用 R-id;agent 用 `read_reference` 工具按 id 读全文(找不到 → `[F-v3-resource-reference-not-found]`)。
- **校验**:id/path/summary 合法(`[F-v3-resource-reference-invalid]` / `-id-invalid` / `-path-invalid` / `-summary-missing`);body `@reference:Rx` 必须可达 frontmatter `references[].id`(§2.7)。

### 2.8.2 example(样例)
两种,都注入 `examples` 槽(§2.6):
- **inline**:body `<example id="E1">…</example>` → `{skill_examples_inline}`(短样例直接进 prompt;id 规则见 §2.5.3)。
- **registry**:frontmatter `examples: [{id, path, summary}]` → `{example_registry_listing}`(扩展案例库,只列 id/summary);agent 用 `read_example` 工具按需读(找不到 → `[F-v3-resource-example-not-found]`)。
- **校验**:registry id/path/summary 合法(`[F-v3-resource-example-invalid]` 等);`@example:Ex` 可达 body inline 或 registry(§2.7)。

### 2.8.3 reference vs example(职责区分)
| | reference | example |
|---|---|---|
| 是什么 | 领域**资料**(给 agent 判断依据) | **样例**(给 agent 懂格式/边界) |
| 装配期 | reader 预读 → knowledge_base 报告 | inline 直接进 examples 槽 |
| 运行期 | `read_reference`(按 R-id) | `read_example`(registry 按 E-id) |
| cognitive 槽 | `knowledge_base` | `examples` |
> 二者都是"agent 可查阅资产",代码错误码统称 `resource` domain;reference 重**知识注入**(预读进 prompt),example 重**格式示范**(按需取)。

## 3. 接口契约
skill 源码(语法)→ AST(`GraphManifest` / `PhaseAST` / `Phase` 等,归 `data-contracts`)。
- **GRAPH**:AST 持根 metadata、inline `io.inputs/outputs`、phase registry；body DAG 产出拓扑顺序与 output phase 集合。
- **LOGIC**:AST 持 `io`、`actions`、`validator`；运行层按 `def <action_name>(inputs)->dict` 调度 action 链。
- **SUBGRAPH**:AST 持 `path`(绝对路径)、`io`、`validator`；下游 `02-resolver` 按绝对 path 直接解析(无 registry)。
- **SKILL/AGENT**:AST 持 `role`、`goal`、`steps`、`protocols`、`examples_inline`、`io`、`tools`、`subagents`、`subgraphs`、`references`、`examples`、`max_iterations`、`validator`、`llm_role`；body XML 只提供 5 类业务块。
- **SKILL agent `subgraphs[]`**:引用项持绝对 `path`;`subagents[]` 仍持 `target_skill`,二者生命周期不同。
- **cognitive 模板语法**:Agent AST + resources + `io.outputs` 填充固定 8 槽模板；渲染机制归 `02-mechanism/03-assemble`。
- **mention**:`@type:NAME` 只允许 7 类,按静态 registry 做可达性校验。

## 4. 设计决策基础(用户原话)
> 子图 path(PM 2026-06-02):"subgraph.md里面写path, 直接解析就好了, 随便放哪里。唯一要注意的是copilot 的工作目录范围要把subgraph的子图path 加进去。还有一个是注册在agent phase里的子图,也一样写path"
> path 必须绝对路径(PM 2026-06-05):"path写绝对路径"——理由即上条"随便放哪里":相对路径绑死基准目录、移动即失效,做不到随便放。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SS1 | **唯一真理在 mvp1**,旧 mvp0 spec 弃用、不作 SSOT 引用;真空部件报警、必须在 mvp1 补 | mvp0 要废弃;靠引用旧文档=假装写了,会随 mvp0 删除而真空 |
| SS2 | 子图引用用 **`path`(绝对路径)**,无注册表、直接解析 | path 即物理地址、能随便放、直接解析(PM 2026-06-02 / 06-05) |
| SS3 | 子图 io 像普通节点(黑板切片过滤),不强制父子 1:1 | 严格 1:1 太死;统一走黑板状态机过滤 |
| SS4 | GRAPH 根 IO 只允许 inline frontmatter,物理 IO 文件退役 | skill 语法自包含,减少物理文件漂移 |
| SS5 | LOGIC action 采用 V4 干净契约:`def <action_name>(inputs)->dict`、只读 inputs、纯返回 | 去掉 Context mutation 和编排副作用,让 action 可测、可序列化、可 checkpoint |
| SS6 | AGENT `subagents[]` 保持 `target_skill`;AGENT `subgraphs[]` 改为绝对 `path` | 子代理是运行期 Agent 委派,子图是编译期 graph skill 寻址,生命周期不同 |
| SS7 | cognitive 只在本文定义模板语法与 8 槽结构,渲染机制归 `02-mechanism/03-assemble` | 契约层只管 skill 写法,装配期机制不在 syntax 内重复 |
| SS8 | mention 固定 7 类 `@type:NAME`,静态 registry 可达性失败即编译失败 | 引用必须在编译期可验证,不能留给 LLM 猜 |

## 6. 测试关键点
1. **GRAPH**:frontmatter `phases`、body `<phase>`、物理 `phases/<name>/` 三者不一致会失败；inline `io.inputs/outputs` 合法；旧物理 IO/ref 字段失败。
2. **LOGIC**:frontmatter `actions` 与 body `<action>` 顺序一致；action 文件只能按 action 名寻址；`def <action_name>(inputs)->dict` 纯返回；Context mutation、`run_skill`、FS/sys.path/import 越界失败。
3. **LOGIC validator**:`validator: true` 缺 `validator.py` 或无 `validate(output, state_slice, **kwargs)` 失败；validator 抛错/返回非法字段时不回写。
4. **子图引用**:`SUBGRAPH.md` / agent `subgraphs[]` 解析的是**绝对 `path`** 字段(不是逻辑 id);父子 io 不再做 1:1 相等校验。
5. path 不在 copilot 工作目录边界内 → 解析失败报警(归 `02-resolver`)。
6. **AGENT frontmatter/body**:未知字段失败；`io.inputs/outputs` 必填且合法；`max_iterations` 限 1..50；body 只允许 5 类顶层标签；缺/重复 `<role>` 或 `<goal>` 失败；`<step>` / `<protocol>` / `<example>` id 非法或重复失败。
7. **AGENT registries**:`subagents[].target_skill` 仍按子代理机制校验；`subgraphs[].path` 按绝对 path 校验；references/examples path/summary 合法；frontmatter 与 body mention 可达域一致。
8. **cognitive 模板语法**:8 个固定容器存在；`<exit_contract>` 只由模板 hardcode；`{output_schema}` 来自当前 Agent phase `io.outputs`。
9. **mention**:7 类 regex 命中；未知 type、残缺 token、目标不存在、大小写不一致均失败；未使用注册项只 WARN。

## 7. 涉及 region / platform
engine 全权(子图语法是 engine 主决策);skill 源码被 studio 编辑器/copilot 消费。

## 8. gaps / 报警
1. 🚨 **mvp1 语法真空(剩余批次)**:§2 标「真空」的部件(**iterate / io 切片**)语法正文**尚未迁入 mvp1**(resource/example 已补 §2.8)。mvp0 弃用后这是真空,**必须在 mvp1 自写补齐**。
2. **代码 drift(refactor-target)**:当前代码对 LOGIC action / SUBGRAPH path / SUBGRAPH io / AGENT body 严格校验 / cognitive slot 细节 / mention 完整静态校验仍有旧实现或缺口,详见 `baseline` 差异表；本文是目标契约,代码应向本文对齐。
3. **subagents[] 不改 path(PM 2026-06-05 拍)**:子代理(`subagents[]`)与 **agent phase 捆绑**、是**运行期由 LLM 委派**的机制,跟子图(编译期解析、靠物理 path 引用的独立 skill)**不是一回事**(生命周期不同,断层#7)——引用方式**维持 `target_skill`,不改 path**。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `01-physical-layout`(子图默认落点)· `compile-rules` · `02-mechanism/02-resolver`(绝对 path 解析)· `02-mechanism/03-assemble`(cognitive 模板渲染)· `02-mechanism/05-run-inner/04-tools`(Agent tools)· `04-run-outer/02-iterate`
