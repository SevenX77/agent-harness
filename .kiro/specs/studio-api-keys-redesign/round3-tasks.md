# API Keys Round 3 Implementation Plan

> **For agentic workers (ccb agents a1=Codex / a2=Gemini)**: 派任务前 master Claude 必读 spec `round3-design.md`。每个 task 是一个 self-contained deliverable, 含 files / scope / acceptance / commit message。TDD discipline 内置 (test 先于 impl, 跑测后再 commit)。

**Goal**: API Keys round 3 改造 — 单入口 + 类型 RadioGroup + Official Select 下拉 + 多 SDK 自动探测 + Mask CSS (Firefox fallback) + Badge utility color + 5 vendor doc 入库

**Architecture**: 3 PR 顺序执行 — PR-A (a2 主笔 docs) → PR-B (a1 主力 backend) → PR-C (a1 主力 frontend), 依赖链不可并行

**Tech Stack**:
- Frontend: TypeScript + React + shadcn/ui + Tailwind CSS (Vite build)
- Backend: Python 3.12 + FastAPI + Pydantic (uv + pytest)
- Docs: Markdown + YAML frontmatter

**Spec**: `.kiro/specs/studio-api-keys-redesign/round3-design.md` (Status: Draft, a2 review PASS)

**Code Workspace** (ccb agent workspace): `/home/sevenx/coding/agent-harness/apps`

---

## File Structure (Locked, see spec §9)

### 新增 (frontend)

- `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx` — Inline form (RadioGroup + 条件渲染 Official/Third-party)
- `apps/studio/frontend/src/components/studio/api-keys/OfficialVendorSelect.tsx` — 5 vendor Select 下拉
- `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx` — 现有 ProviderRow 拆出 (含 mask+eye + AlertDialog 删除)
- `apps/studio/frontend/src/components/studio/api-keys/ProviderListSkeleton.tsx` — Loading skeleton
- `apps/studio/frontend/src/components/studio/api-keys/index.ts` — barrel export
- `apps/studio/frontend/public/fonts/text-security-disc.woff2` — Firefox fallback webfont

### 修改 (frontend)

- `apps/studio/frontend/src/components/studio/SettingsPage.tsx` — ApiKeysTab 拆分, 移逻辑到 api-keys 子目录
- `apps/studio/frontend/src/api/llm.ts` — `CredentialProviderState` 加 `available_sdks` / `available_models` 字段
- `apps/studio/frontend/src/index.css` (或 `apps/studio/frontend/src/styles/globals.css`) — 加 `.mask-input` rule + `@font-face` text-security-disc

### 新增 (backend)

- `apps/studio/backend/services/llm_provider_meta.py` — Module: 读 `docs/llm-providers/<vendor>.md` 元数据 (parse §1.5 YAML)
- `apps/studio/backend/tests/services/test_llm_provider_meta.py` — 单元测试

### 修改 (backend)

- `apps/studio/backend/services/llm_credentials.py` — `CredentialProviderState` 加 `available_sdks: list[str]` + `available_models: list[str]` 字段
- `apps/studio/backend/services/llm_provider_test.py` — Test handler 重构 (按 vendor 元数据组装 SDK 探测 + `GET /models`)
- `apps/studio/backend/models/llm_config.py` — Response shape 加新字段
- `apps/studio/backend/routers/llm.py` — endpoint 响应序列化新字段
- `apps/studio/backend/tests/services/test_llm_provider_test.py` — 集成测试改造

### 新增 (docs)

- `docs/llm-providers/deepseek.md` (新)
- `docs/llm-providers/ark.md` (新, 字节火山方舟)
- `docs/llm-providers/openrouter.md` (新, 第三方聚合)
- `docs/llm-providers/wavespeed.md` (新, 第三方)
- `docs/llm-providers/qiniu.md` (新, 第三方, 待 a2 确认是 LLM 服务)

### 修改 (docs)

- `docs/llm-providers/_template.md` — 加 §1.5 探测元数据章节
- `docs/llm-providers/anthropic.md` — 补 §1.5
- `docs/llm-providers/openai.md` — 补 §1.5
- `docs/llm-providers/gemini.md` — 补 §1.5

### 不动 (按 spec §9 修改范围精准)

- `apps/studio/frontend/src/components/studio/SettingsPage.tsx` 的 General tab / LLM Roles tab
- Backend `ProviderType` enum 4 个值 (复用)
- PR #74 加的 password-manager 抑制属性 (`data-1p-ignore` 等)
- `docs/llm-providers/{anthropic,openai,gemini}.md` 的 §1-§4 + §6-§8 章节 (只加 §1.5, 其他不动)

---

# PR-A: docs/llm-providers/ — 5 vendor 新 doc + 3 老 doc 补元数据

**Owner**: a2 (Gemini, 主笔; 中英文 doc 处理强项)
**Blocking**: 无
**Total tasks**: 9

---

### Task A0: `docs/llm-providers/_template.md` 加 §1.5 探测元数据章节

**Files**:
- Modify: `docs/llm-providers/_template.md`

**Scope**:
在 §1.4 之后 (§2 之前) 插入 §1.5 章节, 格式:

```markdown
## §1.5 探测元数据 (round 3 新增, 用于 Studio 自动 Test 探测)

```yaml
compatible_sdks:
  # 该 vendor 的 API 兼容哪些 SDK enum
  # 已有 enum: anthropic_compatible / openai_compatible / gemini_official / wavespeed_any_llm
  - <sdk_enum>

models_endpoint_path: "<path>" | null
  # GET <base_url><path> 返回 models 列表 (e.g., OpenAI: "/v1/models")
  # null = 该 vendor 没有 models endpoint, Studio 走 §4 Notable Model IDs fallback (e.g., Anthropic)

auth_header_format: |
  Header1: <template>
  Header2: <template>
  # 含 ${key} 占位符, Studio Test handler 用 user 填的 key 填入
  # 例: OpenAI "Authorization: Bearer ${key}"
  # 例: Anthropic "x-api-key: ${key}\nanthropic-version: 2023-06-01"
```
```

**Acceptance**:
- §1.5 章节存在, 在 §1.4 之后 §2 之前
- 3 个字段 (`compatible_sdks`, `models_endpoke_path`, `auth_header_format`) 全有, 含 YAML 注释解释取值

**Commit**:
```
docs(llm-providers): add §1.5 detection metadata section to _template

For round 3 Studio Test 多 SDK 自动探测: 每 vendor doc 补 §1.5 含
compatible_sdks / models_endpoint_path / auth_header_format 3 字段, backend
读元数据组装 1-token verify + GET /models 调用。

参考 .kiro/specs/studio-api-keys-redesign/round3-design.md §8.1。
```

---

### Task A1: `docs/llm-providers/anthropic.md` 补 §1.5

**Files**:
- Modify: `docs/llm-providers/anthropic.md`

**Scope**:
在 anthropic.md 的 §1.4 之后插入 §1.5, 内容:

```yaml
compatible_sdks:
  - anthropic_compatible

models_endpoint_path: null
  # Anthropic 官方 API 没有 GET /models endpoint
  # Studio 走 §4 Notable Model IDs fallback

auth_header_format: |
  x-api-key: ${key}
  anthropic-version: 2023-06-01
```

**Acceptance**:
- §1.5 章节存在
- `models_endpoint_path: null` (Anthropic 没 endpoint)
- `auth_header_format` 含 x-api-key + anthropic-version 两行

**Commit**:
```
docs(llm-providers): add §1.5 metadata to anthropic.md

models_endpoint_path 为 null, 走 §4 fallback。
```

---

### Task A2: `docs/llm-providers/openai.md` 补 §1.5

