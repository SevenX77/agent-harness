# round-14 现状调研: Task B skill-compilation cutover

署名：a2
日期：2026-05-25

## 污染溯源：为何出现错误前提的 spec
在 2026-05-23 的 `e485261` commit 中，旧的 `02-graph-md-spec.md` 将 `GRAPH.md` 中 body XML 的 `<phase>` 标签定义为需要被剔除的遗产，取而代之的是纯 YAML 的 `phases: list[str]`。
这就导致了上一版 round-14 spec 和 WIP 代码错误地将 `loader.py` 中的 `_extract_phase_attrs` (读取 body 的 DAG 连线) 给删掉了。

而真实情况（PM 于 5-24 拍板的 `00-FORMAT-GROUND-TRUTH.md`）是双轨制：
- frontmatter `phases` 只做注册（不含 depends_on 连线，因为 YAML 层级表示 DAG 不直观）。
- body `<phase>` XML 做 DAG 拓扑连线。

因此，我们在 round-14 必须**重新恢复 XML 的提取正则**，但将其作为 DAG 连线的唯一事实来源，与 frontmatter registry 互相校验，而不是把它当作兼容 V2.1 的垃圾代码删掉。

## AST 内部状态与文件推导论证
**核心问题**：为什么要求用户在 `LOGIC.md` 或 `SKILL.md` 的 frontmatter 里写 `mode: logic` 是错的？
1. **冗余且易致分歧**：物理文件名（`LOGIC.md`）已经从结构上决定了其行为。要求作者再写一次 `mode` 违反了 DRY (Don't Repeat Yourself) 原则。
2. **校验成本高**：上一版代码中 `loader.py:625` 的 `_validate_mode_matches_filename` 就暴露出这种冗余设计的代价——框架不仅要读 YAML，还要对比文件名是否合法，不一致时抛出的异常让用户很困惑。
3. **架构解法**：Pydantic 的 `Field(discriminator="mode")` 确实非常适合用来做联合类型的多态反序列化。所以，我们的解法是在 AST (`manifest.py`) 中**保留 `mode` 字段**，但在 `loader.py` 读取时，**从文件名自动推导字符串并动态注入进解析前的字典中**。这样既让开发者免去手写之苦，又保持了 Python 代码类型推导的严谨性。

## Example 的双机制拆分溯源
先前的版本把 inline 案例（直接注入 prompt）和 document 案例（按需读取的大文档）混在一个 YAML `content` 字段里，甚至允许 `content` 写多行字符串，这在长 prompt 下会破坏 YAML 的可读性。
PM 决议：
- 短 inline 案例：必须像 `<step>` 那样写在 body 的 `<example id="xx">` 标签内。
- 长 document 案例：放在 frontmatter 的 `examples: [{id, path, summary}]` 中，不加载原文，只暴露给 `read_example` tool。
因此在 AST `AgentNodeAST` 解析层面，我们需要单独新增一个 `<example>` XML 正则捕获流。

## 为什么 Cognitive Template (C2) 移出 round-14
认知模板的 8 插槽装配（`{skill_steps_splat}`, `{aligned_concepts_and_critical_corrections_markdown}` 等）不仅涉及字符串替换，还涉及：
1. `knowledge_base` subagent 的 pre-run 装配逻辑。
2. `<exit_contract>` 从 `SKILL.md` 中剥离并在装配层 Hardcode 追加 output_schema 的逻辑。
将其塞入静态 AST 编译的 Task B 中，会使得原本只需要校验 Pydantic 解析结果的纯静态测试，演变为高度依赖 LLM chain 初始化、上下文注入和 string mock 的高成本 E2E 测试。将其隔离，是维护 PR 高内聚 (Cohesion) 的必要架构策略。