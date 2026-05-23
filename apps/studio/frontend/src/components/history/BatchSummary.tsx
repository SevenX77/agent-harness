import type { BatchRunStatus } from '../../api/types'
import { renderBatchReport, reportFileBase } from '../../utils/reportTemplates'
import { ExportButton } from '../export/ExportButton'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Progress } from '../ui/progress'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table'

interface BatchSummaryProps {
  status: BatchRunStatus | null
  onOpenRun: (runId: string) => void
}

function progressPercent(status: BatchRunStatus): number {
  return status.total === 0 ? 0 : Math.round((status.completed / status.total) * 100)
}

function statusVariant(status: string): 'default' | 'destructive' | 'outline' {
  if (status === 'failed') {
    return 'destructive'
  }
  return status === 'success' ? 'default' : 'outline'
}

export function BatchSummary({ status, onOpenRun }: BatchSummaryProps) {
  if (!status) {
    return (
      <section className="flex flex-1 items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Run a batch to see progress and per-case results.
      </section>
    )
  }

  const percent = progressPercent(status)

  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-background p-4">
      <div className="mb-4 rounded-md border border-border bg-card p-4 text-card-foreground">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-foreground">{status.batch_id}</h3>
            <Badge variant={statusVariant(status.status)}>{status.status}</Badge>
          </div>
          <div className="text-right text-sm text-muted-foreground">
            <div>{status.completed}/{status.total} complete</div>
            <ExportButton
              label="Export Batch"
              title="Export batch report"
              filenameBase={reportFileBase(status.skill_id, status.batch_id)}
              buildContent={(format) => renderBatchReport({ status }, format)}
            />
          </div>
        </div>
        <Progress value={percent} className="mt-3 h-2" />
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card">
        <Table className="table-fixed">
          <TableHeader className="bg-muted/40 text-xs uppercase text-muted-foreground">
            <TableRow>
              <TableHead className="px-3 py-2">Input</TableHead>
              <TableHead className="w-24 px-3 py-2">Status</TableHead>
              <TableHead className="w-24 px-3 py-2">Tokens</TableHead>
              <TableHead className="w-24 px-3 py-2 text-right">Trace</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {status.items.map((item) => (
              <TableRow key={item.run_id} className="text-sm">
                <TableCell className="truncate px-3 py-2 font-mono text-xs text-foreground">
                  {item.input_id}
                </TableCell>
                <TableCell className="px-3 py-2">
                  <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                </TableCell>
                <TableCell className="px-3 py-2 text-xs text-muted-foreground">
                  {item.metrics?.total_tokens?.toLocaleString() ?? 'n/a'}
                </TableCell>
                <TableCell className="px-3 py-2 text-right">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onOpenRun(item.run_id)}
                  >
                    Open
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}
