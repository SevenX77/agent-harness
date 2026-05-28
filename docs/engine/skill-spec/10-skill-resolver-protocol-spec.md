---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# Skill Resolver Protocol Spec

本文定义 V0.3.0 全局 Registry 寻址的单方法 DI 接口和 Engine/Studio 边界。它被 [SUBGRAPH target_skill 寻址](./04-subgraph-md-spec.md#target_skill-寻址规则) 与 [Mention 静态可达性](./07-mention-syntax-spec.md#7-大分类静态可达性算法) 共同引用。

## Protocol Interface 定义

物理位置:

```text
packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py
```

V0.3.0 只允许一个方法:

```python
from pathlib import Path
from typing import Protocol


class SkillResolutionError(SkillLoadError):
    def __init__(
        self,
        skill_id: str,
        reason: str,
        *,
        code: str = "[F-v3-skill-not-registered]",
    ) -> None:
        ...


class SkillResolverProtocol(Protocol):
    def resolve_skill(self, skill_id: str) -> str | Path:
        """Return graph skill root path or raise SkillResolutionError."""
```

接口字段级契约:

| 项 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | 正则 `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`; 是 registry key, 不是路径 | `[F-v3-resolver-skill-id-invalid]` | registry 查询 key |
| 返回值 | `str \| pathlib.Path` | 是 | 无 | Engine 会转成 `Path`; 路径必须存在、是目录、目录内含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` | 子 graph skill 根目录 |
| 异常 | `SkillResolutionError` | 否 | — | 未注册、不可访问或歧义时抛出 | `[F-v3-skill-not-registered]` / `[F-v3-skill-id-ambiguous]` | 统一失败语义, 供 Studio/CLI 标红和诊断 |

禁止扩展:

| 禁止接口 | 原因 |
|---|---|
| `resolve_resource()` | round 2 已决议不做资源级 resolver; reference/example 是当前 skill 内资源 |
| `resolve_skill_path()` | 方法名不稳定, 与决议不一致 |
| 返回非路径语义对象 | Engine 内部统一转成 `Path` 并做物理校验 |

接口失败和兜底行为见 [F-v3-resolver 错误契约](./11-error-code-spec.md#resolver-domain)。

## 依赖注入 (DI) 边界

Engine 只定义 Protocol, 不拥有 Studio registry。PR-1 后 Engine 还提供了一个本地文件系统实现 `LocalWorkspaceResolver`，供 CLI、README 示例、独立工具和简单宿主项目使用；Studio backend 仍然有自己的 Studio registry resolver。

本地实现:

```text
packages/graph-agent/src/graph_agent/core/local_workspace_resolver.py
```

`LocalWorkspaceResolver` 字段级行为:

| 字段/步骤 | 真实行为 | 错误码 |
|---|---|---|
| `search_paths` | 构造参数可传 `Iterable[str \| Path]`; 未传时默认 `Path.cwd()` 和 `Path.cwd() / "skills"` | — |
| `validate_skill_id(skill_id)` | 解析前先校验 `skill_id` 正则 | `[F-v3-resolver-skill-id-invalid]` |
| literal 候选 | 对每个 base 尝试 `base / skill_id` | — |
| dotted-id 候选 | 对每个 base 尝试 `base / Path(*skill_id.split("."))`, 即 `acme.echo` -> `acme/echo` | — |
| 命中条件 | candidate 必须是目录且包含 `GRAPH.md` | — |
| 唯一命中 | 返回去重后的唯一 root `Path` | — |
| 多命中 | fail-loud, message 包含所有匹配 root | `[F-v3-skill-id-ambiguous]` |
| 零命中 | message 包含 search paths | `[F-v3-skill-not-registered]` |

多命中必须 fail-loud，而不是 silent first-match。否则 literal `acme.echo/` 与 dotted `acme/echo/` 同时存在时，search path 顺序会静默改变实际调用的 child skill，违反零静默失败原则。

Studio 实现位于:

```text
apps/studio/backend/app/services/skill_resolver.py
```

边界划分:

| 层 | 职责 | 禁止做的事 |
|---|---|---|
| Engine | 定义 `SkillResolverProtocol`; 在编译 SUBGRAPH 或 Agent subgraph registry 时调用 `resolve_skill()`; 提供 `LocalWorkspaceResolver` 作为本地实现 | 读取 Studio settings、弹文件选择器、在 compile/assemble/run 入口隐式 new resolver |
| Studio backend | 实现 `StudioSkillResolver`; 从 Studio skill registry 查 skill root; 提供导入流程 | 改写 Engine 的 resolver 接口 |
| Studio frontend | 在 subgraph asset panel 展示已注册/未注册状态; 未注册时触发导入 | 直接让 Engine 读取任意前端路径 |

Engine 入口必须强注入 resolver。PR-1 已移除测试环境对 `skill_resolver` 的默认值注入，以下入口都没有 `= None` 默认值：

- `compile_skill(..., skill_resolver: SkillResolverProtocol)`
- `SkillLoader.compile_skill(..., skill_resolver: SkillResolverProtocol)`
- `load_workflow_from_md(..., skill_resolver: SkillResolverProtocol)`
- `assemble_graph(..., skill_resolver: SkillResolverProtocol)`
- `run_skill(..., skill_resolver: SkillResolverProtocol)`
- `_run_skill_dict(..., skill_resolver: SkillResolverProtocol)`
- `_run_v030_skill_dict(..., skill_resolver: SkillResolverProtocol)`

缺 resolver 时，Python 签名会先暴露缺少必填 keyword-only 参数；进入内部边界后，`require_skill_resolver(None, caller=...)` 抛 `[F-v3-resolver-missing]`。

```python
def _run_v030_skill_dict(
    skill_root: Path,
    inputs: dict,
    *,
    skill_resolver: SkillResolverProtocol,
) -> dict:
    ...
```

CLI 是调用方之一，会自动接线本地 resolver：用户运行 `python -m graph_agent --skill <root>` 时，`runner.main()` 根据当前目录、`./skills`、`--skill` root、root 的 `registry/` 和相邻目录构造 `LocalWorkspaceResolver`，再传给 `run_skill`。`tools/dual_run_shadow.py` 作为独立工具也会构造 `LocalWorkspaceResolver(search_paths=[skill_root, skill_root.parent, skill_root.parent / "registry"])`，并同时传给 `compile_skill` 和 `assemble_graph`。

Studio 需求来源见 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md#需求-1--studio-assets-panel-subgraph-类目与跨-skill-导入流程-2026-05-22)。
