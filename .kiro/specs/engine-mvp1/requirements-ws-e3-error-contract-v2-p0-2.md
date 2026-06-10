---
ws_id: WS-E3-error-contract-v2-p0-2
modules:
  - 01-contract/03-compile-rules
  - 01-contract/04-data-contracts
  - 03-api-contract
depends_on:
  - WS-E3-error-contract-v2-p0-1
blocks: []
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e3-error-contract-v2-p0-2.md
  - .kiro/specs/engine-mvp1/task-ws-e3-error-contract-v2-p0-2.md
  - .kiro/specs/engine-mvp1/gemini-prompt-ws-e3-error-contract-v2-p0-2.md
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/tests/core/test_ws_e3_error_registry_metadata_red.py
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - docs/engine/mvp1/01-contract/03-compile-rules/baseline.md
  - docs/engine/mvp1/01-contract/04-data-contracts/baseline.md
  - docs/engine/mvp1/03-api-contract/baseline.md
spec_ssot:
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §3.1/§3.1.1
  - docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md DC5
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §2.1/§3/§8
status: drafted
created: 2026-06-10
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
review_flow: requirements -> RED tests -> contract gate -> task.md + Gemini prompt -> GREEN -> baseline -> review
---

# WS-E3 错误契约 V2 P0-2 - 需求书

> 本需求书只推进 P0-2:registry metadata 与 engine-first 错误目录导出。下一步是 Codex 写 RED 测试并停在契约门；契约门前不得写 task/Gemini prompt，不得实现生产代码。

## 1. 目标(intent + why)

在 P0-1 已落地的 `ErrorPayload.details` 与 `RunResult.diagnostics` 基础上，把错误码 registry 从“内部 code -> level/stage/doc_link 表”推进为可被任意 host/app 消费的通用错误目录。P0-2 要让每个现有码都有可导出的修复建议、稳定文档引用、可点击文档 URL、details schema 与版本信息，并提供 JSON-safe、版本化的 engine-side catalog export。Studio 如需 `GET /errors`，只能薄透传 engine export；本 WS 默认不实现 Studio HTTP route。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标唯一真理：
  - `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` §3.1 G3/G4 与 §3.1.1 P0-2。
  - `docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md` DC5。
  - `docs/engine/mvp1/03-api-contract/mvp1-alignment.md` §2.1、§3、§8。
- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` Wave 4A，WS-E3 是错误契约 V2 独立轨。
- Backlog 来源：`docs/engine/mvp1/_impl-backlog.md` Tier 3 V2b。
- 上游完成项：`.kiro/specs/engine-mvp1/requirements-ws-e3-error-contract-v2-p0-1.md`。
- 现状锚点：
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`
  - `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`
  - `docs/engine/mvp1/03-api-contract/baseline.md`
- 必读源码与测试(实现前先读并回述关键符号/现状，行号只作 grounding，不作编辑坐标)：
  - `packages/graph-agent/src/graph_agent/core/error_registry.py`：当前 `ErrorCodeMetadata` 只含 `code/level/stage/doc_link`，`ERROR_REGISTRY` 当前 key set 由代码与测试共同锁定为 96 个码。
  - `packages/graph-agent/src/graph_agent/core/exceptions.py`：`ErrorPayload` 的 P0-1 details/unknown code/gateway 外部 code 兼容边界。
  - `packages/graph-agent/src/graph_agent/core/result.py`：`RunResult.diagnostics` 的 P0-1 有界快照边界。
  - `packages/graph-agent/tests/core/test_error_payload_contract.py`、`packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py`、`packages/graph-agent/tests/test_round28_invariant_guards.py`：现有回归锁。

## 3. 文件归属(并发锁,IR1)

本 WS owns 见 frontmatter `owns_files`。默认只实现 engine-side registry metadata/export，不实现 Studio route。

禁止触碰：

- `apps/studio/frontend/**`：P0-2 不做 Studio 前端展示。
- `apps/studio/backend/app/routers/**` 与对应 backend tests：只有契约门明确决定要做 thin `GET /errors` route 时才可另行扩 owns；默认不碰。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`：诊断事件归 WS-E4。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`、WS-E1-io runtime/checkpoint/resume/gateway 热点文件：P0-2 不触碰。
- `packages/graph-agent/src/graph_agent/core/exceptions.py` 与 `result.py`：本 WS 只回归验证 P0-1 语义，不默认修改它们；若 RED 证明必须修改，先停下扩 owns。

