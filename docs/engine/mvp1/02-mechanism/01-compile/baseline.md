---
module: 02-mechanism/01-compile
doc: baseline
status: audited-ready（现状对齐 pinned 代码 7cd4b9c；编译机制 = loader 校验流水线 + compiler 缓存壳）
---

# 01-compile — Baseline(当下代码实现逻辑)

> **Scope**: 把磁盘 skill 源码读进来 → 校验 → 编成可信 AST(`CompiledSkill`)的引擎机制:`compiler.py`(公开入口+缓存)、`loader.py`(SkillLoader 校验流水线,1700 行)、`purity.py`(纯度扫描器)、`module_sandbox.py`(导入隔离)。
> **现状一句话**:`compile_skill`(`compiler.py:41`)是带缓存的公开壳,真正干活的是 `SkillLoader.compile_skill`(`loader.py:146`)——它跑一整套校验(拓扑无环/无孤岛、IO 契约、mention 可达、action/tool 签名、**purity**),通过出 `CompiledSkill`,否则抛带 `[F-v3-*]` 码的错误。**编译期只读源码、不执行 action、不调 Agent。**

## UI/UX
N/A —— 纯 backend。编译错误以 `[F-v3-*]` 码 + `CompileIssue` 暴露,studio 编辑器 / copilot 消费(渲染归 studio)。

## 前端逻辑
N/A。

## 后端功能

### 1. 公开入口 + 缓存(compiler.py)
`compile_skill(skill_root, *, skill_resolver, cache=True, ...)`(`compiler.py:41`)是公开编译入口:开 cache 时先 `compute_cache_key(skill_root)` → `load_from_cache`(`:57-60`)命中直接返回;否则编译完 `save_to_cache`(`:64-65`)。产出经 `CompileResult`(`:23`,含 `fatals()`/`warnings()`/`passed()`)+ `CompileIssue`(`:15`)聚合。
> **`CompiledSkill` 第一次出现需定义**:编译产物 = 可信 AST(manifest / phases / tools / subagents 等),是下游装配(`03-assemble`)的输入。

### 2. SkillLoader.compile_skill + 递归防护(loader.py)
`SkillLoader`(`loader.py:134`)的 `compile_skill`(`:146`)是校验主体。递归编译(SUBGRAPH / subagent 的 child skill)用 `_loading_stack` 防环 → `[F-v3-compile-recursion-cycle]`(`:157-161`)。

### 3. 校验流水线(loader.py,逐项 `[F-v3-*]`)
- **拓扑**:`_validate_graph_topology`(`:1006`)→ `_validate_acyclic_graph`(`:1138`,DFS 检环 → `[F-v3-graph-phase-cycle]` `:1153`)+ `_validate_no_islands`(`:1165`,从 input 不可达 → `[F-v3-graph-phase-island]` `:1184`)。
- **phase 声明 / 依赖**:`_validate_graph_phase_declarations`(`:1046`)、`_validate_phase_name_sets`(`:1079`)、`_validate_unknown_dependencies`(`:1125`)。
- **IO 契约**:`_validate_subgraph_io_contracts`(`:528`)。
- **引用**:`_validate_agent_reference_paths`(`:559`)、mention 可达 `scan_mentions` / `first_broken_mention`(`mentions.py`,import `:30`)。
- **action/tool 签名**:`_validate_action_signature`(`:808`)、`_validate_tool_signature`(`:836`)。
- **purity**:`_raise_on_purity_violations`(`:763`)→ `scan_python_purity`(`:764`)有 violation → `[F-v3-logic-action-purity-violation]`(`:770`)+ `_purity_fatal`(`:362/:772`)。

### 4. purity 扫描器(purity.py)
`scan_python_purity(path)`(`purity.py:134`)对一个 Python 源文件做 AST walk,收集 purity hard-ban 违规(返回 `PurityViolation` `:11`)。现状已覆盖 `run_skill` 编排调用、`open` / `io.open`、`pathlib.Path` 读/探测/枚举/变更、`os` / `os.path` 文件系统访问或变更、`shutil` 变更、`tempfile`、`glob`、`sys.path` mutation 调用与赋值/删除目标、`importlib` / `__import__` 动态导入。`scan_tool_imports_context`(`purity.py:165`)扫工具导入上下文。
> **现状局限**:这是针对 loader 识别出的 skill-local action/tool 文件的静态 AST 启发式扫描,不执行代码、不做全仓扫描,也不替代 `module_sandbox`。LOGIC action 的纯签名、Context mutation 退场、非序列化返回等仍归 `graph-exec` / `skill-syntax` 后续目标。

### 5. module_sandbox(导入隔离)
`module_sandbox.py`(208 行)把 skill 本地 Python 导入隔离,不污染全局 `sys.modules`(loader 加载 skill 代码时用)。

## API
- `compile_skill(skill_root, *, skill_resolver, cache=True) -> CompiledSkill`(`compiler.py:41`)——公开;签名权威归 `03-api-contract`,产出形状归 `data-contracts`。
- `SkillLoader(...).compile_skill(root)`(`loader.py:146`)——内部校验主体。
- `scan_python_purity(path) -> list[PurityViolation]`(`purity.py:134`)。

## Data Model / State
产出 `CompiledSkill`(可信 AST)+ `CompileResult` / `CompileIssue`(`compiler.py:23/15`);错误经 `make_error_payload([F-v3-*])`(`ErrorPayload` 归 `data-contracts`)。无运行时 state——编译期是纯函数(同源码同产物,缓存友好)。

## 当前边界(这个模块现在不是什么)
- **不执行 action、不调 Agent**:只读源码 + 校验(可调 resolver 做 skill root 可达性检查)。
- **读不到 `.workspace`**:compile 只看 skill 源码树 → golden 失效**不在编译期**(mvp1 移 eval 期,见 `compile-rules` CR3 / `golden-eval`)。
- **purity 是编译期源码门**:已挡 skill-local action/tool 源码里的 `run_skill`、直接 FS、`sys.path`、动态 import 高风险路径；运行期执行范式仍看 `graph-exec`。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| purity 范围 | 已挡 local-write、`run_skill`、直接 FS、`sys.path`、动态 import 高风险路径(`purity.py:134`) | 剩余 LOGIC 纯签名/Context mutation/非序列化返回等由 run-outer 与 skill-syntax 后续收口 |
| golden 失效 | 编译期无(读不到 workspace) | eval 期(`golden-eval`) |
| iterate 码 | 无 | 新增 `[F-v3-iterate-*]` 进 ERROR_REGISTRY |
| 死簇 | `graph_builder`/`phase_executor`/`phase_nodes`(~1900 行)仍在 | 删(live 走 `assemble_graph`) |

> **验"是否按 mvp1 改了"**:① action 里写 `run_skill`/碰 FS/改 `sys.path`/动态 import 是否触发编译期 `[F-v3-logic-action-purity-violation]`;② golden-stale 是否不再在编译期报;③ 死簇是否删净。

## 读代码主路径提示
`compile_skill`(`compiler.py:41`)→ 缓存 miss → `SkillLoader.compile_skill`(`loader.py:146`)→ 校验流水线(拓扑 `:1138/1165`、IO `:528`、签名 `:808/836`、purity `:763`)。purity 细节看 `purity.py:134`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-contract/03-compile-rules`(规则+码+生命周期契约,双向)· `02-resolver`(子图解析)· `03-assemble`(下游)· `data-contracts`(CompiledSkill/ErrorPayload)
