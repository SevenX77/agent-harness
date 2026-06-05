---
module: 01-contract/02-skill-syntax
doc: mvp1-alignment
status: drafted（mvp1 自写=唯一真理；子图 path=绝对路径已写清；GRAPH/LOGIC/SUBGRAPH 语法已迁入；🚨 SKILL/cognitive/mention/resource/iterate/io 切片仍是真空债，见 §2/§8）
binds_baseline: ./baseline.md
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 02-skill-syntax — 契约 A · skill 文件内容/语法

> **Tier**: 契约层 A(声明式,喂 copilot) | **Owns**: skill 文件**里写什么**——四 phase(GRAPH/LOGIC/SUBGRAPH/SKILL)字段 schema + body XML + mention + io/iterate 声明 + cognitive 模板语法 | **现状**: 子图 path 已写清(§2.1);GRAPH/LOGIC/SUBGRAPH 语法已迁入(§2.2-§2.4);🚨 SKILL/cognitive/mention/resource/iterate/io 切片仍待补(§8) | **Related**: `physical-layout`(文件放哪)· `compile-rules`(怎么判)· `02-mechanism/02-resolver`(path 怎么解析)· `03-cognitive`(模板渲染)· `02-iterate`(iterate 执行)

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
| SKILL.md(Agent frontmatter + body XML + 引用注入) | 🚨 **真空**(其 `subgraphs[]` 引用按 §2.1 用绝对 path) |
| cognitive 模板(8 槽布局) | 🚨 **真空** |
| mention `@type:NAME`(7 类) | 🚨 **真空** |
| reference/example 机制 | 🚨 **真空** |
| iterate 声明(batch/loop/range/accumulate) | 🚨 **真空**(执行见 `04-run-outer/02-iterate`) |
| io 切片声明(从黑板切片) | 🚨 **真空**(切片见 `04-run-outer/01-graph-exec`) |
> 🚨 上述「真空」部件是 **mvp1 的债**:语法正文还没从旧文档迁进 mvp1。mvp0 弃用后这些就是真空,**必须在 mvp1 自写补齐**(这正是"mvp1 没有=错误"的报警点,见 §8)。本批已补 GRAPH/LOGIC/SUBGRAPH；下一批继续 SKILL/cognitive/mention/resource/iterate/io 切片。
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

## 3. 接口契约
skill 源码(语法)→ AST(`GraphManifest` / `PhaseAST` / `Phase` 等,归 `data-contracts`)。
- **GRAPH**:AST 持根 metadata、inline `io.inputs/outputs`、phase registry；body DAG 产出拓扑顺序与 output phase 集合。
- **LOGIC**:AST 持 `io`、`actions`、`validator`；运行层按 `def <action_name>(inputs)->dict` 调度 action 链。
- **SUBGRAPH**:AST 持 `path`(绝对路径)、`io`、`validator`；下游 `02-resolver` 按绝对 path 直接解析(无 registry)。
- **SKILL agent `subgraphs[]`**:引用项同样持绝对 `path`,但 SKILL.md 字段表仍在 §2 真空清单中,待下一批迁入。

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

## 6. 测试关键点
1. **GRAPH**:frontmatter `phases`、body `<phase>`、物理 `phases/<name>/` 三者不一致会失败；inline `io.inputs/outputs` 合法；旧物理 IO/ref 字段失败。
2. **LOGIC**:frontmatter `actions` 与 body `<action>` 顺序一致；action 文件只能按 action 名寻址；`def <action_name>(inputs)->dict` 纯返回；Context mutation、`run_skill`、FS/sys.path/import 越界失败。
3. **LOGIC validator**:`validator: true` 缺 `validator.py` 或无 `validate(output, state_slice, **kwargs)` 失败；validator 抛错/返回非法字段时不回写。
4. **子图引用**:`SUBGRAPH.md` / agent `subgraphs[]` 解析的是**绝对 `path`** 字段(不是逻辑 id);父子 io 不再做 1:1 相等校验。
5. path 不在 copilot 工作目录边界内 → 解析失败报警(归 `02-resolver`)。

## 7. 涉及 region / platform
engine 全权(子图语法是 engine 主决策);skill 源码被 studio 编辑器/copilot 消费。

## 8. gaps / 报警
1. 🚨 **mvp1 语法真空(剩余批次)**:§2 标「真空」的部件(SKILL/cognitive/mention/resource/iterate/io 切片)语法正文**尚未迁入 mvp1**。mvp0 弃用后这是真空,**必须在 mvp1 自写补齐**。
2. **代码 drift(refactor-target)**:当前代码对 LOGIC action / SUBGRAPH path / SUBGRAPH io 仍有旧实现残留,详见 `baseline` 差异表；本文是目标契约,代码应向本文对齐。
3. **subagents[] 不改 path(PM 2026-06-05 拍)**:子代理(`subagents[]`)与 **agent phase 捆绑**、是**运行期由 LLM 委派**的机制,跟子图(编译期解析、靠物理 path 引用的独立 skill)**不是一回事**(生命周期不同,断层#7)——引用方式**维持现状、不改 path**。其引用语法随 SKILL.md 部件迁入 mvp1 时一并定(§2 真空)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `01-physical-layout`(子图默认落点)· `compile-rules` · `02-mechanism/02-resolver`(绝对 path 解析)· `04-run-outer/02-iterate`
