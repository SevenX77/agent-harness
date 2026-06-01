# workspace-file-system (studio system-level) — MVP0 Alignment (下一步脚手架与持久化对齐)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: `.workspace` 初始化职责 (High-004)、FileWatcher 行为、Draft 持久化存储策略
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

在 MVP0 中，PM 新建一个技能不再会看到莫名其妙丢失文件夹的情况（旧有冲突见 [baseline.md#后端功能](./baseline.md#后端功能) 中提到的 High-004）。
PM 在 Studio 选择“新建空白 V2.1 技能”后，界面将给出一个优雅的全局 Loading，并在几百毫秒后展示一个内部含有完整标准结构（含 `SKILL.md`，`.workspace/` 配置，甚至配套数据夹）的侧边文件树。这种开箱即用的脚手架，让不懂文件层级规范的 PM 能够安全快速地进入开发流程。同时，针对修改未保存的情况，文件名边上会显示小圆点以暗示未持久化的改动。

### 6. 清理废弃的 `.workspace` 残留
考虑到用户可能会在系统资源管理器中直接物理删除一些文件夹，UI 层应该配合后端检测这种孤儿配置，并给予清理选项弹窗，以免因为污染导致文件树加载出幻影结构。

### 7. 对重命名行为的体验优化
在 MVP0 中，如果 PM 想要重命名一个 Phase（这意味着不仅是文件夹变化，`GRAPH.md` 的引用也必须跟着改变）。我们要求这些在前端触发的重命名动作，都必须弹出确认框，并且只有通过后端统筹修改后，UI 树才被允许刷新。

### 8. 空态页的引导
如果在加载路径下没有发现任何技能（可能因为是纯净的新工作区），右侧主视图区必须由原本空白尴尬的状态变为呈现具有极强引导性的 "Create your first Skill" Hero Banner。

## 前端逻辑

为彻底解决 Audit High-004 的职责模糊问题：
- **职责转移**：前端 Tauri 层**将不再直接调用系统 fs API 去创建空目录与空脚手架**。Tauri 的 IPC 职能将降级，只作为文件对话框（如弹窗选择目标路径）的提供者。所有的复杂生成统统推入后端。
- **主动触发创建**：当前端需要创建一个新 Workspace，它将构造完整的路径请求并发向后端的 `POST /api/skills/init` 接口。
- **草稿持久化 Draft Persist 升级**：针对 PM 编辑了一半未保存的文本内容，将从以前模糊的本地存取升级为基于 IndexedDB（例如 Dexie）或 Tauri `local_data_dir` 的可靠快照写入。这保障了 Studio 因为外力崩溃时，PM 辛苦修改的 prompt 绝对不会丢失。

### 1. Tauri FS 退役与权限隔离
前端不应该信任自己对操作系统底层的调用能力。目前在新建技能时，如果调用了 `fs.createDir` 却碰上了系统权限问题，极易引发前端挂死。
MVP0 将回收这部分权限：
前端仅通过 `<input type="file" directory />` 或者 Tauri 专有的 `dialog.open` 拿到一个 Path String，剩下的统统交给安全的后端 API。

### 2. File Status 同步视图
配合后端给出的 `FileWatcher`，前端 `PanelFiles` 必须能够实时接收文件变化。当收到某节点文件的更新推送时，应当有平滑的颜色动画或是 Reload 按钮出现，而不是强制覆盖 PM 当前正在敲击的输入框，防止造成数据抹除的惨案。

### 3. Tauri 权限回收带来的网络变迁
既然 FS 的直接读写权力已经退役交还给 FastAPI 的 REST 接口，那就意味着网络请求有可能变慢。
在 Studio 层面：对于 `POST /api/skills/init` 这种需要较长系统 IO 的事务，我们要在前端挂接标准的 React Query 或是 SWR 机制。它不仅仅包含 `isPending`，更要具备在断网或后端拒绝响应时的强超时取消（AbortController），以防 PM 点击了一次后整个界面永久锁死。

### 4. Golden 数据集存放规则的默认配置
在后端真正生成的脚手架里，不仅仅是代码文件，我们强烈要求在生成的 `.workspace/` 内默认写入针对于测试集的扫描配置。这将使得后续的测试集发现能做到零配置。这是脚手架应当具备的前瞻性。

### 5. File Status 同步视图的视觉消噪
配合后端给出的 `FileWatcher`，前端 `PanelFiles` 必须能够实时接收文件变化。当收到某节点文件的更新推送时，应当有平滑的颜色动画或是 Reload 按钮出现，而不是强制覆盖 PM 当前正在敲击的输入框，防止造成数据抹除的惨案。

## 后端功能

High-004 问题的终极对齐落在后端引擎和 FastAPI 的脚手架生成：
- **初始化创建服务**：由 Python 后端提供深度的模板生成能力。当前实现代码在 `apps/studio/backend/app/services/skills.py:425` 的 `create_new_skill` 中，虽然生成了基础结构，但未生成 `golden/` 或完善的 `io/inputs.json`。收到初始化 REST 请求时，后端将严格按照 Engine 所规范的 V2.1 格式，不仅创建目录，还一次性落盘带有默认 Frontmatter（例如强制带有 `io: {}`）的 `GRAPH.md` 和各阶段的 `SKILL.md` 代码桩。这就一次性保证了新建图的绝对可跑。
- **FileWatcher 机制落地**：目前的后端 `FileWatcher` 服务并没有做到真正有效的长轮询挂载。MVP0 将使用 `watchdog` 等库去监听已载入的 Workspace 目录树。当监听到外界改变（比如 PM 在外头使用了 VSCode 存盘修改了 `LOGIC.md`），后端将在第一时间通过 WebSocket 给前端发出 `FILE_CHANGED` 通知，催促前端重载文件流。

## API

以下为统一收敛脚手架创建职责所需的核心 API，落地在 `apps/studio/backend/app/routers/skills.py:88` 的调用。这使得一切变得极度规范。

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class InitSkillRequest(BaseModel):
    """Payload requested from Studio frontend to init a directory."""
    target_path: str
    skill_name: str
    template_type: str = "blank_v21"

class InitSkillResponse(BaseModel):
    success: bool
    created_files: list[str]
    root_path: str

@router.post("/api/skills/init", response_model=InitSkillResponse)
async def init_new_skill_workspace(req: InitSkillRequest):
    """
    Solves High-004 by centralizing the creation of V2.1 
    project skeleton in the Python backend rather than frontend Rust fs.
    
    This function creates all necessary `GRAPH.md`, `io/inputs.json`
    and standard directories to ensure valid compilation upon first run.
    It guarantees atomic creation: either all succeed or none do.
    """
    pass
```

## Data Model / State

- **草稿库 Model**:
  对于前端的 Draft Persist 策略，如果采用 IndexedDB（例如借助 Dexie.js），我们建立如下简单快照实体结构，存在客户端游览器中：
  ```json
  {
      "filePath": "/absolute/path/to/skill/phases/main/SKILL.md",
      "unsavedContent": "...",
      "timestamp": 1690000000
  }
  ```
- **草稿的销毁策略**:
  这个持久化的状态一旦在前端点击了真正的全局保存（触发 `POST /api/save` 落地），它在 DB 里的镜像就必须立刻被删除，以确保这个本地缓存在任何时间只持有 **脏状态 (Dirty State)**。

## Cross-feature interaction

- **给 Skill Lifecycle 赋能**:
  前端页面上的向导或创建动作归属于 [skill-lifecycle feature](../../feature-folders/skill-lifecycle/mvp0-alignment.md)。那个特性的 UI 会直接消费这儿定义的 `POST /api/skills/init` 接口完成流转闭环。这两者的配合如同表与里。
- **支撑 Split Editor 文件树更新**:
  后端的 `FileWatcher` 发出的物理磁盘更新信令，将直接投递给 [multi-file-editor](../../feature-folders/multi-file-editor/mvp0-alignment.md)。编辑器据此判定本地的 Draft 是否过期，从而提示 PM 合并或者加载外部最新文本。这种底层的坚实系统功能保障了功能域不出现 “文件内容串台”。只有底层文件同步做好了，上层 Editor 才敢说支持协同。