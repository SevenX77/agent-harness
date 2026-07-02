import React, { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Check, Columns2, FilePlus2, FilePenLine, RotateCcw, X } from 'lucide-react'
import { toast } from 'sonner'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { computeLineDiff, lineDiffStats } from '../../lib/line-diff'
import { CopilotCompareOverlay } from './copilot-compare-overlay'
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
  workspaceRoot?: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

type Review = 'pending' | 'accepted' | 'rejected'

export type CheckpointStatus =
  | { state: 'seeding' }
  | { state: 'ready' }
  | { state: 'unsafe'; message: string }

export function resolveCopilotCheckpointRoot(
  skillId: string | null,
  workspaceRoot?: string | null,
): string | null {
  const explicitWorkspaceRoot = workspaceRoot?.trim()
  if (explicitWorkspaceRoot) {
    return explicitWorkspaceRoot
  }
  if (!skillId) return null
  return resolveWorkspaceIdentity(skillId).workspaceRoot ?? skillId
}

type SeedWorkspaceCheckpoint = (
  workspaceRoot: string,
  path: string,
  content: string,
  existed: boolean,
) => Promise<unknown>

export async function seedCopilotRestoreCheckpoint({
  root,
  event,
  seedWorkspaceCheckpoint: seedCheckpoint = seedWorkspaceCheckpoint,
  onApplied,
}: {
  root: string | null
  event: Pick<CopilotPatchProposedEvent, 'path' | 'beforeContent' | 'beforeExisted'>
  seedWorkspaceCheckpoint?: SeedWorkspaceCheckpoint
  onApplied: () => void
}): Promise<CheckpointStatus> {
  if (!root) {
    onApplied()
    return { state: 'ready' }
  }

  try {
    await seedCheckpoint(root, event.path, event.beforeContent, event.beforeExisted)
    onApplied()
    return { state: 'ready' }
  } catch (err: unknown) {
    return {
      state: 'unsafe',
      message: `Checkpoint unavailable: this change cannot be safely restored. ${errorMessage(err)}`,
    }
  }
}

function PatchProposedBubbleBase({ event, skillId, workspaceRoot, onFileChanged }: PatchProposedBubbleProps) {
  const [review, setReview] = useState<Review>('pending')
  const [busy, setBusy] = useState(false)
  const [showCompare, setShowCompare] = useState(false)
  const [checkpointStatus, setCheckpointStatus] = useState<CheckpointStatus>({ state: 'seeding' })

  const resolveRoot = (): string | null => {
    return resolveCopilotCheckpointRoot(skillId, workspaceRoot)
  }

  // Apply path (model B): record the pre-edit bytes the moment the edit lands so
  // Reject rewinds the whole pending change through the Rust sole writer.
  // Earliest-wins + durable; uses the bytes the backend shipped in the event
  // (race-free vs re-reading the already-applied file). The seed result gates
  // rollback UI: failure becomes an unsafe restore state, not normal pending.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current) return
    const root = resolveRoot()
    if (!root) return
    seededRef.current = true
    void seedCopilotRestoreCheckpoint({
      root,
      event,
      onApplied: () => {
        // The SDK already wrote the file; tell the workspace to reflect it live
        // in the editor buffer (design F5: "改动即时进编辑器 buffer").
        onFileChanged?.(event.path, 'applied')
      },
    }).then(setCheckpointStatus)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onAccept = async () => {
    setBusy(true)
    try {
      const root = resolveRoot()
      if (root) {
        // The edit is already on disk (apply-then-review); just drop the
        // checkpoint so it can't be rewound later.
        if (checkpointStatus.state !== 'unsafe') {
          await clearWorkspaceCheckpoint(root, event.path)
        }
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
    if (checkpointStatus.state !== 'ready') {
      toast.error(
        checkpointStatus.state === 'unsafe'
          ? checkpointStatus.message
          : 'Restore checkpoint is still being prepared.',
      )
      return
    }
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

  return (
    <PatchProposedBubbleView
      event={event}
      review={review}
      busy={busy}
      checkpointStatus={checkpointStatus}
      showCompare={showCompare}
      onAccept={onAccept}
      onReject={onReject}
      onShowCompare={() => setShowCompare(true)}
      onCloseCompare={() => setShowCompare(false)}
    />
  )
}

export function PatchProposedBubbleView({
  event,
  review,
  busy,
  checkpointStatus,
  showCompare,
  onAccept,
  onReject,
  onShowCompare,
  onCloseCompare,
}: {
  event: CopilotPatchProposedEvent
  review: Review
  busy: boolean
  checkpointStatus: CheckpointStatus
  showCompare: boolean
  onAccept: () => void
  onReject: () => void
  onShowCompare: () => void
  onCloseCompare: () => void
}) {
  const rows = useMemo(
    () => computeLineDiff(event.beforeContent, event.afterContent),
    [event.beforeContent, event.afterContent],
  )
  const stats = useMemo(() => lineDiffStats(rows), [rows])
  const verb = event.beforeExisted ? 'Edited' : 'Created'
  const Icon = event.beforeExisted ? FilePenLine : FilePlus2
  const rejectDisabled = busy || checkpointStatus.state !== 'ready'
  const acceptDisabled = busy || checkpointStatus.state === 'seeding'

  return (
    <div className="mt-2 rounded-md border border-border bg-muted/30 text-xs">
      <div className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-1.5">
        <div className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
          <Icon className="size-3.5 shrink-0" />
          <span className="truncate">{verb} {event.path}</span>
          <span className="shrink-0 font-normal text-muted-foreground">
            <span className="text-success">+{stats.added}</span>{' '}
            <span className="text-destructive">−{stats.removed}</span>
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label="Open side-by-side compare"
            onClick={onShowCompare}
            className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-muted-foreground hover:bg-background"
          >
            <Columns2 className="size-3" /> Compare
          </button>
          {review === 'pending' ? (
            <>
              <button
                type="button"
                aria-label="Reject change"
                disabled={rejectDisabled}
                onClick={onReject}
                className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-muted-foreground hover:bg-background disabled:opacity-50"
              >
                <RotateCcw className="size-3" /> Reject
              </button>
              <button
                type="button"
                disabled={acceptDisabled}
                onClick={onAccept}
                className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-primary hover:bg-primary/20 disabled:opacity-50"
              >
                <Check className="size-3" /> Accept
              </button>
            </>
          ) : (
            <span
              className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 ${
                review === 'accepted'
                  ? 'bg-success/15 text-success'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {review === 'accepted' ? <Check className="size-3" /> : <X className="size-3" />}
              {review === 'accepted' ? 'Accepted' : 'Reverted'}
            </span>
          )}
        </div>
      </div>
      {checkpointStatus.state === 'unsafe' ? (
        <div
          role="alert"
          className="flex items-start gap-1.5 border-b border-border bg-destructive/10 px-2.5 py-2 text-destructive"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>{checkpointStatus.message}</span>
        </div>
      ) : null}
      <pre className="max-h-72 overflow-auto px-2.5 py-2 font-mono leading-relaxed">
        {rows.map((row, index) => (
          <div
            key={index}
            className={
              row.kind === 'add'
                ? 'bg-success/10 text-success'
                : row.kind === 'del'
                  ? 'bg-destructive/10 text-destructive'
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
      {showCompare ? (
        <CopilotCompareOverlay
          path={event.path}
          before={event.beforeContent}
          after={event.afterContent}
          onClose={onCloseCompare}
        />
      ) : null}
    </div>
  )
}

export const PatchProposedBubble = React.memo(PatchProposedBubbleBase)
