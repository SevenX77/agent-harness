---
module: 01-contract/02-skill-syntax
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；子图语法现状=target_skill 逻辑 id=被 mvp1 path 反转；🚨 其余部件语法真相待迁 mvp1）
---

# 02-skill-syntax — Baseline(当下代码实现逻辑)

> **Scope**: skill 文件语法的**现状代码**:四 phase(GRAPH/LOGIC/SUBGRAPH/SKILL)的 frontmatter 解析 + AST。本文聚焦**子图语法现状**(本次 scope);其余部件语法的现状散在 `core/`,真相待 mvp1 自写(见 mvp1-alignment §2 真空报警)。
> **现状一句话**:子图节点 `SUBGRAPH.md` 现在用 **`target_skill`**(逻辑 skill id,`manifest.py:104` `Field(pattern=SKILL_ID_PATTERN)`,子图/subagent 引用同款)引用;agent `SKILL.md` 的 `subgraphs[]`(`manifest.py:175`)每项也用 `target_skill`。⚠️ 这套**逻辑 id** 是 mvp1 要反转的旧模型——mvp1 改 **绝对 path**(见 mvp1-alignment §2.1)。

## UI/UX
N/A。

## 前端逻辑
N/A —— skill 源码语法被 studio 编辑器/copilot 消费。

## 后端功能

### 1. 子图语法现状(target_skill 逻辑 id)
- `SUBGRAPH.md` frontmatter:`target_skill: <逻辑 id>`(AST `loader.py:87` `target_skill: str`;schema `manifest.py:104` `Field(pattern=SKILL_ID_PATTERN)` = 逻辑 id 正则,**不是路径**)。
- agent `SKILL.md` 的 `subgraphs[]`:`manifest.py:175` `subgraphs: list[AgentRegistryItem]`,每项 `target_skill`。
- 父子图 io **严格 1:1** 校验:`loader.py:528` `_validate_subgraph_io_contracts` → 不匹配报 `[F-v3-subgraph-io-mismatch]`(`loader.py:553`)。
- 禁路径:`error_registry.py:58` `[F-v3-subgraph-target-skill-invalid]`(现状禁止写路径)。

### 2. 其余语法部件(现状散 core/,语法真相待 mvp1)
GRAPH/LOGIC/SKILL/cognitive/mention/resource 的 frontmatter 解析在 `core/`(manifest/parser/mention/template/schema_engine);**语法正文真相** mvp0 弃用后待自写进 mvp1(见 mvp1-alignment §2/§8 🚨 真空报警)。本次只动子图,不展开其余。

## API
- 子图 AST:`SubgraphNode.target_skill`(`loader.py:87`)、`AgentRegistryItem`(`manifest.py:156/175`)。

## Data Model / State
skill 源码(语法)→ AST(`Phase`/`SubgraphNode`/`AgentRegistryItem`,归 `data-contracts`)。

## 当前边界(这个模块现在不是什么)
- 子图引用现状是**逻辑 id(target_skill)**,不是 path——正是 mvp1 要反转的。
- 其余部件语法 mvp1 尚未自写(真空债)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 子图引用字段 | `target_skill`(逻辑 id,`manifest.py:104`) | `path`(绝对路径) |
| 子图路径 | 禁止(`[F-v3-subgraph-target-skill-invalid]`) | path 即绝对路径(标准) |
| 父子 io | 严格 1:1(`_validate_subgraph_io_contracts` `loader.py:528`) | 放宽,黑板字段过滤 |

> **验"是否按 mvp1 改了"**:① `SUBGRAPH.md` / `subgraphs[]` 解析 `path`(绝对)而非 `target_skill`;② 写 `target_skill` 报未知字段;③ 不再有父子 io 1:1 校验(`_validate_subgraph_io_contracts` 移除/改)。

## 读代码主路径提示
子图 AST `loader.py:87` → schema `manifest.py:104/156/175` → io 1:1 校验 `loader.py:528` → 解析 `resolve_skill_root`(`loader.py:539/609`,归 `02-resolver`)。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-mechanism/02-resolver`(子图解析现状/目标)· `01-physical-layout`(子图落点)· `data-contracts`(AST)
