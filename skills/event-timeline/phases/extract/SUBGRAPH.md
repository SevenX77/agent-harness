---
target_skill: event-extraction-v2
validator: false
iterate:
  mode: batch
  over: segmentation_result
  item_var: chapter_segmentation
  concurrency: 10
  inputs_mapping:
    segmentation_result: chapter_segmentation
    chapter_number: chapter_segmentation.chapter_number
    # 注: 不传 prev_chapter_last_event(子skill可选输入) —— 跨章衔接职责整体上移到 stitch
  on_item_failure:
    policy: abort
    retry: {count: 2, interval: 60}
io:
  inputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [event_timeline]
    properties:
      event_timeline:              # batch 聚合: 每章一个 event_timeline 对象
        type: array                # 验收规则: 聚合顺序 = over 数组输入顺序(并发完成先后不影响), 即按章序
        items: {type: object}
---
