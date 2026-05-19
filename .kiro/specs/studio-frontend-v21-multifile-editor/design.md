# Studio V2.1 Multi-file Editor & API (Full Stack) — Design

## §0. 范围声明
本文档覆盖 Frontend Editor 组件的目录化重构，以及 Backend Router/Service/Model 层关于 `POST/PUT /api/skills` 的多文件接收与原子写入。设计基准参考 `skills/batch-analysis/`。

## §1. 技术选型
- **Frontend**: `monaco-editor` (热切 Model) + `react-arborist` (虚拟化 DND 树) + `zustand` (跨文件脏状态存储)。
- **Backend**: Pydantic V2 ( `extra="forbid"` Req model 校验 ) + 自定义防御性路径白名单验证 (`Path traversal guard`) + 临时目录原子替换写盘 (Atomic swap)。

## §2. 数据流图
```ascii
[FileTree Panel] <-----> [Workspace Store] <----> [EditorTabs]
       |                     (Zustand)                  |
   (Select File)                 |              (Switch Model)
       v                         |                      v
[Active node sync]               |             [Monaco Editor]
                                 v                      ^
                         [ Api Client ]                 |
  Frontend                       |                      |
=================================|======================|==========
  Backend                        v                      |
                      [ routers/skills.py ]             |
                                 |                      |
                      [ models/skills.py  ]             |
                        (Req Validation)                |
                                 |                      |
                     [ services/skills.py ]-------------+
                     (Atomic Disk Write)
```

## §3. 关键组件清单 (Before vs After)

### Frontend
- **Before (现状)**: 
  - 单 `App.tsx` 持有单 `skillCode: string` state，其 `handleSave` 方法 (line 330-352) 强行用单文件模式调 `api.put`，导致 422。
  - `components/MonacoPanel.tsx` 挂载单一 editor，仅接受 `skillCode` string prop。
  - `components/SkillSidebar.tsx` 仅作 Skill ID 列表选择器。
  - 组件扁平堆放在 `src/components/` 下，无多文件目录结构心智。
- **After (改后)**: 
  - 新建 `components/FileTree.tsx` (基于 `react-arborist`，呈现多文件目录)。
  - 新建 `components/EditorTabs.tsx` (封装多 Tab 与 Monaco 热切逻辑)。
  - 新建 `stores/workspace.ts` (Zustand 管理多文件树状态与脏标)。
  - 修改 `api/client.ts` 暴露新的多文件保存接口 `saveSkillFiles(skill_id, files)`。
  - 重构 `App.tsx`：移除硬编码单文件存取，改为统筹 Tree State 并调用多文件 Save。
  - 修改 `MonacoPanel.tsx`：改用 `monaco.editor.setModel` 接受 active model 参数进行文件热切。

### Backend
- **`routers/skills.py` (Before/After)**: 接口签名保持，但依赖下层的 Model 变化。
- **`services/skills.py` (Before)**: `update_skill_content` 强制报 422 (`_raise_v21_directory_authoring_required`)。
- **`services/skills.py` (After)**: 实现 `update_skill_files(user_id, skill_id, files_dict)` 原子覆盖写入逻辑。

## §4. 跟 Backend 接口契约对比

**Before (现状)**
`models/skills.py` (line 46-50):
```python
class UpdateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str
```
触发 `services/skills.py:553` 的 422 报错："V2.1 skills are directory-based; single-file SKILL.md authoring is not supported".

**After (改后推荐)**
`models/skills.py`:
```python
class UpdateSkillReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: dict[str, str] # Key=相对路径(如 GRAPH.md, phases/prep/LOGIC.md), Value=文本内容
```

