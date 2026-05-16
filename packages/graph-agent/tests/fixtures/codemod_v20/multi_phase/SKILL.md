---
schema_version: "2.0"
name: batch-analysis
description: >
  Analyze a single batch (10 chapters) across 7 dimensions with entity registration and narrative continuity checking.
  Star topology: entity+character analysis runs first, other paths consume entity list.
  Use for each batch in story deconstruction pipeline.
type: graph
context_mapping:
  batch_events: "{input.batch_events}"
  accumulated_context: "{input.accumulated_context}"
  para_text_lookup: "{input.para_text_lookup}"
  dynamic_dimensions: "{input.dynamic_dimensions}"
  chapter_range: "{input.chapter_range}"
  batch_events_text: ""
  accumulated_context_text: ""
  batch_chapter_range: ""
  batch_event_count: ""
  dynamic_dimensions_hint: ""
  character_latest_states_text: ""
  batch_character_changes_text: ""
  tension_results: ""
  character_results: ""
  prop_results: ""
  arc_results: ""
  foreshadowing_results: ""
  spatiotemporal_results: ""
  system_results: ""
  entity_registry: ""
  batch_result: ""
io:
  inputs:
    - name: batch_events
      type: list
      source: runtime
    - name: accumulated_context
      type: dict
      source: runtime
    - name: para_text_lookup
      type: dict
      source: runtime
    - name: dynamic_dimensions
      type: list
      source: runtime
    - name: chapter_range
      type: list
      source: runtime
  outputs:
    - name: batch_result
      type: dict
      target: artifact
    - name: updated_accumulated
      type: dict
      target: artifact
