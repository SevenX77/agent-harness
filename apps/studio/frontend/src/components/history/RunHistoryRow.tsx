import { GitCompareArrows, RefreshCw, Trash2 } from 'lucide-react'
import type { RunMetadata } from '../../api/types'
import { runTokenTotal } from '../../hooks/useRunHistory'
import { ExportButton } from '../export/ExportButton'
import type { ExportFormat } from '../../utils/reportTemplates'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { TableCell, TableRow } from '../ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

interface RunHistoryRowProps {
  run: RunMetadata
  selected: boolean
  filenameBase: string
  onSelect: (runId: string) => void
  onReplay: (runId: string) => void
  onCompare: (runId: string) => void
  onExport: (runId: string, format: ExportFormat) => Promise<string> | string
  onDelete: (runId: string) => void
}

function statusVariant(status: RunMetadata['status']): 'default' | 'destructive' | 'outline' {
  if (status === 'failed') {
    return 'destructive'
  }
  return status === 'success' ? 'default' : 'outline'
}

function shortRunId(runId: string): string {
  return runId.length > 18 ? `${runId.slice(0, 18)}...` : runId
}

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) {
    return value
  }
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) {
    return `${seconds}s ago`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return `${Math.floor(hours / 24)}d ago`
}

export function RunHistoryRow({
  run,
  selected,
  filenameBase,
  onSelect,
  onReplay,
  onCompare,
  onExport,
  onDelete,
}: RunHistoryRowProps) {
  const totalTokens = runTokenTotal(run)

  return (
    <TableRow
      data-state={selected ? 'selected' : undefined}
      className="cursor-pointer text-sm"
      onClick={() => onSelect(run.run_id)}
    >
      <TableCell className="px-3 py-2">
        <Badge variant={statusVariant(run.status)}>
          {run.status}
        </Badge>
      </TableCell>
      <TableCell className="px-3 py-2">
        <div className="font-mono text-xs font-semibold text-foreground">
          {shortRunId(run.run_id)}
        </div>
        <div className="text-xs text-muted-foreground">{relativeTime(run.started_at)}</div>
      </TableCell>
      <TableCell className="max-w-[13rem] truncate px-3 py-2 text-xs text-muted-foreground">
        {run.input_summary ?? 'No input summary'}
      </TableCell>
      <TableCell className="px-3 py-2 text-xs text-muted-foreground">
        {totalTokens === null ? 'n/a' : totalTokens.toLocaleString()}
      </TableCell>
      <TableCell className="px-3 py-2">
        <div className="flex items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="Replay run"
                onClick={(event) => {
                  event.stopPropagation()
                  onReplay(run.run_id)
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Replay run</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="Compare run"
                onClick={(event) => {
                  event.stopPropagation()
                  onCompare(run.run_id)
                }}
              >
                <GitCompareArrows className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Compare run</TooltipContent>
          </Tooltip>
          <span onClick={(event) => event.stopPropagation()}>
            <ExportButton
              compact
              title="Export run report"
              filenameBase={filenameBase}
              buildContent={(format) => onExport(run.run_id, format)}
            />
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="Delete run"
                onClick={(event) => {
                  event.stopPropagation()
                  onDelete(run.run_id)
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete run</TooltipContent>
          </Tooltip>
        </div>
      </TableCell>
    </TableRow>
  )
}
