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


class SkillResolutionError(Exception):
    pass


class SkillResolverProtocol(Protocol):
    def resolve_skill(self, skill_id: str) -> Path:
        """Return graph skill root path or raise SkillResolutionError."""
```

接口字段级契约:

| 项 | 类型 | 必填 | 默认值 | 校验规则 | 校验失败错误码 | 业务作用 |
|---|---|---|---|---|---|---|
| `skill_id` | string | 是 | 无 | 正则 `^[a-z][a-z0-9_-]*$` | `[F-v3-resolver-skill-id-invalid]` | registry 查询 key |
| 返回值 | `pathlib.Path` | 是 | 无 | 路径存在; 是目录; 目录内含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` | 子 graph skill 根目录 |
| 异常 | `SkillResolutionError` | 否 | — | 未注册或不可访问时抛出 | `[F-v3-skill-not-registered]` | 统一失败语义, 供 Studio 标红导入 |

禁止扩展:

| 禁止接口 | 原因 |
|---|---|
| `resolve_resource()` | round 2 已决议不做资源级 resolver; reference/example 是当前 skill 内资源 |
| `resolve_skill_path()` | 方法名不稳定, 与决议不一致 |
| 返回 string | Engine 内部统一用 `Path` 做物理校验 |

接口失败和兜底行为见 [F-v3-resolver 错误契约](./11-error-code-spec.md#resolver-domain)。

## 依赖注入 (DI) 边界

Engine 只定义 Protocol, 不拥有 Studio registry。具体实现位于 Studio backend:

```text
apps/studio/backend/app/services/skill_resolver.py
```

边界划分:

| 层 | 职责 | 禁止做的事 |
|---|---|---|
| Engine | 定义 `SkillResolverProtocol`; 在编译 SUBGRAPH 或 Agent subgraph registry 时调用 `resolve_skill()`; 把失败归一为 `[F-v3-skill-not-registered]` | 读取 Studio settings、猜测用户目录、弹文件选择器 |
| Studio backend | 实现 `StudioSkillResolver`; 从 Studio skill registry 查 skill root; 提供导入流程 | 改写 Engine 的 resolver 接口 |
| Studio frontend | 在 subgraph asset panel 展示已注册/未注册状态; 未注册时触发导入 | 直接让 Engine 读取任意前端路径 |

Engine 入口必须强注入 resolver:

```python
def _run_v3_skill_dict(
    skill_root: Path,
    inputs: dict,
    *,
    skill_resolver: SkillResolverProtocol,
) -> dict:
    ...
```

没有 resolver 时运行含 SUBGRAPH 的 graph 必须 FATAL `[F-v3-resolver-missing]`。对纯 Agent/Logic graph, Engine 也可以要求统一注入 no-op resolver, 但 no-op resolver 一旦被调用必须抛 `SkillResolutionError`。

Studio 需求来源见 [V0.3.0 New Requirements](../../studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md#需求-1--studio-assets-panel-subgraph-类目与跨-skill-导入流程-2026-05-22)。
