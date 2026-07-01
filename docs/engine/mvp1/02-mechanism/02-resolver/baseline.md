---
module: 02-mechanism/02-resolver
doc: baseline
status: audited-ready（现状对齐 pinned 代码 7cd4b9c；DI 接缝 = Protocol + LocalWorkspaceResolver,live；⚠️ 现状=registry/id 寻址=被 mvp1 path 反转的旧模型）
---

# 02-resolver — Baseline(当下代码实现逻辑)

> **Scope**: 把 skill 引用(SUBGRAPH `target_skill`、subagent 目标、registry id)解析成本地 skill root 的 DI 接缝:`skill_resolver_protocol.py`(协议+校验+缺失防护)、`local_workspace_resolver.py`(本地实现)。
> **现状一句话**:接口是 `SkillResolverProtocol`(`skill_resolver_protocol.py:33`),引擎只认协议、Studio 等宿主可注入实现;公共入口省略 resolver 时使用引擎自带 `LocalWorkspaceResolver`(`local_workspace_resolver.py:15`)按 skill/cwd 周边搜索路径解析。内部 helper 仍保留 `require_skill_resolver` 缺失防护(`[F-v3-resolver-missing]`)。

## UI/UX
N/A。

## 前端逻辑
N/A —— studio 注入 resolver 实现(registry 真相源在 studio);引擎只定义协议。

## 后端功能

### 1. 协议接缝(skill_resolver_protocol.py)
`SkillResolverProtocol`(`:33`,`@runtime_checkable`)定义唯一方法 `resolve_skill(skill_id) -> str | Path`(`:36`)。
> **DI(依赖注入)第一次出现需定义**:引擎不硬编码 registry,由宿主(studio)传入 resolver 实现,引擎只调协议——这样引擎不知道 studio 存在、可独立测试。
- `validate_skill_id(skill_id)`(`:40`):非法 id → `[F-v3-resolver-skill-id-invalid]`(`:47`)。
- `resolve_skill_root(resolver, skill_id)`(`:51`):调 `resolver.resolve_skill`(`:59`)→ 校验路径 → 非法 `[F-v3-resolver-path-invalid]`(`:69/:75`)。
- `require_skill_resolver(resolver, ...)`(`:80`):内部 helper 的缺失防护;公共入口会先补默认 resolver,所以普通 SDK 调用不应因省略 resolver 触发 `[F-v3-resolver-missing]`。

### 2. 本地实现(local_workspace_resolver.py)
`LocalWorkspaceResolver`(`:15`,实现 `SkillResolverProtocol`)按 `search_paths`(`:18`)把 skill_id 解析成本地 root,`resolve_skill`(`:22`)。它是引擎内置的默认实现(公开导出,见 `data-contracts` `__all__` 的 `LocalWorkspaceResolver`)。

### 3. 谁消费 resolver
loader 在编译 SUBGRAPH / AgentNode subagent 时,经 resolver 递归解析 child skill root(`loader.py`,见 `01-compile`);递归防环用 `[F-v3-compile-recursion-cycle]`。

## API
- `SkillResolverProtocol.resolve_skill(skill_id) -> str | Path`(`:36`)——producer=studio 实现,consumer=engine loader。
- `require_skill_resolver(resolver) -> SkillResolverProtocol`(`:80`)——内部缺失防护;公共入口使用默认本地 resolver。
- `LocalWorkspaceResolver(search_paths)`(`local_workspace_resolver.py:15`)——引擎内置实现。

## Data Model / State
无运行时 state。输入 `skill_id`(str),输出本地 root(Path)。错误码 `[F-v3-resolver-*]`(归 `data-contracts` / `compile-rules`)。

## 当前边界(这个模块现在不是什么)
- **不是全局单例**:DI 显式注入,不得被 middleware 隐式全局化(中间件消费 `_build_skill_node` 已备好的 runtime map,不自己找 resolver——见 `07-subagent` SA3)。
- **不管运行期 subagent 派发**:那是 `07-subagent`(运行期,`wrap_tool_call`);本域只管**编译期**引用解析(SUBGRAPH)。两者不同生命周期(断层#7)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 子图寻址 | `resolve_skill(skill_id)` 按 registry / `search_paths` 解析**逻辑 id** | 子图**绝对 `path`** 直接解析,删 registry/id/dotted-id/多命中(RS1) |
| resolver 职责 | id→root 寻址 + 本地 search_paths 查找 | 只剩**边界校验 + 合法性校验**(RS2) |
| DI 纪律 | 代码已显式注入 | 文档明确"不全局化"(RS4) |

> **验**:公共入口省略 resolver → 使用默认本地 resolver;无法命中目标 skill 时是 `[F-v3-skill-not-registered]` 而不是 `[F-v3-resolver-missing]`;SUBGRAPH/subagent target 递归解析正确 + 循环引用防护;中间件不绕过 resolver 重新解析。

## 读代码主路径提示
协议 `skill_resolver_protocol.py:33` → 缺失防护 `:80` → 本地实现 `local_workspace_resolver.py:15` → 消费方 loader(见 `01-compile`)。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-compile`(用它递归解析)· `05-run-inner/07-subagent`(运行期对照,断层#7)· `data-contracts`(LocalWorkspaceResolver 导出)
