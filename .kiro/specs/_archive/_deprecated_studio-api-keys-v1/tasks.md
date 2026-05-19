# Studio Copilot LLM API Keys v1 — Tasks

> **Status**: Draft, v0.1, 2026-05-14
> **Implementer**: a1 (Codex)
> **Spec link**: requirements.md / design.md / research.md
> **Branch**: 跟 brief #1 (studio-tunnel-safety) 共用, 或独立 `feat/studio-api-keys-v1`
> **预估**: 总 ≈ 6 小时 a1 工作时间

## 任务总览

```
T1  后端 schema 演进 (砍 V1_5_PLACEHOLDER + 加 base_url)        ── 1h
T2  后端 Test endpoint (POST /api/copilot/credentials/test)      ── 2h
T3  后端 GET/PUT credentials 响应 schema 改 (含 last4 + base_url) ── 0.5h
T4  前端 API 客户端方法增加 (testCopilotCredentials)              ── 0.5h
T5  前端 SettingsPage 重构 (3 tab 导航 + AI & Copilot 4 卡片)      ── 1.5h
T6  e2e 验证 (Tauri + tunnel 两种场景)                            ── 0.5h
```

---

## T1: 后端 schema 演进

### 文件 + 改动

**`apps/studio/backend/app/services/copilot_credentials.py`**:
- `BackendCredentials.v1_5_placeholder` 字段**删除**
- `BackendCredentials` 加 `base_url: str = ""` 字段
- `BackendCredentials.model_config = ConfigDict(extra="ignore", populate_by_name=True)` — 把 `extra="forbid"` 改为 `"ignore"`, 老文件含 `V1_5_PLACEHOLDER` 加载兼容
- `default_credentials()` 移除 `v1_5_placeholder=True/False` 行
- `__all__` export 更新

**`apps/studio/backend/app/models/copilot.py`**:
- `BackendStatus.v1_5_placeholder` 字段**删除**, 加 `last4: str | None = None` 和 `base_url: str = ""`
- `CredentialsWriteRequest` 加 `base_url: str | None = None` 字段 (None = 不改, 同 api_key 语义)

### 测试

**`apps/studio/backend/tests/test_copilot_credentials.py`** (假设已有, 补 case):
- 默认 credentials 不含 `v1_5_placeholder` 字段
- 老格式文件 (含 `V1_5_PLACEHOLDER`) 加载不报错, 字段被忽略
- 写新 backend 时 `base_url` 持久化
- atomic write 测试不变

### 验收

- `uv run pytest apps/studio/backend/tests/test_copilot_credentials.py -v` pass
- Manual: cat `~/.studio/copilot.json` 不含 V1_5_PLACEHOLDER

---

## T2: 后端 Test endpoint

### 文件 + 改动

**`apps/studio/backend/app/routers/copilot.py`** 加新 route:
```python
@router.post("/api/copilot/credentials/test")
async def test_copilot_credentials(request: TestCredentialsRequest) -> TestCredentialsResponse:
    """Use candidate key+base_url to test LLM provider connectivity."""
    backend = request.backend
    api_key = request.api_key
    base_url = request.base_url or DEFAULT_BASE_URLS[backend]
    
    try:
        async with asyncio.timeout(8):
            result = await _ping_provider(backend, api_key, base_url)
        return TestCredentialsResponse(status="ok", latency_ms=result.latency_ms, model_seen=result.model_seen)
    except asyncio.TimeoutError:
        return TestCredentialsResponse(status="timeout", message="Request exceeded 8s")
    except _Unauthorized:
        return TestCredentialsResponse(status="invalid_key", message="Provider rejected key (401)")
    except _RateLimited:
        return TestCredentialsResponse(status="rate_limited", message="Rate limit (429)")
    except _QuotaExceeded:
        return TestCredentialsResponse(status="quota_exceeded", message="Quota exceeded")
    except _NetworkError as e:
        return TestCredentialsResponse(status="network_error", message=str(e)[:200])
```

**`apps/studio/backend/app/services/copilot_test.py`** (新文件):
- `async def _ping_provider(backend, api_key, base_url) -> PingResult`
- 4 个 backend 各自实现 (Claude `messages.create max_tokens=1`, OpenAI `models.list`, DeepSeek `chat.completions max_tokens=1`, Gemini `models.list`)
- 异常分类: HTTP 401 → `_Unauthorized`, 429 → `_RateLimited`, 402/usage → `_QuotaExceeded`, ConnectionError → `_NetworkError`
- Log `logger.info("test_credentials backend=%s last4=%s status=%s latency_ms=%d")` — **mask 末 4 位**

**`apps/studio/backend/app/models/copilot.py`** 加 schema:
```python
class TestCredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: CopilotBackend
    api_key: str
    base_url: str = ""

class TestCredentialsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "invalid_key", "rate_limited", "quota_exceeded", "network_error", "timeout"]
    latency_ms: int | None = None
    model_seen: str | None = None
    message: str | None = None
```

### 测试

**`apps/studio/backend/tests/test_copilot_test_endpoint.py`** (新):
- Mock `_ping_provider` 返回 ok → API 返回 status=ok + latency_ms
- Mock 抛 `_Unauthorized` → API 返回 invalid_key
- Mock 抛 `_RateLimited` → API 返回 rate_limited
- Mock asyncio.timeout → API 返回 timeout
- Verify **响应不含 api_key** (anti-reflection)
- Verify log 行 mask 末 4 位