**Files**:
- Modify: `docs/llm-providers/openai.md`

**Scope**:
```yaml
compatible_sdks:
  - openai_compatible

models_endpoint_path: "/v1/models"

auth_header_format: |
  Authorization: Bearer ${key}
```

**Acceptance**: §1.5 存在, 3 字段全, `models_endpoint_path` 是 `/v1/models`

**Commit**:
```
docs(llm-providers): add §1.5 metadata to openai.md
```

---

### Task A3: `docs/llm-providers/gemini.md` 补 §1.5

**Files**:
- Modify: `docs/llm-providers/gemini.md`

**Scope**:
a2 read Gemini 官方 doc 后 verify 这些值 (Gemini 官方 API endpoint 跟 OpenAI Compatible 不同):

```yaml
compatible_sdks:
  - gemini_official
  # 注意: Gemini 官方 API 协议只支持 gemini_official SDK, 不兼容 openai_compatible
  # User 原话 2026-05-19 Turn 3: "Gemini 官方的 API 只能用 Gemini sdk"

models_endpoint_path: "/v1beta/models"  # 待 a2 read 官方 doc 确认精确路径

auth_header_format: |
  x-goog-api-key: ${key}  # 待 a2 read 官方 doc 确认
```

**Acceptance**:
- §1.5 存在, 3 字段全
- `compatible_sdks` **只**含 `gemini_official` (不许包含 openai_compatible, 跟 user 原话一致)
- `models_endpoint_path` + `auth_header_format` 实际值 a2 自己 verify 准 (查 Google AI SDK 官方 doc)

**Commit**:
```
docs(llm-providers): add §1.5 metadata to gemini.md

Gemini 官方 API 只支持 gemini_official SDK (user 原话 2026-05-19)。
```

---

### Task A4: `docs/llm-providers/deepseek.md` 新建

**Files**:
- Create: `docs/llm-providers/deepseek.md`

**Scope**:
按 `_template.md` 8 章节模板 (含 §1.5) 全写, 数据 a2 从 https://api-docs.deepseek.com/ 扒。重点字段:

- §1.1-§1.4: Supported SDKs (DeepSeek 兼容 OpenAI API 协议), auth (Bearer), base URL (`https://api.deepseek.com`), notable model IDs (deepseek-chat / deepseek-reasoner / deepseek-coder)
- §1.5:
  ```yaml
  compatible_sdks:
    - openai_compatible

  models_endpoint_path: "/v1/models"  # 待 a2 verify

  auth_header_format: |
    Authorization: Bearer ${key}
  ```
- §5 能力维度: max_context_tokens / max_output_tokens (从官方 doc 抄, 不 runtime 测)
- §6 Known Quirks: deepseek-reasoner 有 reasoning_content 字段; max_tokens 默认值差异等
- §7 Testing (cURL): 一份 minimal 测试请求
- §8 Error Code Reference

**Acceptance**:
- 文件存在, 8 章节齐, 含 §1.5
- 数据从官方 doc 抄, 不编造
- `compatible_sdks` 是 `[openai_compatible]`
- max_context_tokens / max_output_tokens 数字 a2 标 source (引用官方 doc URL)

**Commit**:
```
docs(llm-providers): add deepseek.md (DeepSeek-V3.x / deepseek-reasoner)

source: https://api-docs.deepseek.com/
- §1.5 元数据: openai_compatible, /v1/models, Bearer auth
- §5 max_context_tokens / max_output_tokens 从官方 doc 抄
- §6 quirks: reasoning_content 字段差异
```

---

### Task A5: `docs/llm-providers/ark.md` 新建 (字节火山引擎方舟)

**Files**:
- Create: `docs/llm-providers/ark.md`

**Scope**:
按模板写, 数据从 https://www.volcengine.com/docs/82379 扒。重点:

- §1.1: Ark 兼容多协议 (OpenAI Compatible + Ark 自己的 API)
- §1.4: 旗舰模型 doubao-pro-32k / doubao-pro-128k / doubao-1.5-pro 等
- §1.5:
  ```yaml
  compatible_sdks:
    - openai_compatible
    # Ark 也有官方 SDK (volcengine-python-sdk), 但 round 3 不引入, 走 OpenAI Compatible 路径
    # 如果后续要支持原生 SDK, 加新 enum (e.g., ark_official) 然后这里追加

  models_endpoint_path: "/api/v3/models"  # 待 a2 verify

  auth_header_format: |
    Authorization: Bearer ${key}
  ```
- §5: 各 model max_context_tokens (32K / 128K) + max_output_tokens
- §7 cURL: ark endpoint base URL `https://ark.cn-beijing.volces.com/api/v3/`

**Acceptance**:
- 8 章节齐
- 中文 doc 翻译/整理准确, model ID 跟官方一致
- §1.5 `compatible_sdks: [openai_compatible]`
- base URL 含 region (cn-beijing) 子域名

**Commit**:
```
docs(llm-providers): add ark.md (字节火山方舟)

source: https://www.volcengine.com/docs/82379
- §1.5 元数据: openai_compatible (Ark 兼容 OpenAI API 协议)
- §5 doubao-pro-32k / doubao-pro-128k 模型规格
- 注: round 3 不引入 ark_official SDK, 走 openai_compatible
```

---

### Task A6: `docs/llm-providers/openrouter.md` 新建 (第三方聚合)

**Files**:
- Create: `docs/llm-providers/openrouter.md`

**Scope**:
按模板写, 数据从 https://openrouter.ai/docs 扒。重点:

- §1.1: OpenRouter 聚合多模型供应商, 协议 OpenAI Compatible
- §1.4: Notable models (路由式标识 `anthropic/claude-opus-4-7` / `openai/gpt-5` / `meta-llama/llama-4-405b` 等), 强调 OpenRouter 模型 ID 是 `<vendor>/<model>` 格式不是 vendor 原生 model ID
- §1.5:
  ```yaml
  compatible_sdks:
    - openai_compatible

  models_endpoint_path: "/api/v1/models"  # 待 a2 verify

  auth_header_format: |
    Authorization: Bearer ${key}
    HTTP-Referer: https://your-site.com  # optional but recommended
    X-Title: Your Site Name  # optional
  ```
- §5: 不写死 max_context / max_output (OpenRouter 聚合, 不同 model 不同, 让 user 看 model 详情)
- §6 quirks: 模型 ID 格式 / fallback model 机制 / referer header
- §7 cURL: base URL `https://openrouter.ai/api/v1/`

**Acceptance**:
- 8 章节齐, 强调 OpenRouter 是聚合器不是模型厂商
- §1.5 `models_endpoint_path: "/api/v1/models"` (注意 `/api/v1` 前缀)
- 模型 ID 格式说明清楚 `<vendor>/<model>`

**Commit**:
```
docs(llm-providers): add openrouter.md (第三方聚合)

source: https://openrouter.ai/docs
- §1.5 元数据: openai_compatible, /api/v1/models endpoint
- §6 quirks: 模型 ID 是 <vendor>/<model> 格式, fallback model 机制
```

---

### Task A7: `docs/llm-providers/wavespeed.md` 新建 (第三方)

**Files**:
- Create: `docs/llm-providers/wavespeed.md`

**Scope**:
WaveSpeed 是 backend `ProviderType` enum 里现有的 `wavespeed_any_llm` 对应 vendor。a2 先 read 现有 backend 代码 grep `wavespeed`:

```bash
grep -rn "wavespeed" apps/studio/backend/
```

找到 wavespeed 的 base URL + auth 方式, 加上 https://wavespeed.ai 官方 doc verify。重点:

