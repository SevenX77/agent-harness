import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Check, FilePlus2, FilePenLine, RotateCcw, X } from 'lucide-react'
import { toast } from 'sonner'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { computeLineDiff, lineDiffStats } from '../../lib/line-diff'
import {
  clearWorkspaceCheckpoint,
  restoreWorkspaceFile,
  seedWorkspaceCheckpoint,
} from '../../lib/tauri'
import { resolveWorkspaceIdentity } from '../studio/workspace-identity'
import { errorMessage } from '../../utils/errors'

/** F5 DEF-025: tells the workspace a copilot edit hit disk so the editor buffer
 * reloads and predict/run recompile against the reviewed code. */
export type CopilotFileAction = 'applied' | 'accepted' | 'rejected'

/**
 * What the workspace should do for each copilot file action:
 * - applied (SDK just wrote the edit) → reload the open buffer to show it live.
 * - accepted (review final)           → recompile so predict/run use it.
 * - rejected (file rewound on disk)   → reload the buffer AND recompile.
 */
export function copilotFileActionEffects(action: CopilotFileAction): {
  reload: boolean
  recompile: boolean
} {
  return {
    reload: action === 'applied' || action === 'rejected',
    recompile: action === 'accepted' || action === 'rejected',
  }
}

interface PatchProposedBubbleProps {
  event: CopilotPatchProposedEvent
  skillId: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

type Review = 'pending' | 'accepted' | 'rejected'

function PatchProposedBubbleBase({ event, skillId, onFileChanged }: PatchProposedBubbleProps) {
  const [review, setReview] = useState<Review>('pending')
  const [busy, setBusy] = useState(false)

  const rows = useMemo(
    () => computeLineDiff(event.beforeContent, event.afterContent),
    [event.beforeContent, event.afterContent],
  )
  const stats = useMemo(() => lineDiffStats(rows), [rows])

  const resolveRoot = (): string | null => {
    if (!skillId) return null
    return resolveWorkspaceIdentity(skillId).workspaceRoot ?? skillId
  }

  // Apply path (model B): record the pre-edit bytes the moment the edit lands so
  // Reject rewinds the whole pending change through the Rust sole writer.
  // Earliest-wins + durable; uses the bytes the backend shipped in the event
  // (race-free vs re-reading the already-applied file). Best-effort — does not
  // run in web/test (seedWorkspaceCheckpoint throws "Desktop only", caught here).
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current) return
    const root = resolveRoot()
    if (!root) return
    seededRef.current = true
    void seedWorkspaceCheckpoint(root, event.path, event.beforeContent, event.beforeExisted).catch(
      (err: unknown) => {
        console.warn(`copilot: could not seed checkpoint for ${event.path}: ${errorMessage(err)}`)
      },
    )
    // The SDK already wrote the file; tell the workspace to reflect it live in
    // the editor buffer (design F5: "改动即时进编辑器 buffer").
    onFileChanged?.(event.path, 'applied')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onAccept = async () => {
    setBusy(true)
    try {
      const root = resolveRoot()
      if (root) {
        // The edit is already on disk (apply-then-review); just drop the
        // checkpoint so it can't be rewound later.
        await clearWorkspaceCheckpoint(root, event.path)
      }
      setReview('accepted')
      // Reviewed code is final — recompile so predict/run use it (改后自动 compile).
      onFileChanged?.(event.path, 'accepted')
    } catch (err: unknown) {
      toast.error(`Couldn't accept change: ${errorMessage(err)}`)
    } finally {
      setBusy(false)
    }
  }

  const onReject = async () => {
    setBusy(true)
    try {
      const root = resolveRoot()
      if (!root) {
        throw new Error('No workspace to restore into (desktop only).')
      }
      // Rewind through the Rust sole writer from the checkpoint seeded on apply:
      // write-back for an edited file, delete for a copilot-created one. This is
      // the design's "Reject 经 Rust 从 checkpoint 还原" — not a blind overwrite.
      await restoreWorkspaceFile(root, event.path)
      setReview('rejected')
      // File rewound on disk — reload the editor buffer + recompile.
      onFileChanged?.(event.path, 'rejected')
    } catch (err: unknown) {
      toast.error(`Couldn't revert change: ${errorMessage(err)}`)
    } finally {
      setBusy(false)
    }
  }

  const verb = event.beforeExisted ? 'Edited' : 'Created'
  const Icon = event.beforeExisted ? FilePenLine : FilePlus2

  return (
    <div className="mt-2 rounded-md border border-border bg-muted/30 text-xs">
      <div className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-1.5">
        <div className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
          <Icon className="size-3.5 shrink-0" />
          <span className="truncate">{verb} {event.path}</span>
          <span className="shrink-0 font-normal text-muted-foreground">
            <span className="text-emerald-600 dark:text-emerald-400">+{stats.added}</span>{' '}
            <span className="text-red-600 dark:text-red-400">−{stats.removed}</span>
          </span>
        </div>
        {review === 'pending' ? (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              disabled={busy}
              onClick={onReject}
              className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-muted-foreground hover:bg-background disabled:opacity-50"
            >
              <RotateCcw className="size-3" /> Reject
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onAccept}
              className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-primary hover:bg-primary/20 disabled:opacity-50"
            >
              <Check className="size-3" /> Accept
            </button>
          </div>
        ) : (
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 ${
              review === 'accepted'
                ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            {review === 'accepted' ? <Check className="size-3" /> : <X className="size-3" />}
            {review === 'accepted' ? 'Accepted' : 'Reverted'}
          </span>
        )}
      </div>
      <pre className="max-h-72 overflow-auto px-2.5 py-2 font-mono leading-relaxed">
        {rows.map((row, index) => (
          <div
            key={index}
            className={
              row.kind === 'add'
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                : row.kind === 'del'
                  ? 'bg-red-500/10 text-red-700 dark:text-red-300'
                  : 'text-muted-foreground'
            }
          >
            <span className="select-none opacity-60">
              {row.kind === 'add' ? '+' : row.kind === 'del' ? '−' : ' '}{' '}
            </span>
            {row.text || ' '}
          </div>
        ))}
      </pre>
    </div>
  )
}

export const PatchProposedBubble = React.memo(PatchProposedBubbleBase)
