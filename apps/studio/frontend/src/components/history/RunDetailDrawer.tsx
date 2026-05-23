import { GitCompareArrows, RefreshCw } from 'lucide-react'
import type { RunDetail } from '../../api/types'
import { renderRunReport, reportFileBase } from '../../utils/reportTemplates'
import { ExportButton } from '../export/ExportButton'
import { Button } from '../ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '../ui/sheet'

interface RunDetailDrawerProps {
  detail: RunDetail | null
  skillId: string | null
  open: boolean
  onClose: () => void
  onReplay: (runId: string) => void
  onCompare: (runId: string) => void
}

function jsonBlock(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2)
}

export function RunDetailDrawer({
  detail,
  skillId,
  open,
  onClose,
  onReplay,
  onCompare,
}: RunDetailDrawerProps) {
  if (!open || !detail) {
    return null
  }

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <SheetContent
        className="w-[min(88vw,48rem)] max-w-none p-0 sm:max-w-none"
        side="right"
      >
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="truncate font-mono text-sm font-bold">
            {detail.metadata.run_id}
          </SheetTitle>
          <SheetDescription>
            {detail.metadata.status} / {new Date(detail.metadata.started_at).toLocaleString()}
          </SheetDescription>
        </SheetHeader>

        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          <Button
            type="button"
            onClick={() => onReplay(detail.metadata.run_id)}
            size="sm"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Replay
          </Button>
          <Button
            type="button"
            onClick={() => onCompare(detail.metadata.run_id)}
            size="sm"
            variant="outline"
          >
            <GitCompareArrows className="h-3.5 w-3.5" />
            Compare
          </Button>
          <ExportButton
            label="Export"
            title="Export run report"
            disabled={!skillId}
            filenameBase={reportFileBase(skillId, detail.metadata.run_id)}
            buildContent={(format) => {
              if (!skillId) {
                throw new Error('Select a skill before exporting.')
              }
              return renderRunReport({ skillId, run: detail }, format)
            }}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-2 gap-3">
            <section>
              <h4 className="mb-2 text-xs font-bold uppercase text-muted-foreground">
                Input
              </h4>
              <pre className="max-h-80 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
                {jsonBlock(detail.input_data)}
              </pre>
            </section>
            <section>
              <h4 className="mb-2 text-xs font-bold uppercase text-muted-foreground">
                Output
              </h4>
              <pre className="max-h-80 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
                {jsonBlock(detail.final_context)}
              </pre>
            </section>
          </div>

          <section className="mt-4">
            <h4 className="mb-2 text-xs font-bold uppercase text-muted-foreground">
              Metrics
            </h4>
            <pre className="max-h-48 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
              {jsonBlock(detail.metadata.metrics)}
            </pre>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  )
}
