---
schema_version: "2.0"
name: story-deconstruction
description: >
  Complete story deconstruction pipeline orchestrator. Segments chapters, extracts events, runs batch analysis with LLM-driven loop, then global synthesis.
  Use for full novel/screenplay analysis.
type: graph
context_mapping:
  chapters: "{input.chapters}"
  project_id: "{input.project_id}"
  all_segmentations: ""
  all_events: ""
  total_chapters: ""
  total_events: ""
  dynamic_dimensions: ""
  all_batch_results: ""
  accumulated_context: ""
  entity_registry: ""
  story_framework: ""
io:
  inputs:
    - name: chapters
      type: list
      source: runtime
    - name: project_id
      type: str
      source: runtime
  outputs:
    - name: story_framework
      type: dict
      target: artifact
phases:
  - name: segmentation
    mode: logic
    execute_steps:
      - script.orchestrator.segment_all_chapters
  - name: event_extraction
    mode: logic
    execute_steps:
      - script.orchestrator.extract_all_events
  - name: batch_loop
    mode: llm
    llm_role: analyst
    max_iterations: 50
    max_nudges: 5
    agent_tools:
      - script.orchestrator.discover_tracking_dimensions
      - script.orchestrator.prepare_next_batch
      - script.orchestrator.run_batch_analysis
      - script.orchestrator.check_all_batches_done
    prompt: |
      你是故事解构分析的编排器。你的任务是按批次（每10章一批）分析所有事件。
      ## 执行步骤
      1. 首先调用 discover_tracking_dimensions 发现动态追踪维度
      2. 调用 prepare_next_batch 获取下一批事件
      3. 调用 run_batch_analysis 运行批次分析
      4. 调用 check_all_batches_done 检查是否还有未处理的批次
      5. 如果还有批次，回到步骤2
      6. 所有批次处理完毕后，调用 finish_task 报告完成
      ## 重要
      - 每个批次必须按顺序处理（第1批 → 第2批 → ...）
      - 每个批次的结果会累积到下一个批次的上下文中
      - 如果某个批次失败，记录警告并继续下一批
    user_prompt_template: |
      项目：{project_id}
      总章节数：{total_chapters}
      总事件数：{total_events}
      请开始批次分析。
  - name: global_synthesis
    mode: delegate
    subgraph: ../global-synthesis/SKILL.md
    context_bridge:
      inputs:
        all_batch_results: batch_outputs
        final_accumulated: accumulated_context
        entity_registry: entity_registry
      outputs:
        story_framework: story_framework

---
