import type { JsonObject, JsonValue } from '../api/types'

export type CopilotBackend = 'claude' | 'deepseek' | 'gemini' | 'openai'
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

export interface CopilotErrorEvent extends CopilotEventBase {
  type: 'error'
  message: string
}

export interface CopilotUnknownEvent extends CopilotEventBase {
  type: 'unknown'
  payload: unknown
}

export type CopilotEvent =
  | CopilotTextDeltaEvent
  | CopilotToolUseStartEvent
  | CopilotToolUseResultEvent
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

export interface CopilotBackendStatus {
  has_key: boolean
  V1_5_PLACEHOLDER?: boolean
  v1_5_placeholder?: boolean
}

export interface CopilotCredentials {
  active_backend: CopilotBackend
  backends: Record<CopilotBackend, CopilotBackendStatus>
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
