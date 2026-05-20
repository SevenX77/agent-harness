---
status: Living
target_goal: "Studio LLM API Key 的本地持久化形式、安全模型、运行时读取路径, 以及 Studio↔Engine 边界"
linked_code_paths:
  - apps/studio/backend/app/services/llm_credentials.py
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/models/llm_config.py
  - apps/studio/backend/app/services/copilot.py
  - apps/studio/backend/app/services/llm_env.py
  - apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx
  - apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx
  - packages/graph-agent/src/graph_agent/models/llm_client_manager.py
  - packages/graph-agent/src/graph_agent/config/llm_config.py
linked_specs:
  - .kiro/specs/studio-api-keys-redesign/
  - .kiro/specs/_archive/_deprecated_studio-api-keys-v1/
last_updated: 2026-05-20
---

# Studio API Key 存储与运行时 (API Key Storage & Runtime)

本文档描述 Studio 桌面端 LLM 凭据 (API Key) 的本地持久化形式、安全模型, 以及两条互相独立的运行时读取路径 (Copilot vs Graph-agent run), 并标注当前存在的 Studio↔Engine 边界 gap。

`engine` 层 (graph-agent) 自身只关心"从环境变量取 key"这一项契约, 该契约的形式在 [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../engine/LLM_ROUTING_AND_FALLBACK.md) 中已隐含描述; 本文档负责 Studio 这一侧的 storage / UX / runtime 注入的完整故事。

## 1. 持久化文件 (Persistence)

### 1.1 存储位置与 Schema

凭据持久化为单个 JSON 文件:

```
~/.studio/llm_credentials.json
```

Schema 在 `app/models/llm_config.py:LLMCredentialsFile` 定义, 当前为 v3:

```python
class LLMCredentialsFile(BaseModel):
    schema_version: Literal[3] = 3
    providers: list[ProviderCredential] = Field(default_factory=list)
```

`ProviderCredential` 携带 6 个用户可编辑字段 (`id` / `name` / `api_key` / `base_url` / `provider_type`) + 6 个 Test outcome 字段 (`last_test_status` / `last_test_at` / `last_test_message` / `last_error_code` / `available_sdks` / `available_models`)。`id` 是 UUID, 是凭据级唯一标识 — 多条凭据可以共用同一个 `provider_key` (元数据维度), 但 `id` 必须互异。

### 1.2 原子写流程

`app/services/llm_credentials.py:_save_credentials_unlocked` 是底层写入路径, 单一来源:

```python
def _save_credentials_unlocked(data: LLMCredentialsFile, credential_path: Path) -> None:
    payload = data.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    credential_path.parent.mkdir(parents=True, exist_ok=True)
    credential_path.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{credential_path.name}.",
        suffix=".tmp",
        dir=credential_path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(serialized)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.chmod(0o600)
        os.replace(tmp_path, credential_path)
        credential_path.chmod(0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
```

写入流程的关键不变式:

| 项 | 做法 |
|---|---|
| 锁 | 全模块共享 `threading.Lock()`, 与 `_persist_test_outcome` 共用同一把 |
| 原子性 | 同目录 `tempfile.mkstemp` → `fsync` → `os.replace` |
| 父目录权限 | `0o700` (owner-only enter/list) |
| 临时文件权限 | `mkstemp` 默认 `0o600`, replace 前再显式 `chmod 0o600` 双保险 |
| 最终文件权限 | replace 后再 `chmod 0o600`, 防御 inode 历史宽松权限 |
| 加密 | **无**, JSON plaintext 存储 |
| OS keychain | **未集成** (macOS Keychain / Linux libsecret / Windows Credential Manager 均不接入) |

### 1.3 PUT 语义 (整表替换 + 空 key 保留)

`PUT /api/llm/credentials` 是**整表替换**, 不是 incremental upsert:

* Request body 里的 `providers` 列表会原样替换磁盘上的 `providers` 列表 — 凡是 `id` 没出现在 body 里的凭据**会被删除**。
* `api_key` 字段为空串时, 后端会**保留**该 `id` 对应的旧 key (`apps/studio/backend/app/routers/llm.py:184`)。这是给前端的"只编辑 base_url 而不重发 secret"的便利路径, 不是安全脱敏。
* 6 个 Test outcome 字段**不可**经 PUT 写入 (`ProviderCredentialWrite` 使用 `extra="forbid"`)。它们由 POST `/providers/test` / `/providers/test-models` 通过 `_persist_test_outcome` 单写路径回写, 与 PUT 共享同一把锁, 保证 Test 结果不会被并发 PUT 抹掉。

### 1.4 GET 语义 (明文回读)

