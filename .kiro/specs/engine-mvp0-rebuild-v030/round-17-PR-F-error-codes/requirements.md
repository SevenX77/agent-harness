# Requirements: Standard Error Payload (PR F2)

本需求文档规范了 PR F2 (Standard Error Payload) 落地到代码库的必须实现标准与验收条件。

## Req 1: 定义 `ErrorPayload` Pydantic 模型
- **规范**: 必须在 `packages/graph-agent/src/graph_agent/core/exceptions.py` 或同级域内定义 `ErrorPayload(BaseModel)`。
- **字段要求**:
  - 必须包含 (必填): `code: str`, `level: str`, `stage: str`, `message: str`, `doc_link: str`。
  - 可选包含 (推荐): `skill_id: str | None`, `phase_id: str | None`, `field_path: str | None`, `source_path: str | None`。
- **行为**: `ErrorPayload` 的实例化不应要求调用方手动填入所有字段；它应结合 Req 2 自动填充 `level`, `stage`, `doc_link`。

## Req 2: 引入静态错误码元数据映射
- **规范**: 必须建立一个静态映射（如字典或 Registry 类），将 `11-error-code-spec.md` 中的所有细粒度错误码与它们的 `level`, `stage`, `doc_link` 绑定。
- **行为**: 当业务代码通过 `ErrorPayload(code="[F-v3-graph-phase-cycle]", message="...")` 实例化时，模型须拦截并根据 `code` 自动查表补全剩余的必填字段。

## Req 3: 异常层重构 (`GraphAgentError` 基类改造)
- **规范**: 将 `GraphAgentError` 的签名改造为 `__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict | None = None)`。
- **规范**: 迁移 `SkillCompilationError` 中特有的定位信息字段（如 `skill_path`, `field_path`）至统一的 `ErrorPayload` 模型内，使得系统异常信息对外边界的 JSON 形态完全统一。
- **规范**: 消除代码库中散落的通过 kwargs (`error_code="..."`) 传递错误码的写法（例如 `ValidationError`, `cognitive_flow.py` 等处）。

## Req 4: 消除 Coarse Codes (粗粒度码漂移)
- **规范**: 彻底清除在 `loader.py` 等文件中硬拼接的 `[F-v3-route]`, `[F-v3-io]`, `[F-v3-graph]`, `[F-v3-actions]`, `[F-v3-purity]` 前缀。
- **行为**: 必须将其准确替换为 `11-error-code-spec.md` 速查表中对应的语义细码（例如用 `[F-v3-logic-actions-empty]` 代替原来的 `[F-v3-actions]`）。

## Req 5: 测试断言升级 (Breaking)
- **规范**: 必须将测试库中的正则断言范式从字符串模式升级为结构化字段模式。
- **旧模式**: `with pytest.raises(SkillLoadError, match=r"\[F-v3-graph-schema-unknown-field\]"):`
- **新模式**: 
  ```python
  with pytest.raises(SkillLoadError) as exc_info:
      # ...
  assert exc_info.value.payload.code == "[F-v3-graph-schema-unknown-field]"
  ```
- **验收**: 测试套件 `pytest tests/` 须全量通过。