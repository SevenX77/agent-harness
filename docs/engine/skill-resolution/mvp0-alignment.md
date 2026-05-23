# skill-resolution (engine) — MVP0 Alignment (V0.3.0 SkillResolverProtocol DI)

> **Status**: Added by a1 (Codex), 2026-05-23
> **Scope**: `SkillResolverProtocol` 单方法 DI、Studio / production resolver 实现边界、跨 Skill 导入联动、旧 `_resolve_subagent_root` 退役。
> **配套**: [SkillResolverProtocol Spec](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义), [SUBGRAPH target_skill](../skill-spec/04-subgraph-md-spec.md#target_skill-寻址规则)。

## V0.3.0 改造摘要

V0.3.0 把子 skill 寻址从“父目录下相对路径扫描”改成“全局 registry id 解析”。

| V2.1 现状 | V0.3.0 目标 | 改造点 | 错误码 |
|---|---|---|---|
| `_resolve_subagent_root(skill_root, phase_path, subagent_path, name)` | `skill_resolver.resolve_skill(skill_id) -> Path` | C-RES-1 | `[F-v3-skill-not-registered]` |
| `subagents[].path` | `subagents[].target_skill` | NEW-RES-3 | `[F-v3-resolver-skill-id-invalid]` |
| 编译器直接拼路径 | `compile_skill(..., skill_resolver=...)` 强注入 | NEW-RES-2 | `[F-v3-resolver-missing]` |
| 无独立协议文件 | `core/skill_resolver_protocol.py` | NEW-RES-1 | `[F-v3-resolver-interface-invalid]` |

执行顺序:

1. NEW-RES-1: 新建 `SkillResolverProtocol` + `SkillResolutionError`。
2. NEW-RES-2: `compile_skill()` / `run_skill()` 顶层签名传入 resolver。
3. C-RES-1 + NEW-RES-3: 废除旧路径扫描, 所有 `target_skill` 解析切到 Protocol。

## 改造点落地顺序

| 改造点 | 阶段 | 具体动作 | 完成判定 |
|---|---|---|---|
| NEW-RES-1 | 1 | 新建 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py` | Protocol + `SkillResolutionError` 可被 compiler/runtime import |
| NEW-RES-2 | 2 | `compile_skill()` / `run_skill()` / graph assembly 入口显式接收 `skill_resolver` | 含 child skill 的图无 resolver 时 FATAL `[F-v3-resolver-missing]` |
| C-RES-1 | 3 | 删除 `_resolve_subagent_root` 相对路径拼接路径 | 不再读取 `subagents[].path` |
| NEW-RES-3 | 3 | `SUBGRAPH.md target_skill`、Agent `subagents[].target_skill`、Agent `subgraphs[].target_skill` 全部调用 `resolve_skill` | registry miss 统一 `[F-v3-skill-not-registered]` |

## UI/UX

N/A — 此模块为纯 backend Python library, 无直接 UI / 前端调用面。

用户可见的“未注册 subgraph 标红”和“点击导入 graph skill”由 Studio 实现。Engine 只负责把 registry miss 变成稳定错误 `[F-v3-skill-not-registered]`。

## 前端逻辑

N/A — 此模块无 React 逻辑。

Studio Assets Panel 会消费 resolver 失败状态, 但文件选择器、导入确认、重新加载 skill registry 都属于 Studio feature。Engine 不弹窗、不访问 Tauri API、不猜用户本地目录。

## 后端功能

### 1. SkillResolverProtocol 接口 (NEW-RES-1)

Engine MUST 新建协议骨架:

```python
from pathlib import Path
from typing import Protocol


class SkillResolutionError(Exception):
    pass


class SkillResolverProtocol(Protocol):
    def resolve_skill(self, skill_id: str) -> Path:
        """Return graph skill root path or raise SkillResolutionError."""
```

| 字段 / 对象 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | registry 查询 key |
| `resolve_skill` | callable | 是 | 无 | 单方法语义, 不加 `resolve_resource` | `[F-v3-resolver-interface-invalid]` | Engine / Studio DI 边界 |
| return `Path` | `pathlib.Path` | 是 | 无 | 存在、是目录、含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` | 可编译 graph skill root |
| `SkillResolutionError` | exception | 未注册时抛 | — | resolver miss 或无权限时抛 | `[F-v3-skill-not-registered]` | 统一失败语义 |

字段级规范见 [SkillResolverProtocol Interface](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义)。

### 2. DI 装配生命周期 (NEW-RES-2)

`skill_resolver` 必须从顶层调用入口注入, 不能在 Engine 内部 new 一个默认 Studio resolver。

| 注入点 | 参数 | 类型 | 必填条件 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `compile_skill` | `skill_resolver` | SkillResolverProtocol | 编译含 SUBGRAPH / subagents / subgraphs 时必填 | 实现 `resolve_skill` | `[F-v3-resolver-missing]` | 编译期解析 target skill |
| `run_skill` | `skill_resolver` | SkillResolverProtocol | 是 | 透传给 compile / runtime child graph | `[F-v3-resolver-missing]` | 运行期子图调用 |
| `assemble_graph` | `skill_resolver` 或 resolved metadata | Protocol / metadata | 含 child graph 时必填 | 不允许相对路径 fallback | `[F-v3-resolver-missing]` | runtime wrapper 调用 |
| tests | fixture resolver | InMemory implementation | 是 | 显式 id -> temp root map | `[F-v3-skill-not-registered]` | 可预测测试 |

如果调用方没有注入 resolver, Engine 不应尝试从 cwd、父 skill root、环境变量或 Studio settings 猜路径。DI 边界见 [execution-runtime SkillResolverProtocol](../execution-runtime/mvp0-alignment.md#15-skillresolverprotocol-di-注入边界-c10-new-d)。

### 3. Studio 沙箱实现

Studio sandbox resolver 负责把 UI 导入的 skill registry 记录解析成本地目录。

| 字段 / 来源 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `settings_dir` | Path | 是 | Studio settings root | 必须可读 | `[F-v3-resolver-path-invalid]` | 本地 registry 存储根 |
| `metadata_local.json` / skill summary | JSON object | 是 | 无 | 包含 skill id -> root path 映射 | `[F-v3-skill-not-registered]` | Studio 本地导入记录 |
| `skill_id` | string | 是 | 无 | 与 `GRAPH.md name` / registry id 对齐 | `[F-v3-resolver-skill-id-invalid]` | 查询 key |
| `root_path` | Path | 是 | 无 | 目录含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` | Engine 可编译路径 |
| import status | enum | 否 | `registered` | `registered` / `missing` / `invalid_path` | `[F-v3-skill-not-registered]` | Assets Panel 标红 |

Studio 的跨 Skill 导入需求来源见 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md#需求-1--studio-assets-panel-subgraph-类目与跨-skill-导入流程-2026-05-22)。

### 4. 生产 Registry 实现

生产环境 resolver 应支持只读 workspace mount、私有 skill 和公共 skill 分层。Engine 不感知租户模型, 只接收 resolver 返回 Path。

| 字段 / 策略 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `tenant_id` | string | production 必填 | 无 | resolver 内部校验, 不进入 Engine Protocol | `[F-v3-skill-not-registered]` | 私有 registry 隔离 |
| private registry | mapping | 否 | `{}` | 优先于 public | `[F-v3-skill-not-registered]` | 用户 / workspace 私有 skill |
| public registry | mapping | 否 | `{}` | 只读 mount | `[F-v3-resolver-path-invalid]` | 共享 skill |
| `version_hash` | string | 建议 | computed | 与 cache key 绑定 | — | resolver cache invalidation |
| permission check | boolean | 是 | deny by default | 未授权视为未注册 | `[F-v3-skill-not-registered]` | 防跨租户读取 |

生产 resolver 可以返回带 metadata 的内部结构, 但 Protocol 对 Engine 暴露的返回值仍是 `Path`; 扩展 metadata 放在 resolver cache 或 `ResolvedSkill` 数据模型中。

### 5. 跨 Skill 导入流程

导入流程由 Studio 触发, Engine 只提供结构化失败。

| 步骤 | 参与方 | 输入 | 输出 / 错误 | 业务作用 |
|---|---|---|---|---|
| 解析 `target_skill` | Engine compile/runtime | `target_skill` | 调 `resolve_skill(target_skill)` | 尝试定位子 skill |
| 未注册 | Resolver | skill id | 抛 `SkillResolutionError` -> `[F-v3-skill-not-registered]` | 给 Studio 明确导入入口 |
| 前端标红 | Studio frontend | error payload | subgraph asset 红色状态 | 告知用户缺失 |
| 选择目录 | Studio Tauri / frontend | folder path | candidate graph skill directory | 用户导入 |
| 后端验证 | Studio backend | directory + expected skill id | 写 registry 或报错 | 确保 `GRAPH.md name` 对齐 |
| 重编译 | Engine | updated resolver | success / remaining issues | 红色状态恢复 |

SUBGRAPH 和 mention 的静态可达性都依赖这个流程。规范见 [SUBGRAPH target_skill](../skill-spec/04-subgraph-md-spec.md#target_skill-寻址规则) 与 [Mention 7 类可达性](../skill-spec/07-mention-syntax-spec.md#7-大分类静态可达性算法)。

### 6. 错误码与失败语义

| 错误码 | 阶段 | 触发条件 | 修复建议 | Cross-link |
|---|---|---|---|---|
| `[F-v3-resolver-missing]` | 编译期 / 运行期 | 需要解析 target skill 但未注入 resolver | 调用入口传入 SkillResolverProtocol | [Error Code Spec](../skill-spec/11-error-code-spec.md#resolver-domain) |
| `[F-v3-resolver-skill-id-invalid]` | 编译期 | `target_skill` / `skill_id` 命名非法 | 改为小写 skill id | [Error Code Spec](../skill-spec/11-error-code-spec.md#resolver-domain) |
| `[F-v3-skill-not-registered]` | 编译期 / 装配期 / 运行期 | resolver 查不到 skill 或无权限 | Studio 导入 / 注册 skill | [Error Code Spec](../skill-spec/11-error-code-spec.md#resolver-domain) |
| `[F-v3-resolver-path-invalid]` | 编译期 | resolver 返回路径不存在或无 `GRAPH.md` | 修 registry 记录 | [Error Code Spec](../skill-spec/11-error-code-spec.md#resolver-domain) |
| `[F-v3-resolver-interface-invalid]` | 编译期 | resolver 不符合单方法协议 | 实现 `resolve_skill` | [Error Code Spec](../skill-spec/11-error-code-spec.md#resolver-domain) |

Tracing 侧应把这些错误放进 `EXCEPTION.payload.error_code`, 见 [Execution Runtime 调用点绑定](../tracing-and-observability/mvp0-alignment.md#3-execution-runtime-调用点绑定)。

## API

### Python Protocol

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class SkillResolutionError(Exception):
    def __init__(self, skill_id: str, reason: str) -> None:
        self.skill_id = skill_id
        self.reason = reason
        super().__init__(f"skill {skill_id!r} could not be resolved: {reason}")


class SkillResolverProtocol(Protocol):
    def resolve_skill(self, skill_id: str) -> Path:
        """Return a graph skill root path or raise SkillResolutionError."""
```

### Entry Point Shape

```python
def compile_skill(
    root: Path,
    *,
    skill_resolver: SkillResolverProtocol,
    cache: bool = True,
) -> CompiledSkill:
    ...


def run_skill(
    root: Path,
    inputs: dict[str, Any],
    *,
    skill_resolver: SkillResolverProtocol,
    model_resolver: ModelResolverProtocol,
) -> WorkflowResult:
    ...
```

## Data Model / State

### ResolvedSkill

```python
@dataclass(frozen=True)
class ResolvedSkill:
    skill_id: str
    root_path: Path
    metadata: dict[str, Any]
    version_hash: str
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | registry id |
| `root_path` | Path | 是 | 无 | 存在、目录、含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` | Engine compile root |
| `metadata` | dict | 否 | `{}` | JSON-serializable | — | Studio / production 附加信息 |
| `version_hash` | string | 建议 | computed | 参与 compile cache key | — | registry cache invalidation |

`ResolvedSkill` 是 resolver 实现内部可用的数据模型。Protocol 仍只返回 Path, 避免 Engine 依赖 Studio metadata 结构。

## Cross-feature interaction

| 模块 | 交互点 | 本模块提供 | 对方负责 |
|---|---|---|---|
| skill-compilation | [子图寻址 DI 注入](../skill-compilation/mvp0-alignment.md#3-子图寻址-di-注入-c6) | `target_skill` -> Path | AST 构建、IO 对齐、compile issue |
| execution-runtime | [SkillResolverProtocol DI 边界](../execution-runtime/mvp0-alignment.md#15-skillresolverprotocol-di-注入边界-c10-new-d) | runtime child graph resolver | StateMapper、child graph invoke |
| state-and-io-contract | [Child Graph 黑板隔离](../state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation) | target skill root | child `io.inputs` funnel |
| tracing-and-observability | [Execution Runtime 调用点绑定](../tracing-and-observability/mvp0-alignment.md#3-execution-runtime-调用点绑定) | resolver error codes / target ids | EXCEPTION event payload |
| Studio backend | import / registry service | Protocol implementation | settings registry, folder validation |
| skill-spec/10 | [Protocol Interface](../skill-spec/10-skill-resolver-protocol-spec.md#protocol-interface-定义) | implementation plan | contract truth source |

## 与当前源码的差异

本文件描述的是目标收敛方向；当前源码还保留了一些兼容路径和错误码差异：

| 本文件目标态 | 当前源码事实 |
|---|---|
| 所有跨 skill 寻址都通过 `target_skill` 和 resolver | 当前 subagent 仍兼容 legacy `path` 相对路径。 |
| 无 resolver 时含 child skill 的图统一报 resolver missing | 当前只有声明了 `target_skill` 才必须传 resolver；legacy `path` 不需要 resolver。 |
| `resolve_skill()` 目标签名是返回 `Path` | 当前协议允许返回 `str | Path`，helper 再规整成 Path。 |
| skill id 非法错误码归一为 resolver skill id invalid | 当前非法 id 使用 `[F-v3-invalid-skill-id]`。 |
| `_resolve_subagent_root` 相对路径扫描退役 | 当前源码仍保留并用于 legacy `path`。 |
| SUBGRAPH 全部通过 `target_skill` 解析 | 当前 SUBGRAPH runtime 仍主要使用 `sub_skill_ref` 路径解析。 |