**Backend Atomic Write 策略**
后端在处理 `files: dict[str, str]` 字典时，不应该原位逐个文件覆写，而是走操作系统级别的原子替换（Atomic Swap），确保一旦出错不会出现“部分保存”的坏账态。伪代码如下：
```python
import os, shutil
from pathlib import Path

def write_skill_files_atomic(skill_dir: Path, files: dict[str, str]) -> None:
    # 1. 校验全部 file path (Path validation，防目录穿越)
    backup_dir = skill_dir.with_name(f"{skill_dir.name}_bak")
    tmp_dir = skill_dir.with_name(f"{skill_dir.name}_tmp")
    
    # 2. 在 tmp_dir 中写入全量 files
    # ...
    
    # 3. Swap: 现存的重命名为 bak，tmp 扶正为正式 dir
    if skill_dir.exists():
        os.rename(skill_dir, backup_dir)
    try:
        os.rename(tmp_dir, skill_dir)
    except Exception:
        # 4. 回滚
        if not skill_dir.exists() and backup_dir.exists():
            os.rename(backup_dir, skill_dir)
        raise
    finally:
        # 5. 清理现场
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
```

## §5. 跟 CompiledSkill schema 对齐
(保持前端只读消费 GET Preview API 的 `graph_topology` / `node_schema_v21` / `io_schema`，用于画布渲染与智能补全)

## §5.5 V2.1 物理结构 Tree Schema
基于 loader 实证，合法白名单文件及 Phase Type 约束映射如下：
- **公共 Required**: `GRAPH.md` (根目录), `io/inputs.json`, `io/outputs.json`
- **Phase 文件约束 (互斥映射)**：
  - phase type "logic" → REQUIRED `phases/<id>/LOGIC.md` + FORBIDDEN `phases/<id>/SUBGRAPH.md`, `SKILL.md`
  - phase type "subgraph" → REQUIRED `phases/<id>/SUBGRAPH.md` + FORBIDDEN `phases/<id>/LOGIC.md`, `SKILL.md`
  - phase type "skill" → REQUIRED `phases/<id>/SKILL.md` + FORBIDDEN `phases/<id>/LOGIC.md`, `SUBGRAPH.md`
- **Optional**: `phases/<id>/actions/*.py`, `phases/<id>/tools/*.py`, `tools/*.py`

## §6. 错误处理、性能策略与写盘决议

**决议：PUT 全覆盖 vs Diff 增量**
针对多文件更新，**推荐采用全量覆盖 (PUT) + tmpdir-rename swap**。
*Rationale*:
1. PUT 符合 REST 语义中的“状态全量替换”，与前端 Zustand 持有全量代码树 Snapshot 的模型天然契合。
2. Backend 处理 Diff 增量会引入极大的复杂度（需要解析 canonical state），且跨多文件的 Patch 操作如果在中途宕机，原子性极难保证。
3. 性能不是瓶颈：单个 Skill 的文本总体积仅在 ~10KB 级别，全量构建临时目录并 Rename 在磁盘层面不足 100ms。依赖 POSIX 级别的 Rename 是最稳健的设计。

**路径白名单**
Backend 迭代 `files` 时，必须拦截：以 `/` 开头、包含 `../`、或非 `.md`/`.json`/`.py` 结尾的键。命中抛 422。

**Frontend 报错联标**
接管编译期 `file:line` 报错，转换为 Monaco markers 并标注在对应 Tree Node 上。

## §7. 实施 Phase 拆分
- **Phase A (Backend Core) [估时: S]**: 修改 Req Models，实现 `services/skills.py` POST/PUT 的原子写盘策略，移除 422 限流。
- **Phase B (Frontend Data) [估时: S]**: 建立 Zustand store，升级 `api/client.ts` 提供全量 `files` Payload 保存。
- **Phase C (Frontend UI) [估时: M]**: 集成 `react-arborist` 搭建侧边栏，拆除旧单文件逻辑，搭建多 Tab 与 Monaco 热切架构。
- **Phase D (Integration) [估时: S]**: 联调保存，Monaco 补全注入，错误行号联动，确保 Reference Skill 端到端跑通。
