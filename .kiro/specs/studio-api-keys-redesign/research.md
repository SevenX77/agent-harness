---
spec: studio-api-keys-redesign
status: Drafting
date: 2026-05-18
authors:
  - a2 (Gemini) — web_search round 2
  - apps master (Claude) — synthesis
---

# Research — LLM Provider SDK 现状 + 设计参考

## 1. Web Research: 各 vendor SDK / Protocol 实证

a2 (Gemini) 2026-05-18 通过 `web_search` 拉取各 vendor 官方 / GitHub / 文档现状 (避免凭训练记忆瞎写, 因为 Gemini cutoff 之后 Anthropic / Gemini / DeepSeek 协议都在变).

### 1.1 LLM (text-only / chat completion)

| Vendor | 现状 (web 实证) | 应归到的 enum | 官方文档 URL |
|---|---|---|---|
| **Anthropic** | 官方 `anthropic` Python/TS SDK; Vertex AI 部署 (`anthropic[vertex]`); AWS Bedrock 部署 (`anthropic[bedrock]`); **近年正式支持 OpenAI compatible 协议** (通过 `/v1/messages` 兼容层, 但 native SDK 更推荐 — 因为支持 Prompt Caching / Extended Thinking / Computer Use 等) | `anthropic_compatible` (native) / `openai_compatible` (兼容层) | https://docs.anthropic.com/ |
| **OpenAI** | 官方 SDK, Azure OpenAI (api-key header 而不是 Bearer, 需后端 adapter), OpenAI compatible 协议是业界 defacto standard | `openai_compatible` | https://platform.openai.com/docs/ |
| **DeepSeek** | **完全 OpenAI compatible**, 官方虽有轻量 SDK 但底层就是改了 base_url 的 openai 客户端. 还提供了一个 Anthropic 兼容端点用于平替 Claude | `openai_compatible` | https://platform.deepseek.com/api-docs |
| **Google Gemini** | 官方 `google-generativeai` SDK; Vertex AI; **2024-11 起加了 OpenAI compatible endpoint** (`https://generativelanguage.googleapis.com/v1beta/openai/`), 允许直接用 openai SDK 调 gemini-1.5/2.0/3.x 系列 | `google_genai` (native, 有 grounding 等高级特性) / `openai_compatible` (兼容 endpoint) | https://ai.google.dev/gemini-api/docs/openai |
| **Mistral** | 官方 SDK (`mistralai`), 同时**完全兼容 OpenAI 协议**. Azure 上作为 MaaS 运行同样兼容 | `openai_compatible` | https://docs.mistral.ai/ |
| **xAI Grok** | API **完全兼容 OpenAI 规范**, 推荐直接用 openai 库换 `base_url="https://api.x.ai/v1"` | `openai_compatible` | https://docs.x.ai/ |
| **Cohere** | 提供专门的 **Compatibility API** (`https://api.cohere.ai/compatibility/v1`) 完美对接 OpenAI SDK | `openai_compatible` | https://docs.cohere.com/docs/compatibility-api |
| **WaveSpeed** | **LLM 聚合中转平台** (类似 OpenRouter), 提供**完全统一的 OpenAI compatible API** (`https://llm.wavespeed.ai/v1`), 通过 `vendor/model` 形式 model ID 路由 (e.g., `anthropic/claude-opus-4.6`) | `openai_compatible` (**不**是独立 enum) | https://wavespeed.ai/docs |

### 1.2 多模态 (image / video / audio generation) — v2.1 不做

| Vendor | 现状 | 应归 enum (将来) |
|---|---|---|
| **Replicate** | Async job 模型, POST 拉起预测 → polling `get_url`. 没有原生 openai 兼容 | (v2.2+) `replicate_async` 或统一 `async_polling_rest` |
| **Fal.ai** | Async job 队列, 高阶 SDK `subscribe` 自动 polling, 或底层 `submit` 拿 request_id 轮询 | (v2.2+) `fal_async` |
| **Stability AI** | v2beta 走纯 REST API (POST 请求, 同步或异步) | (v2.2+) 新 enum |
| **BFL (Flux) / Midjourney / Runway** | 均为异步 REST (提交任务 → 拿 ID 轮询 / Webhook 回调) | (v2.2+) 新 enum |

