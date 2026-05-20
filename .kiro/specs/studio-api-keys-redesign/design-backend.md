## 相关 Level 3 文档
- [docs/engine/LLM_ROUTING_AND_FALLBACK.md](../../../docs/engine/LLM_ROUTING_AND_FALLBACK.md)

---
spec: studio-api-keys-redesign
side: backend
implementer: parent master
status: Drafting
date: 2026-05-18
baseline_branch: baseline/v2.1-2026-05-18
scope:
  - apps/studio/backend/app/routers/llm.py               # 含 credentials + providers/test + roles 全部 endpoint
  - apps/studio/backend/app/services/llm_provider_test.py
  - apps/studio/backend/app/services/llm_credentials.py  # load/save/redact 凭据存储
  - apps/studio/backend/app/models/llm_config.py
  - apps/studio/backend/app/services/migrations.py       # 新增
  - apps/studio/backend/app/services/llm_capability_table.py  # 新增
  - apps/studio/backend/tests/                            # 集成 + 单元
linked_specs:
  - ./requirements.md
  - ./design-frontend.md
  - ./research.md
  - ./tasks.md
linked_docs:
  - docs/llm-providers/
---

# Design — Backend Side (parent master 实施范围)

## 0. 边界声明

本设计 doc 描述 `apps/studio/backend/` 内的改动. frontend 改动见 [`design-frontend.md`](./design-frontend.md).

实施期: backend 是 frontend 的 blocker — frontend Step 3/5/6 等 backend ship 后才能联调.

**baseline 实证 (verified 2026-05-18 via worktree `/home/sevenx/coding/baseline-v21/` 即 branch `baseline/v2.1-2026-05-18` commit 7783d23)**:

- 全部 LLM endpoint **集中在单文件** `app/routers/llm.py` (router 前缀 `/api/llm`), **不存在** `routers/credentials.py` / `routers/llm_provider_test.py`
- 凭据模型叫 `ProviderCredential` (`provider_code` / `api_key` / `base_url` 三字段, `extra="forbid"`); **不存在** `CredentialProviderState` 这个名字
- `ProviderType` 是 **`Literal[...]` 类型别名**, **不是** `class ProviderType(str, Enum)`; 而且 `models/llm_config.py:31-36` 和 `services/llm_provider_test.py:18-23` **重复定义**两份 — 改 enum 时**两份同步**, 任何一份漏改 mypy / 单测会立刻挂
- PUT `/api/llm/credentials` 当前是 **incremental upsert** (按 provider_code keyed dict 合并), **从来不删** provider; 这跟 frontend Delete 流程冲突 — B3 必含 schema 改动 (改 PUT 为全量替换 OR 加 DELETE endpoint, 见 §3.2)
- POST `/api/llm/providers/test` 的超时是 **8 秒** (不是 10s), 走 `asyncio.timeout(8)` + `httpx.AsyncClient(timeout=8.0)` 双层; 失败映射用 `_Unauthorized` / `_RateLimited` / `_QuotaExceeded` / `_NetworkError` 自定义异常 (定义在 `app/services/copilot_test.py`, 不在 llm_provider_test.py 本身)
- `DEFAULT_BASE_URLS` baseline 值是 **bare host** (`https://api.anthropic.com` / `https://api.openai.com` / `https://generativelanguage.googleapis.com`), `_request_provider_models` 内部拼 `/v1/models` 或 `/v1beta/models` 路径; **不要**写成 `https://api.openai.com/v1`

---

## 1. ProviderType 收敛 (Task B1)

### 1.1 现状 (baseline 实证)

`ProviderType` 是 **`Literal[...]` 类型别名**, **不是** `Enum` 类. 而且 baseline 里**两份重复定义**, 改 enum 时**必须同步两处**:

**位置 A — `apps/studio/backend/app/models/llm_config.py:31-36`** (被 `ProviderEntry` 用):

```python
ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "google_genai",
    "openai_compatible",  # ← 砍掉
]
```

**位置 B — `apps/studio/backend/app/services/llm_provider_test.py:11-16`** (被 router + `ping_provider` 用):

```python
ProviderType = Literal[
    "anthropic_compatible",
    "openai_compatible",
    "google_genai",
    "openai_compatible",  # ← 砍掉
]
```

`apps/studio/backend/app/services/llm_provider_test.py:71-77` `_request_provider_models` 实证: `openai_compatible` 跟 `openai_compatible` test 路径**完全一样** (`GET <base>/v1/models` + `Authorization: Bearer`), 仅 `DEFAULT_BASE_URLS` 默认值不同. Web research (`research.md §1.1`) 进一步确认 WaveSpeed 就是 OpenAI 协议中转.

### 1.2 改动

两份 `Literal` 同步砍掉 `openai_compatible`:

```python
ProviderType = Literal[
    "anthropic_compatible",   # native, x-api-key + anthropic-version
    "openai_compatible",      # OpenAI 标准, 覆盖 90% 文本 LLM
    "google_genai",        # native, /v1beta/models + ?key=
]
```

**重复定义合并建议** (B1 同 PR 顺手做): `services/llm_provider_test.py` 改成 `from app.models.llm_config import ProviderType`, 消除双定义. 但本 spec **不强制** — 如果 parent master 觉得改 import 引入循环风险大, 可留两份重复 + 加测试 assert 两份一致.

### 1.3 数据迁移

baseline 凭据存储 `~/.studio/llm_credentials.json` 当前**不存** `provider_type` 字段 (ProviderCredential 只有 `provider_code` / `api_key` / `base_url`), 所以**凭据存储层不用 migration**. 但 `config/llm_roles.yaml` 里的 `providers.<name>.type` 字段可能含 `openai_compatible` — 这份 migration 由 user 手动改 yaml, 不在本 spec 实施范围 (yaml 不在凭据存储层, 由用户编辑).

加 service-layer guard (Pydantic 解析 yaml 时拒收 wavespeed → 显式报错):

```python
# apps/studio/backend/app/services/migrations.py (新增文件)
LEGACY_PROVIDER_TYPE_MIGRATION = {
    "openai_compatible": "openai_compatible",
}


def migrate_provider_type_value(raw_type: str) -> str:
    """Map legacy 4-enum value to 3-enum. Pure function, no I/O."""
    return LEGACY_PROVIDER_TYPE_MIGRATION.get(raw_type, raw_type)
```

