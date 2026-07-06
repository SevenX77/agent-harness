import type { CurrentSchemaVersion } from '@/config/schema'

export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[]

export interface JsonObject {
  [key: string]: JsonValue
}

export interface ErrorResponse {
  error_code: string
  http_status: number
  message: string
  details: JsonObject | null
  retry_strategy: 'idempotent' | 'not_retryable' | 'backoff'
}

export interface LintError {
  file?: string | null
  line: number | null
  column: number | null
  error_code: string
  severity: 'error' | 'warning'
  message: string
  phase_name: string | null
  // Engine's typed nearest-field locator, forwarded by the Studio shell. Drives
  // field-level Properties projection; null/absent → degrade to node/file axis.
  field_path?: string | null
  source_path?: string | null
}

export interface LintResult {
  status: 'passed' | 'failed'
  errors: LintError[]
  phases_summary: JsonObject[] | null
}

export interface CompileError {
  file: string | null
  line: number | null
  field: string | null
  severity: 'fatal' | 'warning'
  message: string
  error_code?: string | null
  details?: string[]
}

export interface ArtifactRef {
  artifact_id: string
  content_hash: string
  store: 'ephemeral' | 'product'
  version: string | null
  manifest_ref: string
  source_map_ref: string
  execution_fingerprint?: string | null
}

export interface CompileSuccess {
  skill_id: string
  status: 'ok'
  phase_count: number
  manifest_name: string
  artifact_ref: ArtifactRef
  source_map_ref: string
  execution_fingerprint: string
}

export interface CompileFailure {
  code: 'compile_failed'
  detail: string
  errors: CompileError[]
}

export type CompileResult = CompileSuccess | CompileFailure

export interface RuntimeImportField {
  name: string
  type?: string | null
  value_type?: string | null
  json_path?: string[] | null
  items?: RuntimeImportField[] | null
  content_type?: string | null
}

export interface RuntimeImportEntry {
  kind?: 'file' | 'dir' | 'batch' | string
  name: string
  stem?: string | null
  path?: string | null
  dir?: string | null
  pattern?: string | null
  numbers?: number[] | null
  count?: number | null
  format?: string | null
  content_type?: string | null
  fields?: RuntimeImportField[] | null
  entries?: RuntimeImportEntry[] | null
}

export interface RuntimeInputBinding {
  path?: string
  dir?: string
  pattern?: string
  numbers?: number[]
  value_type?: string
  content_type?: string
  type?: string
  json_path?: string[]
  sha256?: string
}

export interface RuntimeArtifactRow {
  stem: string
  mode: 'single' | 'per-item'
  format?: 'json' | 'md'
  fields: string[]
}

export interface RuntimeConfig {
  schema_version: string
  inputs: {
    import_root: string
    manifest: {
      root: RuntimeImportEntry[]
      phases: Record<string, RuntimeImportEntry[]>
    }
    root: Record<string, RuntimeInputBinding>
    phases: Record<string, Record<string, RuntimeInputBinding>>
  }
  llm?: Record<string, unknown>
  artifacts: RuntimeArtifactRow[]
  updated_at?: string
  fingerprint?: string
}

export interface SkillSummary {
  id: string
  name: string
  description: string
  phase_count: number
  has_golden: boolean
  last_run_at: string | null
  directory_path: string | null
}

export interface SkillTemplate {
  id: string
  name: string
  description: string
  type: string
  content: string
}

/**
 * Studio UI language persisted in app settings. Mirrors the frontend
 * `supportedLngs` (src/i18n.ts) and the backend `SupportedLanguage`
 * (models/settings.py); keep the three in sync.
 */
export type AppLanguage = 'en' | 'zh-CN'

export interface AppSettings {
  user_id: string
  gitea_host: string
  default_skills_directory: string
  language: AppLanguage
  remote_model_catalog_enabled: boolean
}

export interface CollaborateResult {
  status: 'ok' | 'requires_review' | 'conflict' | 'error'
  message: string
  pr_url?: string | null
  extra?: Record<string, unknown>
}

export type SyncAction = 'save_to_team' | 'sync_from_team' | 'submit_for_review'

export interface SyncSkillReq {
  action: SyncAction
  branch?: string
  dev_branch?: string
  pr_title?: string
}

export interface PublishSkillReq {
  version?: string
}

export interface ReleaseArtifactRef {
  artifact_id: string
  content_hash: string
  store: 'product'
  manifest_ref: string
  source_map_ref?: string | null
  execution_fingerprint?: string | null
}

