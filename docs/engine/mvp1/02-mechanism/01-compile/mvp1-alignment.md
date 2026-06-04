---
module: 02-mechanism/01-compile
doc: mvp1-alignment
status: drafted（机制·编译期;⏳ 成段 + 死簇清理归 kiro）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·编译）
---

# 01-compile — 机制 B · 编译机制

> **Tier**: 机制层 B · 编译期 | **Owns**: loader · parser · 校验器实现(DAG/IO/mention/**purity 扫描器**)· `module_sandbox`(导入隔离)· cache · serializer | **现状**: ⏳ | **Related**: `compile-rules`(它实现的规则)· `02-resolver`(子图解析)· `03-assemble`(下游)· `data-contracts`(产出 AST)

## 1. 定义
compile = 把磁盘 skill 源码**读进来 → 校验 → 编译成可信 AST**(或聚合 `[F-v3-*]`)的引擎机制。它是 `compile-rules`(契约 A)的**实现**:规则定义"怎么判",本域是"判的代码"。**编译期不执行 action、不调业务 Agent**(可调 resolver 做 skill root 可达性检查)。

## 2. 数据流 / 机制
读根 GRAPH.md → 解析 frontmatter/拓扑/phase 节点 → DAG 无环/孤岛 + IO 数据流 + mention 可达 + **purity 扫描** → 出 AST。机制细节(时序)权威在 mvp0 `12-compile-runtime-flow`,本域链接不复制。
- **purity 扫描器**(`purity.py`,AST walk 挡文件写)在此;**规则**("action 要纯"+ 码)在 `compile-rules`(双向引用)。
- **`module_sandbox`**(`module_sandbox.py`,把 skill 本地 Python 导入隔离、不污染 sys.modules)是 loader 加载 skill 代码的机制,在此。
- cache(源 hash 重编)、serializer(图序列化,供 studio `/graph/serialize`)。

## 3. 接口契约
`compile_skill(root,*,chat_model?,cache,skill_resolver) -> CompiledSkill`(签名归 `03-api-contract`;CompiledSkill/CompileResult 形状归 `data-contracts`);用 `02-resolver` 解析 SUBGRAPH/subagent 的 target_skill。

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

## 8. gaps / 待设计
1. 成段化 loader/compiler 实现机制(现散在 mvp0 + 代码)。
2. **死簇清理**(~1900 行 legacy `graph_builder`/`phase_executor`/`phase_nodes`,live 走 `assemble_graph`)+ 消 `md2json` 重复 → kiro 实施。
3. 换 create_agent 节点内核后编译/序列化契约是否成立(断层#5)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-contract/03-compile-rules`(规则,双向)· `02-resolver` · `03-assemble` · `data-contracts` · mvp0/`12-compile-runtime-flow`(FROZEN)
