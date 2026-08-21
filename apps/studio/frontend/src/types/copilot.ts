import type { JsonObject } from '../api/types'

export type CopilotEventStatus = 'pending' | 'running' | 'success' | 'error'

export interface CopilotEventBase {
  id: string
  status: CopilotEventStatus
  receivedAt: number
  raw: unknown
}

export interface CopilotTextDeltaEvent extends CopilotEventBase {
  type: 'text_delta'
  content: string
}

export interface CopilotToolUseStartEvent extends CopilotEventBase {
  type: 'tool_use_start'
  /** Real tool name as the SDK reports it — an open string: read-only tools
   * (Glob/Grep) and studio MCP tools (mcp__studio__<tool>) included. */
  tool_name: string
  tool_input: JsonObject
}

export interface CopilotToolUseResultEvent extends CopilotEventBase {
  type: 'tool_use_result'
  tool_name: string
  success: boolean
  result_summary: string
}

export interface CopilotDoneEvent extends CopilotEventBase {
  type: 'done'
}

export interface CopilotThinkingDeltaEvent extends CopilotEventBase {
  type: 'thinking_delta'
  content: string
}

export interface CopilotContextResolvedEvent extends CopilotEventBase {
  type: 'context_resolved'
  summary: string
  detail: string
}

export interface CopilotErrorEvent extends CopilotEventBase {
  type: 'error'
  message: string
}

/** F5 safe-write: a copilot Write/Edit applied; carries the diff + restore data. */
export interface CopilotPatchProposedEvent extends CopilotEventBase {
  type: 'patch_proposed'
  toolUseId: string
  toolName: 'Write' | 'Edit'
  path: string
  beforeExisted: boolean
  beforeContent: string
  afterContent: string
  beforeHash: string | null
  afterHash: string
  diff: string
  checkpointId: string
  /** Review state, driven locally by Accept/Reject. */
  review: 'pending' | 'accepted' | 'rejected'
}

/** A copilot tool call held for human approval (Bash / out-of-fence read).
 * Approving lets the CLI execute the tool itself; `detail` is the Bash
 * command text or the out-of-fence path being read. */
/**
 * How a held tool call ended.
 *
 * `timed_out` is here rather than in a field of its own because this one field
 * already answers "how did this hold end", and a second field answering the
 * same question is a second thing that can disagree with the first. Nobody
 * decided in that case — which is exactly why it is worth recording.
 */
export type ToolApprovalDecision = 'pending' | 'approved' | 'denied' | 'timed_out'

export interface CopilotToolApprovalRequiredEvent extends CopilotEventBase {
  type: 'tool_approval_required'
  toolUseId: string
  toolName: string
  detail: string
  /**
   * What the user decided, on the event itself — the session is written to disk
   * as JSON, so a decision kept anywhere else does not survive the panel being
   * collapsed, a session tab switch, or Restore chat (problem ledger CP6).
   */
  decision: ToolApprovalDecision
}

export interface CopilotUnknownEvent extends CopilotEventBase {
  type: 'unknown'
  payload: unknown
}

export type CopilotEvent =
  | CopilotTextDeltaEvent
  | CopilotThinkingDeltaEvent
  | CopilotContextResolvedEvent
  | CopilotToolUseStartEvent
  | CopilotToolUseResultEvent
  | CopilotPatchProposedEvent
  | CopilotToolApprovalRequiredEvent
  | CopilotDoneEvent
  | CopilotErrorEvent
  | CopilotUnknownEvent

export interface CopilotMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  events: CopilotEvent[]
  status: CopilotEventStatus
  createdAt: number
}

/**
 * The `tool_use_id` of a hold the server just expired, or null for any other
 * record.
 *
 * This one stream record does not become an event of its own: it settles a
 * card that is already on screen. It is read here, beside the decoder, because
 * both answer the same question — what does this raw record mean — and reading
 * a wire shape in two places is how the two readings drift apart.
 */
