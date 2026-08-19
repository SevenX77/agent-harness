# Decision: an error code either fires or leaves (2026-08-19)

## 背景

`ERROR_REGISTRY` 冻结在 99 码,其中 13 个码在引擎源码里没有任何发出点
(emitter)。它们能通过 registry 形状测试,却永远不会出现在任何编译结果里 —
文档引用它们时读者以为存在对应校验,实际不存在。触发点:story-deconstruction
skill 排障期间,后台审计发现这 13 个"死码"(chip 3)。

裁决方法:**经验探针**。为每个码构造违例 skill,真实调用 `compile_skill`,
观察实际报出的码,再对照权威设计源(`docs/engine/mvp1/01-contract/`)判定
该码描述的条件是(a)已被活码覆盖、(b)在 MVP1 下不可表示/与钉死行为矛盾、
还是(c)真实存在却无人把守的缺口。

## 裁决

原则:**码必发出、否则离表。** registry 不为计数冻结保留死条目 — 旧的
99 码计数冻结(round28)随本裁决废除,计数锁改为 88。

### DELETE(11 个)

| 码 | 依据 |
|---|---|
| `[F-v3-graph-phase-dir-missing]` | 条件已被活码覆盖:整个 `phases/` 缺失或单个声明目录缺失分别报 `[F-v3-graph-root-missing]` / `[F-v3-graph-phase-node-missing]`(探针实证) |
| `[F-v3-agent-name-invalid]` | SKILL.md frontmatter 没有 `name` 字段可言;phase 命名由活码 `[F-v3-graph-phase-id-invalid]` 把守 |
| `[F-v3-logic-name-invalid]` | 同上 |
| `[F-v3-mention-type-unknown]` | mvp0 的"未知 mention 类型即 FATAL"过宽:`@word:word` 与普通散文(邮箱、用户名)不可区分,MVP1 扫描器只识别 7 类、未知类型按纯文本处理是正确设计 |
| `[F-v3-mention-unused-registry-entry]` | 被 `read_reference` 设计取代:body @mention 只是引用的一条访问路径,模型可在运行期直接读 registry,"注册未提及"不构成缺陷 |
| `[F-v3-reference-reader-input-invalid]` | 与 fallback 设计矛盾:reader 任何失败都走 raw-excerpt fallback + WARN(`[F-v3-reference-reader-failed]`),已有测试钉死"FATAL 码也不阻断装配" |
| `[F-v3-reference-reader-output-invalid]` | 同上 |
| `[F-v3-cognitive-slot-render-failed]` | 装配期 slot 渲染的输入在编译期已被上游校验挡住,渲染失败态不可达 |
| `[F-v3-cognitive-output-schema-render-failed]` | 同上 |
| `[F-v3-subgraph-io-mismatch]` | **设计裁决在先**:`02-skill-syntax/mvp1-alignment.md` §3.4「父图和子图 IO 不需要字段全集一一相等」,§4 把 1:1 强绑定列为 drift;编译闸已由 commit `cad7dbc0`(2026-06-20,PM 授权)移除,边界由运行期 `StateMapper` 守(`[F-v3-runtime-state-mapping-failed]`)。码此前仅为 99 计数冻结保留;冻结废除,码离表 |
| `[F-v3-subgraph-io-schema-incompatible]` | 同上;自 round-17 建表(`c32575fa`)起从未有过发出点 |

> 实施备注:本 PR 初版曾把最后两码误判为 WIRE 并实现了 seam 校验;
> `test_baseline_doc_error_code_liveness` 的 cad7dbc0 守卫拦下了它。
> 探针只能证明"能接线",不能证明"该接线" — 设计源优先于探针直觉。

### WIRE(2 个)

| 码 | 缺口 | 发出点 |
|---|---|---|
| `[F-v3-subgraph-name-invalid]` | SUBGRAPH.md 相位节点的 `name` 无标识符校验(`name: bad sub!` 编译通过),而 agent 内嵌 subgraph 声明早已按同一规则把守;设计表把它列为活的编译期检查 | `loader._validate_subgraph_node_name` |
| `[F-v3-resolver-interface-invalid]` | 传入不含可调用 `resolve_skill` 的 resolver,深处才炸 AttributeError,而非边界快速失败 | `skill_resolver_protocol.require_skill_resolver`;沿用 `[F-v3-resolver-missing]` 的既有 seam(裸抛 `SkillResolutionError`,resolver 域错误 = 调用方配置错误,不聚合进 SkillLoadError) |

## 关键设计决定

1. **计数锁 99 → 88**,同步 5 处事实源:`ERROR_REGISTRY` + `_CATALOG_METADATA_ROWS`
   (位置 zip,strict=True,同步删行)、`test_compile_diagnostics_v2_red` 冻结表、
   compile-rules `mvp1-alignment.md` §4 全表(表头计数即测试提取锚点)、
   mvp0 `11-error-code-spec.md`、`spec/features.yaml` primary-owner 映射。
2. **§4 注释里的历史码引用去括号**(`F-v3-...` 不带 `[]`):key-set 门禁从
   §4 全文提取一切 `[F-v3-*]` token,散文引用死码会被当成契约行。
3. 新增守卫测试 `test_thirteen_codes_adjudicated.py`:11 码离表断言、2 个
   WIRE 闸的违例触发断言、以及"非 1:1 seam 照常编译"的设计钉
   (防止将来有人再把两死码接回去)。

## 验收判据

- `test_thirteen_codes_adjudicated.py` 6/6;
- registry↔spec-doc↔features.yaml↔catalog 四方 key-set 门禁全绿
  (`test_error_payload_contract` / `test_ws_e3` / `test_round28_invariant_guards`
  / `test_baseline_doc_error_code_liveness`);
- 引擎全量 pytest + `mypy --strict` + ruff 绿。