共享文件协调：

- `error_registry.py` 是本 WS 的 engine SSOT。任何 HTTP route、Studio DTO 或 UI 都不得反向定义 registry 语义。
- baseline 只在 GREEN 后照真实代码回写，不在 RED 或契约门前预写目标。

## 4. 现状锚点(baseline)

当前 registry 是 96 个现有码的静态表；每条 metadata 只有 `code/level/stage/doc_link`。P0-1 已让 payload details 与 result diagnostics 可用，但 registry 仍不能导出通用 consumer 需要的 remediation、稳定 doc ref、公开 doc URL、details schema 或 catalog schema/version envelope。

## 5. 目标行为(可测的契约)

### 5.1 Registry metadata 补齐 P0-2 字段

- 每个现有码必须继续能通过 `ERROR_REGISTRY[code]` 读取旧字段：`code`、`level`、`stage`、`doc_link`。
- 每个现有码还必须有 P0-2 metadata：`remediation`、`doc_ref`、`doc_url`、`details_schema`、`schema_version`，以及当前 catalog item 所需的 `status`。
- `remediation` 来自 compile-rules 全表里的修复建议语义；必须是稳定、非空、面向作者/host 的简短建议。
- `doc_ref` 是稳定机器引用，语义上对应 `graph-agent://errors/<code>`；`doc_url` 是可点击的公开 URL。`doc_link` 保留为向后兼容别名，不在 P0-2 删除或改成唯一来源。
- `details_schema` 必须是 JSON Schema 形状的 dict；P0-2 可对尚未逐码细化的 code 使用安全的 object schema，但不能是自由的非 JSON Python 类型。
- `schema_version` 标记当前 metadata/details schema 版本语义；P0-2 不引入 i18n、remediation_actions、deprecated/replaced_by 生命周期。
- `status` 只表达当前 catalog item 可消费状态。P0-2 可以统一为 active；不得实现生命周期管理。

### 5.2 Engine-side 错误目录导出

- Engine 必须提供稳定、JSON-safe、版本化的错误目录导出 API。该 API 是任意 host/app 的 SSOT，Studio 只能消费它。
- Engine-side API 入口为 `export_error_catalog() -> dict[str, Any]` 与 `export_error_metadata(code: str) -> dict[str, Any]`。这是 host/app 可依赖的目录读取契约；具体内部数据结构由实现者决定。
- 导出 envelope 至少包含 registry/catalog 版本语义、schema 版本语义和 `items` 列表。
- 每个 item 至少包含：`code`、`level`、`stage`、`domain` 或等价既有轴、`remediation`、`doc_ref`、`doc_url`、`status`、`details_schema`、`schema_version`。
- 导出顺序必须确定，适合 snapshot/test/HTTP cache；不得依赖 dict 插入漂移或非确定性集合序列化。
- 导出结果必须可 `json.dumps` / `json.loads` 往返，不带 tuple、Path、BaseModel、Exception 等非 JSON 传输类型。
- `export_error_metadata(code)` 对 unknown engine code 必须拒绝，不能静默生成目录项；gateway 外部 code 仍由 P0-1 兼容分支处理，不纳入 engine registry。

### 5.3 旧行为与边界不回归

- `ERROR_REGISTRY` key set 不因 P0-2 改变；当前代码/测试锁定的 96 个 code 一个不少、一个不多。
- `ErrorPayload` 继续拒绝 unknown engine code；gateway 外部 code 兼容分支继续不生成 engine payload。
- P0-1 的 `ErrorPayload.details` 与 `RunResult.diagnostics` 语义不变：本 WS 可复用它们做回归，但不重新定义 diagnostics 事件或运行期 catch-all 细分。
- 旧 consumer 读取 `metadata.code`、`metadata.level`、`metadata.stage`、`metadata.doc_link` 不破。

### 5.4 Studio HTTP route 默认不做

- 本 WS 的必交付是 engine export。是否做 Studio `GET /errors` 必须由契约门显式决定。
- 若后续纳入 Studio route，它只能从 engine export 读取同一 envelope；HTTP 层不得复制 registry 数据、不得发明 Studio-only 字段、不得成为 SSOT。
- 不碰 Studio frontend。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试并运行到预期失败，随后停在契约门。测试至少覆盖：