### 1.3 中转 / 聚合 API

| 中转 | 现状 | enum | Base URL |
|---|---|---|---|
| **OneChats** | OpenAI 协议中转, URL 形如 `chatapi.onechats.ai/v1` | `openai_compatible` | `https://chatapi.onechats.ai/v1` |
| **Jiekou** | **双协议入口**: `/openai/v1` 走 OpenAI, `/anthropic` 走 Anthropic native | `openai_compatible` 或 `anthropic_compatible` | `https://api.jiekou.ai/openai/v1` 或 `https://api.jiekou.ai/anthropic` |
| **OpenRouter** | 多 vendor 聚合, 纯正 OpenAI compatible | `openai_compatible` | `https://openrouter.ai/api/v1` |
| **Together AI** | OSS model hosting, OpenAI compatible | `openai_compatible` | `https://api.together.xyz/v1` |

## 2. Backend `ProviderType` Enum 收敛判决

### 当前 baseline (4 enum)

`apps/studio/backend/app/services/llm_provider_test.py:18-25`:

```python
class ProviderType(str, Enum):
    anthropic_compatible = "anthropic_compatible"
    openai_compatible = "openai_compatible"
    google_genai = "google_genai"
    openai_compatible = "openai_compatible"
```

### Web research 揭示的问题

`apps/studio/backend/app/services/llm_provider_test.py:75-79` 实证: `openai_compatible` 跟 `openai_compatible` test 路径**完全一样** (都是 `GET /v1/models` + `Authorization: Bearer`). 这暗示 4-enum 区分**只是 base URL 不同**, 没有协议层差异.

### v2.1 收敛后 (3 enum)

```python
class ProviderType(str, Enum):
    anthropic_compatible = "anthropic_compatible"   # native SDK, x-api-key + anthropic-version header
    openai_compatible = "openai_compatible"         # OpenAI 标准, 覆盖 90%+ 文本 LLM
    google_genai = "google_genai"             # 可选保留, native SDK 有 grounding 等特性
```

理由:
- `openai_compatible` 干掉 — 它就是 `openai_compatible` 套了不同 base URL
- DeepSeek / Mistral / Grok / Cohere / WaveSpeed / 各中转商 全部统一到 `openai_compatible`, 用户改 base URL 就能切换
- `google_genai` 保留是因为 native protocol (`:generateContent`) 跟 OpenAI 协议 message format 不同 (`contents` 而非 `messages`, role 用 `model` 而非 `assistant`), 而 Google 的 OpenAI 兼容 endpoint 又不支持所有特性

### v2.2+ 加多模态时

需要额外新 enum (`replicate_async` / `fal_async` 或统一 `async_polling_rest`) + 新 `ProviderTestStrategy` (async media 服务没 `/v1/models`, 用 vendor-specific 探活)

## 3. 设计参考: video_analysis 项目

user 明示 (历史 feedback memory): "Studio 的 API key 设计参考 video_analysis 项目".

**核心借鉴**:

### 3.1 Auto-debounce save (取代 Save 按钮)

`/home/sevenx/coding/video_analysis/app/src/views/ConfigView.tsx`:
- `useEffect` watch state 变化, debounce 300-500ms 后 POST 持久化
- 失败 toast.error, 成功静默或 toast.success
- 没有 "Save" 按钮, 用户每次 onChange 都被自动保存

### 3.2 Test 状态持久化 + inline 显示

`/home/sevenx/coding/video_analysis/app/src/views/ConfigView.tsx:L82-87, L131-137`:
- 每个 provider 配 SecretField 组件含 `testing` / `testResult` props
- Test 结果通过 `<Alert variant="default/destructive">` 内嵌显示 (**Studio 不采用 inline Alert, 改 toast + 持久化 badge**)
- testResult 持久化到 backend (重启 frontend 后仍显示)