export interface ReleaseRemoteSync {
  status: 'pending' | 'failed' | 'succeeded' | 'skipped'
  reason?: string
  error_type?: string
  error?: string
  details?: JsonObject
}

export interface ReleaseManifest {
  release_version: string
  artifact_id: string
  content_hash: string
  manifest_ref: string
  artifact_ref: ReleaseArtifactRef
  remote_sync?: ReleaseRemoteSync | null
  idempotency_key?: string
  created_at?: string
}

export interface PublishResult {
  status: 'ok' | 'error'
  message: string
  artifact_id?: string | null
  extra?: Partial<ReleaseManifest> & Record<string, unknown>
}

export interface TokensMetrics {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cost_estimate: number | null
  // ⑧a: engine run wall-clock duration, projected through the Studio run history
  // (backend models/runs.py declares it explicitly). Optional because older sealed
  // runs may predate the field; the run list renders "n/a" when absent.
  wall_time_sec?: number | null
}

export interface RunRequest {
  input_data?: JsonObject | null
  golden_id?: string | null
  paste_json?: string | null
}

export interface TestInputMetadata {
  id: string
  name: string
  created_at: string
  size_bytes: number
  content_preview: string
}

export interface TestInputDetail {
  id: string
  name: string
  content: JsonObject
}

export interface BatchRunRequest {
  input_ids: string[]
}

export interface BatchRunResponse {
  batch_id: string
  sub_run_ids: string[]
}

export interface BatchRunItem {
  input_id: string
  run_id: string
  status: 'running' | 'success' | 'failed'
  started_at: string
  metrics: TokensMetrics | null
}

export interface BatchRunStatus {
  batch_id: string
  skill_id: string
  status: 'running' | 'success' | 'failed'
  total: number
  completed: number
  items: BatchRunItem[]
}

export interface RunMetadata {
  run_id: string
  status: 'running' | 'success' | 'failed'
  started_at: string
  metrics: TokensMetrics | null
  input_summary: string | null
  git_status?: 'committed' | 'locked' | 'failed' | 'no_git' | null
  artifact_ref?: ArtifactRef | null
  source_map_ref?: string | null
  execution_fingerprint?: string | null
  // PR2 node-compare: set only on candidate side-runs so the Trace can group/tab
  // per-candidate results under the compared node; omitted on ordinary runs.
  compare_group_id?: string | null
  compare_node_id?: string | null
  candidate_id?: string | null
  candidate_label?: string | null
}

export interface RunListResponse {
  runs: RunMetadata[]
  total: number
}

/**
 * PR2 node-level Compare LLMs: one model candidate for a node. Model-only —
 * a model group + one endpoint route ("auto" = let the group's fallback decide).
 * Persisted per skill+node in the studio backend (not SKILL.md).
 */
export interface CompareCandidate {
  candidate_id: string
  model_group_id: string
  route: string
}

/** PUT body / per-node response: a node's candidate list. */
export interface NodeCompareCandidates {
  candidates: CompareCandidate[]
}

/** GET response: node id -> its candidate list (only non-empty nodes). */
export interface CompareCandidatesMap {
  nodes: Record<string, CompareCandidate[]>
}

/**
 * PR3: per-node direct overrides of the three simple LLM params. Each field is
 * a direct override — a null/absent field means "inherit the role default".
 * Persisted per skill+node in the studio backend (not SKILL.md).
 */
export interface NodeLlmParams {
  enabled?: boolean
  thinking?: boolean | null
  max_output_tokens?: number | null
  temperature?: number | null
}

/** GET response: node id -> its param overrides (only nodes with overrides). */
export interface NodeLlmParamsMap {
  nodes: Record<string, NodeLlmParams>
}

/** PR2: one candidate's isolated single-node side-run inside a compare group. */
export interface CompareCandidateRun {
  candidate_id: string
  label: string
  metadata: RunMetadata
}

/** PR2 POST response: the compare group + the per-candidate side-runs it spawned. */
export interface CompareRunResponse {
  compare_group_id: string
  node_id: string
  base_run_id: string
  runs: CompareCandidateRun[]
}

/** PR2 GET response: per-candidate side-runs for one compare group, for Trace tabs. */
export interface CompareRunGroupResponse {
  compare_group_id: string
  runs: CompareCandidateRun[]
}

export type GitHistoryKind = 'auto_run' | 'manual' | 'other' | 'release'
export type GitHistorySource = 'git' | 'manifest'

