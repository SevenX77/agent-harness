import type { JsonObject } from '../../api/types'

interface PredictSplitProps {
  output: JsonObject | null
  goldenDraft: string
  onGoldenDraftChange: (value: string) => void
}

export function PredictSplit({ output, goldenDraft, onGoldenDraftChange }: PredictSplitProps) {
  return (
    <section className="grid min-h-[28rem] overflow-hidden rounded-md border border-border bg-card md:grid-cols-2">
      <div className="flex min-h-0 flex-col border-b border-border md:border-b-0 md:border-r">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">Predict output</h2>
          <p className="mt-1 text-xs text-muted-foreground">Read-only response from the predict run.</p>
        </div>
        <pre className="min-h-0 flex-1 overflow-auto bg-background p-4 text-xs text-foreground">
          {JSON.stringify(output ?? {}, null, 2)}
        </pre>
      </div>

      <div className="flex min-h-0 flex-col">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">Golden draft</h2>
          <p className="mt-1 text-xs text-muted-foreground">Adjust the baseline before saving.</p>
        </div>
        <textarea
          value={goldenDraft}
          onChange={(event) => onGoldenDraftChange(event.target.value)}
          className="min-h-0 flex-1 resize-none bg-background p-4 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-inset focus:ring-ring"
          spellCheck={false}
          aria-label="Golden draft JSON"
        />
      </div>
    </section>
  )
}
