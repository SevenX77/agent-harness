import { useState } from 'react'
import { Undo2 } from 'lucide-react'
import { api } from '../../api/client'
import { deleteRole } from '../../api/llm'
import { Button } from '../ui/button'

/** Compact backend snapshot carried in the role-write tool result (R10.2). */
interface RoleSnapshot {
  role_kind?: string
  model_fallback_enabled?: boolean
  intent?: Record<string, unknown>
  model_groups?: Array<{ canonical_id?: string }>
}

export interface RoleChangeSummary {
  role_name: string
  before: RoleSnapshot | null
  after: RoleSnapshot
}

const ROLE_WRITE_TOOLS = new Set([
  'mcp__studio__create_llm_role',
  'mcp__studio__update_llm_role',
])

/** Parse a role-write tool result into a change card model; null = not one. */
export function parseRoleChangeSummary(
  toolName: string,
  resultSummary: string,
): RoleChangeSummary | null {
  if (!ROLE_WRITE_TOOLS.has(toolName)) return null
  try {
    const parsed: unknown = JSON.parse(resultSummary)
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof (parsed as { role_name?: unknown }).role_name === 'string' &&
      typeof (parsed as { after?: unknown }).after === 'object' &&
      (parsed as { after?: unknown }).after !== null
    ) {
      const record = parsed as { role_name: string; before?: RoleSnapshot | null; after: RoleSnapshot }
      return { role_name: record.role_name, before: record.before ?? null, after: record.after }
    }
  } catch {
    // a role-write tool can also fail with a plain error string — no card then
  }
  return null
}

function groupList(snapshot: RoleSnapshot | null): string {
  const ids = (snapshot?.model_groups ?? [])
    .map((group) => group.canonical_id)
    .filter((id): id is string => typeof id === 'string')
  return ids.length > 0 ? ids.join(', ') : '(none)'
}

type UndoState = 'idle' | 'undoing' | 'undone' | 'failed'

/** R10.2: every copilot-driven role config change surfaces as a visible card
 * with a one-click undo. Undo goes through the SAME service layer as any
 * Settings save (create → DELETE /llm/roles/<name>; update → PUT the before
 * snapshot back), so it re-validates, republishes the domain event, and shows
 * up as a change of its own. */
export function RoleChangeCard({ change }: { change: RoleChangeSummary }) {
  const [undoState, setUndoState] = useState<UndoState>('idle')
  const created = change.before === null

  async function undo() {
    setUndoState('undoing')
    try {
      if (created) {
        await deleteRole(change.role_name)
      } else {
        await api.put('/llm/roles', { roles: { [change.role_name]: change.before } })
      }
      setUndoState('undone')
    } catch {
      setUndoState('failed')
    }
  }

  return (
    <div className="mt-1.5 rounded-md border border-border bg-muted/30 p-2 text-[11px] leading-snug">
      <div className="font-medium text-foreground">
        {created ? 'Created LLM role' : 'Updated LLM role'}{' '}
        <span className="font-mono">{change.role_name}</span>
      </div>
      <div className="mt-1 space-y-0.5 text-muted-foreground">
        {!created && <div>was: {groupList(change.before)}</div>}
        <div>now: {groupList(change.after)}</div>
        {typeof change.after.model_fallback_enabled === 'boolean' && (
          <div>fallback: {change.after.model_fallback_enabled ? 'on' : 'off'}</div>
        )}
      </div>
      <div className="mt-1.5">
        {undoState === 'undone' ? (
          <span className="text-muted-foreground">Undone — role restored.</span>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="h-6 gap-1 px-2 text-[11px]"
            disabled={undoState === 'undoing'}
            onClick={() => {
              void undo()
            }}
          >
            <Undo2 className="size-3" />
            {undoState === 'undoing' ? 'Undoing…' : undoState === 'failed' ? 'Undo failed — retry' : 'Undo'}
          </Button>
        )}
      </div>
    </div>
  )
}
