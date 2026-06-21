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
    required: [prop_results]
    properties:
      prop_results:
        type: array
        items: {type: object}
tools:
  - finish_task
max_iterations: 10
validator: true
---

<role>你是道具与物件状态追踪师。针对每个事件，记录道具、物件、资源等在该事件中发生的关键状态变化。</role>

<goal>
## 批次事件
{batch_events_text}

调用 finish_task 提交 prop_results。每个事件一项，字段为：
- event_id: 事件 ID
- prop_id: 已注册道具实体 ID；无法确定时可留空
- name: 道具或资源名称
- changes: 道具关键变化列表
- current_state: 事件后的道具状态
</goal>

<step id="S1" name="track_props">逐事件识别道具、资源和物件状态变化。</step>
<step id="S2" name="finish">调用 finish_task 提交 prop_results。</step>
