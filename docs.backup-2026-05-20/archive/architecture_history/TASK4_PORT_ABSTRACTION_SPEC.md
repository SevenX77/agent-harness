# TASK4_PORT_ABSTRACTION_SPEC

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在通过“六边形架构”（Ports & Adapters）对 Studio Backend 的基础设施进行解耦。我们将定义 4 个核心 Port（Storage, Metadata, EventBus, Auth），并提供其 Local 实现。这将消除 `services/*.py` 中对本地文件系统和内存状态的硬编码依赖，为未来平滑迁移至云端（S3 / PostgreSQL / Redis / OIDC）奠定标准接口。

## 2. 现状扫描 (Hardcoded Ops)

### a. `services/skills.py` 硬编码清单
*   **L25**: `config.default_workspace_skills_dir().mkdir(...)` - **FS Write**
*   **L31-35**: `os.iterdir` 通过 `_iter_skill_dirs` 扫描目录 - **FS Read**
*   **L85**: `shutil.copytree(public_dir, workspace_dir)` - **FS Write**
*   **L100**: `candidate_path.replace(target_path)` - **FS Write**
*   **L121**: `runs_dir.glob("*/run_metadata.json")` - **FS Read**
*   **L241**: `tempfile.NamedTemporaryFile` - **FS Write**

### b. `services/run_manager.py` 硬编码清单
*   **L159**: `run_dir.mkdir(parents=True, exist_ok=True)` - **FS Write**
*   **L170**: `_write_json(run_dir / "final_state.json", ...)` - **FS Write**
*   **L219**: `_write_run_metadata(run_dir, metadata)` - **FS Write**

### c. `services/event_bus.py` 现状
*   使用 `asyncio.Queue` 进行内存分发。
*   强绑定 `watchdog` 进行本地文件监听。

### d. Auth 现状
*   全量使用 `config.DEFAULT_USER_ID = "default"`，无鉴权层。

---

## 3. Port 接口最终设计

### 3.1 完整目录结构
```
apps/studio/backend/app/
├── core/
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── storage.py       # 抽象 Blob/文件存储
│   │   ├── metadata.py      # 抽象 元数据存储 (Skills/Runs)
│   │   ├── eventbus.py      # 抽象 事件总线
│   │   └── auth.py          # 抽象 用户鉴权
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── storage_local.py
│   │   ├── metadata_sqlite.py
│   │   ├── eventbus_memory.py
│   │   └── auth_local.py
│   ├── backends.py          # DI 工厂与配置
```

### 3.2 核心 Protocol 定义

#### StorageBackend
```python
class StorageBackend(Protocol):
    async def read_text(self, path: str) -> str: ...
    async def write_text(self, path: str, content: str) -> None: ...
    async def exists(self, path: str) -> bool: ...
    async def list_dirs(self, path: str) -> list[str]: ...
    async def copy_tree(self, src: str, dst: str) -> None: ...
    async def move(self, src: str, dst: str) -> None: ...
    async def delete(self, path: str) -> None: ...
```

#### MetadataStore
```python
class MetadataStore(Protocol):
    async def list_skills(self, user_id: str) -> list[SkillSummary]: ...
    async def save_skill_summary(self, user_id: str, summary: SkillSummary) -> None: ...
    async def list_runs(self, user_id: str, skill_id: str) -> list[RunMetadata]: ...
    async def save_run_metadata(self, user_id: str, skill_id: str, metadata: RunMetadata) -> None: ...
```

#### EventBus
```python
class EventBus(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]: ...
```

#### AuthProvider
```python
class AuthProvider(Protocol):
    async def get_current_user_id(self, request: Request) -> str: ...
```

---

## 4. Local Adapter 实施要点

*   **`LocalFilesystemBackend`**: 使用 `aiofiles` 实现异步文件操作。`base_dir` 从 `BackendConfig` 注入。
*   **`SqliteMetadataStore`**: 初始阶段可先用 **`LocalJsonMetadataStore`** (保持简单)，将 `run_metadata.json` 视为存储对象。
*   **`InMemoryEventBus`**: 包装现有的 `set[asyncio.Queue]` 逻辑。
*   **`NoAuthProvider`**: 始终返回 `"default"`。