### 验收

- pytest pass
- Manual: curl 调 Test endpoint 真实 Claude 错 key → 收 401 invalid_key (8s 内)
- Manual: log 文件 grep api_key 全文不应找到完整 sk-***

---

## T3: 后端 GET/PUT credentials schema 改

### 文件 + 改动

**`apps/studio/backend/app/routers/copilot.py`** 改:
- `_to_read_response(data)`: 生成 `BackendStatus` 时填 `last4 = api_key[-4:] if api_key else None`, `base_url = backends[b].base_url`
- `put_copilot_credentials(...)`: 接受 `base_url` 字段 (按 `request.base_url is None` 不改; `""` 清空; 其他设值, 跟 api_key 同 idempotent 语义)

### 测试

**`apps/studio/backend/tests/test_copilot_credentials_router.py`** (假设已有):
- GET 返回 last4 末 4 位
- PUT base_url 持久化
- PUT api_key=None base_url=null 不改任何
- PUT api_key="" 清空 key

### 验收

pytest pass

---

## T4: 前端 API 客户端

### 文件 + 改动

**`apps/studio/frontend/src/api/copilot.ts`** 加 `testCopilotCredentials(req)` + 调整 type 定义 (含 `last4`, `base_url`)。

### 测试

**`apps/studio/frontend/src/api/copilot.test.ts`** (假设已有 client.test 类似 pattern):
- mock axios → testCopilotCredentials 返回 mock 响应
- mock 4xx → throw error 包含 status 字段

### 验收

`pnpm test copilot` pass

---

## T5: 前端 SettingsPage 重构

### 文件 + 改动

**`apps/studio/frontend/src/components/studio/settings-page.tsx`** 大改:
- 顶层用左侧 nav + 右侧 content (radix `Tabs` + 自定义垂直布局, 或 `RadioGroup` + conditional content)
- 3 个 tab: General / AI & Copilot / Advanced
- General tab: 把原 Studio User ID + Gitea Host 搬过来 (内容不变)
- AI & Copilot tab: 实现 design.md §4.1 的 mockup
  - Active backend radio (4 个 backend)
  - 4 个 backend 卡片, 每个含:
    - Mask 输入框 (`type="password"`, 已配显 `••••<last4>`)
    - Test 按钮 + 状态 chip
    - Advanced 折叠区 (radix `Collapsible` 或自实现), 含 Base URL 输入
  - 每卡独立状态 (`use-state` per backend, 或一个 `Record<Backend, BackendDraft>`)
  - dirty diff 检测 (改 key / base_url 跟 server 不同时 enable Save)
- Advanced tab: 占位 "More settings coming soon"
- 复用 uikit 组件 (`Card`, `Input`, `Button`, `RadioGroup`, `Tabs`, `Collapsible`) 跟现有 Studio 视觉规范一致

### 测试

**`apps/studio/frontend/src/components/studio/settings-page.test.tsx`** (假设新):
- Render 3 个 tab 名
- 切到 AI & Copilot, 4 个卡片可见
- Mock API 已配 claude key → 卡片显示 `••••4xyz`
- 点 Test → Spinner → 200 ok → 绿勾
- 点 Test → 4xx invalid_key → 红叉 + "Invalid API key"
- 改 key + Save → PUT 调用 + 卡片更新

**`apps/studio/frontend/tests/e2e/copilot-settings.spec.ts`** (新, e2e by a3):
- E2E 进 Settings → AI & Copilot tab → 输入 key → Test → 看到状态变化
- E2E 改 key → Save → 立即触发 /api/copilot/query → backend 用新 key

### 验收

- `pnpm test settings-page` pass
- Playwright e2e pass (a3 跑)
- 视觉对照 uikit tokens, 主控亲眼看浏览器实证 (Iron Law: 前端任务必视觉验证)

---

## T6: e2e 端到端验证

### 场景

1. **Tauri 模式 (production-like)**:
   - tauri dev build, sidecar 起来
   - 打开 SettingsPage → AI & Copilot
   - 输入 Claude 错 key → Test → 红叉
   - 输入 Claude 真 key → Test → 绿勾
   - Save → 切回主界面 → Copilot 聊天 → 收到 Claude 响应
   - 改 key 为另一真 key → Save → 再聊天 → 收到响应 (热加载验证)

2. **Dev tunnel 模式 (brief #1)**:
   - `python scripts/dev-tunnel.py` 拉起
   - 手机扫码进 SettingsPage
   - 同上 5 步全跑通
   - 验证: 浏览器 DevTools Network 显示所有调用带 `Authorization: Bearer <dev_tunnel_token>` header
   - 验证: 没 token 用 curl 试 `POST /api/copilot/credentials/test` 应返 401

### 报告

a1 + a3 协作产出 `docs/studio-api-keys-v1-validation.md`, 含两种模式 5 步截图/log。

---

## Out of scope (不做)

- OS keychain 集成
- OAuth account 集成
- Per-skill backend override
- Quota / cost UI
- Base URL preset 库 (用户必须手动填 URL, 不提供 "OneAPI" 一键)
- 老 `~/.studio/copilot.json` migration script (Pydantic `extra="ignore"` 已兼容)