### 3.3 字段密钥的视觉处理

video_analysis 用 `getSecretPresentation` 把字符串截短显示 (`abc...xyz`). Studio v2.1 round 1 曾计划 focus-aware mask; 2026-05-19 round 2 已反转为明文 input (见 `design-frontend.md §4`).

### 3.4 Studio v2.1 偏离 video_analysis 的地方 + 理由

| 项 | video_analysis | Studio v2.1 | 理由 |
|---|---|---|---|
| Test 反馈 | inline `<Alert>` | toast + 持久化 badge | user 拍 round 1 (Alert 太吵, badge 一直显示状态更直观) |
| 字符串显示 | 截短 (`abc...xyz`) | round 2 改明文 input | user round 2 明确要求 "input 值 = 存储值" |
| Provider 模型 | 单体 (一个 OpenAI provider) | 多个扁平 (用户加多个) | Studio 是多 vendor agent platform, 不是单 LLM 视频工具 |
| Save 触发 | debounce 自动 | debounce 自动 ✓ 一致 | user 明示 |

## 4. 行业 LLM 客户端 paradigm 对比

| 工具 | Provider 信息架构 | Studio v2.1 借鉴? |
|---|---|---|
| **Continue.dev** (VSCode plugin) | `config.json` 里 `models` 数组, 每个 model 是顶层实体, 无 vendor 分组 | ✓ 顶层扁平思路 (user #8 一致) |
| **Cline / Roo Code** (VSCode plugin) | Settings 页用 vendor 作 dropdown, 选定后才显示该 vendor 字段 | ✗ 这是 vendor 分组, user #8 否决 |
| **OpenWebUI** (web 自托管) | Admin Panel → Connections, 用户加多个 OpenAI-compatible endpoint | ✓ 多 endpoint 扁平思路 |
| **Cursor** (闭源 desktop) | 固定 vendor 列表 (OpenAI / Anthropic / Google), 用户只填 key | ✗ 不支持自定义 vendor / 中转 |
| **LobeChat** (开源 chat) | vendor 预定义, 每个 vendor 可加多个 endpoint | ✗ 类似 OpenWebUI 但有 vendor 分组 |

Studio v2.1 paradigm = **Continue.dev + OpenWebUI 风格** (provider 顶层 + 无 vendor 强制分组).

## 5. Gemini Round 2 推送的 3 条 push back

a2 Gemini round 2 (web research 后) 主动推送的设计 risk:

1. **`openai_compatible` Enum 的荒谬性** — Web research 实证 WaveSpeed 就是 `openai_compatible`. 后端只需要统一成 2-3 enum (anthropic / openai / google_genai), 靠用户配置 Base URL 去分发. **user 2026-05-18 已采纳, 收敛到 3 enum**.

2. **多模态测试 (Test) 按钮怎么做?** Fal / Replicate 没 `/v1/models`, 需要不同 Ping 策略. **user 2026-05-18 已拍: 多模态 v2.1 不做, 延到 v2.2+**.

3. **密码管理器对抗的实现成本** (CSS Blur 砍掉后) — `type="text"` + 字符级 mask 需要维护 rawValue/displayValue 双态 + onChange 游标计算, 比原生 `type="password"` 脏得多. Gemini 建议: **未获焦点显示静态 `••••••`, 获焦点显示真实值, 规避游标问题**. **user 2026-05-18 已采纳, 2026-05-19 round 2 已反转为直接明文显示 `api_key`, 不再 mask / Eye toggle**.

## 6. 落盘的 docs 参考

`docs/llm-providers/` 已落盘 5 个 md:
- `README.md` — vendor matrix + enum 收敛决策
- `_template.md` — 新 vendor 文档模板
- `anthropic.md` / `openai.md` / `gemini.md` — 3 个 vendor 示范, 含 base URL / auth header / model id / capabilities / quirks / cURL test sample / error code reference

后续加新 vendor 时拷贝 `_template.md` + 在 README.md matrix 加一行.