export interface GitHistoryItem {
  sha: string
  message: string
  author: string
  timestamp: string
  kind: GitHistoryKind
  source?: GitHistorySource
  revertable?: boolean
  release_version?: string | null
  artifact_id?: string | null
  content_hash?: string | null
  manifest_ref?: string | null
}

export interface RevertSkillReq {
  sha: string
}

export interface RunDetail {
  metadata: RunMetadata
  input_data: JsonObject | null
  events: EventEnvelope[]
  final_context: JsonObject | null
  artifacts: string[] | null
}

export interface ResumeValidityResponse {
  run_id: string
  resume_allowed: boolean
  reason:
    | 'ok'
    | 'dirty_upstream'
    | 'checkpoint.not_found'
    | 'checkpoint.invalid'
    | 'state.not_found'
    | 'artifact.invalid_ref'
    | 'artifact.identity_mismatch'
    | 'compile_failed'
  checkpoint_id: string | null
  checkpoint_ns: string | null
  resume_from_node_id: string | null
  resume_to_node_id: string | null
  dirty_fields: Array<'content_hash' | 'execution_fingerprint'>
  // n5-node#3 (dirty-downstream-graying): the downstream node ids the resume node
  // can dirty. The Studio shell slices these from the dependency graph when the
  // whole-skill compare is dirty and `resume_from_node_id` is set; empty on the
  // clean / no-resume-node paths. The frontend grays exactly these nodes.
  dirty_node_ids: string[]
  affected_downstream: string[]
  snapshot_content_hash: string | null
  current_content_hash: string | null
  snapshot_execution_fingerprint: string | null
  current_execution_fingerprint: string | null
}

export type MockedSource = 'golden_case' | 'copilot' | 'heuristic_stub' | 'manual'

export interface PathDiff {
  expected_path: string[]
  actual_path: string[]
  missing: string[]
  extra: string[]
  order_mismatch: boolean
}

export interface PhaseRecord {
  phase_name: string
  type: 'logic' | 'llm'
  inputs: JsonObject
  outputs: JsonObject
  mocked_source: MockedSource | null
}

export interface EngineErrorPayload {
  code: string
  level: string | null
  stage: string[] | null
  message: string
  doc_link: string | null
  skill_id: string | null
  phase_id: string | null
  field_path: string | null
  source_path: string | null
  details: JsonObject
}

export interface PredictDiagnosticExport {
  is_predict: boolean
  status: 'success' | 'failed'
  phases: PhaseRecord[]
  path_diff: PathDiff | null
  error: EngineErrorPayload | null
  diagnostics: EngineErrorPayload[]
  diagnostics_truncated: boolean
  diagnostic_counts: JsonObject
}

/**
 * One agent node's golden case, projected from baseline.json for the UI badge.
 * Mirrors backend models/golden.py GoldenBaselineCase. Presence of a node_id in
 * a baseline's `cases` is what drives the canvas golden 🟢 has-golden state.
 */
export interface GoldenBaselineCase {
  case_id: string
  node_id: string
  phase_id: string
  expected_output_ref: string
}

export interface GoldenBaseline {
  id: string
  source_run_id: string | null
  source_run_results_ref: string | null
  baseline_ref: string | null
  linked_input_id: string
  created_at: string
  locked: boolean
  content_path: string
  // Per-node cases projected from baseline.json. Optional/defaulted: older payloads
  // may omit it — consumers treat an absent value as an empty list.
  cases?: GoldenBaselineCase[]
}

/**
 * N4 atom #29 read path: one agent node's stored golden case content — the editable
 * `expected_output` the case file holds. Mirrors backend models/golden.py
 * GoldenCaseContent. The list endpoint only projects per-node case METADATA
 * (GoldenBaselineCase, with an `expected_output_ref`); this carries the resolved content
 * the ref points at so the I/O panel can open a golden file for editing.
 */
export interface GoldenCaseContent {
  case_id: string
  node_id: string
  phase_id: string
  expected_output: JsonObject
}

/**
 * N4 atom #29: a golden baseline with each case's resolved `expected_output`, returned by
 * `GET /skills/{id}/golden/{golden_id}/content` (optionally `?node_id=` to scope to one
 * node). Mirrors backend models/golden.py GoldenBaselineContent. Editing is read-only
 * here — saving an edit still goes through the existing manual-golden write
 * (`POST /golden/manual/plan` → Rust native-fs, D12), NOT a new write path.
 */