- Registry metadata：每个现有码都有 P0-2 字段，字段 JSON-safe，旧字段 lookup 行为不回归。
- Catalog envelope：engine export 有 registry/schema 版本语义和稳定 `items`；items 至少含 §5.2 的字段，`stage` 导出为 JSON array，顺序确定。
- Unknown/gateway 回归：unknown engine code 仍拒绝；外部 gateway code 兼容仍不被 engine registry 强行接管。
- Key set 回归：不新增/删除现有码，继续与 compile-rules 全表和现有 invariant 锁一致。
- P0-1 回归：`ErrorPayload.details` 和 `RunResult.diagnostics` 的基础语义不被 P0-2 metadata 改动。
- 真实 consumer 边界：至少一条测试把 engine export 做 JSON 序列化/反序列化后断言 shape 仍可消费；若实现 Studio route，则必须另测 HTTP route 返回同一 envelope。
- 负面范围：测试不得要求 i18n、remediation_actions、deprecated/replaced_by 生命周期、分页/过滤、P0-3 运行期细分码或 Studio frontend 展示。

## 7. 硬依赖约束

1. P0-2 metadata 不能破坏 P0-1 payload/result 语义；先守旧回归，再加 catalog export。
2. Engine export 必须以 `ERROR_REGISTRY` 为 SSOT；任何 host route 只能薄透传。
3. baseline 回写只能发生在 GREEN 后，且只能描述真实落地代码。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 RED 测试先失败，失败形状证明缺的是 P0-2 metadata/export，而不是环境错误。
- [ ] 契约门确认测试没有把 P0-3/P1/P2 或 Studio frontend 拉进来。
- [ ] GREEN 后所有新增/修改测试通过。
- [ ] `ERROR_REGISTRY` key set 仍为当前 96 个现有码，旧 metadata lookup 属性不回归。
- [ ] 每个 catalog item JSON-safe，带 remediation/doc_ref/doc_url/details_schema/schema_version/status。
- [ ] Engine export envelope JSON roundtrip 通过，顺序稳定。
- [ ] Unknown code、gateway 外部 code、P0-1 details/diagnostics 回归通过。
- [ ] 若实现 Studio `GET /errors`，HTTP 测试证明它只是 thin consumer；若未实现，验收汇报明确说明本 WS 只交付 engine export。
- [ ] 不触碰 forbidden files。

## 9. 不做(范围锁定,IR7)

- 不做 P0-3 运行期 catch-all 细分，不新增 tool/state-transform/persistence/provider 错误码。
- 不做 i18n、message_key/template_vars、remediation_actions。
- 不做错误码生命周期管理；P0-2 只允许当前 `status` 输出，不实现 deprecated/replaced_by 迁移语义。
- 不做 pagination/filtering/etag 后台优化；若 envelope 包含预留字段，也不得要求行为实现。
- 默认不做 Studio backend route，不碰 Studio frontend。
- 不改 `callbacks/events.py`/`emit.py`，不实现 `DiagnosticEmittedEvent`。
- 不改 `graph_assembler.py`、WS-E1 runtime/checkpoint/resume/gateway 文件。

## 10. baseline 回写指令(IR6)

实现落地后，Codex 按真实代码回写：

- `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`：记录 P0-2 registry metadata 字段、现有码数量、doc_ref/doc_url/details_schema/status 的真实形状。
- `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`：记录 `ErrorPayload.details`/`RunResult.diagnostics` 未被 P0-2 改语义，以及 registry metadata 与 payload 的真实关系。
- `docs/engine/mvp1/03-api-contract/baseline.md`：记录 engine-side catalog export envelope；若未实现 Studio `GET /errors`，明确 HTTP route 仍未 live。

## 11. 评审检查点

- 契约门(Claude 审测试)：重点查 RED 是否忠实编码 registry metadata + engine export，是否有 JSON consumer 边界，是否错误引入 Studio route/P0-3/P1/P2。
- Codex 审查退出：只按 §8 硬退出条件，不因“字段大概有了”放行；尤其查旧 consumer 属性、key set、JSON-safe 和 forbidden files。
- Claude 终审：看 engine-first 是否成立、baseline 是否诚实、测试是否假绿或过度锁死实现。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准测试写 kiro `task.md`，落点 `.kiro/specs/engine-mvp1/task-ws-e3-error-contract-v2-p0-2.md`，遵守：

- 来源 = 已批准测试，测试是契约；不凭空设计实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`，不重写设计。
- 嵌入编排注解：`owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；本需求书行号只作 grounding。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出 Gemini prompt，包含工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令、回报格式。
- 完整规范见 `docs/development/task-spec-standard.md` §四 4.2。
