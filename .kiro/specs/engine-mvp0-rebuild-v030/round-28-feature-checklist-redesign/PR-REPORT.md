# Round 28 PR Report — Feature Checklist Redesign

## 1. 这轮设计是什么

这轮的目标是把 PM 的黄金原则变成可守住的工程门禁: 功能和 API 一个都不能少, 已经承诺出去的能力不能在没人发现的情况下被删掉、合并掉、改弱掉。

上一轮 Round 27 已经把公开 API 和 14 份引擎规格文档冻结成契约基线。Round 28 做的是下一层: 把"功能合规清单"从一份人工维护的文本清单, 升级成一套机器能检查、人也能读懂的 manifest 系统。

这套系统把引擎里的每个业务能力都登记成一个 feature。每个 feature 都必须说明它守的业务能力是什么、由哪些源码支撑、由哪些测试守门、拥有哪些错误码和事件。它还配了三张清单: 一张说明每个源码文件属于哪个能力, 一张说明公开 API 和内部契约章节对应哪些能力, 一张说明 consumer 和 vendor-only 债务怎么归属。

最后, 这套清单接进 CI。以后任何人改引擎, 如果漏登记功能、漏登记 API、引用了不存在的 feature、一个错误码被多个 feature 抢 primary owner, CI 都会红, PR 不能合入。

为了迁移安全, 旧的 Round 27 清单没有直接扔掉, 而是进入 dual-run。旧的 30 项 strict hard lock 被升级成 Round 28 的 35 项 strict hard lock: feature 数量、checklist 条目数、覆盖测试引用数都锁死为 35, 漂移就失败。

## 2. 是否按设计完成

结论: 已按设计完成, 并且经过机器测试和双审。

机器审计层已经跑通。当前系统登记了 35 个真实业务 feature, 不是一个大 umbrella 凑数。121 个引擎源码文件全部归类, 当前分布是 61 个核心 feature 文件、60 个 detail 文件。65 个公开 API、53 个内部规格章节、6 个 vendor-only 契约项都映射到了具体 feature, 没有悬空引用。

错误码和事件也被穷尽检查。92 个 concrete 引擎错误码和 33 个事件类型, 每一个都恰好有 1 个 primary owner feature。也就是说, 以后某个错误语义或事件语义变化时, reviewer 能明确知道是哪条业务能力负责。

测试证据是 CI 模式实跑通过: 从仓库根目录运行, 模拟 GitHub Actions 的真实工作目录。Round 28 契约 manifest 测试 18 项全绿; 新增 5 类机制守护测试全绿; 全套 graph-agent 测试结果是 1071 passed, 2 skipped, 19 xfailed, 0 failed。

审计证据也闭环。a2 在测试设计审计中确认红灯不是假红灯, jsonschema 和 subprocess 都是真断言。a3 作为 PM 替身在后续审计中抓到过一次真实问题: 初版把 121 个源码文件塞进一个 umbrella feature, 黄金原则保障度只有 30%。这个问题已经修掉, manifest 被拆成 35 个有业务意义的 feature, a3 后续 verdict 确认保障度提升到 95%, CI gate 真正接入, 反向 cross-check 有效。

还有一个反漂移问题也被审计抓到并修复: 初版把旧清单锁改成了动态计数加最低 30 的弱保护, 会失去 Round 27 strict hard lock 的价值。现在已经改回 Round 28 hard lock: 35 features、35 checklist 条目、35 覆盖引用, 任一漂移都会失败。

## 3. 完成后怎么守门

从 PM 角度看, Round 28 之后的规则很简单: 改引擎可以, 但不能偷偷改。

以后有人新增、修改或删除任何引擎源码文件, 都必须说明这个文件属于哪个业务能力。如果它是核心实现, 要进对应 feature 的核心路径; 如果只是实现细节, 也要挂到一个父 feature。否则 CI 会发现源码文件没有归属。

以后有人新增错误码或事件, 也必须指定它属于哪个 feature 的 primary owner。一个错误码不能没人负责, 也不能两个 feature 同时说自己是 primary owner。否则 CI 会失败。

以后有人改公开 API、内部规格章节或 consumer 契约, 也必须映射到 feature。公开 API 漏映射、vendor-only 契约漏登记、引用不存在的 feature, 都会被机器挡住。

这套机制允许加功能, 但不允许静默减少功能。要删除、降级或豁免已有能力, 必须显式写出原因, 走 PM approval 和 exemption 记录。也就是说, Round 28 把"功能/API 一个都不能少"从口头原则变成了合并前硬门。

