# Round-31 后续任务书 —— V2 基线重定(2026-05-31)

> 本文档只定义「待办任务 + 目标 + 基线 + 边界」,不预设实现方案。每个任务的实际设计(research→思路→design)走 SOP-08 §1.1 流程,届时由 a2/a1/a3 产出。
> PM 指令:写好任务书,**暂不开始实施**。

---

## 一、基线(最重要,先读)

- **主基线 = V2 分支 `codex/llm-platform-main-reconcile`**(LLM 平台 registry 模型;三方审计已确认设计扎实、黄金原则过)。
- **但 V2 不含 round-31 已完成的 PR-A / PR-B / PR-trace-bug**(实证三个 `merge-base` 全 NO)。所以真正的设计基线 = **V2 + 这 3 个 PR 的成果 reconcile 在一起**,不是单纯 V2。
- V2 对引擎核心的改动范围(已实证):
  - 改了 `core/runner.py`(model_resolver 注入)、`core/graph_assembler.py`(per-phase 模型解析,+48 行);
  - **没碰** `callbacks/` 和 tracing 目录 —— 所以 PR-D 的 tracing 主体逻辑仍以 main 现状为准,只需处理与 V2 在 runner/graph_assembler 的交叉点。

---

## 二、待办任务(按依赖排序)

### T0 —— 已完成的 PR-A/B/trace 独立合 main【不等 V2】
- **结论**:这 3 个 PR 独立于 LLM 平台、已完成、之前全绿,`wc/round31-api-design` 现状领先 main 17 / 落后 0 / 可干净合,**不需要等 V2**,本机自己落 main。
- **路径**:① 删尾部死的 `PR-C-design.md`(加删除 commit,不改写历史)→ ② 开 PR `wc/round31-api-design → main` → ③ CI 复验三绿(cutover,SOP-05)+ 查 main 最近 3 次 CI → ④ PM ack → ⑤ squash 合 main。
- **runner.py 交叉**:PR-B 与 V2 都改 runner,但谁后落谁解冲突。本机先落,V2(别人机器)晚落时由 V2 owner 解一次,**不是本机的事**。

### T1 —— V2 自身 cutover 收尾【让基线能合 main】
- **目标**:修 V2 留下的 CI 债(三方审计实测出的真实失败):
  1. SDK 有 3 个老测试还在 import 已删的 `llm_config`,导致整批测试 collection 阶段就崩;
  2. Studio copilot 有 4 个测试的假 route 对象缺新字段 `call_method_id`;
  3. 对外 API 契约有 4 项还引用已删符号,且 `assemble_graph` 签名变了没同步契约。
- **目标态**:基线 CI 三绿,可合 main(宪法 5,绝不 admin skip)。
- **归属**:见「需 PM 拍 #1」(本机收编 vs 另一台机器/V2 owner 自己修)。

### T2 —— 指纹基线对账
- **目标**:V2 建于 round-31 引入「对外 API 指纹守卫」机制之前,合进来会跟现有指纹基线打架。重新生成/对账指纹基线,纳入 V2 的新 API 形态。

### T3 —— PR-D 重新设计(tracing 默认落 + 事件订阅 + 真实分阶段事件)
- **目标(不变,沿用原 PR-D)**:
  1. tracing 默认自动落运行轨迹文件;
  2. 单一事件源 → 两个出口(轨迹文件 + 可选的外部事件订阅回调);把"用户继承回调类"的后门从对外面收掉,改成传一个回调函数;
  3. **还债**:把现在"批量预先合成的分阶段事件"换成"真实分阶段流式事件"(现状:崩溃时会显示还没跑的阶段已经 start,是黑匣子误导)。
- **基线**:V2 的 runner/graph_assembler。已有 main 基线的研究草稿(同目录 `PR-D-research-audit-findings.md` / `PR-D-idea.md`)大部分可复用,只需重对 V2 在 runner/graph_assembler 的交叉点。
- **边界**:不碰 predict(归 T4);不为 model_resolver 大改 runner 签名(V2 已定形态)。

### T4 —— PR-E 重新评估(predict + 缓存)
- **目标**:predict 缓存链式失效 + Gateway copilot bridge,在 V2 上重新界定 scope(V2 的 registry/resolver 已涉及 predict 的反向依赖,原 PR-E 的边界需重画)。

### T5 —— notable-models 降级补回
- **目标**:V2 把"配 API key 时输入框的建议模型占位符"从【后端动态、8 厂商、文档驱动】降级成【前端硬编码、6 厂商、其它兜底 gpt-5】,丢了 qiniu/wavespeed 两厂商的提示 + 可维护性。按黄金原则补回(补全前端表 + 重指向搬走的文档,或恢复文档驱动)。
- **严重度**:低(它只是输入建议,不挡用户手敲任意模型;但确属"功能少了一点")。

### T6 —— 统一迁移总览文档
- **目标**:V2 是 32 commit / 4.4 万行,目前缺一份"总共改了啥 + 现网怎么迁"的总览。补一份,方便把握影响面。(credential 凭据格式硬切那条,PM 已拍"没用户、不担心",可略。)

---

## 三、scope 边界(PM 2026-05-31:我只管自己的分支,不管别人的)

V2 是**另一台机器的分支** → V2 内部的事归 V2 owner(另一台机器),**不是本机的活**:

- **T1(修 V2 CI 债)、T5(notable-models 降级,在 V2/Studio 里)、T6(V2 迁移总览文档)= flag 给 V2 owner,本机不执行。**

**本机的活 = round-31 引擎本身的工作**,在 V2 落 main 后基于新 main 推进:

- **T0**(已完成的 PR-A/B/trace **独立合 main,不等 V2**)、**T2**(round-31 指纹基线对账)、**T3**(PR-D 重设计)、**T4**(PR-E 重评估)。
- T0 可立即推进(不依赖别人)。T3/T4 在 V2 落 main 后基于新代码做更稳,但也可在 wc 分支先起设计。

无待 PM 拍的方向项。合并顺序 / 分支命名 / test-first 切分等工程细节本机自驱。

---

## 四、合并顺序(我的自驱方案,先说明不抛你拍)

倾向:**T0+T1 先把「V2 + round-31 三 PR」reconcile 成一条干净基线 → CI 三绿 → 整体合 main(你 ack)**,而不是让 round-31 三 PR 和 V2 分别合 main 再撞车。理由:两条都改 runner.py,分别合会在 main 上产生二次冲突,合一处理一次更干净。T2–T6 在基线合 main 后(或基线分支上)按 SOP-08 逐个推进。