phases:
  - name: prepare
    mode: logic
    execute_steps:
      - script.accumulator.load_accumulated_state
      - script.accumulator.build_batch_context_text
      - script.paths.format_batch_events
  - name: entity_and_characters
    mode: llm
    llm_role: analyst
    max_iterations: 15
    max_nudges: 3
    agent_tools:
      - script.entity.register_entity
      - script.entity.resolve_alias
      - script.entity.get_entity_registry_summary
      - script.paths.analyze_character_changes
    output_schema: script.models.BatchAnalysisReport
    prompt: |
      你是角色分析和实体管理专家。你的任务是分析批次内所有事件中的角色，同时注册和消歧实体。
      ## 任务1：实体注册与消歧（星形拓扑中心）
      对批次中出现的每个角色/地点/道具：
      1. 检查是否已在实体注册表中存在（调用 get_entity_registry_summary 查看）
      2. 如果是新实体 → 调用 register_entity 注册
      3. 如果是已有实体的别名 → 调用 resolve_alias 关联
      4. ID格式：角色 CHR_NNN，地点 LOC_NNN，道具 PRP_NNN
      **消歧规则**：
      - 名称完全匹配 → 同一实体
      - 称呼/别名（如"老公"→已知角色名）→ resolve_alias
      - 代词无法确认指代 → 跳过，不创建实体
      - 外貌描述变化不等于新实体（换衣服≠换人）
      ## 任务2：角色状态分析
      对每个事件中的角色，分析：
      - characters_involved: 参与角色列表
      - character_states: 每个角色的状态快照（appearance, clothing, makeup, hygiene, injuries, health, emotion, social_position, key_relationships, is_inferred）
      - character_changes: 状态变化记录（character, field, from, to）
      **状态推断规则**：
      - clothing → hygiene 联动（脏衣服 = 脏）
      - injuries → health 联动
      - 前序批次状态优先继承，无变化不重复记录
      - is_inferred: 标记推断字段（非原文明确描述的）
      {dynamic_dimensions_hint}
      ## 执行步骤
      1. 调用 get_entity_registry_summary 查看已有实体
      2. 遍历每个事件，识别角色/地点/道具
      3. 对新实体调用 register_entity，对别名调用 resolve_alias
      4. 调用 analyze_character_changes 分析角色状态
      5. 调用 finish_task 报告完成
    user_prompt_template: |
      ## 批次事件（第{batch_chapter_range}章）
      {batch_events_text}
      ## 前序累积上下文
      {accumulated_context_text}
      请完成实体注册和角色状态分析。
  - name: parallel_analysis
    mode: llm
    llm_role: analyst
    max_iterations: 20
    max_nudges: 3
    agent_tools:
      - script.paths.analyze_tension_emotion_vibe
      - script.paths.analyze_system_evolution
      - script.paths.analyze_prop_changes
      - script.paths.analyze_emotional_arcs
      - script.paths.analyze_foreshadowing
      - script.paths.analyze_spatiotemporal
    output_schema: script.models.BatchAnalysisReport
    prompt: |
      你是叙事分析编排器。你的任务是调用 6 个分析工具，对批次内的事件做多维度分析。
      ## 需要调用的 6 个分析工具
      每个工具会执行一条独立的 LLM 分析路径并返回结果摘要。请依次调用：
      1. **analyze_tension_emotion_vibe** — 张力/情绪/光影氛围分析
         - 输出：每个事件的 climax_intensity(0-10), climax_type, emotion_intensity(0-10), emotion_type, lighting_vibe
      2. **analyze_system_evolution** — 系统演化分析（仅C类事件）
         - 输出：system_actions, updated_parameters
      3. **analyze_prop_changes** — 道具变化分析
         - 输出：每个事件的 props_involved, prop_changes
      4. **analyze_emotional_arcs** — 情感弧线分析
         - 输出：arc_moments（跨批次复用 arc_id）
      5. **analyze_foreshadowing** — 伏笔追踪分析
         - 输出：foreshadowing_plant, foreshadowing_payoff（跨批次复用 fs_id）
      6. **analyze_spatiotemporal** — 时空标准化分析
         - 输出：time_coordinate, normalized_location, scene_space_type, location_visual_change
      ## 执行步骤
      1. 依次调用所有 6 个分析工具
      2. 每个工具返回结果摘要后继续下一个
      3. 全部完成后调用 finish_task
      注意：实体注册表已在上一阶段完成，这些工具会使用已注册的实体 ID。
    user_prompt_template: |
      批次范围：第{batch_chapter_range}章
      事件数量：{batch_event_count}
      请依次调用 6 个分析工具完成多维度分析。
  - name: continuity
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 2
    agent_tools:
      - script.continuity.check_continuity
      - script.continuity.log_continuity_warning
    output_schema: script.models.BatchAnalysisReport
    prompt: |
      你是叙事连续性检查专家。你的任务是检查本批次的分析结果与前序批次之间是否存在矛盾。
      ## 检查维度
      1. **角色外貌连续性**：角色的外貌描述是否前后一致？衣服变化必须有事件支撑。
      2. **道具状态连续性**：道具的持有者/状态变化是否合理？
      3. **时空连续性**：时间是否单向推进？地点变化是否有合理路径？
      4. **角色存活连续性**：已"死亡"的角色是否在后续事件中再次出场？
      ## 判断标准
      - 衣服/妆容变化：需要有"换装""梳洗"等事件支撑，否则标记为矛盾
      - 合理变化：受伤后衣服脏了、战斗后外貌变化 → 不是矛盾
      - 推断 vs 显式：is_inferred=true 的字段矛盾可标记为 warning 而非 error
      ## 执行步骤
      1. 调用 check_continuity 进行自动化检查
      2. 对发现的问题调用 log_continuity_warning 记录
      3. 调用 finish_task 报告结果
    user_prompt_template: |
      请检查本批次（第{batch_chapter_range}章）的分析结果与前序累积状态之间的连续性。
      ## 前序角色最新状态
      {character_latest_states_text}
      ## 本批次角色变化
      {batch_character_changes_text}
      检查是否存在矛盾，记录所有 warning。
  - name: assemble
    mode: logic
    execute_steps:
      - script.paths.assemble_batch_results
      - script.accumulator.update_accumulator
      - script.accumulator.save_accumulated_state
    validator: script.validators.validate_batch_analysis

---
<!-- TODO(schema-2.0): assemble phase lost max_retries=1 / retry_target=parallel_analysis (LogicPhase has no retry semantics in 2.0). -->