- §1.5:
  ```yaml
  compatible_sdks:
    - wavespeed_any_llm

  models_endpoint_path: "<待 a2 verify>" | null

  auth_header_format: |
    <待 a2 verify, 大概率是 Authorization: Bearer ${key}>
  ```

**Acceptance**:
- 8 章节齐
- §1.5 `compatible_sdks` 包含 `wavespeed_any_llm` (跟现有 backend enum 一致)
- 实际 base URL / auth header / models endpoint 从现有 backend 代码 + 官方 doc 双重 verify

**Commit**:
```
docs(llm-providers): add wavespeed.md (第三方)

source: https://wavespeed.ai docs + apps/studio/backend grep "wavespeed"
- §1.5 元数据: wavespeed_any_llm SDK (backend 现有 enum)
```

---

### Task A8: `docs/llm-providers/qiniu.md` 新建 (第三方, 七牛)

**Files**:
- Create: `docs/llm-providers/qiniu.md`

**Scope**:
**Step 1 (verify 阶段)**: a2 先 WebFetch https://www.qiniu.com/ 确认这是 LLM 服务 (七牛传统印象是 CDN/对象存储, user 原话提及但未明示 LLM 子产品)。如果不是 LLM 服务 — **暂停, reply 给 master 让 user clarify**, 不强行写一份 fake doc。

**Step 2 (verify 通过)**: 按模板写。重点字段从七牛 LLM 子产品官方 doc 扒:

- §1.5:
  ```yaml
  compatible_sdks:
    - openai_compatible  # 大概率, 待 a2 verify

  models_endpoint_path: "<待 verify>"

  auth_header_format: |
    <待 verify>
  ```

**Acceptance**:
- 如果七牛是 LLM 服务: 8 章节齐, §1.5 全
- 如果不是 LLM 服务: 此任务挂起, master 收 a2 reply 后呈 user 决定 (从 list 移除 / 等找到正确 vendor)

**Commit (verify 通过)**:
```
docs(llm-providers): add qiniu.md (七牛 LLM 服务)

source: <待 a2 verify URL>
- §1.5 元数据: openai_compatible (待 verify)
```

---

# PR-B: backend (a1 主力)

**Owner**: a1 (Codex)
**Blocking**: PR-A merge 完
**Total tasks**: 6

依赖: 读取 `docs/llm-providers/<vendor>.md` 的 §1.5 YAML 元数据需要 PR-A 已 land。

---

### Task B1: `apps/studio/backend/services/llm_provider_meta.py` 新增 module + 单元测试

**Files**:
- Create: `apps/studio/backend/services/llm_provider_meta.py`
- Create: `apps/studio/backend/tests/services/test_llm_provider_meta.py`

**Scope**:

Module `llm_provider_meta.py` 提供 `ProviderMetaLoader` 类 + `load_provider_meta(vendor: str) -> ProviderMeta` 函数:

```python
from pathlib import Path
import re
from dataclasses import dataclass
import yaml

@dataclass
class ProviderMeta:
    vendor: str
    compatible_sdks: list[str]
    models_endpoint_path: str | None
    auth_header_format: str

DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "llm-providers"  # repo root docs/

def load_provider_meta(vendor: str) -> ProviderMeta:
    """Parse §1.5 YAML block from docs/llm-providers/<vendor>.md.
    
    Raises FileNotFoundError if doc 不存在; ValueError 如果 §1.5 章节缺失或 YAML 解析失败.
    """
    doc_path = DOCS_DIR / f"{vendor}.md"
    if not doc_path.exists():
        raise FileNotFoundError(f"Provider doc not found: {doc_path}")
    content = doc_path.read_text(encoding="utf-8")
    yaml_block = _extract_section_15_yaml(content)
    data = yaml.safe_load(yaml_block)
    return ProviderMeta(
        vendor=vendor,
        compatible_sdks=data["compatible_sdks"],
        models_endpoint_path=data["models_endpoint_path"],
        auth_header_format=data["auth_header_format"],
    )

def _extract_section_15_yaml(md_content: str) -> str:
    """Match §1.5 section's first ```yaml ... ``` fenced block.
    
    Returns the YAML body (no fence markers).
    """
    # Match "## §1.5" heading, then capture first ```yaml fenced block
    pattern = re.compile(
        r"^##\s+§1\.5.*?^```yaml\n(.*?)\n```",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(md_content)
    if not match:
        raise ValueError("§1.5 metadata section not found or YAML block missing")
    return match.group(1)
```

测试 (`test_llm_provider_meta.py`):

```python
import pytest
from apps.studio.backend.services.llm_provider_meta import load_provider_meta, ProviderMeta

def test_load_anthropic_meta():
    meta = load_provider_meta("anthropic")
    assert meta.vendor == "anthropic"
    assert meta.compatible_sdks == ["anthropic_compatible"]
    assert meta.models_endpoint_path is None
    assert "x-api-key" in meta.auth_header_format
    assert "anthropic-version" in meta.auth_header_format

def test_load_openai_meta():
    meta = load_provider_meta("openai")
    assert meta.compatible_sdks == ["openai_compatible"]
    assert meta.models_endpoint_path == "/v1/models"
    assert "Bearer" in meta.auth_header_format

def test_load_gemini_meta():
    meta = load_provider_meta("gemini")
    assert meta.compatible_sdks == ["gemini_official"]
    # 不许包含 openai_compatible (user 原话)
    assert "openai_compatible" not in meta.compatible_sdks

def test_missing_vendor_raises():
    with pytest.raises(FileNotFoundError):
        load_provider_meta("nonexistent")

def test_missing_section_raises(tmp_path, monkeypatch):
    fake_doc = tmp_path / "fake.md"
    fake_doc.write_text("# Just a heading, no §1.5\n", encoding="utf-8")
    # ... monkeypatch DOCS_DIR to tmp_path, test ValueError
```

**Acceptance**:
- `pytest apps/studio/backend/tests/services/test_llm_provider_meta.py -v` 全过
- `load_provider_meta("anthropic" | "openai" | "gemini")` 返回正确 `ProviderMeta`
- 缺 doc 或缺 §1.5 节抛对应异常
- Gemini meta 的 `compatible_sdks` 严格只含 `gemini_official` (这是 user 原话契约)

**Commit**:
```
feat(studio-backend): add llm_provider_meta module for round 3 detection

- ProviderMeta dataclass with 4 fields (vendor / compatible_sdks /
  models_endpoint_path / auth_header_format)
- load_provider_meta() parses §1.5 YAML block from docs/llm-providers/<vendor>.md
- 单元测试 cover anthropic / openai / gemini + 缺失场景
```

---

### Task B2: `CredentialProviderState` schema 加 `available_sdks` + `available_models` 字段

**Files**:
- Modify: `apps/studio/backend/models/llm_config.py` (Pydantic model 加字段)
- Modify: `apps/studio/backend/services/llm_credentials.py` (serialize 加字段)
- Modify: `apps/studio/backend/tests/services/test_llm_credentials.py` (assertion 加字段)

**Scope**:

`CredentialProviderState` Pydantic model 加 2 字段:

```python
class CredentialProviderState(BaseModel):
    # ... existing fields (provider_code, api_key, base_url, name, provider_type) ...
    
    available_sdks: list[str] = Field(default_factory=list)
    """实际测过通的 SDK 列表 (round 3 字段)。Test 按钮按 vendor 元数据探测后写入。
    空列表 = 未测过 (跟 round 2 一致, 不 reset draft)。"""
    
    available_models: list[str] = Field(default_factory=list)
    """实际可调用的 model ID 列表 (round 3 字段)。"""
```

PUT empty-`api_key`-preserves-old semantics (round 2 已实现) 必须**也保留** `available_sdks` / `available_models` 的旧值, 不 reset。

测试加:

```python
def test_credential_state_has_available_sdks():
    state = CredentialProviderState(provider_code="openai", api_key="sk-...", ...)
    assert state.available_sdks == []
    assert state.available_models == []

def test_put_empty_api_key_preserves_available_sdks():
    # ... 创建 provider with available_sdks=["openai_compatible"] ...
    # ... PUT 一次 api_key="" ...
    # ... assert available_sdks still ["openai_compatible"] ...
```

**Acceptance**:
- `pytest apps/studio/backend/tests/ -v` 全过
- 现有 PUT empty-api_key-preserves-old 测试仍过, 且新字段也 preserve
- response shape JSON 含 `available_sdks: []` + `available_models: []` (新 provider 默认空)

**Commit**:
```
feat(studio-backend): add available_sdks / available_models to provider state

- Pydantic model 加 2 字段 (default factory list)
- serialize_for_response 输出新字段
- PUT empty-api_key 语义保留新字段旧值 (不 reset)
```

---

### Task B3: Test handler — SDK 探测 (1-token verify, 按元数据组装)

**Files**:
- Modify: `apps/studio/backend/services/llm_provider_test.py` (新增 `probe_compatible_sdks` 函数)
- Modify: `apps/studio/backend/tests/services/test_llm_provider_test.py`

**Scope**:

新增 `async def probe_compatible_sdks(vendor: str, api_key: str, base_url: str) -> list[str]`:

```python
async def probe_compatible_sdks(vendor: str, api_key: str, base_url: str) -> list[str]:
    """对 vendor 的 compatible_sdks 集合各发 1-token request, 返回实际通的 SDK list.
    
    判定规则 (spec §0 Q2):
    - 200 → 加入
    - 401 / 403 → 鉴权不通, 不加入
    - 400 / 422 → 鉴权层通, 业务 reject, 加入 (我们只验证鉴权)
    - 5xx → 标 unknown, 不加入 (不抛异常但 log)
    """
    meta = load_provider_meta(vendor)
    available = []
    for sdk in meta.compatible_sdks:
        try:
            status = await _send_1_token_request(sdk, api_key, base_url, meta.auth_header_format)
            if status in (200, 400, 422):
                available.append(sdk)
            elif status in (401, 403):
                pass  # 不加入
            else:
                logger.warning("SDK probe vendor=%s sdk=%s unexpected status=%s", vendor, sdk, status)
        except Exception as e:
            logger.warning("SDK probe vendor=%s sdk=%s failed: %s", vendor, sdk, e)
    return available

async def _send_1_token_request(sdk: str, api_key: str, base_url: str, auth_header_template: str) -> int:
    """按 SDK enum 派发到对应实现, 发 max_tokens=1 minimal request, 返 HTTP status code."""
    headers = _render_auth_headers(auth_header_template, api_key)
    if sdk == "openai_compatible":
        return await _probe_openai_1token(base_url, headers)
    elif sdk == "anthropic_compatible":
        return await _probe_anthropic_1token(base_url, headers)
    elif sdk == "gemini_official":
        return await _probe_gemini_1token(base_url, headers)
    elif sdk == "wavespeed_any_llm":
        return await _probe_wavespeed_1token(base_url, headers)
    raise ValueError(f"Unknown SDK enum: {sdk}")
```

测试 (mock httpx response):

```python
@pytest.mark.parametrize("status,expected_in", [
    (200, True),
    (400, True),
    (422, True),
    (401, False),
    (403, False),
    (500, False),
])
async def test_probe_openai_status_to_inclusion(status, expected_in, monkeypatch):
    # mock _send_1_token_request 返回 given status
    # call probe_compatible_sdks("openai", "test-key", "https://api.openai.com")
    # assert "openai_compatible" in result == expected_in
```

**Acceptance**:
- `pytest -k probe_compatible_sdks -v` 全过 (含 6 个 parametrize status 组合)
- 200/400/422 → 加入; 401/403/5xx → 不加入
- 函数 async, 不 block event loop

**Commit**:
```
feat(studio-backend): add probe_compatible_sdks for round 3 multi-SDK detection

按 vendor 元数据 (compatible_sdks list) 各发 1-token 请求,
返回实际通的 SDK 集合。判定规则 spec §0 Q2:
- 200/400/422 = available (鉴权通)
- 401/403 = not available (鉴权不通)
- 5xx = unknown (log warning, 不加入)
```

---

### Task B4: Test handler — 模型探测 (`GET /models` 或 doc fallback)

**Files**:
- Modify: `apps/studio/backend/services/llm_provider_test.py` (新增 `probe_available_models`)
- Modify: `apps/studio/backend/tests/services/test_llm_provider_test.py`

**Scope**:

```python
async def probe_available_models(vendor: str, api_key: str, base_url: str) -> list[str]:
    """读 vendor 元数据 models_endpoint_path:
    - 非 null: GET <base_url><path>, parse 返回的 models list, 返回 model ID 数组
    - null: 走 doc fallback, 读 §4 Notable Model IDs 章节, 返回数组
    """
    meta = load_provider_meta(vendor)
    if meta.models_endpoint_path is None:
        return _load_fallback_models_from_doc(vendor)
    headers = _render_auth_headers(meta.auth_header_format, api_key)
    url = f"{base_url.rstrip('/')}{meta.models_endpoint_path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=15.0)
        resp.raise_for_status()
    return _parse_models_response(resp.json(), vendor)

def _load_fallback_models_from_doc(vendor: str) -> list[str]:
    """读 docs/llm-providers/<vendor>.md §4 Notable Model IDs 章节,
    抽取所有 ``code blocks`` 里的 model ID 字符串。"""
    doc_path = DOCS_DIR / f"{vendor}.md"
    content = doc_path.read_text(encoding="utf-8")
    section = _extract_section(content, "§4")
    return _extract_model_ids_from_section(section)

def _parse_models_response(json_resp: dict, vendor: str) -> list[str]:
    """各 vendor /models response 格式可能不同, 统一抽 model id list."""
    # OpenAI / OpenRouter / DeepSeek 等 OpenAI Compatible: {"data": [{"id": "..."}]}
    if "data" in json_resp and isinstance(json_resp["data"], list):
        return [m["id"] for m in json_resp["data"] if "id" in m]
    # Gemini /v1beta/models: {"models": [{"name": "models/..."}]}
    if "models" in json_resp and isinstance(json_resp["models"], list):
        return [m["name"].replace("models/", "") for m in json_resp["models"] if "name" in m]
    return []
```

测试:
- mock httpx 返回 OpenAI 格式 `{"data": [{"id": "gpt-4"}, {"id": "gpt-5"}]}` → parse 出 `["gpt-4", "gpt-5"]`
- mock 返回 Gemini 格式 → parse 出 model id list (去 `models/` 前缀)
- vendor = "anthropic" (`models_endpoint_path: null`) → 走 doc fallback, 测 fallback 函数读 §4 章节正确抽 model ID

**Acceptance**:
- `pytest -k probe_available_models -v` 全过
- OpenAI 格式 + Gemini 格式 + Anthropic doc fallback 三种 case 都过
- Network error / 401 raise HTTPStatusError (上层 catch 标 unknown)

**Commit**:
```
feat(studio-backend): add probe_available_models with doc fallback

- models_endpoint_path 非 null: GET 调用并 parse OpenAI/Gemini 格式
- models_endpoint_path null (Anthropic): 走 docs/llm-providers/<vendor>.md
  §4 Notable Model IDs fallback
```

---

### Task B5: Test handler — 整合 (probe SDKs + models, 写入 state)

**Files**:
- Modify: `apps/studio/backend/services/llm_provider_test.py` (改造现有 `test_provider` handler)
- Modify: `apps/studio/backend/routers/llm.py` (endpoint 响应)

**Scope**:

现有 `test_provider` handler 重构:

```python
async def test_provider(provider_code: str, request: ProviderTestRequest) -> ProviderTestResponse:
    state = await load_credential_state(provider_code)
    vendor = _infer_vendor_from_provider_code(state)  # e.g., "anthropic" / "openai" / "openrouter"
    
    # round 3 多 SDK 探测 + 模型探测
    available_sdks = await probe_compatible_sdks(vendor, state.api_key, state.base_url)
    available_models = []
    if available_sdks:  # 至少一个 SDK 通才探测模型 (省 API call)
        try:
            available_models = await probe_available_models(vendor, state.api_key, state.base_url)
        except Exception as e:
            logger.warning("Model probe failed for %s: %s", provider_code, e)
    
    # 写入 state 持久化
    state.available_sdks = available_sdks
    state.available_models = available_models
    await save_credential_state(state)
    
    return ProviderTestResponse(
        status="ok" if available_sdks else "error",
        available_sdks=available_sdks,
        available_models=available_models,
        latency_ms=...,
    )
```

`ProviderTestResponse` 加 2 字段 (跟 `CredentialProviderState` 同名)。

测试: integration test 用 mock vendor server (httpx_mock fixture), 测整个流程返回 `available_sdks` + `available_models` 正确。

**Acceptance**:
- `pytest apps/studio/backend/tests/ -v` 全过 (含原有 round 2 测试 + 新 round 3 测试)
- Test 按钮调用 endpoint 返回 JSON 含 `available_sdks: [...]` + `available_models: [...]`
- state 持久化新字段 (重新 GET /credentials 后字段还在)

**Commit**:
```
feat(studio-backend): integrate multi-SDK + model probing in test_provider

- test_provider 重构: 先 probe_compatible_sdks 再 probe_available_models
- 持久化 available_sdks / available_models 到 state
- ProviderTestResponse 加 2 字段返回
```

---

### Task B6: PR-B 整体 E2E 冒烟测试

**Files**:
- Modify: `apps/studio/backend/tests/integration/test_llm_e2e.py` (或 create 如果不存在)

**Scope**:
跑一次真实 vendor (build-time skip if no key) 的 e2e:
1. PUT credential (set api_key)
2. POST test endpoint
3. assert response 含非空 `available_sdks` + 非空 `available_models`
4. GET credentials 返回的 state 含同样字段

环境变量 `LLM_E2E_VENDORS_TO_TEST` (CSV) 控制跑哪些 vendor, e.g. `"openai,deepseek"`, 默认空 (CI 跳过)。

测试用 `@pytest.mark.skipif(no env var, reason="e2e skipped without LLM_E2E_VENDORS_TO_TEST")`.

**Acceptance**:
- `LLM_E2E_VENDORS_TO_TEST=openai pytest -k test_llm_e2e -v` 真发 OpenAI request (要 API key 在 env), 通过
- 默认 (无 env) 跳过, CI 不挂

**Commit**:
```
test(studio-backend): add e2e smoke for round 3 multi-SDK detection

可选跑 (LLM_E2E_VENDORS_TO_TEST=openai,deepseek...), 默认跳过。
真发 vendor request 验证完整 probe 流程。
```

---

# PR-C: frontend (a1 主力)

**Owner**: a1 (Codex)
**Blocking**: PR-B merge 完 (依赖 backend 新字段)
**Total tasks**: 12

---

### Task C1: 拆 `ProviderRow.tsx` 出独立文件

**Files**:
- Create: `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx`
- Create: `apps/studio/frontend/src/components/studio/api-keys/index.ts` (barrel export)
- Modify: `apps/studio/frontend/src/components/studio/SettingsPage.tsx` (移除 inline ProviderRow, import from api-keys/)

**Scope**:

把 SettingsPage.tsx 内的 `ProviderRow` 函数组件 (~76 行, line:666-742) 整体搬到独立文件 `api-keys/ProviderRow.tsx`, props 跟现有一致, 不改逻辑。barrel `index.ts` 导出。

**Acceptance**:
- `npm run typecheck` exit 0
- `npm run test` 全过 (含 SettingsPage.test.tsx 现有断言)
- SettingsPage.tsx 行数减少 ~76 行
- ProviderRow 渲染输出跟之前一致 (现有测试 snapshot/RTL assertion 还过)

**Commit**:
```
refactor(studio-frontend): extract ProviderRow to api-keys/ subdir

为 round 3 多组件改造做准备 (拆出后 add eye/AlertDialog/etc)。
本 commit 纯位置搬迁不改逻辑, 现有测试全过。
```

---

### Task C2: `api/llm.ts` 加 `available_sdks` / `available_models` 字段

**Files**:
- Modify: `apps/studio/frontend/src/api/llm.ts`
- Modify: 任何引用 `CredentialProviderState` 的 test fixture

**Scope**:

```typescript
export interface CredentialProviderState {
  provider_code: string;
  api_key: string;
  base_url: string;
  name: string;
  provider_type: ProviderType;
  // round 3:
  available_sdks: string[];
  available_models: string[];
}
```

`putCredentials()` / `testProvider()` 的 response 类型也加字段。

**Acceptance**:
- `npm run typecheck` exit 0
- Test fixture 含 `available_sdks: []` + `available_models: []` (默认空)

**Commit**:
```
feat(studio-frontend): add available_sdks / available_models to type

backend round 3 字段同步。
```

---

### Task C3: `ProviderListSkeleton.tsx` 新组件

**Files**:
- Create: `apps/studio/frontend/src/components/studio/api-keys/ProviderListSkeleton.tsx`

**Scope**:

```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function ProviderListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-md border p-4 space-y-2">
          <Skeleton className="h-4 w-32" /> {/* vendor 名 */}
          <Skeleton className="h-9 w-full" /> {/* API key 行 */}
          <Skeleton className="h-8 w-24" /> {/* 按钮行 */}
        </div>
      ))}
    </div>
  );
}
```

测试: render 3 个 skeleton 块, assert role="status" 或类似无障碍属性 (shadcn Skeleton 提供)。

**Acceptance**:
- 组件渲染 3 行 skeleton, 高度匹配实际 ProviderRow
- shadcn Skeleton 直接 import, 不自创

**Commit**:
```
feat(studio-frontend): add ProviderListSkeleton component

