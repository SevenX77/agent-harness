# Copilot Playbooks

<summary>
  <purpose>给 Studio Copilot 的路由指令层。接到用户请求后, 先匹配一个 scenario, 再按 required_docs 读取规则真相, 最后按 workflow 使用 Read/Write/Edit/Bash 工具操作工作区。</purpose>
  <single_source_of_truth>本文件不复制 skill 格式正文。格式、字段、错误码、编译和运行规则的唯一真相在 docs/engine/skill-spec/。执行任何新建、修改、排障前, 必须重新读取 scenario.required_docs 指向的最新 spec。</single_source_of_truth>
  <few_shot_sources>需要真实写法示范时, 读取 skills/ 下现有 skill。优先按 workflow 指定目录查找, 不要把示例当成比 skill-spec 更新的格式真相。</few_shot_sources>
</summary>

<scenario name="new_skill">
  <intent>用户要求新建 skill、新工作流、新图、把自然语言流程落成可运行 graph skill。触发词示例: "新建 skill"、"做一个工作流"、"帮我搭一个 graph"、"把这个流程变成 skill"。</intent>
  <required_docs>
    - docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md
    - docs/engine/skill-spec/01-physical-layout.md
    - docs/engine/skill-spec/02-graph-md-spec.md
    - docs/engine/skill-spec/03-logic-md-spec.md
    - docs/engine/skill-spec/04-subgraph-md-spec.md
    - docs/engine/skill-spec/05-agent-md-spec.md
    - docs/engine/skill-spec/07-mention-syntax-spec.md
    - docs/engine/skill-spec/08-resource-mechanisms-spec.md
  </required_docs>
  <workflow>
    1. [Read] 读取用户指定或当前 workspace 的目标目录, 确认是否已有 GRAPH.md、phases/、references/、examples/ 或同名 skill, 避免覆盖用户文件。
    2. [Read] 读取 required_docs。先以 00-FORMAT-GROUND-TRUTH.md 确认双轨制、文件类型、frontmatter/body 分工; 再用 01/02 确认目录、GRAPH.md、DAG、根 IO; 用 03/05 确认 Logic/Agent phase 写法。
    3. [Read] 如用户要引用资料、案例、工具、协议或跨节点资源, 读取 07/08 确认 @mention 与 references/examples 注册方式。
    4. [Read] 需要 few-shot 时读取 skills/ 下相近示范; 仅把它当作风格和文件组织参考, 不覆盖 required_docs 的规则。
    5. [Write] 创建 skill root、GRAPH.md、phases/&lt;phase_id&gt;/ 下唯一节点文件。根据用户流程选择 LOGIC.md、SKILL.md 或 SUBGRAPH.md; 每个 phase 目录只放一种节点文件。
    6. [Write] 为 GRAPH.md 同时写 frontmatter phases 注册和 body &lt;phase depends_on="..."&gt; 拓扑; 入口依赖 input, 输出节点标 output。
    7. [Write] 为每个 phase 写 inline io.inputs/io.outputs。Agent prompt 内容写 SKILL.md body XML; 确定性 Python 步骤写 LOGIC.md actions; 不写已退役的外部 IO 文件。
    8. [Bash] 如仓库提供编译或校验命令, 运行最小校验; 若失败, 按错误码回到对应 required_docs 修正。
  </workflow>
</scenario>

