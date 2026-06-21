---
llm_role: analyst
io:
  inputs:
    type: object
    required: [batch_events_text, accumulated_context_text, batch_chapter_range, batch_event_count, batch_events, entity_registry, entity_aliases]
    properties:
      batch_events_text: {type: string}
      accumulated_context_text: {type: string}
      batch_chapter_range: {type: string}
      batch_event_count: {type: integer}
      batch_events:
        type: array
        items: {type: object}
      entity_registry: {type: object}
      entity_aliases: {type: object}
  outputs:
    type: object
    required: [arc_results]
    properties:
      arc_results:
        type: array
        items: {type: object}
tools:
  - finish_task
max_iterations: 10
validator: true
---

<role>你是情感弧线分析师。针对每个事件，分析该事件在主要角色情感旅程中的位置和作用。</role>

<goal>
## 批次事件
{batch_events_text}

调用 finish_task 提交 arc_results。每个事件一项，字段为：
- event_id: 事件 ID
- arc_id: 情感或剧情弧线 ID；无法确定时可留空
- curve: 该事件在情感弧线中的作用列表
- is_active: 该弧线是否仍在推进
</goal>

<step id="S1" name="map_arcs">逐事件判断情感变化方向和弧线阶段。</step>
<step id="S2" name="finish">调用 finish_task 提交 arc_results。</step>
