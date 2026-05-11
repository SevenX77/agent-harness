import type { GoldenBaseline, JsonObject } from '../../api/types'

interface PredictSplitProps {
  output: JsonObject | null
  baselines: GoldenBaseline[]
}

export function PredictSplit({ output, baselines }: PredictSplitProps) {
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
          <h2 className="text-sm font-semibold text-foreground">Golden baselines</h2>
          <p className="mt-1 text-xs text-muted-foreground">Read-only references for comparison.</p>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-background p-4">
          {baselines.length > 0 ? (
            <div className="space-y-3">
              {baselines.map((baseline) => (
                <div key={baseline.id} className="rounded-md border border-border bg-card p-3 text-sm">
                  <div className="font-mono text-xs font-semibold text-foreground">{baseline.id}</div>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                    <div>linked input: {baseline.linked_input_id}</div>
                    <div>locked: {baseline.locked ? 'yes' : 'no'}</div>
                    <div className="break-all">path: {baseline.content_path}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
              No golden baselines found for this skill.
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
