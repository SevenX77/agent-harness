---
module: 01-contract/01-physical-layout
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；现状无 subgraph/ 约定目录、子图靠 target_skill 逻辑 id；🚨 workspace 户型待迁 mvp1）
---

# 01-physical-layout — Baseline(当下代码实现逻辑)

> **Scope**: 磁盘文件结构的**现状代码**:skill 源码树校验(loader 从根向下)+ workspace 入口。聚焦**子图物理现状**(本次 scope)。
> **现状一句话**:loader 从 skill root 向下校验物理结构(`loader.py:154/183` root/`GRAPH.md`、`:372` `_guard_v030_root`),phase 节点在 `phases/<id>/`、文件名→类型(`loader.py:51` `"SUBGRAPH.md": "subgraph"`)。⚠️ **现状没有 `subgraph/` 约定目录**——子图靠 `target_skill`(逻辑 id)经 resolver/registry 找物理位置,**位置不在 skill 布局里**;mvp1 改成子图默认落 `<skill_root>/subgraph/`、绝对 path(见 mvp1-alignment §2.1)。

## UI/UX
N/A。

## 前端逻辑
N/A —— 布局被 loader 校验、被 studio 文件树消费。

## 后端功能

### 1. skill 源码树校验现状(loader 从根向下)
- root 入口 `GRAPH.md`:`loader.py:183` `graph_path = root / "GRAPH.md"`;`loader.py:372` `_guard_v030_root`(缺 GRAPH.md FATAL)。
- phase 节点:`phases/<id>/` 下 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 三选一;文件名→类型 `loader.py:51`(`"SUBGRAPH.md": "subgraph"` 等);缺/多报 `[F-v3-graph-phase-node-missing]`/`[F-v3-graph-phase-mode-ambiguous]`(`loader.py:442/1219`)。
- 配套目录:references/、examples/(可选)。**代码现状无 `subskills/` 目录**(`grep subskills` 在 `src/` 下为空——`subskills` 仅是 mvp0 spec 遗留概念,代码不消费;engine 统一用 `subgraph/`)。

### 2. 子图物理现状(无 subgraph/ 约定)
- **现状无 `subgraph/` 目录约定**:子图不靠物理位置,靠 `target_skill`(逻辑 id,`manifest.py:104`)经 `resolve_skill_root`(`loader.py:539`,归 `02-resolver`)找 root——物理位置由 resolver/registry 决定、**不在 skill 源码树布局里**。
- mvp1 反转:子图默认落 `<skill_root>/subgraph/<name>/`、绝对 path、递归自包含。

### 3. workspace 入口现状
`run_skill`/`predict_skill` 校验 `workspace_dir`(绝对路径)——产物落 `runs/<run_id>/`。

## API
- 物理校验入口:`loader.py:154`(`compile_skill(skill_root)`)、`loader.py:372` `_guard_v030_root`。

## Data Model / State
磁盘目录树 → loader 校验 → AST。无运行时 state。

## 当前边界(这个模块现在不是什么)
- 现状**无 subgraph/ 约定目录**——子图物理位置不在 skill 布局里(靠 target_skill + resolver)。
- workspace 运行时户型字段正文现状散在旧文档,mvp1 待自写(🚨 真空债)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 子图落点 | 无约定目录;靠 target_skill 逻辑 id + resolver | `<skill_root>/subgraph/<name>/` 默认 + 绝对 path + 递归自包含 |
| workspace 户型 | 现状代码 live(runner 校验 workspace_dir) | 户型字段正文自写进 mvp1(🚨 待补) |

> **验"是否按 mvp1 改了"**:① 新建子图默认落 `<skill_root>/subgraph/<name>/`、是完整 graph skill;② 孙图递归在 `<name>/subgraph/<name2>/`;③ 子图位置由物理 path 定(不再靠 target_skill 逻辑 id + resolver registry 寻址)。

## 读代码主路径提示
根校验 `loader.py:154/183/372` → 文件名→类型 `loader.py:51` → 子图解析 `resolve_skill_root`(`loader.py:539`,归 `02-resolver`)→ workspace 入口 `runner.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-skill-syntax`(子图 path 语法)· `02-mechanism/02-resolver`(子图解析)· `05-run-inner/06-golden-eval`(workspace golden)
