---
module: 02-mechanism/01-compile
doc: mvp1-alignment
status: audited-ready（**U12 单元锁定 2026-06-05**;§2 编译流水线机制已成段、现状/目标 demarcate;死簇清理 + purity LE2 扩展归 kiro;文件未 FROZEN）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·编译）
---

# 01-compile — 机制 B · 编译机制

> **Tier**: 机制层 B · 编译期 | **Owns**: loader · parser · 校验器实现(DAG/IO/mention/**purity 扫描器**)· `module_sandbox`(导入隔离)· cache · serializer | **现状**: ⏳ | **Related**: `compile-rules`(它实现的规则)· `02-resolver`(子图解析)· `03-assemble`(下游)· `data-contracts`(产出 AST)

## 1. 定义
compile = 把磁盘 skill 源码**读进来 → 校验 → 编译成可信 AST**(或聚合 `[F-v3-*]`)的引擎机制。它是 `compile-rules`(契约 A)的**实现**:规则定义"怎么判",本域是"判的代码"。**编译期不执行 action、不调业务 Agent**(可调 resolver 做 skill root 可达性检查)。

## 2. 数据流 / 机制
编译机制 = `SkillLoader.compile_skill`(`loader.py:146`)一条校验流水线(生命周期时序契约定义在 `compile-rules` §2.1,本域是其**实现**,链接不复制):
1. **读 + 解析**:读根 `GRAPH.md` → 解析 frontmatter / 拓扑 / phase 节点(SKILL/LOGIC/SUBGRAPH);递归编译 child skill(SUBGRAPH/subagent)经 `_loading_stack` 防环(`[F-v3-compile-recursion-cycle]`)。
2. **校验**(逐项 `[F-v3-*]`):DAG 无环(`_validate_acyclic_graph`)/ 无孤岛 · phase 声明 + 依赖 · IO 契约(`_validate_subgraph_io_contracts`)· mention 可达(`scan_mentions`)· action/tool 签名 · **purity**(`_raise_on_purity_violations` → `scan_python_purity`)。
3. **出 AST**:全过 → `CompiledSkill`(可信 AST,供 `03-assemble`);否则聚合 `[F-v3-*]` 抛错。
- **purity 扫描器**(`purity.py:scan_python_purity`,AST walk)在本域;**规则**("action 要纯" + 码)在 `compile-rules`(双向)。**现状**只挡 local-write API;**目标 delta**:扩硬禁 `run_skill`/FS/`sys.path`(LE2,归 `graph-exec`/kiro)。
- **`module_sandbox`**(`module_sandbox.py`,skill 本地 Python 导入隔离、不污染 `sys.modules`)= loader 加载 skill 代码的机制,在本域。
- **cache**(源 hash 重编,`compute_cache_key`)、**serializer**(图序列化,供 studio `/graph/serialize`)。
- **编译期纯函数**:只读源码、不执行 action、不调 Agent;读不到 `.workspace` → golden 失效**不在编译期**(移 eval 期,见 `compile-rules` CR3 / `golden-eval`)。
- **topology projection(尽力而为投影,repair view 专用)**(`topology_projection.py:load_graph_topology_projection`)是 §2 主编译流水线**之外**的独立辅助机制:Studio 的 repair 态画布(D2,见 `docs/studio/mvp1/01_workflows/01_init.md`:"不卡导入 ... 我们有 compile, 有 copilot")靠它在 skill 编译不过时仍把 `phases`/DAG 画出来,让用户能看着改。**决策(2026-07-03)**:严格编译路径(`parse_markdown_parts`)把整份 frontmatter 当一份原子 YAML 文档——`io.*` 里一个无关的重复 key 会连累语法完全正常的 `phases` 一起读不出来,导致 repair 画布连"看着改"这个前提都没了。修法是新增 `parse_markdown_parts_best_effort`(容忍 `ruamel.yaml` 的 duplicate-key,last-value-wins),**只给 topology projection 这类"repair 视图"消费者用**;编译期主路径继续严格拒绝重复 key(仍是 `[F-v3-*]` 该报的错,不受影响)。若 frontmatter 连 best-effort 都解不出(真正语法损坏,不只是重复 key),原样抛出,由调用方(Studio `_graph_topology_projection_or_empty`)按既有约定降级为 `([], [])` 并记 WARNING。

## 3. 接口契约
`compile_skill(root,*,chat_model?,cache,skill_resolver) -> CompiledSkill`(签名归 `03-api-contract`;CompiledSkill/CompileResult 形状归 `data-contracts`);用 `02-resolver` 解析 SUBGRAPH 的 `path`；subagent 的 `target_skill` 属运行期委派机制。

## 4. 设计决策基础(用户原话)
> loader 与 compile 关系(2026-06-03 PM):"loader 加载 skill 和 compile 有什么关系?" → loader 就是编译期机制本身(读→解析→校验→AST);它执行的规则归 compile-rules,它本身(loader/purity 扫描器/sandbox)是机制。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CP1 | 本域是 `compile-rules` 的**实现**(规则在契约,代码在机制) | 契约 vs 机制分层 |
| CP2 | purity 扫描器 + module_sandbox 在此(规则在 compile-rules) | 它们是编译期对 skill 代码的门控实现 |

## 6. 测试关键点
1. 各 `[F-v3-*]` 规则的扫描器正确触发(对照 compile-rules 测试点)。
2. module_sandbox 导入 skill 本地类不泄漏 sys.modules。
3. cache:源不变命中、源变重编。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计(实现项归 kiro/TDD)
1. ~~成段化 loader/compiler 实现机制~~(✅ §2 已成段,2026-06-05)。
2. **死簇清理**(~1900 行 legacy `graph_builder`/`phase_executor`/`phase_nodes`,live 走 `assemble_graph`)+ 消 `md2json` 重复 → kiro 实施。
3. **purity LE2 扩展**:硬禁 `run_skill`/FS/`sys.path`(现只挡 local-write API)→ kiro。
4. 换 create_agent 节点内核后编译/序列化契约是否成立(断层#5)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-contract/03-compile-rules`(规则 + 生命周期契约 §2,双向)· `02-resolver` · `03-assemble` · `data-contracts`