### DI 工厂 (`backends.py`)
```python
class BackendConfig(BaseSettings):
    storage_type: str = "local"
    workspaces_root: Path = REPO_ROOT / "workspaces"
    # ... 其他配置

@lru_cache()
def get_storage() -> StorageBackend:
    cfg = BackendConfig()
    return LocalFilesystemBackend(cfg.workspaces_root)

# 其他 get_metadata, get_eventbus, get_auth 类似
```

---

## 5. Wire-in: `services/skills.py` 改造矩阵

我们将 `skills.py` 中的函数转换为 **async**，并注入 Port。

| 现状 (Sync + Path) | 目标 (Async + Port) |
| :--- | :--- |
| `resolve_skill_dir(skill_id)` | `await storage.exists(f"{user_id}/skills/{skill_id}/SKILL.md")` |
| `Path.read_text()` | `await storage.read_text(path)` |
| `shutil.copytree(src, dst)` | `await storage.copy_tree(src, dst)` |
| `latest_run_metadata(skill_id)` | `await metadata.list_runs(user_id, skill_id)` |
| `_iter_skill_dirs(root)` | `await storage.list_dirs(path)` |

**注入示例**:
```python
async def list_skill_summaries(
    user_id: str,
    storage: StorageBackend,
    metadata: MetadataStore
) -> list[SkillSummary]:
    # 逻辑迁移至此
```

---

## 6. 实施 Sub-steps (a1 指南)

### T4.1: 基建搭建 (1.0d)
1.  创建 `app/core/ports/` 目录及 4 个接口文件。
2.  创建 `app/core/adapters/` 目录及 4 个 Local 实现。
3.  编写 `app/core/backends.py` 提供 `Depends` 注入点。
4.  **校验**: `mypy --strict apps/studio/backend/app/core` 必须全绿。

### T4.2: `skills.py` 核心改造 (0.5d)
1.  将 `skills.py` 关键函数（`list_skill_summaries`, `get_skill_detail`, `update_skill_content`）改为 `async`。
2.  在 `routers/skills.py` 中通过 `Depends(get_storage)` 等注入 Port。
3.  **验证**: 运行 `pytest apps/studio/backend/tests`，确保 28 个基础测试通过（可能需要 `pytest-asyncio` 适配）。

### T4.3: `event_bus.py` 与 `run_manager.py` 适配 (0.5d)
1.  将 `EventBus` 类重构为符合 `EventBus` Port 的 Adapter。
2.  `run_manager.py` 中的文件写入改为通过 `StorageBackend`。
3.  **验证**: 启动 Studio 后端，观察 WebSocket 事件是否正常下发。

---

## 7. 风险点与缓解

1.  **Async 传染性**: 修改 service 为 async 会导致 router 也必须 async 且所有调用链增加 `await`。
    *   *缓解*: FastAPI 原生支持 async，这是一次必要的架构升级，a1 需在大规模修改前确认所有 router 调用点。
2.  **Multiprocessing 兼容性**: `run_worker_main` 在子进程运行，无法直接使用主进程的 async Port 实例。
    *   *缓解*: 子进程内部保留简易的 `LocalFilesystemBackend` 实例化，或通过 Queue 将写请求发回主进程。初期维持子进程内简单的 `Path` 操作也可接受，只要接口对齐。
3.  **Path 拼接错误**: 从 `Path / "sub"` 切换到字符串路径 `f"{base}/{sub}"` 易出错。
    *   *缓解*: 在 `StorageBackend` 内部统一处理路径安全校验（防止路径穿越）。

## 8. 工时估算
*   **T4.1**: 8h
*   **T4.2**: 4h
*   **T4.3**: 4h
*   **总计**: 16h (2 dev-days)。

## 9. 验收 Checklist
- [ ] `app/core/ports/` 下 Protocol 定义完整。
- [ ] `app/services/skills.py` 中不再直接 import `os`, `shutil` 或使用 `Path.read_text`。
- [ ] `BackendConfig` 可以通过环境变量切换 Backend 类型。
- [ ] `apps/studio/backend` 所有单元测试通过。
- [ ] Mypy 对 `adapters` 实现 `Protocol` 的校验通过。
