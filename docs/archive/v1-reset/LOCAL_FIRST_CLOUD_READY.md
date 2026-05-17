# Local-First Cloud-Ready 架构演进与接口预留设计 (Local-First Cloud-Ready Architecture)

**日期**: 2026-04-30
**分析者**: 资深云原生架构师 & DDD/六边形架构专家 (a2 Gemini)
**触发条件**: 用户修正优先级，将“云化部署”推迟，转而将“本地编译器与测试完整性”作为首要任务，但要求为云化**预留好未来接口**，避免重构。

---

## 1. Executive Summary

**改动哲学**: "Local First, but Cloud Ready"。我们采用**六边形架构 (Ports & Adapters)**，在核心业务逻辑与外部依赖之间建立硬边界。现在只实现一套轻量级的 Local Adapter 以快速跑通本地测试，但代码中强制使用 Protocol (Port) 调用，为未来随时热插拔 Cloud Adapter 预留插槽。

**总改动估算**: 大约需要 3-4 个 PR，约 5-10 Dev-Day。

**是否会拖慢当前迭代**: **有限的短期成本，巨大的长期收益**。这几天的代码隔离可以彻底避免未来向云迁移时长达数月的“散弹枪式修改”，使得“上云”变成一个纯粹的运维与配置变更。

## 2. 核心改造哲学 (Hexagonal Architecture)

- **为什么选六边形架构**: 传统的层级架构容易导致业务逻辑泄漏到底层实现细节中（如直接 `open()` 文件或使用 `os.listdir()`）。六边形架构通过依赖倒置 (Dependency Inversion)，强迫业务逻辑仅依赖抽象协议 (Protocol)，从而完美隔离基础设施的演进。
- **平衡原则**: "Don't add features beyond requirements"。我们**只定义当前业务真实需要的接口方法**。比如当前没有“增量更新文件”的需求，`StorageBackend` 就只设计全量覆盖的 `write`。
- **反过度设计卫栏**: 不在接口中预设只有云端才有的概念（如不提前把 `boto3.Client` 传进去），只传递单纯的数据与路径 URI。
- **Must Do Now**: 将硬编码路径的 FS 操作与内存队列操作拦截，改为调用 `get_storage()` 等抽象工厂方法。

## 3. 当前代码硬编码点扫描

这些点一旦上云就会被打破，必须立即进行抽象隔离。

| 文件路径 | 现状描述 | 云化时会怎么坏 | 抽象方式 |
|---|---|---|---|
| `studio-backend/app/services/skills.py` | 使用硬编码常量如 `WORKSPACES_DIR` 与 `os`/`pathlib` (如 `root.mkdir()`) 读写。 | 容器内本地盘写入导致多实例间状态不一致与数据丢失。 | 提取为 `StorageBackend` 和 `MetadataStore`。 |
| `studio-backend/app/services/run_manager.py` | L234 `_write_json` 强绑定本地路径，通过 `multiprocessing` 生成子进程并在本地 `asyncio.Queue` 收发事件。 | FastAPI 轻量节点无法承载 Agent 运算，且 OOM；多 Worker 无法读写一致状态。 | 提取 `StorageBackend` 存产物，`EventBus` 接管进程间通信，暂不处理 Celery (当前只需同步)。 |
| `studio-backend/app/services/event_bus.py` | L22 实例化基于单机内存的 `asyncio.Queue`，并使用 `watchdog` 监听本地文件系统。 | K8s Pod A/B 之间无法共享内存 Queue，WS 无法广播。 | 提取 `EventBus` 协议；本地先保持内存，未来换 Redis。 |
| `src/core/graph_agent/core/checkpointer.py` | 强假设单机 `SqliteSaver` 或本地持久化 DB 路径。 | 多实例下 Thread-ID 寻址失败，断点丢失。 | 虽然代码里有 `backend="postgres"` 预留，但仍需上层的统一 Provider 注入抽象。 |
| `studio-backend/app/routers/` 所有路由 | 完全 0 Auth 裸奔，假定 `user_id = "default"`。 | 多租户云环境下导致越权与数据泄露。 | 提取 `AuthProvider` 中间件，目前可返回 mock user。 |
| `config/llm_roles.yaml` & `core.config` | 未抽象 Quota 与 Rate limit 相关配置，模型直连。 | 上云后万级请求会被 Provider 封号限流。 | (加分项) 未来在 Middleware 层注入 Quota 拦截器，目前仅记录使用量不阻断。 |
| `studio-backend/app/services/terminal_manager.py` | (暂缓) 本地 PTY 适用。 | 云端禁用物理 PTY。 | 本地直接保留，上云时直接砍掉此服务路由。 |

## 4. 核心抽象层 - 详细接口设计

我们引入 4 个核心 Port (基于 `typing.Protocol`)。

### 4.1 StorageBackend (存储抽象)

隔离所有 `SKILL.md` 与 `artifacts` 的物理读写。