export interface GoldenBaselineContent {
  id: string
  source_run_id: string | null
  locked: boolean
  cases: GoldenCaseContent[]
}

/**
 * N4 atom #33: a schema-valid empty golden template for an agent node. Mirrors backend
 * models/golden.py GoldenTemplate — `schema` is the node's io.outputs JSON schema and
 * `template` is the structure-valid empty stub the author hand-fills.
 */
export interface GoldenTemplate {
  skill_id: string
  node_id: string
  schema: JsonObject
  template: JsonObject
}

export interface GoldenBaselineFile {
  path: string
  content: string
}

export interface GoldenBaselinePlan {
  baseline: GoldenBaseline
  files: GoldenBaselineFile[]
}

export interface SetGoldenReq {
  run_id: string
  lock: boolean
  // Per-node promote (atom #32): when set, the baseline is written for this agent
  // node only (mirrors backend models/golden.py SetGoldenReq.node_id). Absent =
  // run-level baseline over all agent nodes (existing behavior).
  node_id?: string | null
}

export type FieldDiffType = 'text' | 'number' | 'bool' | 'list' | 'dict' | 'null' | 'unknown'

export interface FieldDifference {
  field_path: string
  type: FieldDiffType
  current_value: JsonValue
  golden_value: JsonValue
  score: number
  changed: boolean
}

export interface NodeGoldenGroup {
  node_id: string
  phase_id: string | null
  status: 'pass' | 'fail'
  score: number
  field_differences: FieldDifference[]
  stale_fields: string[]
  schema_status: 'valid' | 'stale' | 'missing'
  baseline_ref: string
  run_results_ref: string
}

export interface CompareResult {
  baseline_id: string
  source_run_id: string | null
  source_run_results_ref: string | null
  baseline_ref: string
  run_results_ref: string
  total_score: number
  node_groups: NodeGoldenGroup[]
}

export interface TerminalSession {
  term_id: string
  ws_url: string
  cwd: string
  ttl_seconds: number
}

export interface IoInput {
  name: string
  source: 'runtime'
  type: string | null
  default: JsonValue | null
  description?: string | null
  enum?: JsonValue[] | null
  required?: boolean | null
}

export interface IoOutput {
  name: string
  target: 'file' | 'artifact'
  type: string | null
  path: string | null
}

export interface IoDeclaration {
  inputs: IoInput[]
  outputs: IoOutput[]
}

export interface GraphPhaseRef {
  id: string
  src: string
  depends_on: string[]
}

export type GraphPhaseMode = 'logic' | 'subgraph' | 'skill'

export interface SerializableGraphPhaseRef {
  id: string
  src: string
  depends_on: string[]
  output?: boolean
  mode: GraphPhaseMode
}

export interface SerializeGraphRes {
  markdown_content: string
  phase_count: number
  elapsed_ms: number
  current_hash: string
}

export interface GraphManifestV030 {
  schema_version: CurrentSchemaVersion
  name: string
  description: string
  io: {
    inputs: {
      type: 'object'
      properties: Record<string, unknown>
      required?: string[]
    }
    outputs: {
      type: 'object'
      properties: Record<string, unknown>
      required?: string[]
    }
  }
  phases: string[]
  metadata?: JsonObject
}

export interface BaseSkillManifest {
  schema_version: '2.0'
  name: string
  description: string
  license: string | null
  version: string | null
  author: string | null
  metadata: JsonObject | null
}

export interface AgentProfile {
  role: string
  goal: string
  steps: string[]
  constraints: string[]
  domain_protocols: string[]
  references: string[]
  few_shot_examples: string[]
  context_access: Array<'artifact' | 'working_memory'>
  llm_role: string | null
}

export interface AgentSkillDef extends BaseSkillManifest {
  type: 'agent'
  agent_profile: AgentProfile
  model_override: string | null
  agent_tools: string[]
  adopted_persona: string | null
  user_prompt_template: string | null
  context_mapping: Record<string, string>
}

export interface BasePhase {
  name: string
  mode: 'llm' | 'logic'
  model_override: string | null
  depends_on?: string | string[]
  subgraph?: string | null
}

export interface LlmPhase extends BasePhase {
  mode: 'llm'
  prompt: string | null
  user_prompt_template: string | null
  agent_tools: string[]
  steps: string[]
  domain_protocols: string[]
  references: string[]
  few_shot_examples: string[]
  context_access: Array<'artifact' | 'working_memory'>
  llm_role: string | null
  adopted_persona: string | null
  max_iterations: number | null
  max_retries: number | null
  max_nudges: number | null
  dead_end_threshold: number | null
  validator: string | null
  validator_optional: boolean
  retry_target: string | null
  hoist_to: string | null
  output_schema: string | null
  output_example: string | null
  output_schema_md: string | null
  output_example_md: string | null
}

