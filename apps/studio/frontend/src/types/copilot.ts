import type { JsonObject, JsonValue } from '../api/types'

export type CopilotToolName = 'Read' | 'Write' | 'Edit' | 'Bash'
export type CopilotEventStatus = 'pending' | 'running' | 'success' | 'error'
export type CopilotView = 'WelcomeScreen' | 'Edit' | 'Compile' | 'Validate' | 'Predict' | 'Run' | 'Publish'

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
  tool_name: CopilotToolName
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

/** F5: a copilot Bash command held for human approval (not executed). */
export interface CopilotBashApprovalRequiredEvent extends CopilotEventBase {
  type: 'bash_approval_required'
  toolUseId: string
  command: string
  blocked: boolean
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
  | CopilotBashApprovalRequiredEvent
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

export interface CopilotContextPayload {
  view: CopilotView
  context: Record<string, JsonValue>
  timestamp: number
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
      tool_name: record.tool_name as CopilotToolName,
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
  if (record.type === 'bash_approval_required' && typeof record.command === 'string') {
    return {
      id,
      type: 'bash_approval_required',
      status: 'pending',
      receivedAt,
      raw,
      toolUseId: typeof record.tool_use_id === 'string' ? record.tool_use_id : '',
      command: record.command,
      blocked: record.blocked !== false,
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
