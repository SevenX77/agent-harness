# Design: Standard Error Payload (PR F2)

## 0. 前置状态确认 (PR F1)
PR F1 的任务（清理旧 `[F-v21-*]` 错误码）在引擎范围 `src/` 与 `tests/` 下实测为 0 次出现。实质已完成，不再另行设计。

## 1. 核心设计抉择 (F2)

### 1.1 标准 Payload 落地形式
**方案**: 引入 Pydantic 模型 `ErrorPayload` 并挂载为异常类的核心属性。
- 修改 `GraphAgentError` 基类，将签名变更为 `__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict | None = None)`。
- **理由**: 相比于在 `GraphAgentError` 上挂载一系列零散 kwarg 或是从字符串正则提取 code，Pydantic 模型在系统边界（API Gateway, Tracing 链路）能够提供天然的 `.model_dump()` 支持，且能通过 Pydantic 强大的 Field validation 保证 `11-error-code-spec.md` 规定的必须字段（`code`, `level`, `stage`, `message`, `doc_link`）的绝对完整性。

### 1.2 粗粒度码 (Coarse Codes) 的处理
**现状**: `[F-v3-route]`, `[F-v3-io]`, `[F-v3-graph]`, `[F-v3-actions]`, `[F-v3-purity]` 在 `loader.py` 中被大量前缀拼接抛出。
**处理**: **收敛消除（消除漂移）**。
- 这是一类实现期的 drift。11-spec 追求的是通过细粒度的 `doc_link` 提供具体的修复建议，而粗粒度码不仅没有对应的官方速查表记录，也无法映射到明确的指导文档。
- 策略：必须将其在 `loader.py` 等抛出站点的语义替换为 `11-error-code-spec.md` 中的细码。例如：对于 `<actions>` 的验证不应抛出兜底的 `[F-v3-actions]`，而应抛出 `[F-v3-logic-actions-empty]` 等对应的枚举错误码。

### 1.3 `level`, `stage`, `doc_link` 的自动化填充
**设计**: 基于静态字典或 `ErrorRegistry` 的工厂模式/校验器自动注入。
- 在 `packages/graph-agent/src/graph_agent/core/` 引入 `error_registry.py`，其中包含一个从 `11-spec` 导出的（或硬编码同步的）规范字典。
- 当实例化 `ErrorPayload(code="[F-v3-graph-phase-cycle]", message="...")` 时，通过 Pydantic 的 `@model_validator(mode="after")` 或专用的类方法自动查找 `code`，将对应的 `level` (FATAL/WARN)、`stage` (编译期等)、`doc_link` 自动填充至模型内。
- 业务抛出代码保持精简：`raise SkillCompileError(payload=ErrorPayload(code="...", message="..."))`，避免散弹枪式的元数据硬编码。

### 1.4 测试断言契约升级
**设计**: 必须从 "message 正则匹配" **全面升级**为 "结构化 payload 断言"。
- 弃用 `pytest.raises(..., match=r"\[F-v3-...\]")`。
- 升级为抓取异常并断言 `exc_info.value.payload.code == "[F-v3-...]"。
- **影响评估**: `grep` 显示含 `F-v3-` 的测试文件 24 个, message-regex `match=` 断言站点 41 处, `F-v3-` 总 occurrences 118。虽然存在迁移阵痛，但这能强保障对外输出的 Pydantic Schema 的业务契约一致性，杜绝未来因错误提示语修改导致的偶发脆性报错。

---

## §0.5 继承字段表 (SOP-06 强制)

以下为 `packages/graph-agent/src/graph_agent/core/exceptions.py` 及代码库各处 `error_code` kwarg 站点的变更分析：

| 原异常类 / 站点 | 原有字段 (或 kwarg) | Round 17 新映射字段 (挂载至 Payload) | 状态 | 备注 / 判定归属 |
|---|---|---|---|---|
| `GraphAgentError` | `message` (str), `context` (dict) | `payload` (ErrorPayload 模型) | `[NEW]` | **A类** (V0.3.0 必然组成) |
| 各处 Kwarg 传递 | `error_code="..."` (直接散落在外部) | `payload.code` | `[BREAKING]` | **A类** (规范强制收拢，消除散落点) |
| `SkillCompilationError` | `compile_result`, `skill_path`, `line`, `field_path`, `suggestion` | `skill_path` -> `payload.source_path`<br>`field_path` -> `payload.field_path` | `[BREAKING]` | **A类** (不需 PM 再拍)。理由：`11-error-code-spec.md` 明确推荐标准 payload 含 `field_path`, `source_path`。将同名定位字段收拢进 `ErrorPayload` 是执行已批准契约的必然组成，且同系列圆桌已多次 ship 同性质变更。迁移路径：`SkillCompilationError` 内部转发字段到 `payload`，单源收拢，不长期双写。 |
| (自动填充项) | 无 | `payload.level`, `payload.stage`, `payload.doc_link` | `[NEW]` | **A类** (11-spec 指定必须项) |
| (可选结构项) | 无 | `payload.skill_id`, `payload.phase_id` | `[NEW]` | **A类** (11-spec 推荐项) |

> **关于 [BREAKING] 类别的划分补充说明**:
> - **A类**: `error_code` kwarg 的消除是执行 `11-error-code-spec.md` 统一出口的基础前提，属于 PM 已批准的 V0.3.0 hard cutover 范畴。将 `SkillCompilationError` 独占的结构化定位字段（如 `field_path`）重构抽离至全局 `ErrorPayload`，是执行标准 payload 规范 (line 29 推荐字段) 的必然重构，且与 tasks.md §3 的 A类单源委托机制对齐。