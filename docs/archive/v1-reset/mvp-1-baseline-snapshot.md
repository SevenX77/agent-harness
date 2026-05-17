# MVP-1 Baseline Snapshot (2026-04-29 pre-A1)

## WorkflowState
src/core/graph_agent/core/state.py — TypedDict 5 fields: context / messages / current_phase / retry_counts / metrics

## 框架元字段（混入 context dict 的 _underscore 字段）
_ambiguity_reports
_current_phase
_finish_task_result
_group_key
_io_errors
_last_output
_md_schema
_md_schema_path
_md_type_dict
_persistent_runtime_inputs
_persistent_storage_config
phase
skill_base_dir
_sub_run_id
_unattended
_validation_middleware_phase
_validation_warnings
_working_memory

## state.context read/write 站点数
26

## state read/write 总站点数（context + messages + others）
47

## 受影响测试文件
5