## 已知限制

这轮新增的 5 类机制守护测试主要是"结构不准被删"的文本级锁, 例如检查 prompt 槽位、middleware 顺序、sandbox 关键字和错误注册表形状还在。它们不是完整 runtime 行为验证器, 作用是防止核心系统结构被静默删改。

非功能契约类型当前放开到 12 个值, 比原任务要求的 10 个基础值多了 `determinism` 和 `security`。这是 additive 扩展, 不降低原有要求。

runtime compatibility 的识别目前靠 feature 名称或描述里含有 compatibility 语义。当前只有 1 个 runtime compatibility feature, 能满足本轮守门; 未来如果这类 feature 变多, 应升级成显式字段, 避免靠文字匹配。

旧 dual-run checklist 的路径保留了, 但内容已经从 Round 27 的 30 项文本清单切到 Round 28 的 35 项 manifest 反向生成清单。这是 cutover 风格的保留, 不是同时保留两份旧内容。

## 4. 旧 30 项去向表

这张表用 Round 27 checklist commit `6cd143e` 的 30 项做基线。结论是: 30 项没有静默删除; 它们要么保留为同名能力, 要么被拆到更精确的新 feature, 要么并入更大的生命周期 feature。没有本轮降级项, 因此没有新增 exemption_id。

| 旧项 | 去向 | 新 feature |
| --- | --- | --- |
| LP-01 Markdown frontmatter/body split | 保留 | `F-md-frontmatter-parsing` |
| LP-02 CRLF markdown parsing | 合并 | `F-md-frontmatter-parsing` |
| LP-03 missing frontmatter fail-fast | 合并 | `F-md-frontmatter-parsing` |
| LP-04 GRAPH phase registry + body DAG | 保留 | `F-graph-skill-loading` |
| LP-05 physical phase ambiguity rejection | 合并 | `F-graph-skill-loading` |
| LP-06 Agent inline examples for mentions | 拆分 | `F-agent-phase-orchestration`, `F-mention-resolution` |
| CV-01 legacy schema root rejection | 合并 | `F-compile-runtime-flow` |
| CV-02 V0.3.0 schema marker | 合并 | `F-graph-skill-loading` |
| CV-03 duplicate phase registration | 合并 | `F-graph-skill-loading` |
| CV-04 graph cycle rejection | 合并 | `F-graph-skill-loading` |
| CV-05 subgraph input contract validation | 保留 | `F-subgraph-delegation` |
| CV-06 injected skill resolver facade | 保留 | `F-skill-resolution` |
| ER-01 run_skill root-shape error | 合并 | `F-runtime-execution` |
| ER-02 PhaseNode updated runtime state | 合并 | `F-runtime-execution` |
| ER-03 non-LLM phases route to code nodes | 合并 | `F-logic-action-execution` |
| ER-04 validation node string error normalization | 合并 | `F-runtime-execution` |
| ER-05 assemble_graph resolver requirement | 合并 | `F-skill-resolution`, `F-graph-assembly` |
| ER-06 callback emission after callback failure | 保留 | `F-callback-event-stream` |
| SB-01 blackboard reducer merge | 保留 | `F-state-blackboard` |
| SB-02 undeclared output rejection | 合并 | `F-state-blackboard` |
| SB-03 phase wrapper IO mapping | 合并 | `F-state-blackboard` |
| SB-04 reference reader sandbox isolation | 拆分 | `F-resource-reference-access`, `F-state-blackboard` |
| SB-05 cache round-trip preservation | 保留 | `F-checkpoint-persistence` |
| SB-06 nested IO hoist paths | 保留 | `F-storage-io` |
| OE-01 callback event union | 保留 | `F-callback-event-stream` |
| OE-02 typed tracing output | 保留 | `F-callback-tracing` |
| OE-03 error payload registry metadata | 保留 | `F-error-code-recovery` |
| OE-04 error registry/spec key set | 合并 | `F-error-code-recovery` |
| OE-05 trace save failure error | 合并 | `F-callback-tracing` |
| OE-06 LLM usage metrics | 合并 | `F-observability-metrics` |

## 证据摘要

- Round 28 manifest 契约测试: 18 passed。
- Round 28 机制守护测试: 5 passed。
- 全套 graph-agent 回归: 1071 passed, 2 skipped, 19 xfailed, 0 failed。
- a2 audit: 红灯设计为真实断言, 不是假红灯。
- a3 audit: umbrella gaming 已被抓出并修复, 35 个 feature 是业务有意义的拆分, CI gate 已真接入。
