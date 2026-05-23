import { AlertCircle, GitCommit, RefreshCw, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import type { GitHistoryItem } from '../../api/types'
import { useLocalHistory } from '../../hooks/useRunHistory'
import { errorMessage } from '../../utils/errors'
import { Button } from '../ui/button'

interface HistoryPanelProps {
  skillId: string | null
}

export interface LocalHistoryPanelViewProps {
  history: GitHistoryItem[]
  isLoading: boolean
  error: unknown
  selectedSha: string | null
  revertingSha: string | null
  onSelect: (sha: string) => void
  onRefresh: () => void
  onRevert: (sha: string) => void
}

function shortSha(sha: string): string {
  return sha.slice(0, 7)
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return timestamp
  }
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function kindLabel(kind: GitHistoryItem['kind']): string {
  if (kind === 'auto_run') {
    return 'Auto run'
  }
  if (kind === 'manual') {
    return 'Manual'
  }
  return 'Other'
}

export function LocalHistoryPanelView({
  history,
  isLoading,
  error,
  selectedSha,
  revertingSha,
  onSelect,
  onRefresh,
  onRevert,
}: LocalHistoryPanelViewProps) {
  const selectedItem = history.find((item) => item.sha === selectedSha) ?? null

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <div>
          <h3 className="text-xs font-medium text-foreground">Local History</h3>
          <p className="text-[11px] text-muted-foreground">{history.length} snapshots</p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={onRefresh}
          aria-label="Refresh local history"
          title="Refresh local history"
        >
          <RefreshCw className="size-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {error ? (
          <div className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{errorMessage(error)}</span>
          </div>
        ) : null}

        {isLoading ? (
          <div className="px-2 py-4 text-xs text-muted-foreground">Loading local history...</div>
        ) : null}

        {!isLoading && !error && history.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-xs text-muted-foreground">
            No local history snapshots yet.
          </div>
        ) : null}

        {!isLoading && !error && history.length > 0 ? (
          <div className="space-y-1">
            {history.map((item) => {
              const selected = item.sha === selectedSha
              return (
                <Button
                  key={item.sha}
                  type="button"
                  variant={selected ? 'secondary' : 'ghost'}
                  onClick={() => onSelect(item.sha)}
                  className="h-auto w-full justify-start gap-2 px-2 py-2 text-left text-xs"
                  aria-pressed={selected}
                >
                  <GitCommit className="mt-0.5 size-4 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-foreground">{item.message || shortSha(item.sha)}</span>
                    <span className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                      <span>{shortSha(item.sha)}</span>
                      <span>{kindLabel(item.kind)}</span>
                      <span>{item.author}</span>
                      <span>{formatTimestamp(item.timestamp)}</span>
                    </span>
                  </span>
                </Button>
              )
            })}
          </div>
        ) : null}
      </div>

      <div className="sticky bottom-0 flex shrink-0 items-center justify-between gap-2 border-t border-border bg-background px-3 py-2">
        <div className="min-w-0 text-xs text-muted-foreground">
          {selectedItem ? (
            <span className="truncate">Selected {shortSha(selectedItem.sha)}</span>
          ) : (
            <span>Select a snapshot to revert.</span>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={!selectedItem || revertingSha !== null}
          onClick={() => {
            if (selectedItem) {
              onRevert(selectedItem.sha)
            }
          }}
        >
          <RotateCcw className="size-3.5" />
          {revertingSha ? 'Reverting...' : 'Revert'}
        </Button>
      </div>
    </div>
  )
}

export function HistoryPanel({ skillId }: HistoryPanelProps) {
  const localHistory = useLocalHistory(skillId)
  const [selectedSha, setSelectedSha] = useState<string | null>(null)
  const [revertingSha, setRevertingSha] = useState<string | null>(null)

  const handleRevert = async (sha: string) => {
    setRevertingSha(sha)
    try {
      await localHistory.revert(sha)
      toast.success('Reverted to local history snapshot')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setRevertingSha(null)
    }
  }

  return (
    <LocalHistoryPanelView
      history={localHistory.history}
      isLoading={localHistory.isLoading}
      error={localHistory.error}
      selectedSha={selectedSha}
      revertingSha={revertingSha}
      onSelect={setSelectedSha}
      onRefresh={() => void localHistory.refresh()}
      onRevert={(sha) => void handleRevert(sha)}
    />
  )
}