`GET /api/llm/credentials` 直接返回完整的 `api_key` plaintext, **不做脱敏**。这是 round 2 的设计决策, 详见 [`studio-api-keys-redesign/requirements.md`](../../.kiro/specs/studio-api-keys-redesign/requirements.md) §"理由 (round 2)", 核心论点:

* 本地单用户机器, 文件已 `0600`, 前端可见无额外安全收益
* "脱敏占位" UX 反直觉, 会让用户以为 key 没保存上, 反复触发 Test 失败
* 输入框 `type="text"` plain text + 浏览器密码管理器抑制属性 (`data-1p-ignore` / `data-lpignore` / `data-form-type="other"` / `name="provider-secret-{id}"`)

UI 实现见 `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`。

## 2. 安全模型

### 2.1 防御边界

Studio 的"保密"全部建立在 OS 文件系统权限之上:

| 角色 | 能否读到 plaintext key |
|---|---|
| 同机非 owner 用户 (普通账号) | ❌ — 被 0700 父目录拦截 |
| 同机 root | ✅ — root 可读任何文件 |
| 同 OS 账号下任意其它进程 | ✅ — 与 Studio 同 uid |
| 通过 `GET /api/llm/credentials` 的任何客户端 | ✅ — 后端无鉴权差别, 任何能到达 `127.0.0.1:8787` 的进程都能拿到明文 |
| 磁盘镜像 / 备份 / 误传 git | ✅ — 文件本身是 plaintext, 不依赖任何 master key |

### 2.2 日志脱敏

唯一一处显式脱敏在 `app/routers/llm.py:_log_test_provider`, 只打印 `api_key[-4:]` (last4) 用作排障关联键。Pydantic `model_dump` 没有自定义 redaction, 任何把整个 `ProviderCredential` 序列化进日志的下游代码会泄露 plaintext — 截至 round 3 没有这样的代码。

### 2.3 与业内 IDE 的对比

设计阶段参考的"业内通行模式 (file-based + 0600)" 在 [`_deprecated_studio-api-keys-v1/research.md`](../../.kiro/specs/_archive/_deprecated_studio-api-keys-v1/research.md) §1 有完整对比表。需要更新一处事实: **Cursor 实际不是 `settings.json` + 0600**, 而是 `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (SQLite, plaintext, 默认用户权限, 无 0600 加固)。Studio 实际比 Cursor 在文件权限这一点上**严一档** (强制 0600), 但同样**没有进 OS keychain**, 整体与 Cursor 处于同一安全档位 — 都不及 VS Code GitHub Copilot 的 OS-keychain 方案。

参考: [LayerX "CursorJacking" 披露 (2026-02)](https://layerxsecurity.com/blog/cursorjacking-every-cursor-user-is-vulnerable-to-api-key-theft-by-rogue-extensions/) 详细描述 Cursor 的 SQLite plaintext 存储路径与第三方 extension 读取攻击面 (CVSS 8.2, 截至 2026-04-28 未修)。Studio 没有第三方 extension 模型, 该攻击面不直接存在, 但本机同 uid 进程泄露面与 Cursor 等价。

> 如果未来需要对齐 VS Code Copilot 档位 (OS keychain), 设计阶段已显式标记为 out-of-scope, 见 [`_deprecated_studio-api-keys-v1/requirements.md`](../../.kiro/specs/_archive/_deprecated_studio-api-keys-v1/requirements.md) §7。

## 3. 运行时读取路径

Studio 内有**两条互相独立**的 key 读取路径, 通过不同机制取 key, 互不感知。

### 3.1 路径 A: Copilot (读 credentials → 注入 SDK options)

Copilot 走 `~/.studio/llm_credentials.json` 直读 + `ClaudeAgentOptions.env` 注入, **不修改 `os.environ`**。

入口 `app/services/copilot.py:stream_query`:

```python
api_key, base_url = _resolve_provider_runtime(primary.provider_code, primary.provider_def)
if not api_key:
    yield CopilotEventError(
        message=f"Provider {primary.provider_code} 未配置 API key"
    )
    return
```

`_resolve_provider_runtime` 按 `provider_code` / `name` 三段优先级在 credentials 文件里找匹配:

```python
def _resolve_provider_runtime(
    provider_code: str,
    provider_def: ProviderDef,
) -> tuple[str, str | None]:
    credentials = load_credentials()
    provider = next(
        (
            credential
            for credential in credentials.providers
            if credential.id == provider_code
            or credential.name == provider_def.name
            or credential.name == provider_code
        ),
        None,
    )
    if provider is None:
        return "", provider_def.base_url
    return provider.api_key.strip(), provider.base_url.strip() or provider_def.base_url
