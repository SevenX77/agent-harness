# CODEMOD_REPORT

- source: `skills/event-extraction/SKILL.md`
- written candidate files: 8
- initial review markers: 13
- remaining review markers: 0

## Manual decisions

- `setup` remains a LOGIC phase and formats segmented paragraphs.
- `aggregate`, `review`, and `settings` remain SKILL phases.
- Legacy `output_schema`, `llm_role`, retry, and validator fields were removed; terminal validation is handled by `finish_task` + `io/outputs.json`.
- `reviewer` is a critic Tool convention in the review phase.
- The T2.4 md-patch retry DoD is covered by e2e with malformed terminal markdown.

## Script classification

- Actions: `format_segments_for_prompt`
- Tools: none
- Critic: `reviewer`
- Removed as schema 2.0 ctx tools or superseded by finish_task: `parse_events`, `parse_paragraph_indices`, `store_events`, `backup_event_timeline`, `safe_review_store_events`, `parse_settings`, `merge_settings_into_events`, `finalize_event_timeline`, `log_ambiguous_events`, `validate_event_extraction`