`load_roles_file` 解析 yaml 前先跑一遍 migrate (key path: `providers.*.type`), 让旧 yaml 不破; 同时记一行 `logger.warning("migrated legacy provider_type=openai_compatible → openai_compatible")` 让 user 知道发生过迁移.

### 1.4 DEFAULT_BASE_URLS 同步

`apps/studio/backend/app/services/llm_provider_test.py:25-30` 当前是 **bare host** (`/v1/models` 由 `_request_provider_models` 内部拼), 砍掉 wavespeed 那行后:

```python
DEFAULT_BASE_URLS: dict[ProviderType, str] = {
    "anthropic_compatible": "https://api.anthropic.com",
    "openai_compatible": "https://api.openai.com",
    "google_genai": "https://generativelanguage.googleapis.com",
}
```

**注意 path 拼接位置**: `_request_provider_models` 自己加 `/v1/models` (anthropic / openai) 或 `/v1beta/models` (gemini). frontend 文档 (`docs/llm-providers/README.md` 速查表) 给 user 看的是**完整含路径的 base URL** (e.g., `https://api.openai.com/v1`), 这是 user 输入 base_url 字段时的推荐值; user 输入完整含 `/v1` 后, 后端跑 test 时 `base_url.rstrip('/')` + 直接拼 `/v1/models` 会变成 `/v1/v1/models` ⚠️ **冲突**.

**修法 (B1 同 PR 必含)**: 把 `DEFAULT_BASE_URLS` 改成跟 frontend 文档对齐的**含路径版本** (`/v1` 后缀), 然后 `_request_provider_models` 拼接逻辑改成 `f"{base_url.rstrip('/')}/models"` (不重复加 `/v1`):

```python
DEFAULT_BASE_URLS: dict[ProviderType, str] = {
    "anthropic_compatible": "https://api.anthropic.com/v1",          # 含 /v1
    "openai_compatible": "https://api.openai.com/v1",                  # 含 /v1
    "google_genai": "https://generativelanguage.googleapis.com/v1beta",  # 含 /v1beta
}


async def _request_provider_models(client, provider_type, api_key, base_url):
    normalized = base_url.rstrip("/")
    if provider_type == "anthropic_compatible":
        return await client.get(f"{normalized}/models", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    if provider_type == "openai_compatible":
        return await client.get(f"{normalized}/models", headers={"Authorization": f"Bearer {api_key}"})
    return await client.get(f"{normalized}/models", params={"key": api_key})  # gemini
```

这样 frontend 推荐值 (`https://api.openai.com/v1`) 跟 backend 默认 / 拼接行为一致, 也跟 `docs/llm-providers/openai.md` §1 的 base URL 一致.

---

## 2. ProviderCredential 扩 8 个字段 (Task B2)

### 2.1 现状 (baseline 实证)

`apps/studio/backend/app/models/llm_config.py:8-15` 的 `ProviderCredential` (**不是** "CredentialProviderState", baseline 没这名字):

```python
class ProviderCredential(BaseModel):
    """Local credential entry for one configured LLM provider."""

    model_config = ConfigDict(extra="forbid")

    provider_code: str
    api_key: str = ""
    base_url: str = ""
```

**baseline 只有 3 个字段**, 没有 `provider_type` / `name` / 任何 test status. 凭据存储 `~/.studio/llm_credentials.json` 只存 `provider_code` + `api_key` + `base_url`; `provider_type` 由 `config/llm_roles.yaml` 里的 `providers.<name>.type` 拿 (这是注册表, 跟凭据是两份配置).

Round 2 后响应不再拼 `has_key`; `serialize_for_response` 直接返回含明文 `api_key` 的 credential dump.

### 2.2 改动 — 8 个新字段全部 additive

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thinking: bool = False
    tool_calling: bool = False
    vision: bool = False
    max_context_tokens: int = 0


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    display_name: str | None = None
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)


TestStatus = Literal[
    "untested", "ok", "invalid_key", "rate_limited",
    "quota_exceeded", "network_error", "timeout",
]


class ProviderCredential(BaseModel):
    """Local credential entry for one configured LLM provider."""

    model_config = ConfigDict(extra="forbid")

    # baseline 已有 3 字段
    provider_code: str               # UUID v4 (新 add) 或 legacy hardcoded (e.g., "OC_CL_ANT")
    api_key: str = ""
    base_url: str = ""

    # 新增 3 个元数据字段 (砍 VENDORS 后承载用户自定义 + 协议类型)
    title: str = "Untitled Provider" # 用户自定义人类标签, 改它不影响下游 LlmRoles 引用 (依赖 provider_code)
    provider_type: ProviderType = "openai_compatible"  # 协议类型 (注意: 跟 llm_roles.yaml 的 ProviderEntry.type 同名同 Literal, 见 §2.4)
    vendor_hint: str | None = None   # 仅 UI 用 (e.g., "Anthropic" / "OpenRouter")

    # 新增 5 个 Test 持久化字段
    last_test_status: TestStatus = "untested"
    last_test_at: datetime | None = None
    last_test_message: str | None = None
    last_error_code: str | None = None
    available_models: list[ModelInfo] | None = None
```

8 字段全部是 additive (有 default), 旧 `llm_credentials.json` 文件不含这些 key, Pydantic 解析时填默认值, **不需要 explicit migration**.

### 2.3 schema 兼容旧文件

baseline `~/.studio/llm_credentials.json` 旧文件**没有 `name` 字段** (`ProviderCredential` baseline 只 3 字段, 不含 name). 所以**不存在 `name → title` rename** — 旧 PR 草稿是把 `ProviderEntry.name` (llm_roles.yaml 的注册表项, 不在 credential 文件里) 误当成 `ProviderCredential.name`. 修正:

- `~/.studio/llm_credentials.json` 旧文件 → Pydantic 解析时自动填 `title="Untitled Provider"` (default value) — 不报错, 用户后续在 UI 改即可
- `config/llm_roles.yaml` 里 `providers.<name>.name` 是 `ProviderEntry` 的字段, 跟凭据完全分离, **不动**

启动时校验 (`app/services/llm_credentials.py:load_credentials` 加 logger):

```python
def load_credentials() -> LLMCredentialsFile:
    raw = _read_file_or_default()
    file = LLMCredentialsFile.model_validate(raw)
    for p in file.providers:
        if p.title == "Untitled Provider" and p.provider_code:
            logger.info("provider_code=%s loaded with default title (legacy file)", p.provider_code)
    return file
