import React, { useMemo, useState } from 'react'
import { Check, FilePlus2, FilePenLine, RotateCcw, X } from 'lucide-react'
import { toast } from 'sonner'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { computeLineDiff, lineDiffStats } from '../../lib/line-diff'
import {
  clearWorkspaceCheckpoint,
  restoreWorkspaceFile,
  seedWorkspaceCheckpoint,
  writeWorkspaceFile,
} from '../../lib/tauri'
import { resolveWorkspaceIdentity } from '../studio/workspace-identity'
import { errorMessage } from '../../utils/errors'

interface PatchProposedBubbleProps {
  event: CopilotPatchProposedEvent
  skillId: string | null
}

type Review = 'pending' | 'accepted' | 'rejected'

function PatchProposedBubbleBase({ event, skillId }: PatchProposedBubbleProps) {
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
      if (event.beforeExisted) {
        // Restore the pre-edit bytes through the Rust sole writer.
        await writeWorkspaceFile(root, event.path, event.beforeContent)
      } else {
        // Brand-new file: seed an existed:false checkpoint then restore, which
        // deletes the file the copilot created rather than leaving empty bytes.
        await seedWorkspaceCheckpoint(root, event.path, '', false)
        await restoreWorkspaceFile(root, event.path)
      }
      setReview('rejected')
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
