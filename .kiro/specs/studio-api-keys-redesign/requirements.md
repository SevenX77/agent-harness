---
spec: studio-api-keys-redesign
status: Drafting
target_ship: v2.1
date: 2026-05-18
baseline_branch: baseline/v2.1-2026-05-18
authors:
  - user (PM)
  - apps master (Claude) — facilitator
  - a2 (Gemini) — design inspiration round 1 + round 2 web research
linked_specs:
  - studio-from-stash2-baseline
  - studio-frontend-v21-multifile-editor
linked_docs:
  - docs/llm-providers/
---

# Requirements — Studio Settings → API Keys 重新设计

## 0. 业务目标 (Why) 与工作目录

### 0.1 业务目标

让 PM (user 自己, 未来扩到团队) 在 Studio 里**自己一个一个 add LLM provider**, 测连接, 看每个 provider 哪些 model 可用, 失败时看到清晰错误代码 — 不开终端, 不写 YAML, 不依赖工程师改 backend enum.

当前 (`apps/studio/frontend/src/components/studio/SettingsPage.tsx` baseline) 把 provider 按 5 个硬编码 vendor (Anthropic / DeepSeek / Gemini / OpenAI / WaveSpeed) 分组折叠, Add Custom Provider 按钮永久 disabled, 不可用. Test 按钮 inline alert 干扰, password 类型触发浏览器密码管理器.

### 0.2 baseline 工作目录

- **baseline 分支**: `baseline/v2.1-2026-05-18` (local + origin 同步, commit `7783d23`); `main` (`6a0fd57`) 是 ancestor, 尚未含 v2.1 baseline 文件
- **baseline 物理 worktree**: `/home/sevenx/coding/baseline-v21/` (`git worktree list` 实证, 已从 `/tmp/agent-harness-v1/` 迁出; 旧 tmp 路径仍在但是不同分支). **本 spec 全篇引用的 baseline 源码路径以这里为准**, parent master + apps master 实施期在这个 worktree 跑 backend / frontend 改动
- **后端 baseline 实际路径** (本 spec 全篇引用以此为准):
  - `apps/studio/backend/app/routers/llm.py` — 含 `/api/llm/credentials` (GET/PUT) + `/api/llm/providers/test` (POST) + `/api/llm/roles`. router 前缀 `/api/llm`. **不是** `routers/credentials.py`.
  - `apps/studio/backend/app/models/llm_config.py` — 含 `ProviderCredential` (provider_code/api_key/base_url 三字段) + `LLMCredentialsFile` + `ProviderType = Literal[...]` (4 个值) + `ProviderEntry`/`ModelEntry`/`RoleEntry`/`RoleModelEntry`/`RolesData`. **不是** `CredentialProviderState`.
  - `apps/studio/backend/app/services/llm_provider_test.py` — 含独立的 `ProviderType = Literal[...]` (跟 models/llm_config.py 重复定义, **改 enum 时两处都改**) + `DEFAULT_BASE_URLS` + `ping_provider`. `ProviderType` 是 `Literal` 类型别名, **不是** `class ProviderType(str, Enum)`.
  - `apps/studio/backend/app/services/copilot_test.py` — 含异常类 `_Unauthorized` / `_RateLimited` / `_QuotaExceeded` / `_NetworkError` + `PingResult` / `_first_model_id` / `_raise_for_status` helper, 被 llm_provider_test 复用
  - 凭据存储: `~/.studio/llm_credentials.json` (`app/services/llm_credentials.py` 管 load/save/redact)
