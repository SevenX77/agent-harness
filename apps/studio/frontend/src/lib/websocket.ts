import { wsUrl } from '../api/client'
import { resolveWorkspaceIdentity } from '../components/studio/workspace-identity'

export type WebSocketStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting' | 'error'

/**
 * Address one run's event stream.
 *
 * The caller holds a workspace SELECTION (`local-workspace:<id>:<path>` for a
 * locally-opened skill), which is not what the API is addressed by — the same
 * narrowing every HTTP endpoint does in `api/client.ts`. A selection sent as-is
 * is rejected by the backend's URL-segment validator, and because a WebSocket
 * is accepted before the handler runs, the rejection reaches the client as a
 * bare abnormal close: no status, no message, an empty Trace region, and a
 * reconnect loop that can never succeed. Narrowing here is what keeps the
 * illegal address out of the URL in the first place.
 */
export function runEventsWsUrl(skillId: string, runId: string, cursor?: string | null) {
  const apiSkillId = resolveWorkspaceIdentity(skillId).skillId ?? skillId
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return wsUrl(`/ws/skills/${encodeURIComponent(apiSkillId)}/runs/${encodeURIComponent(runId)}${query}`)
}

export function nextBackoffMs(attempt: number) {
  return Math.min(30_000, 1000 * (2 ** Math.max(0, attempt - 1)))
}
