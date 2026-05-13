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
}

export interface RunListResponse {
  runs: RunMetadata[]
  total: number
}

export interface RunDetail {
  metadata: RunMetadata
  input_data: JsonObject | null
  events: CallbackEvent[]
  final_context: JsonObject | null
  artifacts: string[] | null
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
  linked_input_id: string
  created_at: string
  locked: boolean
  content_path: string
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

export interface CompareResult {
  differences: FieldDifference[]
  total_score: number
  golden_run_id: string
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

export type SkillManifest = AgentSkillDef | GraphSkillDef | PersonaSkillDef

export interface SkillDetail {
  manifest: SkillManifest
  file_paths: Record<string, string>
  has_golden: boolean
  latest_run_metadata: RunMetadata | null
  lint_result: LintResult | null
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

export interface StudioGlobalEvent {
  type: 'skill_changed'
  skill_id: string
}
