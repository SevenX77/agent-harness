import { wsUrl } from '../api/client'

export type WebSocketStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting' | 'error'

export function runEventsWsUrl(runId: string) {
  return wsUrl(`/ws/runs/${runId}`)
}

export function nextBackoffMs(attempt: number) {
  return Math.min(30_000, 1000 * (2 ** Math.max(0, attempt - 1)))
}