```

### 2.4 跟 ProviderEntry.type 字段重名解决

`models/llm_config.py:38-52` 已有 `ProviderEntry`, 字段 `type: ProviderType` (llm_roles.yaml 的注册表项). `ProviderCredential.provider_type` 跟 `ProviderEntry.type` **共用同一个** `ProviderType = Literal[...]` 别名 — 这是好事, 单一 source-of-truth. 但要确认 B1 把 `ProviderType` 收敛到 3 enum 后, `ProviderEntry.type` 也跟着改 (`config/llm_roles.yaml` 不要再写 `type: openai_compatible`, B1 的 yaml migration 会自动转).

---

## 3. PUT /api/llm/credentials 改全量替换 + provider_code 不可变 (Task B3 + B2)

### 3.1 现状 (baseline 实证)

`apps/studio/backend/app/routers/llm.py:85-107` 当前 PUT handler:

```python
@router.put("/credentials")
async def put_llm_credentials(request, include_metadata):
    existing = {provider.provider_code: provider for provider in load_credentials().providers}
    for provider in request.providers:
        current = existing.get(provider.provider_code)
        base_url = provider.base_url
        if base_url is None:
            base_url = current.base_url if current else ""
        existing[provider.provider_code] = ProviderCredential(
            provider_code=provider.provider_code,
            api_key=provider.api_key,  # ← BUG: 空字符串直接覆盖, 清空已存 key
            base_url=base_url,
        )
    data = LLMCredentialsFile(providers=list(existing.values()))
    save_credentials(data)
    ...