<scenario name="optimize_skill">
  <intent>用户要求优化已有 skill 的效果、拆分复杂 prompt、减少上下文污染、增加资料/示例、拆 subagent/map-reduce 或把大流程拆成子图。触发词示例: "优化这个 skill"、"效果不稳定"、"拆成子任务"、"加 reference/example"、"map-reduce"。</intent>
  <required_docs>
    - docs/engine/skill-spec/01-physical-layout.md
    - docs/engine/skill-spec/02-graph-md-spec.md
    - docs/engine/skill-spec/03-logic-md-spec.md
    - docs/engine/skill-spec/04-subgraph-md-spec.md
    - docs/engine/skill-spec/05-agent-md-spec.md
    - docs/engine/skill-spec/06-cognitive-template-spec.md
    - docs/engine/skill-spec/07-mention-syntax-spec.md
    - docs/engine/skill-spec/08-resource-mechanisms-spec.md
    - docs/engine/skill-spec/11-error-code-spec.md
    - docs/engine/skill-spec/12-compile-runtime-flow-spec.md
  </required_docs>
  <workflow>
    1. [Read] 读取目标 skill 的 GRAPH.md、相关 phases/*/SKILL.md、LOGIC.md、SUBGRAPH.md、references/、examples/。
    2. [Read] 读取 required_docs。用 06 判断 prompt 内容应落入 role/goal/step/protocol/example 哪个模板槽; 用 08 判断资料应作为 reference 还是 example; 用 04 判断是否应拆成 SUBGRAPH.md。
    3. [Read] 需要 few-shot 时读取 skills/text-segmentation/、skills/story-deconstruction/ 或其他相近 skills/ 条目, 对照其 role/goal/step/protocol/example 的组织方式。
    4. [Edit] 优先做局部优化: 收紧 goal、拆清 step、补 protocol、补 inline example、把长案例移到 examples/ document registry、把领域资料移到 references/ registry。
    5. [Edit] 复杂流程才拆 phase 或 subgraph。新增/改名 phase 时同步更新 GRAPH.md frontmatter phases、body DAG、物理目录和 IO。
    6. [Edit] 如新增 @reference/@example/@protocol/@step/@subagent/@subgraph/@tool, 同步更新对应 registry 或 body 定义, 再按 07 做可达性自查。
    7. [Bash] 运行可用的编译/校验命令; 若出现错误码, 先读 11-error-code-spec.md 对应行, 再修正。
  </workflow>
</scenario>

<scenario name="fix_bug">
  <intent>用户提供编译错误、运行错误、Studio 报错、F-v3 错误码或说 skill 跑不起来。触发词示例: "修 bug"、"编译失败"、"运行失败"、"报 F-v3-..."、"为什么这个 skill 不工作"。</intent>
  <required_docs>
    - docs/engine/skill-spec/01-physical-layout.md
    - docs/engine/skill-spec/02-graph-md-spec.md
    - docs/engine/skill-spec/03-logic-md-spec.md
    - docs/engine/skill-spec/04-subgraph-md-spec.md
    - docs/engine/skill-spec/05-agent-md-spec.md
    - docs/engine/skill-spec/07-mention-syntax-spec.md
    - docs/engine/skill-spec/08-resource-mechanisms-spec.md
    - docs/engine/skill-spec/11-error-code-spec.md
    - docs/engine/skill-spec/12-compile-runtime-flow-spec.md
  </required_docs>
  <workflow>
    1. [Read] 收集用户给出的错误码、报错文本、失败阶段、目标 skill 路径和最近修改文件。
    2. [Read] 先读 11-error-code-spec.md, 用错误码定位 domain、阶段、修复方向和对应 spec 链接。
    3. [Read] 再读 12-compile-runtime-flow-spec.md, 判断失败发生在编译期、装配期还是运行期; 不把运行期症状误改成编译期结构。
    4. [Read] 读取目标 skill 相关文件。按错误 domain 补读 01/02/03/04/05/07/08 中的对应契约。
    5. [Edit] 做最小修复。常见修复包括: 对齐 GRAPH.md phases/body/目录名; 修正 inline IO schema; 保证 phase 目录只有一个节点文件; 补 action/validator; 补 reference/example path 或 summary; 修正 @mention 目标。
    6. [Bash] 重新运行触发失败的最小命令或仓库校验命令。
    7. [Read] 若新错误码出现, 回到第 2 步; 若没有可运行命令, 至少静态复查错误码对应 spec 的字段表。
  </workflow>
</scenario>

<scenario name="analyze_trace">
  <intent>用户要求分析一次执行 trace、定位失败节点、解释为什么某个输出不对、根据 trace 排障。触发词示例: "分析 trace"、"这次运行为什么失败"、"看执行记录"、"哪个节点出错"、"为什么下游没拿到字段"。</intent>
  <required_docs>
    - docs/engine/skill-spec/02-graph-md-spec.md
    - docs/engine/skill-spec/03-logic-md-spec.md
    - docs/engine/skill-spec/04-subgraph-md-spec.md
    - docs/engine/skill-spec/05-agent-md-spec.md
    - docs/engine/skill-spec/06-cognitive-template-spec.md
    - docs/engine/skill-spec/08-resource-mechanisms-spec.md
    - docs/engine/skill-spec/11-error-code-spec.md
    - docs/engine/skill-spec/12-compile-runtime-flow-spec.md
  </required_docs>
  <workflow>
    1. [Read] 读取 trace 或用户贴出的 trace 摘要, 先定位 failed/error 节点、错误码、phase_id、输入 slice、候选输出、工具调用和下游缺字段位置。
    2. [Read] 读取 12-compile-runtime-flow-spec.md, 用运行时流程解释该节点处于 root input 校验、StateMapper slice、phase run、output validate、StateMapper merge 还是 final output 校验。
    3. [Read] 读取 11-error-code-spec.md, 将 trace 中的 F-v3 错误码映射到 domain 和修复方向。
    4. [Read] 读取目标 skill 的 GRAPH.md 和失败 phase 文件。用 02 校验 DAG 与数据流来源; 用 03/04/05 判断 Logic/Subgraph/Agent 的输入输出边界。
    5. [Read] 若失败节点是 Agent, 同时读 06/08 并检查最终 prompt 装配来源: role、goal、steps、protocols、references、examples、output_schema。关注 trace 中 prompt 输入是否缺少用户预期资料, 不读取 tracing 内部实现文档作为格式真相。
    6. [Edit] 只在定位到格式或契约问题时修改 skill 文件。典型修复是补上游输出字段、修正 phase io、补 required source、修 prompt protocol/example、修 reference/example registry。
    7. [Bash] 如有复现命令, 用同样输入重新运行并对比新 trace 的 failed node、inputs、outputs 和错误码。
  </workflow>
</scenario>

<scenario name="edit_prompt">
  <intent>用户要求写或修改 Agent phase prompt、role/goal/step/protocol/example、@mention 引用、输出格式要求或边界案例。触发词示例: "改 prompt"、"写 phase prompt"、"加协议"、"加示例"、"引用这份资料"、"让它按这个规则判断"。</intent>
  <required_docs>
    - docs/engine/skill-spec/05-agent-md-spec.md
    - docs/engine/skill-spec/06-cognitive-template-spec.md
    - docs/engine/skill-spec/07-mention-syntax-spec.md
    - docs/engine/skill-spec/08-resource-mechanisms-spec.md
  </required_docs>
  <workflow>
    1. [Read] 读取目标 phases/&lt;phase_id&gt;/SKILL.md、相关 references/、examples/ 和用户要改的业务规则。
    2. [Read] 读取 05-agent-md-spec.md, 确认 SKILL.md frontmatter 字段和 body 允许标签; 不新增未定义顶级标签, 不写 exit_contract。
    3. [Read] 读取 06-cognitive-template-spec.md, 决定内容放入 role、goal、step、protocol、inline example、document example 或 reference registry。
    4. [Read] 读取 07/08, 校验 @mention 格式和目标可达域; 资料用 references, 长案例用 frontmatter examples, 短稳定案例用 body &lt;example id="..."&gt;。
    5. [Edit] 修改 SKILL.md。保持 body XML 顶层平铺; step/protocol/example id 唯一; @mention 目标必须在对应 registry 或 body 中存在。
    6. [Edit] 如新增 references/examples document, 新建对应文件并更新 frontmatter id/path/summary; 如只改 prompt, 不触碰无关 phase。
    7. [Bash] 运行可用校验命令; 若没有命令, 静态检查 XML 标签、frontmatter registry、@mention 与 io.outputs output_schema 是否一致。
  </workflow>
</scenario>
