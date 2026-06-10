---
target_skill: text-segmentation-v2
validator: false
iterate:
  mode: batch
  over: chapters
  item_var: chapter
  concurrency: 10
  inputs_mapping:                  # [补丁1] item 字段 → 子 skill 输入字段
    chapter_content: chapter.content
    chapter_number: chapter.chapter_number
  on_item_failure:                 # [补丁3] abort 默认且唯一自动策略
    policy: abort
    retry: {count: 2, interval: 60}
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:         # batch 聚合: 各项同名输出聚成数组
        type: array
        items: {type: object}
---