Round 3 loading state for SettingsPage api_keys tab.
```

---

### Task C4: SettingsPage `ApiKeysTab` loading state 接 Skeleton

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/SettingsPage.tsx` (ApiKeysTab function)

**Scope**:

找到 `ApiKeysTab` 现有 loading 判断 (估在 GET /credentials 调用后), 在数据未返回时 render `<ProviderListSkeleton count={3} />`, 替换现有空白态。

**Acceptance**:
- `npm run typecheck` + `npm run test` 全过
- 浏览器 smoke: open Settings → API Keys, network throttle 模拟慢加载, 看到 skeleton 闪现 (人工 verify)

**Commit**:
```
feat(studio-frontend): wire ProviderListSkeleton into ApiKeysTab loading state
```

---

### Task C5: 全局 CSS 加 `.mask-input` rule + Firefox webfont

**Files**:
- Modify: `apps/studio/frontend/src/index.css` (或 `globals.css`)
- Create: `apps/studio/frontend/public/fonts/text-security-disc.woff2` (download + commit binary)
- 引用: a2 reply round 2 推荐 webfont `text-security-disc` (Apache-2.0 open source)

**Scope**:

```css
@font-face {
  font-family: 'text-security-disc';
  src: url('/fonts/text-security-disc.woff2') format('woff2');
  font-display: block;
}

.mask-input {
  -webkit-text-security: disc;
  /* Firefox fallback (-webkit-text-security 不支持) */
  font-family: 'text-security-disc', -apple-system, sans-serif;
}
```