- **PUT 现状语义** (本 spec 重要假设): `apps/studio/backend/app/routers/llm.py:85-107` 当前是**按 provider_code keyed 的 incremental upsert** (新 provider 加进去, 同 code 覆盖, **从来不删**); 同时存在已知缺陷 `request.api_key` 空字符串会**清空**已存 key (B3 修复必含)
- **实施期 cutover**: backend 改动 PR 落在 `baseline/v2.1-2026-05-18` 分支, ship 后整段 v2.1 → main cutover PR 由 user 拍板时机统一推. 详见 [`tasks.md §实施顺序`](./tasks.md#实施顺序--协同)

## 1. User 原话 8 条 + 1 条协作要求 (权威)

> 1. 这个页面所有 input 都不要用 password type;
> 2. 每个 vendor 默认一个 provider 是官方 API,
> 3. add custom provider 功能不完善
> 4. test 按钮缺失
> 5. title 要可以自定义 provider 厂商
> 6. sdk 选择, 每个 vendor 可用的 sdk 都不一样, 需要 research, 落文档,
> 7. 专门开一个和模型 api 相关的文档目录, 里面要放各家模型的配置规范文档, 中转 api 文档, 包括大模型 llm 和多模态模型
> 8. 分类修改, 这里的 API key 应该填 provider 的 key, 不应该像现在是根据大模型厂商划分, 不应该有默认的 vendor, 应该就用户自己一个一个加
>
> 让 Gemini 一起参与设计讨论

**冲突解决**: #2 跟 #8 结构上互斥 — #2 假设有 vendor 分组每组有默认 official, #8 否定 vendor 分组本身. **#8 后写覆盖**: 最终架构 = provider 顶层扁平, 用户自己加, vendor 仅作 provider 上的标签字段.

## 2. Round 1 + Round 2 拍板的事 (按时间顺序)

### Round 1 → Round 2 之间 user 拍板

1. **Provider 顶层扁平, 砍 VENDORS 分组**
2. **provider_code 用 UUID** (改 title 不影响下游 LlmRoles 引用)
3. **Test 反馈走 toast + 持久化 badge**, 不用 inline Alert
4. **填入值自动 debounce 持久化** (像 video_analysis), 不要 Save 按钮
5. **input 不用 password type** — 切 `type="text"` + `autocomplete="off"` + `data-1p-ignore` + `data-lpignore="true"` + `data-form-type="other"` 堵密码管理器; round 2 改为直接显示 server 返回的明文 `api_key`, 不再 mask / Eye toggle
6. **Quick Starts 推荐砍掉** — 用户从空白开始一个一个 add
7. **Test 成功**: 后端要返**完整可用模型列表** + 每个 model 的能力 (thinking / tool_calling / vision / max_context_tokens)
8. **Test 失败**: 返 error_code (例 anthropic 原始 `invalid_x_api_key`) + error_message, frontend 在 toast / badge 上显示
9. **持久化字段** (后端 `ProviderCredential` 扩, 5 个: 4 个 Test 结果 + 1 个原始错误码): `last_test_status` / `last_test_at` / `last_test_message` / `last_error_code` / `available_models`
10. **熔断**: **不要 provider-level**; 用**轻量 model-level**:
    - Test 调用拉 `/v1/models` 拿 ground truth 列表
    - 用户在 LlmRoles 选了 model X 但 X **不在** 列表里 → UI 标 "Unavailable for this provider" + fallback 链跳过
    - 不烧 token 单独 ping 每个 model, 不真做"业务调用熔断", 仅 LlmRoles UI 层 filter

### Round 2 后 user 4 条最终拍板 (2026-05-18)

1. **Backend `ProviderType` enum 收敛** — 从 4 砍到 3 (干掉 `openai_compatible`, 因为 WaveSpeed 实测就是 `openai_compatible`)
2. **多模态 (Replicate / Fal / Stability AI / BFL Flux / Midjourney / Runway) 在 v2.1 不做** — async polling 协议跟当前 text-stream test path 不兼容, 延到 v2.2+
3. **Round 2 反转 Mask** — 不再做 focus-aware mask / Eye toggle; input 值始终等于 server 返回并持久化的 `api_key` 真值
4. **`docs/llm-providers/` 已落盘 5 个 md** (README / _template / anthropic / openai / gemini); v2.1 不覆盖多模态

## 3. 范围 (In / Out)

### In v2.1
- Text-only LLM provider: Anthropic / OpenAI / Gemini / DeepSeek / Mistral / xAI Grok / Cohere / WaveSpeed / OpenRouter / Together AI / OneChats / Jiekou 等
- 3 个 protocol enum (anthropic_compatible / openai_compatible / google_genai)
- Flat provider list + Add / Edit / Test / Delete CRUD
- 明文 `api_key` input + 密码管理器隔离
- Auto-debounce save (300ms)
- Test 成功持久化 available_models, 失败持久化 error_code/message
- LlmRolesTab 用 available_models filter "Unavailable" model (最小改动, 不重画 LlmRolesTab)

### Out v2.1
- **多模态 provider** (Replicate / Fal / Stability AI / 等) → v2.2+
- **Azure OpenAI / Vertex AI / Bedrock 部署变体** → v2.3+
- **OAuth 类 provider 鉴权** → 未来
- **LlmRolesTab 重画** (只做最小改动让 filter 工作) → v2.5
- **拖拽排序 / favorite 标记** → v2.5
- **Quick Start templates / 预制 vendor 列表** → 永不 (用户 #8 砍)
- **真业务调用熔断** (active 拦截调用) → 永不 (用户 round 2 拍, 只做 UI filter)

## 4. 验收标准 (Done Criteria)

### Manual smoke (user 自己跑)
1. 打开 Settings → API Keys, 看到**空列表** + "Add Provider" 按钮 (按钮可点, 不再 disabled)
2. 点 Add → 一行 row 出现, 默认 OpenAI 协议 + base URL = `https://api.openai.com/v1`
3. 改 title 为 "My OpenAI" → debounce 300ms 后**自动保存** (toast 提示 "Saved" 或后端 200 静默)
4. 粘贴 OpenAI key (sk-...) → 保存后 input 仍显示真实值, refresh 后也显示 server 返回的同一值
5. **浏览器密码管理器不弹**保存提示 (1Password / LastPass / Chrome 密码 都不应触发)
6. API Key input 始终是 `type="text"`, 无 Eye 按钮, 浏览器密码管理器不应弹保存提示
7. 点 Test → toast "Testing My OpenAI..." → 1-3s 后 "✓ N models available" (具体数字)
8. Badge 显示绿点 + 时间戳 ("OK · 2026-05-18 14:23")
9. 故意输错 key 重测 → 红点 + 显示 vendor 原始 error_code ("invalid_api_key") + toast 显示中文人话提示
10. 删除该 provider → 列表为空, LlmRoles 引用该 provider 的 role 显示 "Unavailable"
11. Refresh 页面 → 之前的 Test 结果 (badge / available_models) 持久化, 重新加载后仍显示

### Playwright e2e (后端 schema 完成后, 我和 user 一起跑)
覆盖 Add / Edit / Test 成功 / Test 失败 / Delete 5 个 path. 详见 [`design-frontend.md` §8](./design-frontend.md#8-测试计划).

## 5. 非功能性要求

- **响应延迟**: debounce save < 500ms 完成 (本地 300ms 防抖 + 网络 ~200ms)
- **Test 超时**: 后端 timeout 10s, 前端 loading toast 期间不阻塞 UI
- **持久化原子性**: PUT /api/credentials 全量覆盖, 失败时前端 rollback 本地 state
- **错误可观测**: 失败的 Test 在 backend log 留 vendor 原始响应 (脱敏后 — 不含 key), 前端 badge hover 显示完整 message

## 6. 跨 master 协作

本 spec 跨前后端, 拆两个 design doc:

- **[`design-frontend.md`](./design-frontend.md)** — apps master 实施 (`apps/studio/frontend/`)
- **[`design-backend.md`](./design-backend.md)** — parent master 实施 (`apps/studio/backend/`)

实施顺序见 [`tasks.md`](./tasks.md). frontend 大部分能立刻做 (Step 1/2/4), backend schema 扩展 ship 后 frontend Step 3/5/6 才能联调.

## 7. 已知风险 / 未决问题

1. **多模态 Test ping 策略**: v2.2 加多模态时需要新 `ProviderTestStrategy`, async media (Fal/Replicate) 没 `/v1/models`. 当前 deferred.
2. **available_models 完整性**: Anthropic 长期没有完整 model 列表 API. 缓解: 后端在 Test 成功时把 `docs/llm-providers/<vendor>.md §4 Notable Model IDs` 静态列表 union 进 available_models.
3. **多 provider 显示顺序**: 当前按 add 时间. 拖拽 / favorite 延到 v2.5.
4. **provider_type dropdown 默认值**: 当前默认 `openai_compatible` (最普遍). v2.1 ship 后看用户反馈调.

## 8. 参考

- **`docs/llm-providers/`** — vendor matrix + 协议规范, 后端 + 前端 default value 单一来源
- **`/home/sevenx/coding/video_analysis/app/src/views/ConfigView.tsx`** — auto-debounce save + Test 持久化 pattern 参考 (user 明示)
- **a2 Gemini Round 2 web research output** (`/tmp/r2-reply.txt`) — vendor SDK 现状 ground truth

## Round 2 反馈 (2026-05-19, user 拍板反转 round 1 脱敏决定)

### user 原话

> 刚才我填入api key他自动就消失了，api key显示saved key retain。
> 按test报错没有API key。还会弹出是否要保存密码。
>
> 有好几个反模式：
> 1. api key消失，之前需求很明确，功能行为模仿video analysis，
>    api key填好就放在input里，input里面的值和真正存储的值同步
> 2. 不要用把api key当成密码

### round 1 → round 2 翻转

| 字段 | round 1 拍 | round 2 反转 |
|---|---|---|
| GET `api_key` | 脱敏不返, 只 `has_key: bool` | **返明文** |
| Frontend draft `api_key` | 初始化空字符串, 显示 "Saved key retained" placeholder | **直接用 server 返回的真值** |
| Frontend `type` | round 1 已规定 `type="text"` | **同 round 1**, 但代码漂移要修 (当前 `type={showKey ? "text" : "password"}`) |

### 理由 (round 2)

- 本地单用户机器, 凭据文件已 0600 mode, 前端可见无安全收益
- "脱敏占位" UX 反直觉, 让用户以为 key 没保存上 (反复触发 Test 失败 "API key 为空")
- 对齐 user 原 round 1 明示参考实现 `video_analysis` 项目: "input 值 = 存储值"
