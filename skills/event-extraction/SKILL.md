---
schema_version: "2.0"
name: event-extraction
description: >
  Extract event timeline from ABC-segmented paragraphs using 3-pass system.
  Pass 1: event aggregation + timeline reordering.
  Pass 1R: semantic coherence review.
  Pass 2: setting extraction + correlation.
  Use after text-segmentation completes.
type: graph
context_mapping:
  segmentation_result: "{input.segmentation_result}"
  chapter_number: "{input.chapter_number}"
  prev_chapter_last_event: "{input.prev_chapter_last_event}"
  formatted_paragraphs: ""
  events_raw: ""
  parsed_events: ""
  event_timeline: ""
io:
  inputs:
    - name: segmentation_result
      type: dict
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
    - name: prev_chapter_last_event
      type: dict
      source: runtime
  outputs:
    - name: event_timeline
      type: dict
      target: file
      path: "chapter_{context.chapter_number}_events.json"
phases:
  - name: setup
    mode: logic
    execute_steps:
      - script.extractor.format_segments_for_prompt
  - name: aggregate
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 2
    agent_tools:
      - script.extractor.parse_events
      - script.extractor.store_events
      - script.extractor.backup_event_timeline
    prompt: |
      你是专业的小说编辑和叙事分析师。你的任务是分析已分段的小说章节，完成两个任务：
      ## 任务1：时间线重排
      **核心原则**：小说的**段落顺序** ≠ **故事时间线顺序**
      **常见情况**：
      1. **细节展开**：后面的段落可能是前面事件的细节补充
      2. **回忆插叙**：某段落是对更早时间的回顾
      3. **平行叙事**：多个角色/地点的事件交替叙述
      **时间线判断依据**：
      - 明确时间标记（"几个月前"、"夜晚"、"第二天"）
      - 因果关系（A事件导致B事件）
      - 空间位置（从江城出发 → 路上 → 露营地）
      - 叙事逻辑（情节的自然发展顺序）
      ---
      ## 任务2：事件聚合
      **核心原则**：多个连续段落可能是同一个**事件**
      **聚合规则**：
      1. **语义连贯**：描述同一件事的不同方面
      2. **时空一致**：同一时间、同一地点的连续行为
      3. **细节展开**：一个段落是另一个段落的细节补充
      4. **描述性段落**：没有主体动作的描述段落应合并到相邻事件
      **重要**：
      - **C类段落必须独立成事件，严禁与B类段落混入同一个事件**
      - C类事件的类型标注为"C类-系统"，其他事件标注为"B类-事件"
      - 事件必须按**时间线顺序**排列，不是段落顺序
      - **每个段落只能归属一个事件，不允许共享**（严格 N:1）
      ## 执行步骤
      1. 仔细阅读 {formatted_paragraphs} 中的章节分段
      2. 按规则完成时间线重排和事件聚合
      3. 调用 parse_events 解析你的事件列表
      4. 调用 store_events 存储结果
      5. 调用 backup_event_timeline 备份数据（供 review 阶段使用）
      6. 调用 finish_task 报告完成
    user_prompt_template: |
      请分析以下已分段的章节，完成时间线重排和事件聚合：
      ## 章节分段结果（段落按原文顺序）
      {formatted_paragraphs}
      ---
      **输出格式**：
      # 第{chapter_number}章事件时间线
      ## 事件1：[事件概括]
      **类型**：B类-事件 或 C类-系统
      **包含段落**：[段落索引列表，如：1, 2, 3]
      **地点**：[简短地点名（原文位置原词）]
      **地点变化**：[相对上一事件的变化]
      **时间**：[标准时段词（原文时间原词），或精确日期时刻，或相对时间，或"时间未明确"]
      **时间变化**：[与上一事件的时间关系，无明确标记时写出推断理由]
      ---
      ## 事件2：[事件概括]
      ...
      **关键要求**：
      1. 事件按**故事时间线顺序**排列
      2. 段落索引必须非空，格式只写数字
      3. 事件概括简洁（20-30字）
      4. 所有段落都应归入某个事件，不遗漏
      5. 时间括号内只放原文原词，禁止填写自造补注
  - name: review
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 2
    agent_tools:
      - script.extractor.parse_events
      - script.extractor.safe_review_store_events
      - script.extractor.log_ambiguous_events
    prompt: |
      你是专业的小说编辑。你的任务是审查已初步提取的事件时间线，做两项核验。
      ## 核验任务1：逐事件时间/地点核查
      对每个事件，按以下两步操作：
      **第一步：通读连续原文**
      将该事件的所有段落原文（按顺序）在脑中拼合成一段连续文本，忽略段落标号和类型标签，像阅读一篇完整文章一样通读。感受：
      - 整体语义是否连贯？还是存在明显的视角/时态/场景跳变？
      - 文字的"现在感"：是在描述此刻正在发生的事，还是在回溯已经发生过的事？
      - 是否存在"几个月前/那时候/当时"等回溯词，且上下文叙事明显切换到另一个时间层？
      **第二步：结合段落边界做拆分判断**
      在语义层面判断完成后，再回到段落边界，决定是否需要拆分：
      - 语义上连贯、描述同一时间层的事件内容 → **不拆分**
      - 语义上发生了真实时态跳变 → **必须拆分**
      **拆分判断标准**：
      - 连续段落语义上描述的是同一时间发生的事 → 不拆分
      - 段落间存在叙事视角切换到"很久之前/几个月前"，且持续描述另一时间的事件 → 拆分
      - 同一段落内的简短回忆（仅一两句）→ 不拆分，标注"含背景回溯"
      - 世界背景穿插在当前叙事中 → 不拆分
      ## 核验任务2：章节整体时序验证
      把事件序列放回章节全文，验证：
      - 事件排列是否符合故事时间线
      - 是否存在遗漏的时间跳变节点
      - 相邻事件的地点/时间衔接是否合理
      ## 不确定的情况
      如果某个事件的归属拿不准，调用 log_ambiguous_events 记录。
      ## 执行步骤
      1. 逐事件核验，结合原文段落判断
      2. 输出修正后的完整事件列表（如果需要修改）
      3. 调用 parse_events 解析（如果输出了新的事件列表）
      4. 调用 safe_review_store_events 存储（会自动处理解析失败的情况）
      5. 调用 finish_task 报告完成
    user_prompt_template: |
      请审查以下事件时间线，结合章节完整段落做时间/地点核验。
      ## 初步提取的事件列表
      {events_raw}
      ---
      ## 章节完整段落
      {formatted_paragraphs}
      ---
      请完成两项核验，输出修正后的完整事件列表。
      若拆分了事件，新事件统一重新编号。
      每个事件须填写**审查备注**（若无修改写"无变化"）。
  - name: settings
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 2
    max_retries: 2
    retry_target: aggregate
    agent_tools:
      - script.extractor.parse_settings
      - script.extractor.merge_settings_into_events
      - script.extractor.finalize_event_timeline
    validator: script.validators.validate_event_extraction
    prompt: |
      你是专业的小说编辑和知识管理专家。你的任务是从事件的段落中识别并提炼世界设定知识，并对之前的结果做校验。
      ## 任务1：识别并提炼设定知识
      **核心原则**：读每个事件包含的所有段落，找出其中具有"世界设定"性质的内容——即解释这个小说世界运作规则的信息。
      **设定识别标准**：
      - 解释世界如何运作的普遍规则（"诡异无法被热武器杀死"、"序列超凡分为序列0-9"）
      - 读者不理解这段就看不懂后续情节的核心背景知识
      - 对所有人/长期有效的世界规则
      **不是设定的内容**：
      - 主角对设定的疑问/反应/识别
      - 主角的决策和行动
      - 普通场景描写和情节推进
      **提炼要求**：从段落原文中提炼核心知识点（50-100字），保留关键信息，去除冗余
      ---
      ## 任务2：校验事件结果
      **检查项**：
      1. 事件是否按时间线顺序排列？
      2. 段落聚合是否合理？
      3. 地点/时间变化是否正确？
      4. 是否有遗漏的段落？
      ## 执行步骤
      1. 阅读事件段落，识别设定内容
      2. 输出设定知识库
      3. 调用 parse_settings 解析设定
      4. 调用 merge_settings_into_events 合并到事件中
      5. 调用 finalize_event_timeline 生成最终时间线
      6. 调用 finish_task 报告完成
    user_prompt_template: |
      请从以下事件段落中识别世界设定内容，提炼为知识库，并校验事件结果。
      ## 事件时间线
      {events_raw}
      ---
      ## 章节完整段落
      {formatted_paragraphs}
      ---
      **输出格式**：
      # 第{chapter_number}章设定知识库
      ## 设定1：[设定标题]
      **段落**：[段落索引]
      **关联事件**：事件[事件序号]
      **核心知识点**：
      [提炼后的核心知识点，50-100字]
      ---
      **关键要求**：
      1. 只为具有"世界设定"性质的段落创建设定条目
      2. 核心知识点简洁完整（50-100字）
      3. 如发现事件问题，给出修正建议
---
