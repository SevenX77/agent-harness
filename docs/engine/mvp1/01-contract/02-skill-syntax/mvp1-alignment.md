---
module: 01-contract/02-skill-syntax
doc: mvp1-alignment
status: drafted（♻️ mvp0 02–08 FROZEN + mvp1 delta: iterate/io 声明）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 02-skill-syntax — 契约 A · skill 文件内容/语法

> **Tier**: 契约层 A(声明式,喂 copilot) | **Owns**: skill 文件**里写什么**——四 phase 字段 schema + body XML + mention + io/iterate 声明 + cognitive 模板语法 | **现状**: ♻️ mvp0 FROZEN + mvp1 delta | **Related**: `physical-layout`(文件放哪)· `compile-rules`(怎么判)· `03-cognitive`(模板渲染)· `02-iterate`(iterate 执行)

## 1. 定义
定义 skill 文件**内容/语法**:每种文件(GRAPH/LOGIC/SUBGRAPH/SKILL + cognitive 模板)的 frontmatter 字段、body 格式、`@type:NAME` mention 语法、io 声明。**只管"写什么",不管"放哪"**(归 `physical-layout`)、"怎么判"(归 `compile-rules`)。是喂 copilot 生成合法 skill 的核心语言。

## 2. 内容 + V4 处置(♻️ / delta)
| 语法部件 | 权威 SSOT | 处置 |
|---|---|---|
| GRAPH.md frontmatter + DAG + 根 io | mvp0 `02-graph-md-spec` | ♻️ |
| LOGIC.md(action 寻址 + validator 生命周期) | mvp0 `03-logic-md-spec` | ♻️ |
| SUBGRAPH.md(类型推导 + target_skill 寻址) | mvp0 `04-subgraph-md-spec` | ♻️ |
| SKILL.md(Agent frontmatter + body XML + 引用注入) | mvp0 `05-agent-md-spec` | ♻️ |
| cognitive 模板(8 槽布局) | mvp0 `06-cognitive-template-spec` | ♻️(*语法*归此;*渲染*归 `03-assemble`/`03-cognitive`) |
| mention `@type:NAME`(7 类) | mvp0 `07-mention-syntax-spec` | ♻️ |
| reference/example 机制 | mvp0 `08-resource-mechanisms-spec` | ♻️ |
| **iterate 声明**(batch/loop/range/accumulate) | 见 `04-run-outer/02-iterate`(执行) | **V4 delta**(FROZEN 解冻,见 compile-rules) |
| **io 切片声明**(inputs 从黑板切片) | 见 `04-run-outer/01-graph-exec`(io 切片) | **V4 delta** |
> 本域**只汇总 + 链接 mvp0,不复制字段表**(SSOT 在 mvp0 FROZEN)。
> ❌ **无 golden 声明**:golden 已移 `.workspace`,不在 skill 源码语法里(反转决策 A)。

## 3. 接口契约
skill 源码(语法)→ AST(`Phase` 等,归 `data-contracts`)的解析契约;FROZEN 字段改即全链路同步(iterate/io 解冻按 Task1 台账)。

## 4. 设计决策基础(用户原话)
⏳ skill-syntax 字段级决议在 mvp0 各 spec 头部 + `MVP0-DECISIONS-EXPLAINED`(18Q);本域不重述。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SS1 | 语法 ♻️ mvp0 02–08 FROZEN 为主,本域汇总+链接 | 语法稳定;不在设计阶段动 FROZEN |
| SS2 | mvp1 delta = iterate/io 声明(来自 studio 能力对齐) | 新增声明式能力进语法 |
| SS3 | cognitive 模板**语法**归此,**渲染**归 `03-assemble`/`03-cognitive` | 契约(写什么)vs 机制(怎么渲染)分层 |

## 6. 测试关键点
1. 四 phase 文件 frontmatter schema 校验(各 `[F-v3-*]` 域码,归 compile-rules)。
2. iterate 声明 loop 节点 `io.inputs` 必含 `item_var`+`accumulate.var`(编译校验 `[F-v3-iterate-*]`)。

## 7. 涉及 region / platform
engine 全权;skill 源码语法被 studio 编辑器/copilot 消费(喂 copilot 生成合法 skill)。

## 8. gaps / 待设计
1. iterate/io 声明语法成段(标 ♻️ vs delta);FROZEN 解冻落地归 kiro。
2. **LOGIC action 契约 V4 反写**(解冻 `03-logic-md-spec`):action 函数 `def <action_name>(inputs)->dict`、纯返回只读 inputs、禁编排/FS——权威设计在 `02-mechanism/04-run-outer/01-graph-exec` LE1-3;本域只标语法侧 delta(action 声明/签名)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `physical-layout` · `compile-rules` · `03-assemble` · `04-run-outer/02-iterate` · mvp0/skill-spec 02–08(FROZEN)
