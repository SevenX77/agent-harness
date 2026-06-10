---
schema_version: "v0.3.0"
name: story-deconstruction-v2
description: Declarative story deconstruction pipeline (mvp1 iterate baseline). Linear 4-subgraph orchestration; all looping/batching is declarative iterate.
run_scope:
  range: null            # 顶层总开关[补丁4]: [起,止] 章区间; null=全量; predict 默认 [1,1]
                         # 边界语义: 1-based 闭区间, 按 chapter_number 升序排序后裁剪 input.chapters;
                         # 空区间/起>止/越界 → 启动期显式报错, 不静默空跑
  initial_context: {}    # 冷启动注入(无 checkpoint 续跑时); 正常续跑走 checkpoint
io:
  inputs:
    type: object
    required: [chapters, project_id]
    properties:
      chapters:
        type: array
        items:
          type: object
          required: [chapter_number, content]
          properties:
            chapter_number: {type: integer}
            content: {type: string}
      project_id: {type: string}   # 不进任何 phase, 由引擎 run_context 消费: 产物命名/trace 归档
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework: {type: object}
phases: [segmentation, event_timeline, story_analysis, global_synthesis]
---

<phase depends_on="input">segmentation</phase>
<phase depends_on="segmentation">event_timeline</phase>
<phase depends_on="event_timeline">story_analysis</phase>
<phase depends_on="story_analysis" output>global_synthesis</phase>
