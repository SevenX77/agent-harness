---
module: 02-mechanism/07-runtime
doc: mvp1-alignment
status: drafted（机制·入口;B live 且 public API 干净;A 顶层契约 §2/§3 已成文;bootstrap 文档化 + 死簇清理=impl 归 kiro）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·入口）
---

# 07-runtime — 机制 B · 顶层入口(入口)

> **Tier**: 机制层 B · 入口(外顶) | **Owns**: `run_skill`/`predict_skill` 两个执行**模式** · bootstrap(初始化) · public API surface(`__all__`) | **现状**: ⏳(public API 已 live 且干净;待顶层契约成文 + bootstrap 文档化) | **Related**: `03-api-contract`(实现它定义的 API)· `03-assemble`(assemble_graph)· `data-contracts`(`__all__`/RunResult)· 全模块(runtime 是顶层组装者)

## 1. 定义
runtime = 引擎**最顶层的公共入口**:`run_skill`(真跑)/`predict_skill`(干跑)是**两个执行模式**(同一图,predict 换 mock model);bootstrap 初始化(注册表/配置/checkpointer);对外暴露哪些符号(`__all__` public API surface)。它**实现** `03-api-contract`(C 层)定义的操作 API。

## 2. 数据流 / 机制
⏳ **非空白,public API 已 live 且干净**(`__init__.py`:**19 个稳定导出**,分组[执行/静态分析/装配/state/解析/异常]+ 文档 + `mypy --strict no_implicit_reexport`,`test_public_api_contract` 守;内部 helper 明确不进 public ABI)。`run_skill`/`predict_skill` live 在 `runner.py`。runtime 把 16 模块**组装成可调用引擎**:入口收 skill+输入 → bootstrap(`resolve_checkpointer` + model_resolver + `assemble_graph`)→ 跑外层 StateGraph(`graph-exec`)→ 返回 `RunResult`。**缺的是顶层契约成文 + bootstrap 文档化,不是代码。** ⚠️ 文档里入口类 `GraphAgentHarness` 在死簇里**根本不存在** → 删引用(live 走 runner→assemble_graph)。

## 3. 接口契约(本域核心)
- `run_skill`/`predict_skill` 签名 + `RunResult` 返回(签名权威 `03-api-contract`,形状 `data-contracts`)。
- public API surface:`__all__` 符号集(现 19,`test_public_api_contract` 守),增删须过 `test_public_api_contract`。
- bootstrap 初始化契约(checkpointer/注册表/配置注入;DI 显式,见 `02-resolver`)。

## 4. 设计决策基础(用户原话)
> predict 是模式(2026-06-03 PM):run/predict 是 runtime 里两个执行模式,非独立域。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RT1 | run/predict = 两个执行**模式**(非独立域) | predict 只是换 mock model 的同一图执行 |
| RT2 | public API surface(`__all__`)增删过契约 | 对外稳定面被 studio/外部依赖 |

## 6. 测试关键点
1. `test_public_api_contract`:`__all__` 符号集稳定,增删显式过契约。
2. run_skill 端到端:skill+输入 → RunResult,各模块正确组装。
3. predict 模式:换 mock model,产物写 `runs/<run_id>/`,`RunResult.source="predict"`。

## 7. 涉及 region / platform
engine 全权;public API surface 被 studio / 外部 SDK 消费者依赖。

## 8. gaps / 待设计(⏳ live+clean,文档化为主)
1. **public API surface 已干净**(19 导出 + `test_public_api_contract` 守)——非待设计;增删过契约即可。
2. **bootstrap 文档化**:`resolve_checkpointer` / model_resolver / 注册表注入(DI 显式,见 `02-resolver`)的顶层装配契约成文。
3. 死簇 `GraphAgentHarness` 删引用(它不存在,live 走 runner→assemble_graph;`01-compile` 删死代码联动)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `03-api-contract`(实现它)· `03-assemble`(assemble_graph)· `data-contracts`(`__all__`/RunResult)· `02-resolver`(DI 注入)
