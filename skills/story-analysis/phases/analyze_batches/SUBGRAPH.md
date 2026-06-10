---
target_skill: batch-analysis-v2
validator: false
iterate:
  mode: loop
  over: event_batches
  item_var: current_batch
  inputs_mapping:                   # 语义[设计反馈G]: 显式映射优先, 未列出的子skill输入按同名黑板字段直通
    batch_events: current_batch.events
    chapter_range: current_batch.chapter_range
    accumulated_context: accumulated_context     # 同名直通本可省略, 显式写消除歧义(评审建议)
    para_text_lookup: para_text_lookup
    dynamic_dimensions: dynamic_dimensions
  accumulate:                       # [设计反馈D] 双累积变量(02-iterate 当前仅单 accumulate, 此为待反写的扩展语法)
    - var: accumulated_context
      init: {}
      from: updated_accumulated
      merge: replace                # 模式②全量回灌
    - var: batch_outputs_raw
      init: []
      from: batch_result            # batch_result 是 array<object>(逐事件分析结果)
      merge: append                 # 有意嵌套成 array<array>(每批一项), finalize 再还原批包装(评审R2-B1)
  on_item_failure:
    policy: abort
    retry: {count: 2, interval: 60}
io:
  inputs:                           # loop 编译约束: 必含 item_var + 回灌型 accumulate.var(评审 blocking#2 修复)
    type: object
    required: [event_batches, current_batch, accumulated_context, para_text_lookup, dynamic_dimensions]
    properties:
      event_batches: {type: array, items: {type: object}}
      current_batch: {type: object}
      accumulated_context: {type: object}
      para_text_lookup: {type: object}
      dynamic_dimensions: {type: array, items: {type: string}}
  outputs:
    type: object
    required: [batch_outputs_raw, accumulated_context]
    properties:
      batch_outputs_raw:            # 末轮由 loop 引擎写回; array<array>(每批一项), 由 finalize 还原批包装
        type: array
        items: {type: array, items: {type: object}}
      accumulated_context: {type: object}
---