#### 4.1.1 Protocol 定义
```python
# app/core/ports/storage.py
from typing import Protocol, Any
from collections.abc import AsyncIterator

class StorageBackend(Protocol):
    """Abstract file and blob storage operations."""
    
    async def read_text(self, uri: str) -> str:
        """Read file contents as text."""
        ...
        
    async def write_text(self, uri: str, content: str) -> None:
        """Write text to file, overwriting existing."""
        ...
        
    async def list_dir(self, uri_prefix: str) -> list[str]:
        """List files/directories under a prefix."""
        ...
```

#### 4.1.2 本地实现 (Now)
```python
# app/adapters/storage_local.py
import os
import aiofiles
from pathlib import Path
from app.core.ports.storage import StorageBackend

class LocalFilesystemBackend(StorageBackend):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        
    def _resolve(self, uri: str) -> Path:
        # e.g., s3://workspaces/... -> /local/path/workspaces/...
        # Normalize custom scheme if necessary
        clean_path = uri.replace("s3://", "").replace("file://", "")
        return self.base_dir / clean_path
        
    async def read_text(self, uri: str) -> str:
        path = self._resolve(uri)
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return await f.read()

    async def write_text(self, uri: str, content: str) -> None:
        path = self._resolve(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(content)
            
    async def list_dir(self, uri_prefix: str) -> list[str]:
        path = self._resolve(uri_prefix)
        if not path.exists(): return []
        return [str(p.relative_to(self.base_dir)) for p in path.iterdir()]
```

#### 4.1.3 云端实现 (Future)
```python
# app/adapters/storage_s3.py
from app.core.ports.storage import StorageBackend

class S3Backend(StorageBackend):
    # TODO (Phase 1, Task 1.4): Implement using aiobotocore
    async def read_text(self, uri: str) -> str:
        raise NotImplementedError("S3 backend not yet implemented.")
```

#### 4.1.4 Wire-in
- 修改 `services/skills.py` 和 `services/run_manager.py`，不再直接使用 `Path.write_text()`，而是通过注入的 `StorageBackend` 实例进行操作。所有路径统一规范化为相对标识（如 `workspaces/{user_id}/skills/{skill_id}`）。

### 4.2 MetadataStore (元数据 DB 抽象)

隔离目录遍历与内存字典的硬编码，为关系型数据库铺路。

#### 4.2.1 Protocol 定义
```python
# app/core/ports/metadata.py
from typing import Protocol, Optional
from app.models.skills import SkillSummary
from app.models.runs import RunMetadata

class MetadataStore(Protocol):
    """Abstract query operations for entities."""
    
    async def list_skills(self, user_id: str) -> list[SkillSummary]:
        ...
        
    async def get_skill_summary(self, user_id: str, skill_id: str) -> Optional[SkillSummary]:
        ...
        
    async def save_run_metadata(self, user_id: str, skill_id: str, metadata: RunMetadata) -> None:
        ...
```

#### 4.2.2 本地实现 (Now)
```python
# app/adapters/metadata_sqlite.py
# Uses SQLModel or SQLAlchemy with local sqlite db
from app.core.ports.metadata import MetadataStore

class SqliteMetadataStore(MetadataStore):
    # Initializes an sqlite DB engine, currently sync or async
    pass
```

#### 4.2.3 云端实现 (Future)
```python
# app/adapters/metadata_postgres.py
class PostgresMetadataStore(MetadataStore):
    # TODO (Phase 1, Task 1.2): Implement with asyncpg/SQLAlchemy
    pass
```

#### 4.2.4 Wire-in
- 替换 `services/skills.py` 中的 `_iter_skill_dirs` 和 `services/run_manager.py` 中的字典持久化逻辑。

### 4.3 EventBus (事件流抽象)

将跨协程、跨进程通信解耦，剥离具体的 `asyncio.Queue`。

#### 4.3.1 Protocol 定义
```python
# app/core/ports/eventbus.py
from typing import Protocol, AsyncIterator

class EventBus(Protocol):
    """Pub/Sub abstraction."""
    
    async def publish(self, topic: str, event: dict) -> None:
        ...
        
    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        ...
```

#### 4.3.2 本地实现 (Now)
```python
# app/adapters/eventbus_memory.py
import asyncio
from app.core.ports.eventbus import EventBus

class InMemoryEventBus(EventBus):
    def __init__(self):
        self._queues = {}
        
    async def publish(self, topic: str, event: dict) -> None:
        if topic in self._queues:
            for q in self._queues[topic]:
                await q.put(event)
                
    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        q = asyncio.Queue()
        self._queues.setdefault(topic, set()).add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues[topic].remove(q)
```

#### 4.3.3 云端实现 (Future)
```python
# app/adapters/eventbus_redis.py
class RedisEventBus(EventBus):
    # TODO (Phase 2, Task 2.4): Implement with redis-py Pub/Sub
    pass
```

#### 4.3.4 Wire-in
- 改造 `services/event_bus.py`，不再暴露底层的 Queue 对象。路由层 (`websockets.py`) 统一调用 `EventBus.subscribe()` 处理推送。

### 4.4 AuthProvider (鉴权抽象)

