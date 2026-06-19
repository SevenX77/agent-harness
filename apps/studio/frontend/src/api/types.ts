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

export interface ConfigMismatchWarning {
  actual_remote_url: string
  expected_remote_url: string
  recommendation: string
}

export interface SkillSummary {
  id: string
  name: string
  description: string
  phase_count: number
  has_golden: boolean
  last_run_at: string | null
  directory_path: string | null
  config_mismatch?: ConfigMismatchWarning | null
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
  git_status?: 'committed' | 'locked' | 'failed' | null
  artifact_ref?: ArtifactRef | null
  source_map_ref?: string | null
  execution_fingerprint?: string | null
}

export interface RunListResponse {
  runs: RunMetadata[]
  total: number
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

export interface PredictDiagnosticExport {
  is_predict: boolean
  status: 'success' | 'failed'
  phases: PhaseRecord[]
  path_diff: PathDiff | null
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

export interface GraphTopologyItem {
  id: string
  src: string
  depends_on: string[]
  mode: 'logic' | 'subgraph' | 'skill' | string
  /** Absolute child-graph path, surfaced only for subgraph phases. */
  path?: string | null
}

/**
 * Child graph resolved by absolute path for inline subgraph rendering.
 * Mirrors the backend `ChildGraphTopology` model.
 */
export interface ChildGraphTopology {
  path: string
  name: string
  description: string
  phases: string[]
  graph_topology: GraphTopologyItem[]
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