export function readToolApprovalExpiry(raw: unknown): string | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }
  const record = raw as Record<string, unknown>
  if (record.type !== 'tool_approval_timed_out' || typeof record.tool_use_id !== 'string') {
    return null
  }
  return record.tool_use_id || null
}

export function normalizeCopilotEvent(raw: unknown, id: string): CopilotEvent {
  const receivedAt = Date.now()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { id, type: 'unknown', status: 'error', receivedAt, raw, payload: raw }
  }

  const record = raw as Record<string, unknown>
  if (
    record.type === 'context_resolved' &&
    typeof record.summary === 'string' &&
    typeof record.detail === 'string'
  ) {
    return {
      id,
      type: 'context_resolved',
      status: 'success',
      receivedAt,
      raw,
      summary: record.summary,
      detail: record.detail,
    }
  }
  if (record.type === 'thinking_delta' && typeof record.content === 'string') {
    return { id, type: 'thinking_delta', status: 'running', receivedAt, raw, content: record.content }
  }
  if (record.type === 'text_delta' && typeof record.content === 'string') {
    return { id, type: 'text_delta', status: 'running', receivedAt, raw, content: record.content }
  }
  if (record.type === 'tool_use_start' && typeof record.tool_name === 'string') {
    return {
      id,
      type: 'tool_use_start',
      status: 'running',
      receivedAt,
      raw,
      tool_name: record.tool_name,
      tool_input: isJsonObject(record.tool_input) ? record.tool_input : {},
    }
  }
  if (record.type === 'tool_use_result' && typeof record.tool_name === 'string') {
    return {
      id,
      type: 'tool_use_result',
      status: record.success === false ? 'error' : 'success',
      receivedAt,
      raw,
      tool_name: record.tool_name,
      success: record.success !== false,
      result_summary: typeof record.result_summary === 'string' ? record.result_summary : '',
    }
  }
  if (
    record.type === 'patch_proposed' &&
    typeof record.path === 'string' &&
    (record.tool_name === 'Write' || record.tool_name === 'Edit')
  ) {
    return {
      id,
      type: 'patch_proposed',
      status: 'success',
      receivedAt,
      raw,
      toolUseId: typeof record.tool_use_id === 'string' ? record.tool_use_id : '',
      toolName: record.tool_name,
      path: record.path,
      beforeExisted: record.before_existed === true,
      beforeContent: typeof record.before_content === 'string' ? record.before_content : '',
      afterContent: typeof record.after_content === 'string' ? record.after_content : '',
      beforeHash: typeof record.before_hash === 'string' ? record.before_hash : null,
      afterHash: typeof record.after_hash === 'string' ? record.after_hash : '',
      diff: typeof record.diff === 'string' ? record.diff : '',
      checkpointId: typeof record.checkpoint_id === 'string' ? record.checkpoint_id : '',
      review: 'pending',
    }
  }
  if (
    record.type === 'tool_approval_required' &&
    typeof record.tool_name === 'string' &&
    typeof record.detail === 'string'
  ) {
    return {
      id,
      type: 'tool_approval_required',
      status: 'pending',
      receivedAt,
      raw,
      toolUseId: typeof record.tool_use_id === 'string' ? record.tool_use_id : '',
      toolName: record.tool_name,
      detail: record.detail,
      // This function reads the LIVE stream only; a just-arrived approval is
      // pending by definition. Restoring a session does not come through here —
      // the persisted CopilotEvent objects are read back as they were written.
      decision: 'pending',
    }
  }
  if (record.type === 'done') {
    return { id, type: 'done', status: 'success', receivedAt, raw }
  }
  if (record.type === 'error' && typeof record.message === 'string') {
    return { id, type: 'error', status: 'error', receivedAt, raw, message: record.message }
  }
  return { id, type: 'unknown', status: 'error', receivedAt, raw, payload: raw }
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
