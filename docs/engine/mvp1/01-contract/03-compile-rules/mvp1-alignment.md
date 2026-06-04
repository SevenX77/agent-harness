---
module: 01-contract/03-compile-rules
doc: mvp1-alignment
status: drafted（♻️ mvp0 11/12 FROZEN + mvp1 delta: golden-stale 移 eval, 新码）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 03-compile-rules — 契约 A · 编译规则 + 错误码全表

> **Tier**: 契约层 A(声明式,喂 copilot) | **Owns**: 编译/装配/运行**生命周期契约** + 全部校验规则(DAG/IO/mention/purity/golden/iterate)+ `[F-v3-*]` 错误码全表 | **现状**: ♻️ mvp0 FROZEN + mvp1 delta | **Related**: `skill-syntax`(被校验的语法)· `01-compile`(规则的扫描器实现)· `invalidation`(失效规则)· `03-api-contract`(CompileResult)

## 1. 定义
compile-rules = skill **要满足什么才合法可编译**,以及 Loader **怎么判、错误怎么报**(`[F-v3-*]`)。这是喂 copilot 的核心——copilot 生成的 skill 必须过这些规则。**规则是声明式契约;扫描器实现归 `01-compile` 机制**(purity 规则在此,purity 扫描器在那)。

## 2. 三段生命周期契约(♻️ mvp0 `12-compile-runtime-flow` FROZEN)
| 段 | 输入→输出 | 主要规则 | 失败码族 |
|---|---|---|---|
| 编译期 | skill 源码 → 可信 AST | 物理结构、frontmatter、DAG 无环/无孤岛、IO 数据流、mention 可达、**action purity** | `[F-v3-graph-*]`/`[F-v3-logic-*]`/`[F-v3-mention-*]` |
| 装配期 | AST → 可运行节点 | reference reader、cognitive 模板渲染、tool 绑定 | `[F-v3-resource-*]`/`[F-v3-cognitive-*]`/`[F-v3-agent-tool-*]` |
| 运行时 | graph.invoke → 终态 | StateMapper slice/merge、节点执行、输出校验 | `[F-v3-runtime-*]`/`[F-v3-logic-validator-*]` |
> 错误码全表权威 = mvp0 `11-error-code-spec`(FROZEN);本域**汇总+链接,不复制全表**。

## 3. 接口契约
- `compile_skill(root, *, chat_model?, cache, skill_resolver) -> CompiledSkill`(签名归 `03-api-contract` C;CompileResult/CompileIssue 形状归 `data-contracts`)。
- 错误码命名 `[F-v3-<domain>-<detail>]` + 等级(FATAL/WARNING)+ stage 轴;`ErrorPayload` 形状归 `data-contracts`,Task3 加 line 轴。

## 4. 设计决策基础(用户原话)
> purity = compile 规则(2026-06-03 PM):"编译期 AST lint 和 compile 应该是同一块吧? 他们联系的底层逻辑是 compile 的规则 和那些错误码"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CR1 | 生命周期契约 + 错误码全表 ♻️ mvp0 11/12 FROZEN | 编译契约稳定,SSOT 在 mvp0 |
| CR2 | **purity 是 compile 的一条规则**(扫描器实现归 `01-compile` 机制) | 它报 `[F-v3-logic-action-purity-violation]`(编译期 FATAL),和 DAG/IO 校验同台机器 |
| CR3 | **golden 失效校验从编译期移到 eval 期** | golden 移 `.workspace`,compile 只读源码读不到 → `[F-v3-golden-stale-fields]` 不再是编译期码(见 `invalidation`) |
| CR4 | 新增 iterate 码(`[F-v3-iterate-*]`)进 ERROR_REGISTRY | mvp1 iterate 声明的编译校验 |

## 6. 测试关键点
1. DAG 无环/无孤岛、IO 数据流、mention 可达各报对应 `[F-v3-*]`。
2. action 写文件 → 编译期 `[F-v3-logic-action-purity-violation]` FATAL。
3. **golden-stale 不在编译期触发**(golden 在 workspace);改为 eval 时检查(与 `06-golden-eval`/`invalidation` 协同)。

## 7. 涉及 region / platform
engine 全权;规则全表喂 copilot(生成合法 skill 的依据)。

## 8. gaps / 待设计
1. golden-stale 从编译期码移到 eval-time 检查的具体处置(`[F-v3-golden-stale-fields]` 改归属)。
2. iterate 新码进 ERROR_REGISTRY(FROZEN 解冻,kiro)。
3. **LOGIC action 契约 V4 反写**(解冻 `03-logic-md-spec`):action 纯返回(砍 Context mutation)+ purity 扫描器扩展**硬禁** `run_skill`/FS/sys.path——权威设计在 `02-mechanism/04-run-outer/01-graph-exec` LE1-3;本域承接其错误码/编译期校验落点。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `skill-syntax` · `02-mechanism/01-compile`(扫描器实现)· `invalidation` · `data-contracts`(ErrorPayload)· `03-api-contract`(CompileResult)· mvp0/`11-error-code-spec` + `12-compile-runtime-flow-spec`(FROZEN)
