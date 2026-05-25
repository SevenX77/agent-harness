# Error Code Spec

本文定义 `[F-v3-*]` 错误码前缀、等级划分和速查表。它是所有 spec 的统一失败语义出口, 并会被 [编译期校验流](./12-compile-runtime-flow-spec.md#编译期校验流-compile-time-workflow) 与各字段契约反向引用。

## 错误码设计模式 (Prefix [F-v3-*])

格式:

```text
[F-v3-<domain>-<specific>]
```

字段级定义:

| 部分 | 类型 | 必填 | 默认值 | 校验规则 | 业务作用 |
|---|---|---|---|---|---|
| `F` | literal | 是 | 无 | 固定为 `F` | 表示 framework/format 级错误, 不是业务判断失败 |
| `v3` | literal | 是 | 无 | 固定为 `v3` | 对应 V0.3.0 契约族 |
| `domain` | enum | 是 | 无 | `graph`, `logic`, `subgraph`, `agent`, `mention`, `resource`, `resolver`, `cognitive`, `tool`, `runtime` | 定位失败模块 |
| `specific` | kebab-case | 是 | 无 | 小写字母数字短横线 | 定位具体规则 |

等级:

| 等级 | 含义 | 是否中断 | 典型场景 |
|---|---|---|---|
| FATAL | 契约无法满足, 继续会产生错误执行或不可定位状态 | 是 | 字段缺失、mode/path 不一致、IO schema 不合法 |
| WARN | 契约主体可满足, 但质量或可维护性下降 | 否 | reference reader 失败降级、未使用 registry entry |

错误 payload 必须至少包含 `code`, `level`, `stage`, `message`, `doc_link`; 推荐包含 `skill_id`, `phase_id`, `field_path`, `source_path`。

各字段 spec 的 FATAL / WARN 判断最终收敛到本节命名规则。

TraceEventKind (例如 `AMBIGUITY_LOGGED` / `BUILTIN_SUBAGENT_FALLBACK`) 不是错误码, 不进入本速查表; 事件协议由 tracing-and-observability 文档维护。

## 错误码速查全表

### graph domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-graph-schema-unknown-field]` | 编译期 | `GRAPH.md` frontmatter 出现未知字段 | 删除字段或纳入 spec | [GRAPH](./02-graph-md-spec.md#基础元数据字段-metadata) |
| `[F-v3-graph-name-invalid]` | 编译期 | `name` 缺失或命名非法 | 改为小写开头标识 | [GRAPH](./02-graph-md-spec.md#基础元数据字段-metadata) |
| `[F-v3-graph-schema-version-mismatch]` | 编译期 | `schema_version` 不是 `"0.3.0"` | 升级/降级 spec 或 engine | [GRAPH](./02-graph-md-spec.md#基础元数据字段-metadata) |
| `[F-v3-graph-llm-role-unknown]` | 编译期 | `llm_role` 未注册 | 使用 `llm_roles.yaml` 中角色 | [GRAPH](./02-graph-md-spec.md#基础元数据字段-metadata) |
| `[F-v3-graph-root-missing]` | 编译期 | `<skill_root>/GRAPH.md` 缺失或大小写不匹配 | 创建精确命名的 `GRAPH.md` | [Physical](./01-physical-layout.md#物理结构拓扑-directory-tree) |
| `[F-v3-graph-phases-dir-missing]` | 编译期 | `<skill_root>/phases/` 缺失 | 创建 phases 目录 | [Physical](./01-physical-layout.md#物理结构拓扑-directory-tree) |
| `[F-v3-graph-phase-id-invalid]` | 编译期 | phase id 命名非法 | 修正 `phases[].id` 和目录名 | [GRAPH](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag) |
| `[F-v3-graph-phase-id-duplicate]` | 编译期 | phases 列表 id 重复 | 去重 | [GRAPH](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag) |
| `[F-v3-graph-depends-unknown]` | 编译期 | `depends_on` 引用未声明 phase | 修正依赖名 | [GRAPH](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag) |
| `[F-v3-graph-phase-cycle]` | 编译期 | DAG 存在环 | 打断循环依赖 | [GRAPH](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag) |
| `[F-v3-graph-phase-island]` | 编译期 | phase 与入口不可达 | 增加依赖连接或删除孤岛 | [GRAPH](./02-graph-md-spec.md#phases-列表与拓扑校验-phase-dag) |
| `[F-v3-graph-phase-dir-missing]` | 编译期 | phase 目录不存在 | 创建 `phases/<id>/` | [Physical](./01-physical-layout.md#物理结构拓扑-directory-tree) |
| `[F-v3-graph-phase-mode-ambiguous]` | 编译期 | 同一 phase 下多个节点文件 | 保留 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 之一 | [Physical](./01-physical-layout.md#物理结构拓扑-directory-tree) |
| `[F-v3-graph-phase-node-missing]` | 编译期 | phase 目录下没有节点文件 | 添加 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 之一 | [Physical](./01-physical-layout.md#物理结构拓扑-directory-tree) |
| `[F-v3-graph-mode-path-mismatch]` | 编译期 | 文件名与 frontmatter mode 不一致 | 修正文件名或 mode | [Physical](./01-physical-layout.md#mode路径双向校验-mode-path-cross-validation) |
| `[F-v3-graph-io-not-object]` | 编译期 | 根 IO 顶层不是 object schema | 设置 `type: object` | [GRAPH](./02-graph-md-spec.md#根-io-契约-root-io-schema) |
| `[F-v3-graph-io-schema-invalid]` | 编译期 | 根 IO JSON Schema 非法 | 修正 schema | [GRAPH](./02-graph-md-spec.md#根-io-契约-root-io-schema) |
| `[F-v3-graph-io-physical-file-deprecated]` | 编译期 | 使用旧 `io/inputs.json` 或 `io_inputs_ref` | 改为 inline `io.inputs` / `io.outputs` | [Physical](./01-physical-layout.md#io-物理文件退役声明-inline-io-deprecation) |
| `[F-v3-graph-dataflow-source-missing]` | 编译期 | phase input 没有根输入或上游输出来源 | 补依赖或调整 IO | [GRAPH](./02-graph-md-spec.md#根-io-契约-root-io-schema) |

### logic domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-logic-schema-unknown-field]` | 编译期 | LOGIC frontmatter 未知字段 | 删除字段 | [LOGIC](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation) |
| `[F-v3-logic-name-invalid]` | 编译期 | `name` 非法 | 修正命名 | [LOGIC](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation) |
| `[F-v3-logic-mode-invalid]` | 编译期 | `mode` 不是 `logic` | 改为 `logic` | [LOGIC](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation) |
| `[F-v3-logic-io-schema-invalid]` | 编译期 | Logic IO schema 非法 | 修正 object schema | [LOGIC](./03-logic-md-spec.md#frontmatter-字段解析表-schema--validation) |
| `[F-v3-logic-actions-empty]` | 编译期 | `actions` 为空 | 声明至少一个 action | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-action-name-invalid]` | 编译期 | action 名非法 | 使用一级合法函数名 | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-action-dir-missing]` | 编译期 | `<skill_root>/actions/` 缺失 | 创建目录 | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-action-not-found]` | 编译期 | action py 文件不存在 | 增加 `<name>.py` | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-action-entrypoint-missing]` | 编译期 | action 无 `run()` | 导出 `run` | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-action-return-invalid]` | 运行期 | action 返回非 dict | 返回 dict | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-output-field-undeclared]` | 运行期 | 返回未声明输出字段 | 更新 `io.outputs` 或删字段 | [LOGIC](./03-logic-md-spec.md#actions-1-级寻址与执行契约) |
| `[F-v3-logic-validator-type-invalid]` | 编译期 | `validator` 不是 boolean | 改为 true/false | [LOGIC](./03-logic-md-spec.md#validator-生命周期-post-execution-hook) |
| `[F-v3-logic-validator-missing]` | 编译期 | `validator: true` 但无文件 | 增加同级 `validator.py` | [LOGIC](./03-logic-md-spec.md#validator-生命周期-post-execution-hook) |
| `[F-v3-logic-validator-entrypoint-missing]` | 编译期 | validator 无 `validate()` | 导出 `validate` | [LOGIC](./03-logic-md-spec.md#validator-生命周期-post-execution-hook) |
| `[F-v3-logic-validator-failed]` | 运行期 | logic validator 抛异常 | 修正输出或校验规则 | [LOGIC](./03-logic-md-spec.md#validator-生命周期-post-execution-hook) |
| `[F-v3-agent-validator-failed]` | 运行期 | agent validator 抛异常 | 触发 LLM 重试反馈 | |
| `[F-v3-subgraph-validator-failed]` | 运行期 | subgraph validator 抛异常 | 检查子图业务规则 | |

### subgraph domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-subgraph-schema-unknown-field]` | 编译期 | SUBGRAPH 未知字段 | 删除字段 | [SUBGRAPH](./04-subgraph-md-spec.md#mode-声明与类型断言) |
| `[F-v3-subgraph-name-invalid]` | 编译期 | `name` 非法 | 修正命名 | [SUBGRAPH](./04-subgraph-md-spec.md#mode-声明与类型断言) |
| `[F-v3-subgraph-mode-invalid]` | 编译期 | `mode` 不是 `subgraph` | 改为 `subgraph` | [SUBGRAPH](./04-subgraph-md-spec.md#mode-声明与类型断言) |
| `[F-v3-subgraph-target-skill-invalid]` | 编译期 | `target_skill` 非法或像路径 | 使用 registry skill id | [SUBGRAPH](./04-subgraph-md-spec.md#target_skill-寻址规则) |
| `[F-v3-subgraph-io-schema-invalid]` | 编译期 | Subgraph IO schema 非法 | 修正 object schema | [SUBGRAPH](./04-subgraph-md-spec.md#io-严格-11-映射校验-strict-mapping) |
| `[F-v3-subgraph-io-mismatch]` | 编译期 | 父子 IO 字段集合不一致 | 对齐父 phase 和子 GRAPH IO | [SUBGRAPH](./04-subgraph-md-spec.md#io-严格-11-映射校验-strict-mapping) |
| `[F-v3-subgraph-io-schema-incompatible]` | 编译期 | 同名字段 schema 不兼容 | 对齐字段 schema | [SUBGRAPH](./04-subgraph-md-spec.md#io-严格-11-映射校验-strict-mapping) |

### agent domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-agent-schema-unknown-field]` | 编译期 | Agent frontmatter 未知字段 | 删除字段 | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-name-invalid]` | 编译期 | `name` 非法 | 修正命名 | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-mode-invalid]` | 编译期 | `mode` 不是 `agent` | 改为 `agent` | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-llm-role-unknown]` | 编译期 | llm role 未注册 | 使用已注册角色 | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-io-schema-invalid]` | 编译期 | Agent IO schema 非法 | 修正 schema | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-output-schema-invalid]` | 运行期 | CognitiveFlowMiddleware SchemaEngine strict 校验失败 (io.outputs 不匹配) | 触发 LLM 重试反馈 | |
| `[F-v3-agent-output-schema-missing]` | 运行期 | io.outputs schema 缺失 (编译期未生成), fatal 拒绝 | 修正 AST / pipeline | |
| `[F-v3-agent-tool-unknown]` | 编译期 | tool 未注册 | 注册 tool 或删引用 | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-subagent-invalid]` | 编译期 | subagents 项缺字段 | 补 name/target_skill/description | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-subgraph-invalid]` | 编译期 | subgraphs 项缺字段 | 补 name/target_skill/description | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-max-iterations-invalid]` | 编译期 | max_iterations 超范围 | 设为 1..50 | [Agent](./05-agent-md-spec.md#frontmatter-字段解析表) |
| `[F-v3-agent-body-tag-unknown]` | 编译期 | 使用了不允许的顶级标签 | 仅保留 4 类白名单标签 | [Agent](./05-agent-md-spec.md#body-xml-扁平化容器) |
| `[F-v3-agent-role-missing]` | 编译期 | 缺 `<role>` | 添加 role | [Agent](./05-agent-md-spec.md#必须持有的业务核心标签) |
| `[F-v3-agent-goal-missing]` | 编译期 | 缺 `<goal>` | 添加 goal | [Agent](./05-agent-md-spec.md#必须持有的业务核心标签) |
| `[F-v3-agent-step-invalid]` | 编译期 | step id/name 非法或重复 | 修正 step | [Agent](./05-agent-md-spec.md#body-xml-扁平化容器) |
| `[F-v3-agent-protocol-invalid]` | 编译期 | protocol id 非法或重复 | 修正 protocol | [Agent](./05-agent-md-spec.md#body-xml-扁平化容器) |

### mention domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-mention-type-unknown]` | 编译期 | mention 类型不在 7 类内 | 改用合法 type | [Mention](./07-mention-syntax-spec.md#--mention-语法规范) |
| `[F-v3-mention-syntax-invalid]` | 编译期 | token 残缺或含空格 | 改成 `@type:NAME` | [Mention](./07-mention-syntax-spec.md#--mention-语法规范) |
| `[F-v3-mention-target-not-found]` | 编译期 | 目标不在对应 registry | 注册目标或修正文案 | [Mention](./07-mention-syntax-spec.md#7-大分类静态可达性算法) |
| `[F-v3-mention-unused-registry-entry]` | 编译期 | 注册项未被 body 引用 | 确认是否保留 | [Mention](./07-mention-syntax-spec.md#语法滥用与容错) |

### resource domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-resource-reference-invalid]` | 编译期 | reference 项缺字段或结构错 | 补 id/path/summary | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-reference-id-invalid]` | 编译期 | reference id 非法或重复 | 修正 id | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-reference-path-invalid]` | 编译期/运行期 | reference path 不可读或逃逸 root | 修正路径 | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-reference-summary-missing]` | 编译期 | reference summary 为空 | 补 summary | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-reference-not-found]` | 运行期 | `read_reference` id 不存在 | 使用 registry 中 id | [Builtin](./09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example) |
| `[F-v3-resource-example-invalid]` | 编译期 | example 项缺字段或结构错 | 按 inline/document 补字段 | [Resource](./08-resource-mechanisms-spec.md#example-双模式处理逻辑) |
| `[F-v3-resource-example-id-invalid]` | 编译期 | example id 非法或重复 | 修正 id | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-example-type-invalid]` | 编译期 | type 不是 inline/document | 修正 type | [Resource](./08-resource-mechanisms-spec.md#example-双模式处理逻辑) |
| `[F-v3-resource-example-path-missing]` | 编译期 | document example 缺 path | 补 path | [Resource](./08-resource-mechanisms-spec.md#example-双模式处理逻辑) |
| `[F-v3-resource-example-path-invalid]` | 编译期/运行期 | example path 不可读 | 修正路径 | [Resource](./08-resource-mechanisms-spec.md#frontmatter-挂载格式) |
| `[F-v3-resource-example-summary-missing]` | 编译期 | document example 缺 summary | 补 summary | [Resource](./08-resource-mechanisms-spec.md#example-双模式处理逻辑) |
| `[F-v3-resource-example-not-found]` | 运行期 | `read_example` id 不存在 | 使用 registry 中 id | [Builtin](./09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example) |
| `[F-v3-reference-reader-failed]` | 装配期 | builtin reader 超时/异常/输出非法 | 查看 trace; 可依赖降级内容继续跑 | [Builtin](./09-builtin-modules-spec.md#优雅降级策略-graceful-degradation) |

### resolver domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-resolver-skill-id-invalid]` | 编译期 | skill id 非法 | 修正 target_skill | [Resolver](./10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| `[F-v3-skill-not-registered]` | 编译期/装配期 | resolver 查不到 skill | 在 Studio 导入或注册 skill | [Resolver](./10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| `[F-v3-resolver-path-invalid]` | 编译期 | resolver 返回路径无 GRAPH.md | 修正 registry 记录 | [Resolver](./10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| `[F-v3-resolver-interface-invalid]` | 编译期 | resolver 暴露非决议接口 | 实现单方法 `resolve_skill` | [Resolver](./10-skill-resolver-protocol-spec.md#protocol-interface-定义) |
| `[F-v3-resolver-missing]` | 运行期 | 需要 resolver 但未注入 | 调用入口传入 resolver | [Resolver](./10-skill-resolver-protocol-spec.md#依赖注入-di-边界) |

### cognitive / tool / runtime domain

| 错误码 | 阶段 | 具体原因 | 修复建议 | Spec |
|---|---|---|---|---|
| `[F-v3-cognitive-slot-render-failed]` | 装配期 | template slot 序列化失败 | 检查 body AST | [Cognitive](./06-cognitive-template-spec.md#静态组装插槽解析) |
| `[F-v3-cognitive-output-schema-render-failed]` | 装配期 | output schema 无法嵌入 exit_contract | 修正 `io.outputs` | [Cognitive](./06-cognitive-template-spec.md#动态装配插槽解析) |
| `[F-v3-reference-reader-input-invalid]` | 装配期 | reader 输入 JSON 非法 | 检查 references registry | [Builtin](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) |
| `[F-v3-reference-reader-output-invalid]` | 装配期 | reader 输出 JSON 非法 | 修 reader 模块 | [Builtin](./09-builtin-modules-spec.md#builtin-reference-reader-subagent-签名) |
| `[F-v3-tool-argument-invalid]` | 运行期 | builtin tool 参数非法 | 修正 tool 调用参数 | [Builtin](./09-builtin-modules-spec.md#按需调取-tools-read_reference--read_example) |
| `[F-v3-runtime-state-mapping-failed]` | 运行期 | StateMapper 切片或回写失败 | 检查 phase IO 和上游输出 | [Flow](./12-compile-runtime-flow-spec.md#运行时引擎流-run-time-workflow) |
| `[F-v3-runtime-phase-failed]` | 运行期 | phase 执行异常且无法归入更细错误 | 查看 trace 原始异常 | [Flow](./12-compile-runtime-flow-spec.md#运行时引擎流-run-time-workflow) |

本表覆盖 [Physical Layout](./01-physical-layout.md), [GRAPH.md](./02-graph-md-spec.md), [LOGIC.md](./03-logic-md-spec.md), [SUBGRAPH.md](./04-subgraph-md-spec.md), [Agent SKILL.md](./05-agent-md-spec.md) 等契约。