Webfont 下载: https://raw.githubusercontent.com/noppa/text-security/master/dist/text-security-disc.woff2 (or equivalent open source mirror)

**Acceptance**:
- Chrome 测试 (Tauri 环境): masked input 显示 `●●●●●`
- Firefox 测试 (人工 verify): masked input 也显示 `●●●●●` (走 webfont)
- woff2 文件 <5KB
- `npm run build` 输出含 `text-security-disc.woff2` (在 dist/assets/ 或类似)

**Commit**:
```
feat(studio-frontend): add .mask-input CSS rule + Firefox webfont fallback

- @font-face declares text-security-disc (Apache-2.0 open source)
- .mask-input combines -webkit-text-security (Chrome/Tauri) + font fallback (Firefox)
- 契约 A1 (input 永远 type=text), 契约 A2 (mask 不污染 draft.api_key)
```

---

### Task C6: `ProviderRow.tsx` 加 eye toggle + mask 切换

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx`

**Scope**:

```tsx
import { Eye, EyeOff } from "lucide-react";

// inside ProviderRow:
const [visible, setVisible] = useState(false);

// API Key 行渲染:
<div className="flex items-center gap-2">
  <Input
    type="text"  // 契约 A1: 永远不许 password
    value={draft.api_key}  // 契约 A2: 永远是真值
    onChange={(e) => updateDraft({ api_key: e.target.value })}
    className={cn(
      "flex-1",
      !visible && "mask-input",  // 切换 className
    )}
    data-1p-ignore
    data-lpignore="true"
    data-form-type="other"
    name={`provider-secret-${providerCode}`}
  />
  <Button
    size="icon-xs"
    variant="ghost"
    type="button"
    className="transition-none"  // user #2: 去掉 default 动画
    onClick={() => setVisible(v => !v)}
    aria-label={visible ? "Hide API key" : "Show API key"}
  >
    {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
  </Button>
  <Button size="sm" className="px-6" onClick={runTest}>Test</Button>  {/* user #7 px-6 */}
</div>
```

测试 (RTL):

```tsx
test("eye button toggles mask-input className", async () => {
  // render ProviderRow with draft.api_key = "secret"
  const input = screen.getByDisplayValue("secret");
  expect(input).toHaveClass("mask-input");  // 默认 masked
  const eyeBtn = screen.getByLabelText("Show API key");
  await userEvent.click(eyeBtn);
  expect(input).not.toHaveClass("mask-input");
  expect(input).toHaveAttribute("type", "text");  // 永远 text, 不许变 password
});

test("draft.api_key not modified by mask toggle", async () => {
  // ... toggle visible 几次, assert draft.api_key 值不变 ...
});
```

**Acceptance**:
- `npm run test` 通过 (含 2 个新测试)
- 浏览器: 输入 key → 默认显示 `●●●●●` → click eye → 显示明文 → click 又遮挡
- Input `type` 始终是 `text` (DevTools 验证)
- Chrome 不弹 "Save password?" 提示

**Commit**:
```
feat(studio-frontend): add mask + eye toggle to ProviderRow

- input type 永远 text (契约 A1)
- visible state 切 .mask-input className (CSS 控制 display)
- draft.api_key 真值不被污染 (契约 A2)
- eye button 无 hover/active 动画 (user #2 原话)
- 测试 cover 2 条契约
```

---

### Task C7: `ProviderRow.tsx` 启用删除 + 接 AlertDialog

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx`
- 引用: shadcn `AlertDialog` (已在 shadcn registry, 直接 add component)

**Scope**:

如果项目 shadcn 没有 AlertDialog 组件, 跑 `npx shadcn@latest add alert-dialog`。

```tsx
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Trash2 } from "lucide-react";

// inside ProviderRow:
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button size="icon-xs" variant="ghost">
      <Trash2 className="h-4 w-4" />
    </Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>确认删除 {draft.name}?</AlertDialogTitle>
      <AlertDialogDescription>此操作不可恢复。</AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>取消</AlertDialogCancel>
      <AlertDialogAction onClick={() => deleteProvider(providerCode)}>删除</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

`deleteProvider` 实现走现有 backend DELETE endpoint (查 `api/llm.ts` 现有 `deleteCredential` 或加新函数)。

测试:

```tsx
test("delete confirms with AlertDialog", async () => {
  // render ProviderRow
  await userEvent.click(screen.getByLabelText("Delete"));
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  expect(screen.getByText("此操作不可恢复。")).toBeInTheDocument();
  // click 取消 → dialog closes, no DELETE call
  await userEvent.click(screen.getByText("取消"));
  // ... mock DELETE 没被调用 ...
  // 再次 open, click 删除 → DELETE 被调用
});
```

**Acceptance**:
- `npm run test` 通过
- 浏览器: click 删除按钮 → 弹 dialog → 取消 / 确认 行为正确
- 删除成功后 provider 从列表移除

**Commit**:
```
feat(studio-frontend): add AlertDialog confirmation to delete provider

shadcn AlertDialog 防误删 (user #6 原话)。删除按钮启用 (v2.5 解锁),
确认后调用现有 backend DELETE endpoint。
```

---

### Task C8: `TestMessage` Badge variant 改造 + emerald utility

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx` (TestMessage inside or 拆出来)

**Scope**:

按 spec §7.2 映射改 4 个状态对应的 Badge:

```tsx
function TestMessage({ status, latencyMs, error }: { status: TestStatus; latencyMs?: number; error?: string }) {
  if (status === "idle") {
    return <Badge variant="secondary">Untested</Badge>;
  }
  if (status === "testing") {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        Testing...
      </Badge>
    );
  }
  if (status === "ok") {
    return (
      <Badge variant="outline" className="text-emerald-500 border-emerald-500/50 gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Connected{latencyMs ? ` (${latencyMs}ms)` : ""}
      </Badge>
    );
  }
  // status === "error"
  return (
    <Badge variant="destructive" className="gap-1">
      <XCircle className="h-3 w-3" />
      {error ?? "Error"}
    </Badge>
  );
}
```

测试 (4 个状态各 1 个 RTL 测试, assert className contains "emerald" 等):

```tsx
test("Connected badge has emerald color", () => {
  render(<TestMessage status="ok" latencyMs={123} />);
  const badge = screen.getByText(/Connected/);
  expect(badge.closest("[class]")).toHaveClass("text-emerald-500");
});
```

**Acceptance**:
- `npm run test` 通过 (4 状态测试)
- 浏览器: 4 状态 visual 检查 (灰 Untested / 绿 Connected / 红 Error / outline+spinner Testing)
- 不引入新 shadcn variant (维持 baseline)

**Commit**:
```
feat(studio-frontend): apply round 3 Badge variant mapping

- Untested → secondary 灰
- Connected/Tested → outline + text-emerald-500 (utility class, 不引入 custom variant)
- Error → destructive 红
- Testing → outline + spinner
```

---

### Task C9: `OfficialVendorSelect.tsx` 新组件 (5 vendor 下拉)

**Files**:
- Create: `apps/studio/frontend/src/components/studio/api-keys/OfficialVendorSelect.tsx`

**Scope**:

```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const OFFICIAL_VENDORS = [
  { code: "anthropic", label: "Anthropic", baseUrl: "https://api.anthropic.com" },
  { code: "openai", label: "OpenAI", baseUrl: "https://api.openai.com" },
  { code: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com" },
  { code: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com" },
  { code: "ark", label: "Ark (火山方舟)", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
];

interface Props {
  value: string;
  onChange: (vendor: { code: string; label: string; baseUrl: string }) => void;
}

export function OfficialVendorSelect({ value, onChange }: Props) {
  return (
    <Select value={value} onValueChange={(code) => {
      const vendor = OFFICIAL_VENDORS.find(v => v.code === code)!;
      onChange(vendor);
    }}>
      <SelectTrigger><SelectValue placeholder="选择官方厂商..." /></SelectTrigger>
      <SelectContent>
        {OFFICIAL_VENDORS.map(v => (
          <SelectItem key={v.code} value={v.code}>{v.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

注意: base URL 也写在 frontend 常量里, 因为 user 选官方时 name + base URL 自动填 (readOnly), 不绕 backend 查 doc。但**真相** base URL 仍以 `docs/llm-providers/<vendor>.md` 为准, 这里只是 UX 默认值。

**Acceptance**:
- 5 vendor 全列, label 中文 (Ark 标 "火山方舟" 让 user 易识别)
- 选择后 callback 触发, 传入 `{ code, label, baseUrl }`
- shadcn `Select` 直接 import, 不自创

**Commit**:
```
feat(studio-frontend): add OfficialVendorSelect (5 vendor 下拉)

Anthropic / OpenAI / Gemini / DeepSeek / Ark (火山方舟).
base URL 内置默认 (跟 docs/llm-providers/<vendor>.md 元数据一致), 选择后 readOnly 自动填。
```

---

### Task C10: `AddProviderForm.tsx` 新组件 (单入口 + RadioGroup + 条件渲染)

**Files**:
- Create: `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`

**Scope**:

```tsx
import { useState } from "react";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { OfficialVendorSelect } from "./OfficialVendorSelect";

type ProviderType = "official" | "third-party";

interface Props {
  onSubmit: (data: { providerCode: string; name: string; baseUrl: string; apiKey: string; type: ProviderType }) => Promise<void>;
  onCancel: () => void;
}

export function AddProviderForm({ onSubmit, onCancel }: Props) {
  const [type, setType] = useState<ProviderType>("official");
  const [vendor, setVendor] = useState<{ code: string; label: string; baseUrl: string } | null>(null);
  const [customName, setCustomName] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  
  const isOfficial = type === "official";
  const derivedName = isOfficial && vendor ? `${vendor.label}-Official` : customName;
  const derivedBaseUrl = isOfficial && vendor ? vendor.baseUrl : customBaseUrl;
  const derivedProviderCode = isOfficial && vendor ? vendor.code : customName.toLowerCase().replace(/[^a-z0-9]/g, "-");
  
  const canSubmit = apiKey.trim() && (isOfficial ? vendor : (customName && customBaseUrl));
  
  return (
    <div className="rounded-md border p-4 space-y-4">
      <RadioGroup value={type} onValueChange={(v) => setType(v as ProviderType)} className="flex gap-4">
        <div className="flex items-center gap-2">
          <RadioGroupItem value="official" id="type-official" />
          <Label htmlFor="type-official">Official Provider</Label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="third-party" id="type-third-party" />
          <Label htmlFor="type-third-party">Third-party Provider</Label>
        </div>
      </RadioGroup>
      
      {isOfficial ? (
        <>
          <div className="space-y-1">
            <Label>厂商</Label>
            <OfficialVendorSelect value={vendor?.code ?? ""} onChange={setVendor} />
          </div>
          <div className="space-y-1">
            <Label>Provider Name</Label>
            <Input value={derivedName} readOnly />
          </div>
          <div className="space-y-1">
            <Label>Base URL</Label>
            <Input value={derivedBaseUrl} readOnly />
          </div>
        </>
      ) : (
        <>
          <div className="space-y-1">
            <Label>Provider Name</Label>
            <Input value={customName} onChange={(e) => setCustomName(e.target.value)} placeholder="My OpenRouter" />
          </div>
          <div className="space-y-1">
            <Label>Base URL</Label>
            <Input value={customBaseUrl} onChange={(e) => setCustomBaseUrl(e.target.value)} placeholder="https://openrouter.ai/api/v1" />
          </div>
        </>
      )}
      
      <div className="space-y-1">
        <Label>API Key</Label>
        <Input
          type="text"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          className="mask-input"  // 默认 masked
          placeholder="sk-..."
        />
      </div>
      
      <div className="flex gap-2 justify-end">
        <Button variant="ghost" onClick={onCancel}>取消</Button>
        <Button
          disabled={!canSubmit}
          onClick={async () => {
            await onSubmit({
              providerCode: derivedProviderCode,
              name: derivedName,
              baseUrl: derivedBaseUrl,
              apiKey,
              type,
            });
          }}
        >
          添加
        </Button>
      </div>
    </div>
  );
}
```

测试 (RTL):

```tsx
test("official radio shows vendor select", () => {...});
test("third-party radio shows custom name + base URL inputs", () => {...});
test("selecting Anthropic auto-fills name + base URL readOnly", () => {...});
test("submit disabled until apiKey filled", () => {...});
test("submit calls onSubmit with derived values", async () => {...});
```

**Acceptance**:
- `npm run typecheck` + `npm run test` 全过
- 浏览器: click `+ Add Provider` → 展开 form → 选 Official → Select 出现 → 选 Anthropic → name `Anthropic-Official` + base URL 自动填 readOnly → 输入 api key → 添加按钮启用 → click → 调 onSubmit

**Commit**:
```
feat(studio-frontend): add AddProviderForm with RadioGroup + conditional rendering

单入口 inline form (非 Dialog, a2 round 2 §4 推荐):
- RadioGroup 二选一 Official/Third-party
- Official: 显示 OfficialVendorSelect 5 vendor 下拉, name + base URL readOnly 自动填
- Third-party: 显示自由填 name + base URL inputs
- API Key 永远 type=text + .mask-input 默认遮蔽 (契约 A1/A2)
- 表单内置 mask, 跟 ProviderRow 一致
```

---

### Task C11: `ApiKeysTab` 整合 — 用 AddProviderForm 替换 VendorGroup

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/SettingsPage.tsx`

**Scope**:

替换 `ApiKeysTab` 内的 VendorGroup 硬编码 5 vendor 折叠, 改成:

```tsx
function ApiKeysTab() {
  const { credentials, isLoading } = useCredentials();
  const [showAddForm, setShowAddForm] = useState(false);
  
  if (isLoading) {
    return <ProviderListSkeleton count={3} />;
  }
  
  return (
    <div className="space-y-4">
      <h3>API Keys</h3>
      <p className="text-sm text-muted-foreground">Local LLM provider credentials used by Studio runtime. Changes auto-save.</p>
      
      {/* 现有 provider flat 列表 */}
      <div className="space-y-2">
        {credentials.providers.map(p => (
          <ProviderRow
            key={p.provider_code}
            providerCode={p.provider_code}
            draft={...}
            testState={...}
            // ... 现有 props ...
            providerType={inferProviderType(p)}  // "official" | "third-party"
          />
        ))}
      </div>
      
      {/* Add Provider 入口 */}
      {showAddForm ? (
        <AddProviderForm
          onSubmit={async (data) => {
            await putCredentials({ ...data });
            setShowAddForm(false);
          }}
          onCancel={() => setShowAddForm(false)}
        />
      ) : (
        <Button variant="outline" onClick={() => setShowAddForm(true)} className="w-full">
          + Add Provider
        </Button>
      )}
    </div>
  );
}

function inferProviderType(p: CredentialProviderState): "official" | "third-party" {
  const officialCodes = ["anthropic", "openai", "gemini", "deepseek", "ark"];
  return officialCodes.includes(p.provider_code) ? "official" : "third-party";
}
```

ProviderRow 加 `providerType` prop, 在 row header 渲染 `<Badge variant="outline">{providerType === "official" ? "Official" : "Third-party"}</Badge>`.

**Acceptance**:
- `npm run typecheck` + `npm run test` 全过
- 浏览器: 流程跑通 click Add Provider → 选 Official → Anthropic → 填 key → 添加 → 列表新增一行 with "Official" badge

**Commit**:
```
feat(studio-frontend): replace VendorGroup with AddProviderForm flat list

- 删 VendorGroup 5 vendor 硬编码折叠
- 现有 provider 显示在 flat list, 每行带 Official/Third-party Badge
- Add Provider 按钮触发 inline form 展开
- ApiKeysTab loading 接 ProviderListSkeleton
```

---

### Task C12: Available SDKs / Models chip 区 + 集成 PR-B 字段

**Files**:
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderRow.tsx`

**Scope**:

在 ProviderRow 卡片底部加新区, 渲染 `available_sdks` + `available_models`:

```tsx
{(draft.available_sdks?.length > 0 || draft.available_models?.length > 0) && (
  <div className="mt-3 pt-3 border-t space-y-2 text-xs">
    {draft.available_sdks?.length > 0 ? (
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted-foreground">Available SDKs:</span>
        {draft.available_sdks.map(sdk => (
          <Badge key={sdk} variant="secondary" className="font-mono">{sdk}</Badge>
        ))}
      </div>
    ) : (
      <div className="text-muted-foreground">Available SDKs: Untested</div>
    )}
    
    {draft.available_models?.length > 0 ? (
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted-foreground">Available Models:</span>
        {draft.available_models.map(m => (
          <Badge key={m} variant="outline" className="font-mono">{m}</Badge>
        ))}
      </div>
    ) : (
      <div className="text-muted-foreground">Available Models: Untested</div>
    )}
  </div>
)}
```

测试: render with `available_sdks=["openai_compatible"]` + `available_models=["gpt-4", "gpt-5"]`, assert 3 个 Badge 渲染 + 文案。

**Acceptance**:
- `npm run typecheck` + `npm run test` 全过
- 浏览器 e2e: 设置 OpenAI key → click Test → loading → 看到 "Available SDKs: openai_compatible" + "Available Models: gpt-4, gpt-5..." 等

**Commit**:
```
feat(studio-frontend): render available_sdks + available_models chip area

底部新区, 测试后 backend 写入字段直接渲染。
未测时显示 "Untested" placeholder。
```

---

## PR-C End-to-End 验证

**Files**:
- Modify: `apps/studio/frontend/e2e/api-keys.spec.ts` (或 create 如果不存在)

**Scope**:
Playwright e2e 测试:
1. open Settings → API Keys
2. assert 初始空状态 (无 provider) + Add Provider 按钮可见
3. click Add Provider → form 展开
4. 默认 RadioGroup 选 Official, 默认 Vendor Select placeholder "选择官方厂商..."
5. 选 Anthropic → name/base URL readOnly 自动填
6. 输入 api key → 默认 masked (input value 在 DOM 是真值, but visual 是 `●●●`)
7. click eye toggle → unmasked
8. click 添加 → 列表出现 "Anthropic-Official" 行 + "Official" badge
9. click Test → loading (Testing... + spinner) → finished → "Connected (XXXms)" 绿色 badge + Available SDKs/Models chip
10. click 删除 → AlertDialog 弹出 → click 取消 → dialog closes, provider 还在
11. click 删除 → 删除 → 列表移除

**Acceptance**:
- `npx playwright test e2e/api-keys.spec.ts` 全过
- 真发 backend (要 backend 真起 + OpenAI key in env, e2e gate 同 backend B6)

**Commit**:
```
test(studio-frontend): add e2e for API Keys round 3 full flow

10 步覆盖: open page → add Official → mask toggle → Test → delete confirm。
依赖 backend round 3 字段 (PR-B merge 后才能跑)。
```

---

## Self-Review (master Claude PM 跑完前自检)

### 1. Spec coverage scan

| Spec §  | 段标题 | 对应 Task |
|---|---|---|
| §2 (总架构单入口) | 单入口 + RadioGroup + Select 下拉 | C9 + C10 + C11 |
| §3 (Test 行为 + 多 SDK) | 元数据 + 1-token verify + GET /models | A0-A8 (doc) + B1-B5 (backend) + C12 (chip 渲染) |
| §4 (Mask + Eye CSS) | CSS + Firefox webfont + eye toggle | C5 + C6 |
| §5 (Skeleton) | ProviderListSkeleton + loading | C3 + C4 |
| §6 (Delete + AlertDialog) | shadcn AlertDialog | C7 |
| §7 (Button width + Badge) | px-6 + outline + emerald | C6 (px-6) + C8 (Badge) |
| §8 (Docs/llm-providers) | _template + 8 vendor doc | A0-A8 |
| §9 (max_tokens) | 抄官方 doc 不跑 runtime | A4-A8 (含 §5 能力维度表) |
| §10 (PR 拆分) | 3 PR 顺序 | PR-A → PR-B → PR-C 全 cover |
| 契约 A1/A2/A3 (round 3 必守) | input type=text, draft 真值, password manager 抑制保留 | C5 + C6 (CSS mask) + C6 注释保留 PR #74 加的属性 |

**结论**: 9 项 user feedback + spec §2-§10 + 3 条契约全 cover, 无遗漏。

### 2. Placeholder scan

- Task A3 (gemini.md) 有 "待 a2 verify" 占位 (models_endpoint_path + auth_header_format) — **保留**, a2 主笔, master read 官方 doc 时填准
- Task A4-A8 (deepseek/ark/openrouter/wavespeed/qiniu) 有 "<待 a2 verify>" 多处 — **保留**, 同理
- Task A8 (qiniu.md) 有 verify step "如果不是 LLM 服务暂停 escalate" — **保留**, 这是真 gate, 不算 placeholder

无其他 TODO/TBD 残留。

### 3. Type consistency

- `available_sdks: list[str]` (backend Python) / `available_sdks: string[]` (frontend TS) — 一致 ✓
- `available_models` 同上 ✓
- `ProviderMeta` 字段 `compatible_sdks / models_endpoint_path / auth_header_format` 跟 doc §1.5 字段名一致 ✓
- `ProviderTestResponse` 加 2 字段名 = `CredentialProviderState` 加的 2 字段名 ✓

无类型 / 命名不一致。

### 4. PR 依赖一致

PR-A (no blocking) → PR-B (depends on PR-A merge for docs) → PR-C (depends on PR-B merge for backend fields). Task 内 cross-PR 引用一致。

---

## Execution Plan (master Claude PM 推进路径)

按 ccb workflow (非 subagent-driven-development):

1. **PR-A**: master 派 a2 (Gemini) 接 Task A0-A8 (9 tasks). a2 边扒 doc 边写, master 每 task in-loop wait + capture pane verify. PR-A merge 后 master commit + push 到 feature branch + open PR
2. **PR-B**: master 派 a1 (Codex) 接 Task B1-B6 (6 tasks). a1 TDD 全程, a3 (Claude) 跟 a1 review (按 SOP-01 §4 测试分工). PR-B merge 后
3. **PR-C**: master 派 a1 接 Task C1-C12 (12 tasks). 前端组件改造, e2e 用 Playwright 真跑. master 亲眼浏览器 verify (feedback_self_verify_before_report_done memory)

每 PR 内的 task 顺序按本 plan 编号, 不许并行 (TDD discipline + ccb workflow + 主控 in-loop)。
