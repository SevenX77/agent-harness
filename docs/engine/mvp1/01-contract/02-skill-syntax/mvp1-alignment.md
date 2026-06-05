---
module: 01-contract/02-skill-syntax
doc: mvp1-alignment
status: drafted（mvp1 自写=唯一真理；子图 path=绝对路径已写清；🚨 多语法部件尚未迁入 mvp1=真空债，见 §2/§8）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 02-skill-syntax — 契约 A · skill 文件内容/语法

> **Tier**: 契约层 A(声明式,喂 copilot) | **Owns**: skill 文件**里写什么**——四 phase(GRAPH/LOGIC/SUBGRAPH/SKILL)字段 schema + body XML + mention + io/iterate 声明 + cognitive 模板语法 | **现状**: 子图 path 已写清(§2.1);🚨 其余部件 mvp1 真空待补(§2) | **Related**: `physical-layout`(文件放哪)· `compile-rules`(怎么判)· `02-mechanism/02-resolver`(path 怎么解析)· `03-cognitive`(模板渲染)· `02-iterate`(iterate 执行)

## 1. 定义
定义 skill 文件**内容/语法**:每种文件的 frontmatter 字段、body 格式、`@type:NAME` mention 语法、io/iterate 声明。**只管"写什么"**,不管"放哪"(归 `physical-layout`)、"怎么判"(归 `compile-rules`)、"怎么解析引用"(归 `02-resolver`)。是喂 copilot 生成合法 skill 的核心语言。

> **唯一真理在 mvp1**:本文是 skill 语法的权威定义。旧 `docs/engine/mvp0/skill-spec/*` 已弃用,**不得作为 SSOT(唯一真相源)引用**;mvp1 没写或写错 = 缺陷,按 §2 / §8 🚨 报警、必须在 mvp1 补齐,**不允许回退 mvp0「补全」**。

## 2. 语法部件清单 + mvp1 写入状态
| 语法部件 | mvp1 写入状态 |
|---|---|
| **SUBGRAPH 子图 path 引用** | ✅ 已写清,见 §2.1 |
| GRAPH.md frontmatter + DAG + 根 io | 🚨 **真空**:mvp1 未自写,需迁入 |
| LOGIC.md(action 寻址 + validator 生命周期) | 🚨 **真空**(且 action 契约要按 V4 重写,见 §8) |
| SKILL.md(Agent frontmatter + body XML + 引用注入) | 🚨 **真空**(其 `subgraphs[]` 引用按 §2.1 用绝对 path) |
| cognitive 模板(8 槽布局) | 🚨 **真空** |
| mention `@type:NAME`(7 类) | 🚨 **真空** |
| reference/example 机制 | 🚨 **真空** |
| iterate 声明(batch/loop/range/accumulate) | 🚨 **真空**(执行见 `04-run-outer/02-iterate`) |
| io 切片声明(从黑板切片) | 🚨 **真空**(切片见 `04-run-outer/01-graph-exec`) |
> 🚨 上述「真空」部件是 **mvp1 的债**:语法正文还没从旧文档迁进 mvp1。mvp0 弃用后这些就是真空,**必须在 mvp1 自写补齐**(这正是"mvp1 没有=错误"的报警点,见 §8)。本次只把子图 path(§2.1)写清。
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

## 3. 接口契约
skill 源码(语法)→ AST(`Phase` 等,归 `data-contracts`)。**子图**:AST 里 SUBGRAPH / `subgraphs[]` 持 `path` 字段(绝对路径),下游 `02-resolver` 按绝对 path 直接解析(无 registry)。

## 4. 设计决策基础(用户原话)
> 子图 path(PM 2026-06-02):"subgraph.md里面写path, 直接解析就好了, 随便放哪里。唯一要注意的是copilot 的工作目录范围要把subgraph的子图path 加进去。还有一个是注册在agent phase里的子图,也一样写path"
> path 必须绝对路径(PM 2026-06-05):"path写绝对路径"——理由即上条"随便放哪里":相对路径绑死基准目录、移动即失效,做不到随便放。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SS1 | **唯一真理在 mvp1**,旧 mvp0 spec 弃用、不作 SSOT 引用;真空部件报警、必须在 mvp1 补 | mvp0 要废弃;靠引用旧文档=假装写了,会随 mvp0 删除而真空 |
| SS2 | 子图引用用 **`path`(绝对路径)**,无注册表、直接解析 | path 即物理地址、能随便放、直接解析(PM 2026-06-02 / 06-05) |
| SS3 | 子图 io 像普通节点(黑板切片过滤),不强制父子 1:1 | 严格 1:1 太死;统一走黑板状态机过滤 |

## 6. 测试关键点
1. **子图引用**:`SUBGRAPH.md` / agent `subgraphs[]` 解析的是**绝对 `path`** 字段(不是逻辑 id);父子 io 不再做 1:1 相等校验。
2. path 不在 copilot 工作目录边界内 → 解析失败报警(归 `02-resolver`)。

## 7. 涉及 region / platform
engine 全权(子图语法是 engine 主决策);skill 源码被 studio 编辑器/copilot 消费。

## 8. gaps / 报警
1. 🚨 **mvp1 语法真空(高优先)**:§2 标「真空」的部件(GRAPH/LOGIC/SKILL/cognitive/mention/resource/iterate/io)语法正文**尚未迁入 mvp1**。mvp0 弃用后这是真空,**必须在 mvp1 自写补齐**——这是"mvp1 没有=错误"的报警。
2. **LOGIC action 契约 V4**:迁 LOGIC 语法时,action 要按 `def <action_name>(inputs)->dict`、纯返回、禁编排/FS 写(权威设计在 `04-run-outer/01-graph-exec` LE1-3)。
3. **subagents[] 不改 path(PM 2026-06-05 拍)**:子代理(`subagents[]`)与 **agent phase 捆绑**、是**运行期由 LLM 委派**的机制,跟子图(编译期解析、靠物理 path 引用的独立 skill)**不是一回事**(生命周期不同,断层#7)——引用方式**维持现状、不改 path**。其引用语法随 SKILL.md 部件迁入 mvp1 时一并定(§2 真空)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `01-physical-layout`(子图默认落点)· `compile-rules` · `02-mechanism/02-resolver`(绝对 path 解析)· `04-run-outer/02-iterate`