```

匹配后由 `build_options` 把 key 与 base_url 拼成 per-session `ClaudeAgentOptions.env`:

```python
def build_options(
    base_url: str | None,
    api_key: str,
    workspace_dir: str | Path,
) -> ClaudeAgentOptions:
    """Build per-session Claude Agent SDK options without mutating os.environ."""
    env = {"ANTHROPIC_API_KEY": api_key}
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url

    return ClaudeAgentOptions(
        cwd=workspace_dir,
        permission_mode="acceptEdits",
        allowed_tools=_ALLOWED_TOOLS.copy(),
        env=env,
    )
```

**关键性质**:
* 进程级 `os.environ` 全程**不变** — env 只活在该 SDK session 内。
* 多个 provider 凭据可同时存在 (按 `provider_code` 选), 切换 model 不需要重启进程。
* `provider_code` 来自 `config/llm_roles.yaml` 的 `providers` 注册表代号 (例如 `OC_CL`), 与 UI 输入的 `provider_id` (UUID) 通过 `name` 字段映射。

### 3.2 路径 B: Graph-agent Run (读 env)

`packages/graph-agent` SDK 在跑 skill 时**只读 `os.environ`**, **完全不感知** `~/.studio/llm_credentials.json`。

`packages/graph-agent/src/graph_agent/models/llm_client_manager.py:562`:

```python
@classmethod
def _resolve_api_key(cls, provider_def: ProviderDef) -> str:
    api_key = os.environ.get(provider_def.api_key_env) if provider_def.api_key_env else None
    if not api_key and provider_def.api_key_env_fallback:
        api_key = os.environ.get(provider_def.api_key_env_fallback)
    if not api_key:
        raise ValueError(f"{provider_def.api_key_env} not configured, set it in .env")
    return api_key
```

`provider_def.api_key_env` 来自 `config/llm_roles.yaml` 的 `providers.<code>.api_key_env` (例如 `OPENAI_API_KEY`)。子进程通过 `apps/studio/backend/app/services/run_manager.py:_run_worker_main` 启动 `graph_agent.run_skill(...)`, 该 worker **不对子进程做任何 env 注入** — 它继承父进程当前的 `os.environ`。

## 4. Studio↔Engine 边界 Gap

由 §3 两条路径可推出当前的事实 gap:

> **Studio API Keys 页面里保存的 key, 在 graph-agent run 时读不到。**

具体表现: 用户在 Settings → API Keys 页保存了 `openai-official` 这一条 `sk-...` 凭据, 该 key 会:

* ✅ 立刻被 Copilot 用上 (路径 A 直读 credentials 文件)
* ❌ **不会**被 graph-agent run 用上 — graph-agent 只查 `OPENAI_API_KEY` 等 env var; 若用户没在 shell 或 `.env` 里独立配置过对应 env, 子进程会直接 raise `OPENAI_API_KEY not configured, set it in .env`

### 4.1 历史曾有过桥, 当前是 no-op

`app/services/llm_env.py` 曾承担"credentials → env"的桥接职责, 当前已经退化为 no-op compatibility shim:

```python
def patch_environment_from_credentials(
    credentials: LLMCredentialsFile,
    *,
    roles_path: Path | None = None,
) -> dict[str, AppliedProviderEnv]:
    """No-op compatibility shim; runtime no longer mutates ``os.environ``."""
    del credentials, roles_path
    return {}
```

production code 没有任何地方调用它, 仅自身测试和 spec doc 引用。

### 4.2 设计文档约束

* Studio 侧持久化 / UX / 安全模型: [`studio-api-keys-redesign`](../../.kiro/specs/studio-api-keys-redesign/) round 3
* Engine 侧 env 契约 (`provider_def.api_key_env` → `os.environ`): [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../engine/LLM_ROUTING_AND_FALLBACK.md)

本 gap 是 Studio 这一侧的 feature gap (Studio 没把 UI 输入的 key 注入子进程 env), 不是 engine 行为缺陷 — engine 始终遵守"`api_key_env` 是单一来源"的契约。修复方案 (恢复 `patch_environment_from_credentials` 实操 / 或在 engine 侧加 credentials fallback) 留待后续 spec 决定。

## 5. 相关文档

* Engine 侧 LLM 路由与降级: [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../engine/LLM_ROUTING_AND_FALLBACK.md)
* Studio 界面布局 (Settings → API Keys 页): [`docs/studio/STUDIO_LAYOUT_SPEC.md`](./STUDIO_LAYOUT_SPEC.md)
* Round 3 spec 总目录: [`.kiro/specs/studio-api-keys-redesign/`](../../.kiro/specs/studio-api-keys-redesign/)
* 历史 round 1 research (业内 IDE 对比起点): [`.kiro/specs/_archive/_deprecated_studio-api-keys-v1/research.md`](../../.kiro/specs/_archive/_deprecated_studio-api-keys-v1/research.md)
