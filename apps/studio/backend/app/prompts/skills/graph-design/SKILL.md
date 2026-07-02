---
name: graph-design
description: 从需求出发设计一个 graph_skill（phase 拆分、DAG、io schema）的方法论。用户要"新建一个 skill"、"把某个流程做成技能图"、或对现有图做结构性重构时使用。
---

# Graph 流程设计方法论

顺序：先定边界 → 再切 phase → 再连 DAG → 再定每段 io → 最后落地。骨架每一步都编译验证，不要一口气写完再编。

## 1. 定输入输出边界（根 io）
- 问清楚：这个 skill 的**最小输入**是什么、**交付物**是什么？写成根 `io:` 的 JSON schema。
- 输入定义不清就开始切 phase = 返工的最大来源；宁可先跟用户确认。

## 2. 切 phase（单一职责）
每个 phase 一句话说清"吃什么、产出什么、怎么产出"。按"怎么产出"选模式：
- **确定性逻辑**（解析/过滤/格式转换/聚合）→ `LOGIC.md` + Python action，**能确定性做的绝不上 LLM**。
- **需要理解/生成**（判断、抽取语义、写作）→ agent 行为（精确语法查挂载 spec）。
- **一段可复用的子流程** → `SUBGRAPH.md` 子图。
- **已有现成 skill 能干** → `SKILL.md` 委派。
拆分粒度判据：一个 phase 的输出能被独立验证（能写 golden）；不能验证的 phase 要么太大要么职责不清。

## 3. 连 DAG
- 入口 `depends_on="input"`，终点标 `output`；依赖只连"真的读了它输出"的上游，不连保险性依赖。
- 无依赖关系的 phase 天然并行，不要人为串行。

## 4. 逐段定 io schema
- 上游输出 schema = 下游输入 schema 的超集；字段名/类型逐个对齐。
- 字段宁少勿多：每个字段都应该有明确的消费者。

## 5. 落地节奏
1. 先写 GRAPH.md 骨架（frontmatter + `<phase>` DAG）→ Compile 过。
2. 逐个 phase 建目录 + 模式文件（先空实现）→ 每加一个 Compile 一次。
3. 填实现 → Predict 空跑验证数据流 → Run。
三处名字（frontmatter phases / body `<phase>` / 目录名）每一步都保持一致。

## 反模式
- ❌ 一个 phase 里又解析又判断又生成（拆）。
- ❌ 用 agent 做正则能做的事。
- ❌ 整图写完才第一次编译。
- ❌ io schema 里塞"以后可能用"的字段。
