# 决议：一份 io.outputs schema 只有一个真值条件

- 日期：2026-08-19
- 状态：已裁决，随本 PR 落地
- 模块：engine（`packages/graph-agent`）

## 决策

两条，同一原则（同一份 schema 在每道检查点上给出同一个判决）：

1. **JSON Schema 的 `type` 数组（联合类型）是受支持的输入。**
   `type: [string, "null"]` 是 JSON Schema 表达可空的标准写法。schema 物化层
   （`_descriptor_from_json_mapping`）新增 `UnionType` 描述符：成员逐个物化，
   `"null"` 映射为 `type(None)`，注解层合成 `X | Y` 联合。
2. **黑板映射闸采用与 finish 闸相同的判决规则：optional ⇒ 可空。**
   finish 闸的 Pydantic 投影里，非必填字段的注解一律是 `T | None`
   （`_optional_annotation`，函数名即裁决）。`state_mapper` 的 jsonschema
   校验从此先对 raw schema 施加同一规则（非必填属性包一层
   `anyOf: [原 schema, {type: null}]`）再判。必填字段两边都保持严格。

## 事实与证据（真跑，非推断）

**第一现场** — run `2026-08-19T05-21-45_3aca03a5`（skill
`story-deconstruction-v3-lab`，852 秒，84 次 LLM 调用）：

- `foreshadow` 相位 12:35:42 `finish_task_verdict: accepted`——原话
  "passed schema and business validation";12:36:00 `phase_end`。
- 随后整个 run 以 FATAL 收场：`[F-v3-runtime-state-mapping-failed]
  phase output schema validation failed: None is not of type 'string'`,
  field `foreshadow_results.0.resolves_foreshadowing_id`——一个**非必填**字段,
  载着 finish 闸刚放行的 null。
- 两道闸的代码:闸门 `schema_engine.py::_get_pydantic_model_cached`
  (非必填 → `_optional_annotation` → `T | None`);映射
  `runtime/state_mapper.py::_validate_phase_updates_against_schema`
  (`Draft202012Validator(schema)` 按 raw schema 字面判)。

**第二现场** — 把可空性按 JSON Schema 标准显式声明也走不通:
`type: [string, "null"]` 编译通过,predict 阶段死于
`SchemaParseError: List schema shorthand must contain exactly one item type`
(predict `2026-08-19T05-40-31_498a3bfe`),且以 `engine.unexpected_error`
(未分类)冒出——`_descriptor_from_json_mapping` 从未处理过 `type` 为数组的
情形,列表一路落到"列表简写"分支,报错和真实缺陷风马牛不相及。

## 关键设计决定

1. **裁决基准取 finish 闸,不取 jsonschema 字面。** 「optional ⇒ 可空」是引擎
   已经明写的深思熟虑行为(`_optional_annotation` 有名字、有独立函数)。让映射闸
   收严到 jsonschema 字面等于推翻既有裁决,并让每个现存 skill 的每个可选字段
   都变成运行期地雷(LLM 对"无值"天然倾向输出 null)。
2. **`UnionType` 是惰性标记,不是急性注解。** 与 `ListType` 同构:成员可以是
   `ListType`/`SchemaObject` 描述符,只在 `_descriptor_to_annotation` 落成注解;
   急性构造会绕开缓存的模型构建路径。`_canonical_key` 同步获得确定性分支
   (`union[...]`),不落 repr 兜底(呼应 W2-30 决议)。
3. **映射闸的变换只降"可选字段拒 null"这一档,其余不松。** 必填字段带 null
   照死(两闸一致);可选字段给错类型(如 int 给到 string)照死——optional
   的含义是"可缺席、可为空",不是"随便"。三条测试分别钉住这三面。
4. **raw schema 本体不改。** 变换发生在校验时,skill 作者声明的契约原文
   (`raw_schema_dict`)保持逐字保存——它同时是给模型看的提示词素材,悄悄改写
   等于伪造作者的话。

## 验收判据

- RED(修前):`type` 数组物化 3 条 + mapper null 1 条,共 4 failed;
  "严格面不松" 3 条本来就绿。
- GREEN(修后):7 passed;引擎全套 1590 passed;gateway 618;backend 1738;
  ruff / mypy --strict ×3 全绿。
- 端到端判据:`story-deconstruction-v3-lab` 带显式 nullable 声明重新
  Compile → Predict → Run,不再死于该字段(留待 vendor 重建后真机复验)。