解决单租户硬编码，规范化 User 身份提取。

#### 4.4.1 Protocol 定义
```python
# app/core/ports/auth.py
from typing import Protocol
from fastapi import Request

class AuthProvider(Protocol):
    """Extract authenticated user identity."""
    
    async def get_current_user_id(self, request: Request) -> str:
        ...
```

#### 4.4.2 本地实现 (Now)
```python
# app/adapters/auth_local.py
from app.core.ports.auth import AuthProvider

class NoAuthProvider(AuthProvider):
    async def get_current_user_id(self, request: Request) -> str:
        return "default_local_user"
```

#### 4.4.3 云端实现 (Future)
```python
# app/adapters/auth_oidc.py
class OIDCAuthProvider(AuthProvider):
    # TODO (Phase 1, Task 1.6): Decode JWT and extract ID
    pass
```

## 5. 配置驱动选择 (Backend Selection)

集中管理接口的绑定，通过 `BaseSettings` 动态注入适配器。

```python
# app/core/backends.py
from pydantic_settings import BaseSettings
from typing import Literal

class BackendConfig(BaseSettings):
    storage: Literal["filesystem", "s3"] = "filesystem"
    metadata: Literal["sqlite", "postgres"] = "sqlite"
    eventbus: Literal["memory", "redis"] = "memory"
    auth: Literal["none", "oidc"] = "none"

# 简易依赖注入工厂
def get_storage_backend() -> StorageBackend:
    config = BackendConfig()
    if config.storage == "filesystem":
        return LocalFilesystemBackend(base_dir=WORKSPACES_DIR)
    # else return S3...
```
*所有服务逻辑均从该工厂获取实现。*

## 6. 推迟做的事 (Don't do now)

为了保持敏捷，我们仅进行协议占位，**绝对不**现在实施以下任务：
- **不写 S3/Postgres/Redis 客户端代码**：仅通过 `NotImplementedError` Stub 占据路径。
- **不接入实际的 JWT 解析与 OAuth 跳转**：Auth 接口永远返回 "local_user"。
- **不剥离 Subprocess 到 Celery**：当前仅解耦文件 I/O，Agent 仍然在子进程甚至直接 await 运行（如果是单机安全模型）。
- **不做 K8s Helm 配置**。

## 7. 必须现在做的事 (Must do now)

若不在此刻解决，未来重构将“刮骨疗毒”：
- **现在必须剥离全项目的硬编码文件读写 (StorageBackend)**。
  - *原因*: 路径拼接、目录遍历在 SaaS 中完全不存在。一旦产生过多对文件系统属性（如 `os.stat` 或 `path.exists()`）的强耦合，后期切换到 S3 等同于重写大半个 `services/skills.py`。
- **现在必须规范化 EventBus 接口签名**。
  - *原因*: WebSocket 的生命周期非常脆弱。如果不现在把直接依赖 `asyncio.Queue` 的代码替换为隔离的生成器，未来加入多路复用时，极易诱发并发泄漏。

## 8. 改造路线 (实施 plan)

目标在 5-10 Dev-Day 内无感替换：

1. **Task 1: 定义协议与配置层 (1d)**
   - 描述：创建 `app/core/ports/` 与 `app/core/backends.py`，写明所有 Protocol。
   - 阻塞：无。
2. **Task 2: 实现本地适配器 (2d)**
   - 描述：用现有代码逻辑包装出 `LocalFilesystemBackend`, `InMemoryEventBus`, `NoAuthProvider` 等。
   - 阻塞：Task 1。
3. **Task 3: 注入替换 API 与 Router (3d)**
   - 描述：全局替换 `services/*.py` 中的硬编码 `os`/`pathlib` 为 `get_storage_backend()`；将 WebSocket 改造为 `subscribe` 迭代器。
   - 风险：如果之前依赖了过于特殊的本地文件 API，可能会发现接口不兼容需要微调设计。
   - 阻塞：Task 2。
4. **Task 4: 添加 Mock 测试 (1d)**
   - 描述：提供 `MockStorage`，不落盘运行单元测试，验证解耦成果。
   - 阻塞：Task 3。

## 9. 风险与权衡

- **本地 dev 变慢？**：几乎无影响，因为本地 Adapter 依然是直接走本地 API。
- **过度抽象？**：不。只写必要的 Read/Write，是标准防腐层实践。
- **接口锁定**：接口应允许演进（利用 `**kwargs` 或按需拓展），而非强行 Freeze。

## 10. 验收标准

- ✅ `pytest` 在本地环境下 100% 跑通，PM 无感知变化。
- ✅ 扫视 `studio-backend/app/services`，代码中 **0 处**直接使用 `open()` 或 `Path.write_text()` 的非缓存文件写入。
- ✅ 后续只需修改 `BackendConfig` 环境变量，即完成云环境切换。

## 11. 关联文档

- 本文档是 `SPLIT_ARCHITECTURE.md` 的"暂缓云化但留接口"变体。
- 云端全量实现计划请参考：`SPLIT_ARCHITECTURE.md` 的 Phase 1-5。
