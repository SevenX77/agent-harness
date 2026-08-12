# 掩码点数 = 真实 key 长度,不是占位符长度(2026-08-12 决议)

> 状态:已批准(PM,2026-08-12),本决议随实施 PR 同批落地。
> 范围:`apps/studio/backend`(registry DTO + 落盘排除)、`apps/studio/frontend`
> (registry 类型 + API Keys 卡掩码渲染)。gateway SDK 不动。
> 设计源同步:`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §③a 握手契约
> (`GET /api/llm/registry` DTO)在同一 PR 更新。

## 0. 一句话

设置页 API key 掩码态显示的点数,今天恒等于 10——那是 Pydantic `SecretStr`
脱敏占位符的长度,不是用户 key 的长度;用户会误以为 key 存错/被截断。
修复:redacted registry 快照携带一个新的非敏感元数据字段 `api_key_length`
(真实字符数),前端掩码按它画点;明文仍然只在 Eye/Copy 的 scoped reveal 时出后端。

## 1. 证据(为什么恒为 10 个点)

- gateway 模型里 `api_key: SecretStr | None`
  (`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:183`);
  Pydantic `SecretStr` 做 JSON 序列化时固定输出 `"**********"`(10 个星号)。
- Studio 后端把这 10 个星号定成契约常量 `SECRET_REDACTION_PLACEHOLDER`
  (`apps/studio/backend/app/services/llm_credentials.py:29`),前端有对应常量
  `REDACTED_ENDPOINT_SECRET`(`apps/studio/frontend/src/api/llm.ts:621`)。
- 前端掩码渲染是「值有几个字符就画几个 •」:`apiKeyDisplayValue` 返回
  `apiKeyMaskChar.repeat(value.length)`
  (`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:119-122`);
  掩码态下 `value` 是占位符,所以永远 10 个点。
- 设计源规定进 tab 只投影 redacted registry、明文只走 scoped reveal
  (`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:463` §③a、`:479` A10),
  本决议不改这两条。

## 2. 决策

1. **redacted 快照携带长度元数据**:`GET /api/llm/registry` 的 endpoint DTO 新增
   `api_key_length: int | null` —— 有 key 时为真实字符数,无 key(None 或空串)时为
   null。`api_key` 字段本身继续返回 `"**********"`,读写契约(含「回传占位符 =
   保留原 key」的 upsert 语义)不动。
2. **前端掩码按它画点**:API Keys 卡掩码态,当输入值是占位符时按
   `api_key_length` 画点;值已是明文(reveal 后/用户新输入)时按明文长度画点。
3. **安全取舍**:key 长度基本是公开格式信息(各家 key 格式公开),泄露风险可忽略;
   代价是设置页截图能看出 key 位数,判定为可接受。

## 3. 关键设计决定

- **computed field,不是手工 stamping**:`api_key_length` 做成 Studio endpoint DTO
  (`apps/studio/backend/app/models/llm_config.py` `ProviderEndpoint`)上的 Pydantic
  computed field,从 `api_key.get_secret_value()` 现场推导——长度永远不可能与
  真实 secret 不一致(让非法状态不可表示);仿照 gateway `ProviderRoute.canonical_id`
  的既有先例(`schema.py:249`)。
- **两处派生字段排除**(computed field 会进所有 `model_dump`,而输入侧
  `extra="forbid"`):
  1. 落盘 payload 排除——`_credentials_payload_for_storage`
     (`llm_credentials.py:450`)已有 `canonical_id` 排除先例,同法加
     `provider_endpoints.__all__.api_key_length`,credentials 文件不落这个派生值;
  2. gateway 投影排除——`_gateway_endpoint`(`llm_config.py:118`)的 exclude 集合
     加 `api_key_length`,Studio 展示字段不进 SDK(与 `display_name` /
     `last_error_code` / `registrable_provider_name` 同列)。
- **前端不进可编辑 draft**:长度是展示元数据不是编辑状态,挂在
  `CredentialProviderState`(registry 投影,`llm.ts` `endpointToCredential`)上,
  ProviderCard 从 `persisted` prop 读;`ProviderDraft` 及保存链路零改动。
- **放弃的替代项**:①占位符改成「真实长度个星号」——前端识别脱敏态靠精确匹配
  10 星号,变长后只能靠「全是星号」模糊判断,带内魔法值更糟,弃;②显示尾四位
  hint——泄露真实内容片段、要多存字段,Eye 已可看全文,弃;③顺手重构掉整个
  占位符带内契约(显式 `secret_present` + 省略字段=保留)——正交的大改,不夹带。

## 4. 验收判据

1. 后端:`GET /api/llm/registry` 的每个 endpoint 带 `api_key_length`,等于真实
   key 字符数;无 key 时为 null;`api_key` 仍为 `"**********"`(测试断言)。
2. 后端:落盘的 `llm_credentials.json` 不含 `api_key_length` 键,重新 load 不报
   `extra_forbidden`(测试断言 round-trip)。
3. 前端:掩码态、值为占位符且 `api_key_length` 可用时,输入框显示
   `api_key_length` 个 •(单测);reveal 后显示明文。
4. 真机:设置页 API Keys 卡,已存一把非 10 位的 key,掩码点数 = 该 key 位数
   (逐项点验报告附截图)。
5. CI Gates 全绿(ruff / mypy / pytest 后端全套 / 前端 lint+typecheck+test+build)。
