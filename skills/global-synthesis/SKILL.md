---
schema_version: "2.0"
name: global-synthesis
description: >
  Global analysis after all batches complete. Performs climax ranking, foreshadowing closure, character ranking, scene assembly, and retroactive correction.
  Use as final stage of story deconstruction pipeline.
type: graph
context_mapping:
  batch_outputs: "{input.batch_outputs}"
  accumulated_context: "{input.accumulated_context}"
  entity_registry: "{input.entity_registry}"
  total_batches: ""
  total_events: ""
  total_characters: ""
  inferred_events_count: ""
  climax_ranking: ""
  character_ranking: ""
  foreshadowing_closure: ""
  unified_event_stream: ""
  scenes: ""
  story_framework: ""
io:
  inputs:
    - name: batch_outputs
      type: list
      source: runtime
    - name: accumulated_context
      type: dict
      source: runtime
    - name: entity_registry
      type: dict
      source: runtime
  outputs:
    - name: story_framework
      type: dict
      target: artifact
phases:
  - name: global_analysis
    mode: llm
    llm_role: gemini
    max_iterations: 15
    max_nudges: 3
    agent_tools:
      - script.synthesis.rank_climaxes
      - script.synthesis.close_foreshadowing
      - script.synthesis.rank_characters
    output_schema: script.models.GlobalSynthesisReport
    prompt: |
      你是叙事全局分析专家。所有批次分析已完成，你需要从全局视角做 3 项综合分析。
      ## 分析1：高潮排名
      调用 rank_climaxes 工具：
      - 从所有批次收集 climax_intensity > 0 的事件
      - 全局归一化（最高=10，最低=1-3）
      - 输出排序后的高潮列表
      ## 分析2：伏笔闭合
      调用 close_foreshadowing 工具：
      - 检查所有 foreshadowing 记录
      - 验证 open 状态是否仍然有效
      - 标记 resolved/open/abandoned
      - 输出完整闭合状态
      ## 分析3：角色排名
      调用 rank_characters 工具：
      - 统计每个角色的出场次数和变化次数
      - 合并别名（同一角色不同称呼）
      - 按重要性排序
      - 角色分类：主角/主角团/反派/次要配角/边缘角色
      ## 执行步骤
      1. 依次调用 3 个分析工具
      2. 全部完成后调用 finish_task
    user_prompt_template: |
      全部 {total_batches} 个批次已分析完毕。请完成全局综合分析。
      总事件数：{total_events}
      总角色数：{total_characters}
  - name: scene_assembly
    mode: logic
    execute_steps:
      - script.scene_builder.build_unified_event_stream
  - name: retroactive
    mode: llm
    llm_role: gemini
    max_iterations: 10
    max_nudges: 2
    agent_tools:
      - script.retroactive.scan_anchor_points
      - script.retroactive.apply_corrections
    output_schema: script.models.GlobalSynthesisReport
    prompt: |
      你是回溯修正专家。你的任务是用锚定事实修正之前批次中的推断值。
      ## 回溯修正逻辑
      1. 遍历所有事件，找到 is_inferred 字段非空的事件
      2. 在全时间线中搜索"锚定事实"——原文明确描述的值
      3. 用锚定事实回溯修正之前的推断值
      ## 可修正字段
      clothing, makeup, hygiene, injuries, key_relationships, social_position, normalized_location, lighting_vibe, time_coordinate.absolute_date
      ## 不可修正字段（独立判断，不受锚定影响）
      scene_space_type, climax_intensity, emotion_type
      ## 修正格式
      每条修正记录：event_id, field, corrected_value, anchor_event_id, reason
      ## 执行步骤
      1. 调用 scan_anchor_points 扫描锚定事实
      2. 调用 apply_corrections 应用修正
      3. 调用 finish_task 报告
    user_prompt_template: |
      请扫描全时间线，找到锚定事实并回溯修正推断值。
      总事件数：{total_events}
      含推断字段的事件数：{inferred_events_count}
  - name: export
    mode: logic
    execute_steps:
      - script.scene_builder.export_story_framework
    validator: script.validators.validate_global_synthesis

---
<!-- TODO(schema-2.0): export phase lost max_retries=1 / retry_target=global_analysis (LogicPhase has no retry semantics in 2.0). -->
