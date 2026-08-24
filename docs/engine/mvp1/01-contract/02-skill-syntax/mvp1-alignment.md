---
module: 01-contract/02-skill-syntax
doc: mvp1-alignment
status: living
binds_baseline: ./baseline.md
format_ssot: ../../../skill-spec/00-FORMAT-GROUND-TRUTH.md
---

# 02-skill-syntax - MVP1 Alignment

本模块只说明 skill 语法在 MVP1 架构中的职责和边界，不再重复 YAML / Markdown 模板。

`graph_skill` 文件格式模板的唯一真相源是：

> [`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md)

如果本文、baseline、fixture、代码注释或历史迁移文档与 `skill-spec/00-FORMAT-GROUND-TRUTH.md` 冲突，以 `skill-spec/00` 为准。

## 1. Scope

`skill-syntax` 管“文件里写什么”：

- `GRAPH.md` 的根元数据、根 IO、phase 注册表、body DAG、图级 `iterate`。
- `LOGIC.md` 的 name、IO、actions、validator、节点级 `iterate`、body `<action>`。
- `SUBGRAPH.md` 的 name、`path`、IO、validator、节点级 `iterate`。
- Agent `SKILL.md` 的 name、llm_role、use_graph_llm_role（图默认角色优先级开关，见 skill-spec §5）、IO、tools、subagents、subgraphs、references、examples、validator、max_iterations、节点级 `iterate`、body role/goal/step/protocol/example。
- `io`、`iterate`、mention/resource 的合法写法。
- Studio Properties 面板应该从哪些 frontmatter 字段生成表单。

它不管：

- 文件放在哪：见 `../01-physical-layout/`。
- 怎么解析路径：见 `../../02-mechanism/02-resolver/`。
- 怎么编译、报错：见 `../03-compile-rules/`。
- 怎么执行 graph / iterate / subgraph：见 `../../02-mechanism/04-run-outer/`。
- 怎么装配 cognitive prompt、tools、subagents：见 `../../02-mechanism/03-assemble/` 和 `../../02-mechanism/05-run-inner/`。

## 2. Format SSOT

完整模板只放在 skill-spec：

| Topic | Canonical document |
| --- | --- |
| Physical tree | [`skill-spec/00 §1`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#1-物理目录) |
| `GRAPH.md` | [`skill-spec/00 §2`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#2-graphmd) |
| `LOGIC.md` | [`skill-spec/00 §3`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#3-logicmd) |
| `SUBGRAPH.md` | [`skill-spec/00 §4`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#4-subgraphmd) |
| Agent `SKILL.md` | [`skill-spec/00 §5`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#5-skillmd) |
| IO schema | [`skill-spec/00 §6`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#6-io-schema) |
| Iterate | [`skill-spec/00 §7`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#7-iteratespec) |
| Mention/resource | [`skill-spec/00 §8`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#8-mention-与资源引用) |
| Studio Properties mapping | [`skill-spec/00 §9`](../../../skill-spec/00-FORMAT-GROUND-TRUTH.md#9-properties-panel-映射) |

## 3. Locked Decisions

### 3.1 类型由文件名决定

Phase 类型由物理文件名决定：

- `LOGIC.md` => logic phase
- `SUBGRAPH.md` => subgraph phase
- `SKILL.md` => agent phase

作者不写 phase frontmatter `mode`，也不写 `node_type`。

### 3.2 Phase id 由目录名决定

`phase_id` 是 `phases/<phase_id>/` 的目录名。作者不在 frontmatter 里写 `phase_id`。Studio 做 rename 时必须同步目录名、`GRAPH.md phases` 注册表和 body `<phase>` 引用。

### 3.3 SUBGRAPH 使用 path

`SUBGRAPH.md` 用 `path` 指向子图 skill 根目录。Agent `subgraphs[]` 也用 `path`。

`target_skill` 不属于 subgraph 新规范字段。只有 Agent `subagents[]` 继续使用 `target_skill`，因为 subagent 是运行期 agent 委托，不是编译期子图路径解析。

### 3.4 IO 是黑板切片边界

每个节点自己的 `io.inputs` 声明从黑板读取哪些字段，`io.outputs` 声明允许写回哪些字段。父图和子图 IO 不需要字段全集一一相等。

节点 `io.inputs` 只声明消费哪些黑板字段,不存文件路径。导入文件路径、目录、批量 pattern 和解析出的字段绑定都在 `.workspace/runtime_config.json`；compile/lint/run/predict 读取 runtime_config 后把这些字段视为运行前/运行时注入的黑板来源（黑板是主源，文件只是运行配置注入——PM 2026-07-02 r3 + 2026-07-05 runtime_config 收敛）。

### 3.4.1 artifacts 清单（runtime_config 落盘声明）

GRAPH.md 的 `io` 只声明输入/输出 schema。要落盘哪些 artifact 文件、每个文件装黑板的哪些字段,写入 `.workspace/runtime_config.json` 的 `artifacts` 清单：

```yaml
artifacts:
  - stem: story_framework
    mode: single            # single | per-item
    fields: [story_framework, unified_event_stream]
  - stem: abc_segmentation
    mode: per-item          # iterate 每轮一个编号文件
    fields: [segmentation_result]
```

一个文件可装多个字段、一个字段可进多个文件（G3「一 schema 多文件 / 多 schema 多文件」的成型态）。落盘命名固定格式（`<stem>_latest_<ts>` + `history/` + per-item 编号继承输入批量），见 physical-layout §2.2.2。旧 per-field artifact path 与 legacy 别名不是规范字段,不留兼容。

### 3.5 Iterate 只认 iterate

循环声明统一写 `iterate`，其标准字段见 skill-spec。

`batch:` 和 `iterator:` 不是新规范字段。若当前代码仍接受它们，那是 implementation drift，不能出现在新模板、新 UI 写入逻辑或新 fixture 中。

### 3.6 Properties 面板展示 frontmatter

Studio Properties 面板展示当前 `.md` 文件 frontmatter 中可编辑的规范字段：

- 不展示内部推导属性：`phase_id`、`node_type`、frontmatter `mode`。
- 不展示非法字段。
- `name` 通过重命名动作编辑，同步目录和引用。
- `path` 通过选择/重连已有子图目录编辑。
- `io` 属于专门的 Input/Output 面板，不在普通属性表单里重复整块 schema。

## 4. Implementation Drift

以下情况若在代码或历史文档中仍出现，只代表历史实现或迁移残留，不代表规范：

- `SUBGRAPH.md target_skill`
- Agent `subgraphs[].target_skill`
- phase frontmatter `mode`
- phase frontmatter `phase_id`
- phase frontmatter `node_type`
- `batch:`
- `iterator:`
- `io_inputs_ref` / `io_outputs_ref`
- 父子图 IO 1:1 强绑定

这些 drift 应由后续实现任务按 TDD 收敛到 skill-spec，不得反向修改 skill-spec 迁就当前实现偏差。

## 5. Test Focus

测试不应复制本文模板；应引用或构造符合 `skill-spec/00` 的最小 fixture。

关键断言：

- 新写入的 skill 文件只包含 `skill-spec/00` 中列出的合法字段。
- 新建节点不会自动补充未由用户或模板声明的边。
- `SUBGRAPH.md` 使用 `path`，不使用 `target_skill`。
- `iterate` 使用 `mode` / `over` / `item_var` / `range` / `concurrency` / `accumulate`，不使用 `batch` 或 `iterator`。
- Properties 面板只渲染当前文件 frontmatter 中对应的规范字段。