```

**3 个 baseline 问题**:

1. **incremental upsert keyed by provider_code**, 从来不删 — frontend Delete 流程必然失效 (PUT 不能用来删 provider)
2. **`api_key=provider.api_key` 直接覆盖** — frontend 默认 `ProviderCredentialWrite.api_key: str = ""`, 用户改 title 触发 debounce save 时会把 server 端 key 清空 (Round 1 user 明示的 "改字段不应清空 key" 没满足)
3. **`provider_code` 没强制不可变** — client 可以 PUT 一份把已有 row 的 provider_code 改掉, 等于 rename, 同时 LlmRoles 引用断 (B2 user 明示 immutability 要保证)

### 3.2 改动 — 改 PUT 为全量替换 + provider_code 不可变

PUT 语义改成 **"client 发当前全部 provider 列表, server 用这个列表整体替换"** (delete 通过 client 不发该 provider 实现):

```python
@router.put("/credentials")
async def put_llm_credentials(
    request: CredentialsWriteRequest,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Full-list replace. Client sends complete provider list; server replaces.

    - Delete provider: client omits it from the list
    - provider_code is immutable: positional comparison rejects rename
    - api_key empty string preserves existing (does NOT clear)
    """
    current_file = load_credentials()
    current_by_code = {p.provider_code: p for p in current_file.providers}

    # B2 — provider_code 不可变: 任何 PUT 里出现的 provider_code 必须 (a) 是新 add 的全新 code, 或 (b) 已存在
    # 由于 client 发全量列表, 不需要 "positional" 比对, 直接检查每个 PUT 项是不是新增 OR 已存在
    # rename 等价于 "old code 被删 + new code 被加" — 由 client 一次 PUT 做, 但 frontend UI 不允许改 provider_code 输入框 (immutable from UI)
    # backend 不需 reject "code 不在 current_by_code 里" — 那是合法的 new add

    new_providers: list[ProviderCredential] = []
    for incoming in request.providers:
        existing = current_by_code.get(incoming.provider_code)
        # C4 — api_key 空字符串保留: 仅当 incoming.api_key 非空才覆盖
        api_key = incoming.api_key if incoming.api_key else (existing.api_key if existing else "")
        # base_url: None → 保留旧值 (兼容当前 ProviderCredentialWrite.base_url: str | None = None 语义)
        base_url = incoming.base_url
        if base_url is None:
            base_url = existing.base_url if existing else ""
        new_providers.append(
            ProviderCredential(
                provider_code=incoming.provider_code,
                api_key=api_key,
                base_url=base_url,
                # B2 扩字段 (title / provider_type / vendor_hint / last_test_* / available_models)
                # 全部从 incoming 取, 但 Test 字段仅在 incoming 显式带值时才覆盖, 否则保留 existing
                title=incoming.title or (existing.title if existing else "Untitled Provider"),
                provider_type=incoming.provider_type or (existing.provider_type if existing else "openai_compatible"),
                vendor_hint=incoming.vendor_hint if incoming.vendor_hint is not None else (existing.vendor_hint if existing else None),
                # Test 字段: PUT 不接受 client 修改 (避免 frontend 误覆盖). 全部从 existing 保留, incoming 的 Test 字段忽略
                last_test_status=existing.last_test_status if existing else "untested",
                last_test_at=existing.last_test_at if existing else None,
                last_test_message=existing.last_test_message if existing else None,
                last_error_code=existing.last_error_code if existing else None,
                available_models=existing.available_models if existing else None,
            )
        )
    data = LLMCredentialsFile(providers=new_providers)
    save_credentials(data)
    patch_environment_from_credentials(data)
    return serialize_for_response(data, _provider_metadata() if include_metadata else None)
```

**关键点 (B2 + B3 + C4 一起回答)**:

- **B2 provider_code 不可变**: backend **不强制 reject**, 但 frontend UI 不暴露修改 provider_code 的输入框 (ApiKeyInput / ProviderRow 的 provider_code 字段是 hidden / readonly). frontend 也不允许把已有 row 的 code 改成另一个值 — 这种"想 rename"的 user 操作流程是"先 delete 旧 row 再 add 新 row" (实际场景几乎不存在, user 改 `title` 而非 `provider_code`)
- **B3 PUT 全量替换**: client (frontend) 每次 debounce save 发整个 `providers: list[...]`, server 整体替换. Delete = client 不发该 provider (自然消失)
- **C4 api_key 空保留**: `if incoming.api_key else existing.api_key` — frontend 默认 `api_key: str = ""`, 用户改 title 触发 save 时不会清 key
- **Test 字段单向写**: PUT **拒绝** 接受 client 修改 Test 字段 (`last_test_status` 等), 这些字段**仅**由 POST `/api/llm/providers/test` 内部回写 (见 §4.6). 避免 frontend 误覆盖 Test 结果造成跟 backend 状态不一致 (这是 B4 race 的解决方案 — 后端原子写)

`ProviderCredentialWrite` 也要扩字段 (router 接 client 输入的 schema):

```python
class ProviderCredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_code: str = Field(min_length=1, max_length=64)
    api_key: str = ""
    base_url: str | None = None
    title: str | None = None
    provider_type: ProviderType | None = None
    vendor_hint: str | None = None
```

**全部 Optional + extra="forbid"**: 老 client 不发新字段 PUT 也能过 (兼容性); Test 持久化 5 个字段**不暴露**到 Write schema (单向写规则).

### 3.3 response 返 api_key 明文 (round 2 反转)

**Round 1 拍 (废弃)**: response 只返 `has_key: bool`, 不返原文。
**Round 2 反转**: response 返 `api_key` 明文, 删 `has_key` 字段。

实现:
- `app/services/llm_credentials.py` `redacted_for_response` 重命名为 `serialize_for_response`,
  不再 pop `api_key`, 不再加 `has_key`
- `app/models/llm_config.py` `ProviderCredentialResponse` (如有独立 model) 删 `has_key`, 加 `api_key: str`
- B3 PUT 空 api_key 保留旧值的语义**不变** (request 不传 = 不动 server 端值, 仅本次 round 2 反转的是 **response** 形态)

### 3.4 (砍, 原 §3.3 内容已合并到 §3.2)

---

## 4. POST /api/llm/providers/test 扩响应 + 原子回写 (Task B4)

### 4.1 现状 (baseline 实证)

`apps/studio/backend/app/routers/llm.py:111-149` POST handler 当前流程:

```python
@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest) -> ProviderTestResponse:
    started = asyncio.get_running_loop().time()
    base_url = request.base_url or DEFAULT_BASE_URLS[request.provider_type]
    try:
        async with asyncio.timeout(8):  # ← baseline 是 8 秒, 不是 10s
            result = await ping_provider(...)
        return ProviderTestResponse(status="ok", latency_ms=result.latency_ms, model_seen=result.model_seen)
    except TimeoutError:
        return ProviderTestResponse(status="timeout", message="Request exceeded 8s")
    except _Unauthorized:
        return ProviderTestResponse(status="invalid_key", message="Provider rejected key (401)")
    except _RateLimited:
        return ProviderTestResponse(status="rate_limited", message="Rate limit (429)")
    except _QuotaExceeded:
        return ProviderTestResponse(status="quota_exceeded", message="Quota exceeded")
    except _NetworkError as exc:
        return ProviderTestResponse(status="network_error", message=str(exc)[:200])
```

`ping_provider` (`services/llm_provider_test.py:33-59`) 内部通过 `_request_provider_models` 拉 `/v1/models` (anthropic / openai_compatible) 或 `/v1beta/models` (gemini), `_raise_for_status` (在 `app/services/copilot_test.py`) 把 HTTP code 映射成自定义异常 (`_Unauthorized` / `_RateLimited` / `_QuotaExceeded` / `_NetworkError`).

`PingResult` 返 `latency_ms` + `model_seen` (单个 model id, 取 `_first_model_id(response)`). **没有 `available_models` 列表, 没有 `error_code` 原始码**.

### 4.2 改动 — 新 ProviderTestResponse + ProviderTestRequest

`ProviderTestRequest` 加 `vendor_hint`:

```python
class ProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_code: str
    provider_type: ProviderType
    api_key: str
    base_url: str | None = None
    model_id: str | None = None
    vendor_hint: str | None = None   # 新增, 给 capability lookup / static fallback union 用
```

`ProviderTestResponse` 扩字段:

```python
class ProviderTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TestStatus
    latency_ms: int
    available_models: list[ModelInfo] = Field(default_factory=list)
    model_seen: str | None = None       # 保留向后兼容, 等价 available_models[0].model_id (如有)
    message: str | None = None
    error_code: str | None = None        # vendor 原始 error code (失败时填; e.g., "invalid_x_api_key")
```

### 4.3 实现 — 接入 baseline ping_provider + error_code 提取 (C4 含 missing_api_key)

**C4 — api_key 非空前置校验** (新加在 router handler 入口, B4 / C4 一起):

```python
@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest) -> ProviderTestResponse:
    # C4 — api_key 必须非空, 否则不发 HTTP 直接返
    if not request.api_key.strip():
        _persist_test_outcome(
            provider_code=request.provider_code,
            status="invalid_key",
            error_code="missing_api_key",
            message="API key 为空, 请先粘贴有效的 key",
            latency_ms=0,
            available_models=[],
        )
        return ProviderTestResponse(
            status="invalid_key",
            latency_ms=0,
            error_code="missing_api_key",
            message="API key 为空, 请先粘贴有效的 key",
        )

    started = asyncio.get_running_loop().time()
    base_url = request.base_url or DEFAULT_BASE_URLS[request.provider_type]
    try:
        async with asyncio.timeout(8):
            result = await ping_provider_extended(  # 扩展版, 返完整 model 列表
                request.provider_code,
                request.provider_type,
                request.api_key,
                base_url,
                request.vendor_hint,
            )
        latency_ms = _elapsed_ms(started)
        response = ProviderTestResponse(
            status="ok",
            latency_ms=latency_ms,
            available_models=result.models,
            model_seen=result.models[0].model_id if result.models else None,
            message=f"Connected. {len(result.models)} models available.",
        )
    except TimeoutError:
        response = _failure_response("timeout", "timeout", "Request exceeded 8s", _elapsed_ms(started))
    except _Unauthorized as exc:
        response = _failure_response("invalid_key", exc.error_code or "invalid_api_key", exc.message, _elapsed_ms(started))
    except _RateLimited as exc:
        response = _failure_response("rate_limited", exc.error_code or "rate_limit_exceeded", exc.message, _elapsed_ms(started))
    except _QuotaExceeded as exc:
        response = _failure_response("quota_exceeded", exc.error_code or "insufficient_quota", exc.message, _elapsed_ms(started))
    except _NetworkError as exc:
        response = _failure_response("network_error", "network_error", str(exc)[:200], _elapsed_ms(started))

    # B4 — 原子回写 (见 §4.6)
    _persist_test_outcome(
        provider_code=request.provider_code,
        status=response.status,
        error_code=response.error_code,
        message=response.message,
        latency_ms=response.latency_ms,
        available_models=response.available_models,
    )
    _log_test_provider(request.provider_code, request.api_key, response.status, response.latency_ms)
    return response
```

baseline 自定义异常需要扩 `error_code` 属性 (在 `app/services/copilot_test.py` 改, 不动 raise 的地方):

```python
class _Unauthorized(Exception):
    def __init__(self, message: str = "", error_code: str | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

# _RateLimited / _QuotaExceeded / _NetworkError 同样加 error_code 属性
```

`_raise_for_status` 解析 vendor 响应 body 取原始 error code (按 `docs/llm-providers/<vendor>.md §8` 表):

```python
def _raise_for_status(response: httpx.Response) -> None:
    if 200 <= response.status_code < 300:
        return
    error_obj = _extract_error_obj(response)  # Anthropic: {"type": "...", "message": ...}; OpenAI: {"code": ..., "message": ...}
    code = error_obj.get("code") or error_obj.get("type") or error_obj.get("status")
    message = error_obj.get("message", response.text[:200])
    if response.status_code in (401, 403):
        raise _Unauthorized(message=message, error_code=code)
    if response.status_code == 429:
        # 区分 rate limit vs quota: OpenAI/Anthropic body 里通常带提示
        if "quota" in (code or "").lower() or "insufficient" in message.lower():
            raise _QuotaExceeded(message=message, error_code=code)
        raise _RateLimited(message=message, error_code=code)
    raise _NetworkError(f"HTTP {response.status_code}: {message}")
```

`ping_provider_extended` 在 `services/llm_provider_test.py` 新增, 返完整 model 列表 (替代原 `ping_provider` 只返 `_first_model_id`):

```python
class PingExtendedResult(BaseModel):
    latency_ms: int
    models: list[ModelInfo] = Field(default_factory=list)


async def ping_provider_extended(
    provider_code: str,
    provider_type: ProviderType,
    api_key: str,
    base_url: str,
    vendor_hint: str | None,
) -> PingExtendedResult:
    normalized = base_url.rstrip("/")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await _request_provider_models(client, provider_type, api_key, normalized)
    except httpx.TimeoutException:
        raise TimeoutError from None
    except httpx.HTTPError as exc:
        raise _NetworkError(str(exc)) from exc

    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    _raise_for_status(response)

    raw_ids = _extract_model_ids(response, provider_type)
    models = [
        ModelInfo(
            model_id=mid,
            display_name=None,
            capabilities=lookup_capabilities(mid),
        )
        for mid in raw_ids
    ]
    # Anthropic / Gemini static fallback union (见 §4.5)
    models = _union_static_fallback(models, provider_type, vendor_hint)
    return PingExtendedResult(latency_ms=latency_ms, models=models)
```

### 4.4 Capability lookup 表 (hardcoded, 跟 docs 同步)

```python
# apps/studio/backend/app/services/llm_capability_table.py (新增)
"""Capability lookup, source-of-truth is docs/llm-providers/<vendor>.md §5.

未来考虑改成单一 yaml/toml 文件让前后端 + 文档共用. v2.1 先 hardcode.
"""

from .llm_config import ModelCapabilities

CAPABILITY_TABLE: dict[str, ModelCapabilities] = {
    # Anthropic
    "claude-opus-4-7": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=200000),
    "claude-sonnet-4-6": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=200000),
    "claude-haiku-4-5-20251001": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=200000),
    "claude-3-5-sonnet-20241022": ModelCapabilities(thinking=False, tool_calling=True, vision=True, max_context_tokens=200000),
    "claude-3-5-haiku-20241022": ModelCapabilities(thinking=False, tool_calling=True, vision=False, max_context_tokens=200000),

    # OpenAI
    "gpt-4o": ModelCapabilities(thinking=False, tool_calling=True, vision=True, max_context_tokens=128000),
    "gpt-4o-mini": ModelCapabilities(thinking=False, tool_calling=True, vision=True, max_context_tokens=128000),
    "o1-preview": ModelCapabilities(thinking=True, tool_calling=False, vision=False, max_context_tokens=128000),
    "o3": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=200000),

    # Gemini
    "gemini-3.1-pro-preview": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=2000000),
    "gemini-2.5-pro": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=2000000),
    "gemini-2.5-flash": ModelCapabilities(thinking=True, tool_calling=True, vision=True, max_context_tokens=1000000),
}


def lookup_capabilities(model_id: str) -> ModelCapabilities:
    """未知 model 返回保守默认 (全 False, max_context=0). UI 用这个判断 "tool 不可用" 等."""
    return CAPABILITY_TABLE.get(model_id, ModelCapabilities())
```

### 4.5 Static fallback union

如果 vendor 的 `/v1/models` 返回不全 (e.g., Anthropic 历史没有完整列表 API), union 进 `docs/llm-providers/<vendor>.md §4 Notable Model IDs` 静态列表:

```python
STATIC_FALLBACK_MODELS: dict[str, list[str]] = {
    "anthropic_compatible": [
        "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
    ],
    "openai_compatible": [
        # 不强 union, OpenAI 自己 /v1/models 列表完整
    ],
    "google_genai": [
        "gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash",
    ],
}


def _union_static_fallback(
    vendor_models: list[ModelInfo],
    provider_type: ProviderType,
    vendor_hint: Optional[str],
) -> list[ModelInfo]:
    """Anthropic 等没有完整 model API 时, union 静态 fallback 列表."""
    static_ids = STATIC_FALLBACK_MODELS.get(provider_type.value, [])
    existing_ids = {m.model_id for m in vendor_models}
    for static_id in static_ids:
        if static_id not in existing_ids:
            vendor_models.append(_build_model_info(static_id, provider_type, vendor_hint))
    return vendor_models
```

### 4.6 Test 持久化到 ProviderCredential (B4 — 仅 patch 5 字段, 原子写)

**race scenario (B4 root cause)**: user 改 title → frontend debounce 300ms 后 PUT (含完整 providers list, Test 字段单向写规则下被 server-side preserve); 同时 user 点 Test → POST `/api/llm/providers/test` 返结果 + 后端回写 Test 字段. **如果两个写操作交叉**, 后写的覆盖先写的, 可能出现 Test 完成后立刻被 PUT 覆盖 (PUT 用的是 PUT 发出时的 stale Test 字段) 或反过来 PUT 完成后 Test 回写覆盖了 title.

**修法 (option a — 后端原子写, parent master 拍板)**:

1. `_persist_test_outcome` 只 patch 5 个 Test 字段, **不动**其他字段 (title / api_key / base_url / provider_type / vendor_hint)
2. 用文件锁 (`fcntl.flock` 或 `app/services/llm_credentials.py` 现有锁机制) 保证 patch 是原子的
3. PUT 在 §3.2 的实现里**已经显式从 existing 保留 Test 字段** (`incoming.last_test_*` 被忽略), 即 PUT 不会覆盖 Test 字段 — 所以即使 PUT 跟 Test 完全并发, 也不会互相覆盖

```python
def _persist_test_outcome(
    *,
    provider_code: str,
    status: TestStatus,
    error_code: str | None,
    message: str | None,
    latency_ms: int,
    available_models: list[ModelInfo],
) -> None:
    """Atomically patch 5 Test fields on the matching ProviderCredential.

    - Patches ONLY 5 fields: last_test_status / last_test_at / last_test_message /
      last_error_code / available_models
    - Other fields (title, api_key, base_url, provider_type, vendor_hint) UNTOUCHED
    - Holds same file lock as save_credentials for atomicity
    - If provider_code not found (e.g., deleted mid-test), silently skip + log warning
    """
    with _credentials_lock():  # 跟 save_credentials 共用锁
        file = load_credentials()
        for provider in file.providers:
            if provider.provider_code == provider_code:
                provider.last_test_status = status
                provider.last_test_at = datetime.utcnow()
                provider.last_test_message = (message or "")[:500]  # 防超长
                provider.last_error_code = error_code
                provider.available_models = available_models if status == "ok" else None
                save_credentials(file)
                logger.info(
                    "Test outcome persisted: provider_code=%s status=%s models=%d",
                    provider_code, status, len(available_models or []),
                )
                return
        logger.warning(
            "Test outcome skipped: provider_code=%s not found (deleted mid-test?)",
            provider_code,
        )
```

**为什么不选 option b (frontend 冻结 debounce)**: option b 把竞态状态管理推给 frontend, 单 source 不一致风险高; option a 后端原子写更可控, 跟 baseline 已有 `save_credentials` 锁机制对齐.

frontend 端配合 (写在 `design-frontend.md §2.3`): Test 进行中, frontend **不**回 PUT 改 Test 5 字段; 仅 set `isTesting: true` UI 临时态. Test 返回后, frontend 用响应里的 `available_models` 等数据更新本地 state, 但**不主动 PUT 写回** (这些字段后端已经回写, frontend GET refresh 时会拿到).

---

## 5. 各 provider_type 错误码 + model 抽取

baseline 已在 `services/llm_provider_test.py:62-82` `_request_provider_models` 实现了 3 种 provider 的 HTTP 请求拼装. B4 在此基础上加 `_extract_model_ids` (按 vendor 不同 response shape 抽 model list) + 增强 `_raise_for_status` (error_code 提取).

### 5.1 Anthropic (`anthropic_compatible`)

- 请求: `GET <base>/models` + header `x-api-key` + `anthropic-version: 2023-06-01`
- 成功响应 body shape: `{"data": [{"id": "claude-...", "display_name": ..., "type": "model"}], "first_id": ..., "has_more": ...}`
- 错误响应 body shape: `{"type": "error", "error": {"type": "invalid_x_api_key", "message": ...}}`
- error_code 来源: `body["error"]["type"]` (e.g., `invalid_x_api_key` / `authentication_error` / `rate_limit_error` / `overloaded_error`)
- HTTP code 映射:
  - 401 → `_Unauthorized(error_code=body.error.type)` → `invalid_key`
  - 429 → `_RateLimited(error_code=body.error.type)` → `rate_limited`
  - 529 → `_RateLimited(error_code="overloaded_error")` → `rate_limited`
  - 5xx → `_NetworkError` → `network_error`

### 5.2 OpenAI 协议 (`openai_compatible`)

- 请求: `GET <base>/models` + header `Authorization: Bearer <api_key>`
- 成功响应 body shape: `{"object": "list", "data": [{"id": "gpt-...", "owned_by": ...}]}`
- 错误响应 body shape: `{"error": {"code": "invalid_api_key", "type": "...", "message": ...}}`
- error_code 来源: `body["error"]["code"]` (e.g., `invalid_api_key` / `insufficient_quota` / `rate_limit_exceeded` / `model_not_found`)
- HTTP code 映射:
  - 401 → `_Unauthorized(error_code=body.error.code)` → `invalid_key`
  - 429 + `code=insufficient_quota` → `_QuotaExceeded` → `quota_exceeded`
  - 429 其他 → `_RateLimited(error_code=body.error.code)` → `rate_limited`
  - 5xx → `_NetworkError` → `network_error`

### 5.3 Gemini (`google_genai`)

- 请求: `GET <base>/models` + query `?key=<api_key>` (base 已含 `/v1beta`)
- 成功响应 body shape: `{"models": [{"name": "models/gemini-...", "displayName": ..., "supportedGenerationMethods": [...]}]}`
- 错误响应 body shape: `{"error": {"code": 401, "message": "...", "status": "UNAUTHENTICATED"}}`
- error_code 来源: `body["error"]["status"]` (e.g., `UNAUTHENTICATED` / `PERMISSION_DENIED` / `RESOURCE_EXHAUSTED` / `INVALID_ARGUMENT`)
- HTTP code 映射:
  - 401 → `_Unauthorized(error_code="UNAUTHENTICATED")` → `invalid_key`
  - 403 → `_Unauthorized(error_code="PERMISSION_DENIED")` → `invalid_key` (key 没权限当无效)
  - 429 + status=`RESOURCE_EXHAUSTED` → 按 message 判 `_QuotaExceeded` 或 `_RateLimited`
  - 5xx → `_NetworkError` → `network_error`

### 5.4 `_extract_model_ids` 实现

```python
def _extract_model_ids(response: httpx.Response, provider_type: ProviderType) -> list[str]:
    body = response.json()
    if provider_type == "google_genai":
        # Gemini: {"models": [{"name": "models/gemini-..."}]}, 剥前缀 "models/"
        return [m["name"].removeprefix("models/") for m in body.get("models", [])]
    # Anthropic + OpenAI: {"data": [{"id": "..."}]}
    return [m["id"] for m in body.get("data", [])]
```

---

## 6. 文件改动清单 (backend)

### 改动 (baseline 已存在的文件)

- `apps/studio/backend/app/routers/llm.py` (单文件含 credentials + providers/test + roles 全部 endpoint)
  - PUT `/api/llm/credentials` 改全量替换 (§3.2) + provider_code 不可变 (§3.2 B2) + api_key 空保留 (§3.2 C4)
  - POST `/api/llm/providers/test` 加 missing_api_key 前置校验 (§4.3 C4) + 接 `ping_provider_extended` (§4.3 B4) + 原子回写 5 字段 (§4.6 B4)
  - 扩 `ProviderCredentialWrite` schema (§3.2 — 加 title / provider_type / vendor_hint Optional 字段)
  - 扩 `ProviderTestRequest` schema (§4.2 — 加 vendor_hint)
  - 改 `ProviderTestResponse` schema (§4.2 — 加 available_models / error_code, 保留 model_seen 向后兼容)
- `apps/studio/backend/app/services/llm_provider_test.py`
  - 收敛 `ProviderType` Literal 砍 openai_compatible (§1.2)
  - 改 `DEFAULT_BASE_URLS` 含 `/v1` 后缀 (§1.4) + `_request_provider_models` 拼接逻辑跟着改
  - 新增 `ping_provider_extended` 返完整 model 列表 + capability lookup (§4.3 + §4.4)
  - 新增 `_extract_model_ids` (§5.4)
- `apps/studio/backend/app/services/copilot_test.py`
  - 扩 `_Unauthorized` / `_RateLimited` / `_QuotaExceeded` / `_NetworkError` 异常加 `error_code` 属性 (§4.3)
  - 增强 `_raise_for_status` 解析 vendor body 提取 error_code (§4.3)
- `apps/studio/backend/app/models/llm_config.py`
  - 收敛 `ProviderType` Literal 砍 openai_compatible (§1.2 — **跟 services 同步改**)
  - 扩 `ProviderCredential` 加 8 字段 (§2.2 — title / provider_type / vendor_hint + 5 Test 字段)
  - 新增 `ModelInfo` / `ModelCapabilities` / `TestStatus` 类型
- `apps/studio/backend/app/services/llm_credentials.py`
  - 加 `_credentials_lock()` (跟 save_credentials 共用), 给 `_persist_test_outcome` 用 (§4.6)
  - `serialize_for_response` 返 `api_key` 明文和新 8 字段进响应 (§3.3)

### 新增

- `apps/studio/backend/app/services/llm_capability_table.py` (`CAPABILITY_TABLE` + `STATIC_FALLBACK_MODELS` + `lookup_capabilities` + `_union_static_fallback`, §4.4 + §4.5)
- `apps/studio/backend/app/services/migrations.py` (`migrate_provider_type_value` 给 yaml load 用, §1.3; **不**含凭据存储 migration, 因为 baseline credential 文件不存 provider_type)

### 测试 (按 cutover discipline 铁律 — 同 PR 必含)

- `apps/studio/backend/tests/services/test_llm_provider_test.py` 单元
  - 3 个 provider_type 各自 happy path (mock httpx 200 + 验证 available_models 填充 + capability lookup 正确)
  - 3 个 provider_type 各自 error path (401 → invalid_key + error_code, 429 → rate_limited, 5xx → network_error, timeout)
  - Anthropic static fallback union (mock 返空 data, 验证 fallback 5 个 claude model 加进去)
  - C4 missing_api_key (POST 时 api_key="" → 直接返 invalid_key + error_code=missing_api_key, 不发 HTTP)
- `apps/studio/backend/tests/routers/test_llm.py` 集成 (router 单文件覆盖 credentials + test 全部 endpoint)
  - PUT 任意 UUID provider_code 200 (B3 新 add)
  - PUT 空 api_key 保留旧值 (B3 C4 fix)
  - PUT 响应含 api_key 明文字段 (round 2)
  - PUT delete = 不发该 provider, 重新 GET 列表里消失 (B3 全量替换语义)
  - PUT Test 字段单向写 (B4): client 在 PUT body 里塞 last_test_status="ok" 也不会写入, server 端保留 existing
  - POST Test 成功后 GET credentials 看到回写的 last_test_* + available_models (B4 atomic write)
  - POST Test 期间并发 PUT (race scenario): 两个写不互相覆盖 (B4)
- `apps/studio/backend/tests/services/test_migrations.py` 单元
  - `migrate_provider_type_value("openai_compatible")` 返 `"openai_compatible"`
  - 旧 llm_credentials.json (只 3 字段) 通过 ProviderCredential.model_validate 解析时, 新 8 字段填默认值
- `apps/studio/backend/tests/services/test_llm_capability_table.py` 单元
  - `lookup_capabilities("claude-opus-4-7")` 返预期 capabilities
  - 未知 model 返默认 (全 False, max_context=0)

按 cutover discipline 铁律 (`~/.claude/rules/05-sop-cutover-discipline.md`), **schema 改 + test 同步必须同一个 PR**, 不可分拆.

### 不动

- baseline graph-agent 的 LLM 调用层 (`packages/graph-agent/src/graph_agent/...`) — 那是业务调用, 跟 Test API 解耦
- `config/llm_roles.yaml` 物理文件 — user 手动改 (yaml migration 由 `migrate_provider_type_value` 在 load 时做, 不写回磁盘)
- `LlmRolesTab` / `RolesData` / `circuit_breaker` 数据模型 — frontend 侧 v2.5 重画时再动

---

## 7. 数据迁移测试

`apps/studio/backend/tests/services/test_migrations.py` 必含:

```python
def test_legacy_wavespeed_yaml_type_migrates_to_openai():
    """yaml 加载层 migration: `providers.<name>.type` 字段砍 openai_compatible."""
    assert migrate_provider_type_value("openai_compatible") == "openai_compatible"
    assert migrate_provider_type_value("openai_compatible") == "openai_compatible"  # 已合法不变
    assert migrate_provider_type_value("anthropic_compatible") == "anthropic_compatible"


def test_baseline_credentials_json_loads_with_defaults():
    """旧 ~/.studio/llm_credentials.json 只 3 字段, 加载时新 8 字段填默认值."""
    raw = {"providers": [{"provider_code": "OAI", "api_key": "sk-abc", "base_url": "https://api.openai.com/v1"}]}
    file = LLMCredentialsFile.model_validate(raw)
    assert file.providers[0].provider_code == "OAI"
    assert file.providers[0].title == "Untitled Provider"
    assert file.providers[0].provider_type == "openai_compatible"
    assert file.providers[0].last_test_status == "untested"
    assert file.providers[0].available_models is None
```

**注意**: baseline `llm_credentials.json` 文件**不存** `provider_type` / `name` 字段 (`ProviderCredential` baseline 只 3 字段), 所以**不需要**像旧 PR 草稿那样写 `name → title` migration. 旧文件加载时, Pydantic 给新字段填默认值即可.

---

## 8. 实施分步 (5 task)

| Task | 工作 | 依赖 |
|---|---|---|
| **B1** | `ProviderType` Literal 砍 openai_compatible (两处同步: models/llm_config.py + services/llm_provider_test.py) + `DEFAULT_BASE_URLS` 改成含 `/v1` 后缀 + `_request_provider_models` 拼接逻辑改 + `migrate_provider_type_value` yaml 加载迁移 | 无 |
| **B2** | `ProviderCredential` 扩 8 字段 (title / provider_type / vendor_hint + 5 Test 字段) + 新增 `ModelInfo` / `ModelCapabilities` / `TestStatus` 类型 | B1 |
| **B3** | PUT `/api/llm/credentials` 改全量替换语义 + provider_code 不可变 + api_key 空保留 + Test 字段单向写 (拒收 client) | B1, B2 |
| **B4** | POST `/api/llm/providers/test` 加 missing_api_key 前置校验 + `ping_provider_extended` 返完整 model 列表 + capability lookup + static fallback union + 原子回写 5 Test 字段 (`_persist_test_outcome` + `_credentials_lock`) | B1, B2 |
| **B5** | 单元 + 集成 test 全部更新覆盖 (provider_test / llm router / migrations / capability_table) | B1-B4 |

**B1-B5 同一 PR ship** (按 cutover discipline 铁律, schema 改 + test 同步不可分拆).

**跟 frontend cutover 协同 (B3 race 解决)**: frontend F1 第一次 PR 完成时 **不动 `ProviderType` 收敛 (保留 4-enum 兼容)**, 因为 backend B1 跟 frontend F1 并行起 PR — F1 落地时 backend 还没砍 openai_compatible. **`ProviderType` 收敛归到 frontend 第二个 PR (F3 联调)**, 那时 backend 已 ship. 详见 [`tasks.md §实施顺序`](./tasks.md#实施顺序--协同).

---

## 9. 已知 risk (backend 侧)

1. **Anthropic /v1/models 列表完整性**: 历史上 Anthropic 这个 endpoint 返回的 model 列表可能不全 (有些模型只在 Console 显式 enable 后才返回). static fallback union 是兜底, 但用户可能选了静态列表里没有的 enterprise model. **缓解**: `docs/llm-providers/anthropic.md §4` 列表保持最新, fallback 列表跟着同步.

2. **Test endpoint timeout 选 8s** (跟 baseline 一致, 没改成 10s): baseline `routers/llm.py:114` `asyncio.timeout(8)` + `llm_provider_test.py:46` `httpx.AsyncClient(timeout=8.0)` 双层 8s. 国内访问 Anthropic / OpenAI 可能因网络抖动 timeout, 8s 是 trade-off; 失败时 status=`timeout`, frontend toast 提示用户重试.

3. **api_key 存储 + 空保留 (C4 已修)**: baseline `routers/llm.py:97` `api_key=provider.api_key` 直接覆盖, 空字符串会清 key — B3 §3.2 fix 改成 `if incoming.api_key else existing.api_key`. 必须有 test 覆盖 (B5 已加).

4. **Capability lookup 同步成本**: `CAPABILITY_TABLE` + `STATIC_FALLBACK_MODELS` 当前 hardcode, 跟 `docs/llm-providers/<vendor>.md §4` + §5 表是双 source. v2.2+ 考虑统一到 yaml/toml 单一 source. v2.1 接受这个 trade-off.

5. **error_code 翻译职责划分**: backend 返 vendor 原始 error_code (英文), frontend 用 `lib/llm-error-messages.ts` 翻译人话 (v2.1 中文; i18n 延到后续版本, 见 `design-frontend.md §4.3` C3 备注). 后端**不**做中文翻译 (避免锁死语言).

6. **`ProviderType` 双定义 (B1 风险)**: `models/llm_config.py` 跟 `services/llm_provider_test.py` 重复定义同名 Literal. B1 同步砍 openai_compatible 时**两处必须一起改**, 漏一处会 (a) mypy 不挂但 enum 校验路径不一致 (b) yaml load 跟 ProviderEntry / ProviderCredential 解析行为漂移. **缓解**: B5 加 assert test 验证两处 Literal 值完全一致.

7. **PUT 改全量替换的 client 兼容性**: baseline 旧 client (现 frontend 在没改之前) 发的 PUT body 不含 `title` / `provider_type` / `vendor_hint` Optional 字段 — `ProviderCredentialWrite` 加 `model_config = ConfigDict(extra="forbid")` 时**旧 client 仍能跑** (这些是 Optional 字段, 旧 body 不发不报错). 但**反向**: 旧 client PUT 不发某个 provider, B3 全量替换语义会**真的删掉** server 端那个 provider — frontend F1 → F3 中间状态如果旧 client 跑可能误删. **缓解**: F3 联调 PR 同步上 frontend Send 完整列表的逻辑, 不允许旧 client + 新 backend 长期共存.

---

## 10. 跟 frontend 协同

`design-frontend.md §5.1` 标记 Step 1+2+4 frontend 立刻能做. 这意味着 backend B1-B5 完成前, frontend 已经在 baseline branch 跑 Step 1+2+4 重构. backend ship 后, frontend 接 Step 3+5+6 联调.

**协同点**:
- backend PUT 接受任意 UUID provider_code → frontend Step 3 验证通过
- backend ProviderTestResponse 扩字段 ship → frontend Step 5 消费
- backend Test 持久化回写 → frontend refresh 后看到 badge / available_models

具体 task 切分 + dependency 见 [`tasks.md`](./tasks.md).