export interface LogicPhase extends BasePhase {
  mode: 'logic'
  execute_steps: string[]
  validator: string | null
}

export type PhaseDef = LlmPhase | LogicPhase

export interface GraphSkillDef extends BaseSkillManifest {
  type: 'graph'
  io: IoDeclaration
  phases: PhaseDef[]
  context_mapping: Record<string, string>
}

export interface PersonaSkillDef extends BaseSkillManifest {
  type: 'persona'
  role_profile: string
  evaluation_rubrics: string | null
  few_shot_examples: string[]
}

export type SkillManifest = AgentSkillDef | GraphSkillDef | PersonaSkillDef | GraphManifestV030

/**
 * n2-canvas#10 (data-gap-viz): one entry per downstream INPUT field of a phase,
 * resolving where that field is supplied from. Produced by the backend
 * `compute_field_supply` (services/canvas_data_gap.py) and attached to each
 * `graph_topology` row as `field_supply`. `supplied=false` (`source='none'`) is a
 * data gap the i/o panel renders as a missing-input marker; supplied fields name
 * their source (`phase`, `graph_input`, or `file`) and producer phase when applicable.
 */
export interface FieldSupplyEntry {
  field: string
  supplied: boolean
  source: 'phase' | 'graph_input' | 'file' | 'none'
  producer_phase: string | null
}

/** Per-phase io field schema projection (`graph_topology[].io_fields`). */
export interface IoFieldsProjection {
  inputs: Record<string, JsonObject>
  outputs: Record<string, JsonObject>
}

export interface GraphTopologyItem {
  id: string
  src: string
  depends_on: string[]
  /** True only when the GRAPH.md phase ref carries the explicit output marker. */
  output?: boolean
  mode: 'logic' | 'subgraph' | 'skill' | string
  /** Child-graph path, surfaced only for subgraph phases. May be absolute or relative to the owning skill root. */
  path?: string | null
  /** n2-canvas#10: this phase's per-node io.inputs/io.outputs field schema. */
  io_fields?: IoFieldsProjection
  /** n2-canvas#10: per-input-field supply/demand projection for data-gap markers. */
  field_supply?: FieldSupplyEntry[]
}

/**
 * Child graph resolved by path for inline subgraph rendering. The backend response path is absolute.
 * Mirrors the backend `ChildGraphTopology` model.
 */
export interface ChildGraphTopology {
  path: string
  name: string
  description: string
  phases: string[]
  graph_topology: GraphTopologyItem[]
  detail?: SkillDetail | null
}

export interface SkillDetail {
  manifest: SkillManifest
  graph_topology?: GraphTopologyItem[]
  node_schema_v21?: Record<string, JsonObject>
  io_schema?: Record<string, JsonObject>
  file_paths: Record<string, string>
  files?: Record<string, string>
  manifest_errors?: LintError[] | null
  has_golden: boolean
  latest_run_metadata: RunMetadata | null
  lint_result: LintResult | null
}

export interface UpdateSkillFileRes {
  path: string
  hash: string
}

export interface CallbackEventBase {
  schema_version: '1.0'
  event_type: string
  timestamp: string
  phase_name?: string | null
  current_phase?: string | null
  run_id?: string
  status?: string
  input_tokens?: number
  output_tokens?: number
  template_source?: string | null
  mocked_source?: MockedSource | null
  metadata?: JsonObject
  metrics?: JsonObject
  variables?: JsonObject
  resolved_prompt?: JsonObject[]
  messages?: JsonObject[] | null
  response_data?: JsonObject | null
}

export type CallbackEvent = CallbackEventBase & Record<string, JsonValue | undefined>

export interface TransportErrorPayload {
  error_code: string
  message: string
  details: JsonObject
  retryable: boolean
}

export interface EventEnvelope {
  schema_version: 'studio.event.v1'
  stream_id: string
  seq: number
  cursor: string
  run_id: string
  event_type: string
  timestamp: string
  payload: CallbackEvent
  error_code?: string | null
  error_payload?: TransportErrorPayload | null
}

export interface StudioGlobalEvent {
  type: 'skill_changed'
  skill_id: string
}
