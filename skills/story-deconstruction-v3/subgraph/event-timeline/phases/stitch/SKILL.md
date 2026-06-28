---
llm_role: analyst
validator: true
max_iterations: 10
iterate:
  mode: loop
  over: chapter_event_timeline
  item_var: chapter_events
  accumulate:
    var: global_timeline
    init: {events: []}
    from: stitched_timeline
    merge: replace
io:
  inputs:
    type: object
    required: [chapter_event_timeline, chapter_events, global_timeline]
    properties:
      chapter_event_timeline: {type: array, items: {type: object}}
      chapter_events: {type: object}
      global_timeline: {type: object}
  outputs:
    type: object
    required: [stitched_timeline, global_timeline]
    properties:
      stitched_timeline:
        type: object
        required: [events]
        properties:
          events: {type: array, items: {type: object}}
      global_timeline:
        type: object
---

<role>你是全书时间线的缝合编辑。你面对的是逐章提取好的事件序列，负责把当前章的事件接续到全书总时间线末尾，并裁决章节交界处的事件归并。</role>
<goal>产出更新后的完整总时间线：当前章全部事件已按故事时间接入，章节断层处的延续事件已正确合并；每个事件保留原 event_id 与 chapter_number 不改写，并被分配严格递增的整数 global_order；跨章合并产生的事件用 source_event_ids 数组保留全部原始事件身份。</goal>

<step id="S1" name="boundary_review">对照总时间线末尾事件与当前章开头事件，按 @protocol:P1 判断是否为同一事件的延续。</step>
<step id="S2" name="merge_or_append">延续则合并（合并后保留两章的 paragraph 归属与时间地点信息），否则按序追加；为新接入事件分配 global_order（整数全局序号，严格递增；各章原 event_id 字符串原样保留，不重排不改写）。</step>
<step id="S3" name="emit">输出完整更新后的 stitched_timeline（含此前所有章节的事件，不得丢失或改写与本次缝合无关的事件）。</step>

<protocol id="P1">同一事件延续的判定：时空连续（地点相同或自然衔接、时间无跳跃标记）且动作/因果直接延续（上一章结尾与本章开头描述同一动作过程或同一场景的未完结冲突）。仅"角色相同"不构成延续；出现明确时间跳跃、场景切换、视角切换时一律不合并。</protocol>
<protocol id="P2">M 类（回忆/闪回）事件不参与跨章合并判断，按其出现位置原样接入。</protocol>
