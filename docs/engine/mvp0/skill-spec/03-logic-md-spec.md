---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

> 🔖 **本文 = mvp0 迁移源档案，非当前 SSOT。** LOGIC.md frontmatter、body `<action>`、action 寻址与 validator 生命周期已迁入 [`mvp1 skill-syntax`](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#23-logicmd-语法契约)。其中旧 `run()` / 可变 Context action 契约已按 mvp1 V4 反转为 `def <action_name>(inputs) -> dict`、只读 inputs、纯返回；权威运行决策见 mvp1 `graph-exec` LE1-3。mvp1 删除 mvp0 引用时，不得再把本文当权威。
<!-- 核对进度:已迁 4 块 / 未迁 0 块 / 2026-06-05 -->

~~# LOGIC.md Spec~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#23-logicmd-语法契约)

本文定义 `LOGIC.md` 的 Frontmatter、Action 注册 / 调用和 validator 后置钩子契约。它与 [物理布局](./01-physical-layout.md#文件名类型推导-filename-type-derivation)、[错误码字典](./11-error-code-spec.md#错误码速查全表) 和 [运行流](./12-compile-runtime-flow-spec.md#运行时引擎流-run-time-workflow) 共同约束 Logic 节点。

~~## Frontmatter 字段解析表 (Schema & Validation)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#231-frontmatter-字段)

`LOGIC.md` 表示一个不进入 ReAct 循环的确定性执行节点。Loader 由物理文件名 `LOGIC.md` 推导节点类型并注入内部 `mode="logic"`; 作者不在 frontmatter 中书写 `mode:`。未知字段编译期 FATAL `[F-v3-logic-schema-unknown-field]`。

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

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `name` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$`; 建议与 phase id 一致, 不一致只 WARN | `[F-v3-logic-name-invalid]` | Trace、错误定位和 Studio 节点展示名 |
| `io.inputs` | JSON Schema object | 是 | 无 | 顶层 `type: object`; 含 `properties`; `required` 只能引用已有 properties | `[F-v3-logic-io-schema-invalid]` | 声明从 BlackboardState 切给 action 链的 state slice |
| `io.outputs` | JSON Schema object | 是 | 无 | 同 `io.inputs`; 输出字段必须可被 action 返回 dict 覆盖 | `[F-v3-logic-io-schema-invalid]` | 声明 action 链最终允许回写黑板的字段边界 |
| `actions` | list[string] | 是 | 无 | 非空; 每项正则 `^[a-z][a-z0-9_]*$`; 不允许路径分隔符; 按列表顺序执行 | `[F-v3-logic-actions-empty]` / `[F-v3-logic-action-name-invalid]` | 编排确定性 Python action 的执行顺序 |
| `validator` | boolean | 否 | `false` | 必须是 YAML boolean, 不能用 `"true"` 字符串 | `[F-v3-logic-validator-type-invalid]` | 开启后置校验钩子, 用于阻断脏输出回写 |

`io` 的业务含义不是重复根 IO, 而是给 StateMapper 一把“切片尺”: 运行期只把 `io.inputs.properties` 中声明的字段传给本 Logic phase, 并只允许 `io.outputs.properties` 声明的字段写回黑板。这样 action 可以保持普通函数形态, 但不会越权读取或污染全局状态。

[F-v3-* 错误码](./11-error-code-spec.md#错误码速查全表) 覆盖字段缺失、类型错误和 action/validator 错误。

~~## Actions 注册、寻址与执行契约~~ → ✅[已迁入并按 V4 反转](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#233-action-寻址与-v4-干净执行契约)

`actions:` frontmatter 只注册 action 名字。body XML 用 `<action>name</action>` 按顺序调用。action 来源支持两类:

1. 当前 logic phase 路径下 `actions/<action_name>.py`。
2. Studio 或 Engine 内注册的通用 action。

```text
<skill_root>/
  phases/
    normalize_text/
      LOGIC.md
      actions/
        strip_noise.py
        normalize_whitespace.py
```

`actions: [strip_noise]` 只能注册一级 action 名字, 不允许 `./actions/foo.py`、`pkg.module:function` 或多级目录。执行顺序由 body `<action>` 标签顺序决定, 未在 frontmatter 注册的 action 不能被 body 调用。

| 项 | 契约 |
|---|---|
| 解析根 | 当前 logic phase 目录 `<skill_root>/phases/<phase_id>/` + Engine/Studio 通用 action registry |
| 物理目录 | `<skill_root>/phases/<phase_id>/actions/` 可选; 当 action 不在通用 registry 时必须存在 |
| 文件名 | `<action_name>.py` |
| 导出函数 | `def run(state_slice: dict, **kwargs) -> dict` |
| 入参 | `state_slice` 是按 `io.inputs` 从 BlackboardState 切出的浅 dict; `kwargs` 预留 trace_id、phase_id 等系统参数 |
| 返回值 | dict; key 必须是 `io.outputs.properties` 子集 |
| 执行顺序 | 严格按 body `<action>` 标签从上到下串行执行; 上一个 action 的返回会合并进下一次 `state_slice` |
| 纯净性约束 | 编译期执行 purity 扫描, 禁止 action 包含本地写 (`open(..., 'w')`) 等副作用 |

Action 与 Tool 的边界必须固定:

| 概念 | 谁触发 | 所属节点 | 是否进 ReAct | 业务语义 |
|---|---|---|---|---|
| Action | Engine 静默执行 | `LOGIC.md` | 否 | 确定性代码步骤, 适合解析、转换、校验、入库等稳定逻辑 |
| Tool | LLM 主动调用 | Agent `SKILL.md` | 是 | Agent 在推理过程中按需调用的能力, 例如 `read_reference` / `read_example` |

寻址和执行失败按阶段归一:

| 失败场景 | 错误码 | 阶段 | 处理 |
|---|---|---|---|
| phase-local `actions/` 目录缺失且 action 未在通用 registry 注册 | `[F-v3-logic-action-dir-missing]` | 编译期 | FATAL |
| action 文件不存在 | `[F-v3-logic-action-not-found]` | 编译期 | FATAL |
| action 名含 `/`、`.` 或非法字符 | `[F-v3-logic-action-name-invalid]` | 编译期 | FATAL |
| action 模块无 `run` | `[F-v3-logic-action-entrypoint-missing]` | 编译期 | FATAL |
| action 代码存在本地写等副作用违例 | `[F-v3-logic-action-purity-violation]` | 编译期 | FATAL |
| `run()` 返回非 dict | `[F-v3-logic-action-return-invalid]` | 运行期 | FATAL, 不回写 |
| 返回字段超出 `io.outputs` | `[F-v3-logic-output-field-undeclared]` | 运行期 | FATAL, 不回写 |

[Execution Runtime MVP0 Alignment](../execution-runtime/mvp0-alignment.md) 承接 Action 执行边界; Tool 主动调用边界见 [Builtin Tools](./09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example)。

~~## Validator 生命周期 (Post-Execution Hook)~~ → ✅[已迁入](../../mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#234-validator-生命周期)

`validator: true` 表示 action 链全部完成后, 但结果写回 BlackboardState 之前, Engine 必须执行同级物理文件:

```text
<skill_root>/phases/<phase_id>/
  LOGIC.md
  validator.py
```

validator 文件是 phase-local 的, 因为它校验的是该 phase 的业务输出, 不是 skill 级通用动作。

| 字段 / 文件 | 类型 | 必填条件 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `validator` | boolean | 否 | `false` | `true` 时必须存在同级 `validator.py`; `false` 时忽略同级文件 | `[F-v3-logic-validator-type-invalid]` / `[F-v3-logic-validator-missing]` | 声明是否启用后置强校验 |
| `validator.py` | Python file | `validator: true` | 无 | 必须导出 `def validate(output: dict, state_slice: dict, **kwargs) -> None \| dict` | `[F-v3-logic-validator-entrypoint-missing]` | 在回写前检查 action 输出完整性和业务不变量 |

触发顺序:

1. StateMapper 按 `io.inputs` 切出 `state_slice`。
2. Engine 串行执行全部 actions, 得到 `candidate_output`。
3. 若 `validator: true`, 调 `validate(candidate_output, state_slice, phase_id=..., trace_id=...)`。
4. validator 成功返回 `None` 时沿用 `candidate_output`; 返回 dict 时把该 dict 作为最终输出, 仍需满足 `io.outputs`。
5. validator 抛错或返回非法字段时, 本 phase FATAL, `candidate_output` 不写回黑板。

这个生命周期的关键点是“不黑板回写”: validator 失败时下游 phase 看到的仍是进入本 phase 前的状态, Trace 中记录失败候选输出, 但业务状态不被半成品污染。

[运行时引擎流](./12-compile-runtime-flow-spec.md#运行时引擎流-run-time-workflow) 引用 validator 触发和失败中断位置。

~~## 相关核心错误码速查 (Error Codes)~~ → ✅[已迁入](../../mvp1/01-contract/03-compile-rules/mvp1-alignment.md#logic-domain)

| 错误码 | 阶段 | 触发条件 | 修复方向 |
|---|---|---|---|
| `[F-v3-logic-schema-unknown-field]` | 编译期 | frontmatter 出现未定义字段 | 删除字段或提升到正式 spec |
| `[F-v3-logic-name-invalid]` | 编译期 | `name` 缺失或不匹配命名正则 | 改成小写 snake/kebab 标识 |
| `[F-v3-logic-io-schema-invalid]` | 编译期 | `io.inputs` / `io.outputs` 不是合法 object schema | 修正 JSON Schema |
| `[F-v3-logic-actions-empty]` | 编译期 | `actions` 为空 list | 至少声明一个 action |
| `[F-v3-logic-action-not-found]` | 编译期 | phase-local `actions/<name>.py` 不存在且通用 action registry 无此项 | 增加 phase-local action 文件、注册通用 action 或改名 |
| `[F-v3-logic-action-return-invalid]` | 运行期 | `run()` 未返回 dict | 返回 dict |
| `[F-v3-logic-output-field-undeclared]` | 运行期 | action 或 validator 返回未声明字段 | 更新 `io.outputs` 或删除返回字段 |
| `[F-v3-logic-validator-failed]` | 运行期 | validator 抛业务校验异常 | 修复 action 输出或 validator 规则 |

详见 [F-v3-logic 错误契约](./11-error-code-spec.md#logic-domain)。
