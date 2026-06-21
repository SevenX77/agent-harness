---
name: batch_analysis
path: subgraph/batch-analysis
validator: false
iterate:
  mode: loop
  over: event_batches
  item_var: current_batch
  accumulate:
    var: analysis_state
    init:
      entity_registry: {}
      entity_aliases: {}
      character_latest_states: {}
      open_foreshadowing: []
      active_arcs: []
      batch_history: []
    from: updated_state
    merge: merge
io:
  inputs:
    type: object
    required: [event_batches, current_batch, analysis_state, para_text_lookup, dynamic_dimensions]
    properties:
      event_batches: {type: array, items: {type: object}}
      current_batch: {type: object}
      analysis_state: {type: object}
      para_text_lookup: {type: object}
      dynamic_dimensions: {type: array, items: {type: string}}
  outputs:
    type: object
    required: [updated_state, analysis_state]
    properties:
      updated_state: {type: object}
      analysis_state: {type: object}
---
