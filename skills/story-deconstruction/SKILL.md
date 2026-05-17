---
schema_version: "2.0"
name: story-deconstruction
description: >
  Complete story deconstruction pipeline (4 phases, all LLM-driven). Walks
  chapters through segmentation → event extraction → batched analysis → global
  synthesis, producing a story_framework artifact. Cross-skill composition was
  removed in MVP-0 B1 (2026-04-28) and returns in V2 via LangGraph Send API;
  for now each phase runs its own inline LLM work.
type: graph
context_mapping:
  chapters: "{input.chapters}"
  project_id: "{input.project_id}"
  formatted_chapters: ""
  segmented_chapters: ""
  events_by_chapter: ""
  total_chapters: ""
  total_events: ""
  all_batch_results: ""
  accumulated_context: ""
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
    mode: llm
    llm_role: analyst
    max_iterations: 8
    max_nudges: 2
    prompt: |
      你是文本预处理工程师。

      ## ⚠️ 退出契约
      最后一步必须调用 finish_task，把所有章节的分段结果写到 `segmented_chapters` 字段（dict[chapter_number] -> ABC 段落列表）。

      ## 任务
      逐章把原文切分成段落，并按 ABC 三类打标：
      - **A 类**: 主线推进段落 (有主体动作 / 关键决策 / 情节转折)
      - **B 类**: 细节展开 / 描写性段落 (附属于某个 A 类事件)
      - **C 类**: 系统说明 / 世界观介绍 / 旁白说明

      ## 输入
      - chapters: 章节列表，每项形如 `{"chapter_number": int, "content": str}`

      ## 输出
      调用 finish_task，往 `segmented_chapters` 字段写：
      ```
      {
        1: [{"para_index": 0, "type": "A", "text": "..."}, ...],
        2: [...],
      }
      ```
    user_prompt_template: |
      请对以下章节做 ABC 分段：
      {chapters}

  - name: event_extraction
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 3
    prompt: |
      你是叙事时间线分析师。

      ## ⚠️ 退出契约
      最后一步必须调用 finish_task，把每章的事件时间线写到 `events_by_chapter` 字段。

      ## 任务
      逐章把 ABC 分段聚合为事件，按故事时间线 (非段落顺序) 排序：
      1. **时间线重排**: 识别回忆 / 插叙 / 平行叙事，把事件按故事内时间排序
      2. **段落聚合**: 描述同一时空 / 同一行为的连续段落合并为一个事件
      3. **打标**: C 类段落独立成事件 ("C 类-系统")，其余为 "B 类-事件"

      ## 输入
      - segmented_chapters: 上一阶段的 ABC 分段结果

      ## 输出
      调用 finish_task，往 `events_by_chapter` 字段写：
      ```
      {
        1: [{"event_id": "ch1-e1", "summary": "...", "para_indices": [0,1,2], "location": "...", "time": "..."}, ...],
        2: [...],
      }
      ```
    user_prompt_template: |
      请基于以下分段结果做事件聚合 + 时间线重排：
      {segmented_chapters}

  - name: batch_loop
    mode: llm
    llm_role: analyst
    max_iterations: 40
    max_nudges: 5
    prompt: |
      你是故事解构分析的编排器。

      ## ⚠️ 退出契约
      处理完全部批次后必须调用 finish_task，把累积的批次结果写到 `all_batch_results`、把跨批次累积的角色/设定状态写到 `accumulated_context`。

      ## 任务
      按批次 (每批 10 个事件) 跑深度分析，每批输出：
      - 角色弧光变化 (这批事件里角色心态 / 关系的变化)
      - 高潮候选 (这批事件里张力最高的 2-3 个点 + 张力来源)
      - 设定补充 (这批事件揭示出的新世界规则)
      - 伏笔登记 (这批事件提出但未解决的悬念)

      ## 执行步骤
      1. 看完整个 `events_by_chapter`，规划批次切分 (每 10 个连续事件一批)
      2. 逐批分析，把结果累积到 `all_batch_results` 列表
      3. 同步更新 `accumulated_context` (跨批次的角色状态字典)
      4. 全部跑完后调用 finish_task

      ## 重要约束
      - 严格顺序处理 (第 1 批 → 第 2 批 → ...)
      - 单批失败时记录 warning 后继续下一批，不要中断整条 pipeline
    user_prompt_template: |
      项目：{project_id}
      ## 章节事件时间线
      {events_by_chapter}

  - name: global_synthesis
    mode: llm
    llm_role: analyst
    max_iterations: 6
    max_nudges: 2
    prompt: |
      你是叙事全局分析专家。

      ## ⚠️ 退出契约
      调用 finish_task，把全局故事框架写到 `story_framework` 字段 (dict)，包含 climax_ranking / character_arc / scene_assembly 三块。

      ## 任务
      整合所有批次结果，输出全局视角的故事框架：
      1. **climax_ranking**: 全书高潮点排名 (从所有批次的高潮候选里挑出最具张力的 5-10 个，给出排序理由)
      2. **character_arc**: 主要角色弧光 (每个核心角色从开篇到结局的状态变化曲线)
      3. **scene_assembly**: 场景串联 (按故事时间线给出场景序列，标注每个场景的高潮归属)

      ## 输入
      - all_batch_results: 各批次的局部分析结果列表
      - accumulated_context: 跨批次累积的角色 / 设定 / 情节状态
    user_prompt_template: |
      请基于以下材料合成最终 story_framework：
      ## 各批次分析结果
      {all_batch_results}
      ## 累积上下文
      {accumulated_context}
---

# story-deconstruction

完整故事解构 pipeline，从原文章节到全局故事框架。

## Pipeline

```
segmentation → event_extraction → batch_loop → global_synthesis
```

4 个 phase 全部是 LLM-driven，按列表顺序顺序执行。前一个 phase 的 finish_task 输出会写入指定 context 字段，下一个 phase 通过 prompt template 里的 `{field_name}` 引用。

## 输入

- `chapters` (list): 章节列表，每项形如 `{"chapter_number": int, "content": str}`
- `project_id` (str): 项目标识

## 输出

- `story_framework` (dict, artifact): 包含 climax_ranking / character_arc / scene_assembly 的全局故事框架

## 使用

```python
from graph_agent import run_skill

result = run_skill(
    "skills/story-deconstruction/SKILL.md",
    chapters=[{"chapter_number": 1, "content": "..."}, ...],
    project_id="my-novel",
)
print(result["context"]["story_framework"])
```

## 设计取舍

最初这个 skill 是 4 个独立子 skill (text-segmentation / event-extraction / batch-analysis / global-synthesis) 的 subgraph 编排器。MVP-0 B1 (2026-04-28) 把 `mode: delegate` / `mode: parallel_delegate` + 跨 skill 组合从框架里砍掉，等 V2 通过 LangGraph Send API 重新设计后回归。当下版本把每个 phase 改成 inline LLM 工作，等 V2 子 skill 调度回归后可以拆回去复用 4 个子 skill。

原 Python 编排器代码 (`script/orchestrator.py`) 保留在仓库里，等 V2 重新落地时复用。
