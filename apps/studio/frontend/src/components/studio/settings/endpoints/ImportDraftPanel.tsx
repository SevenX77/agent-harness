import { GitCompareArrows } from "lucide-react"
import type { ProviderImportDraft } from "@/api/llm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function ImportDraftPanel({
  drafts,
  onApplyDraft,
}: {
  drafts: ProviderImportDraft[]
  onApplyDraft: (draftId: string) => void
}) {
  return (
    <Card size="sm" className="rounded-md">
      <CardHeader className="gap-1">
        <CardTitle className="flex items-center gap-2 text-sm">
          <GitCompareArrows className="size-4 text-primary" />
          Import Drafts
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Agent-discovered endpoints stay here until probe or user diff review confirms them.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {drafts.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
            No import drafts.
          </div>
        ) : null}
        {drafts.map((draft) => {
          const canApply = draft.status === "probed" || draft.status === "conflicted"
          const endpointCandidates = Object.values(draft.endpoint_candidates)
          const routeCandidates = Object.values(draft.route_candidates)
          return (
            <article key={draft.draft_id} className="rounded-md border border-border bg-card p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="break-words text-xs font-semibold text-foreground">{draft.draft_id}</h3>
                  <p className="mt-1 break-words text-[11px] text-muted-foreground">
                    {String(draft.source.url ?? draft.source.name ?? "agent draft")}
                  </p>
                </div>
                <Badge variant={canApply ? "default" : "secondary"}>{draft.status}</Badge>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="min-w-0 rounded-md border border-border/70 p-2">
                  <div className="text-[11px] font-medium text-muted-foreground">Endpoint Candidates</div>
                  {endpointCandidates.map((endpoint) => (
                    <div key={endpoint.endpoint_id} className="mt-1 min-w-0 text-xs text-foreground">
                      <div className="break-words font-medium">{endpoint.display_name}</div>
                      <div className="break-all text-[11px] text-muted-foreground">{endpoint.base_url}</div>
                    </div>
                  ))}
                </div>
                <div className="min-w-0 rounded-md border border-border/70 p-2">
                  <div className="text-[11px] font-medium text-muted-foreground">Route Candidates</div>
                  {routeCandidates.map((route) => (
                    <div key={`${route.endpoint_id}:${route.route_slug}`} className="mt-1 min-w-0 text-xs text-foreground">
                      <div className="break-words font-medium">{route.display_name}</div>
                      <div className="break-all text-[11px] text-muted-foreground">{route.provider_model_id}</div>
                    </div>
                  ))}
                </div>
              </div>

              {Object.keys(draft.diff).length > 0 ? (
                <pre className="mt-3 max-h-32 overflow-auto rounded-md bg-muted/40 p-2 text-[11px] text-muted-foreground">
                  {JSON.stringify(draft.diff, null, 2)}
                </pre>
              ) : null}

              <div className="mt-3 flex justify-end">
                <Button
                  type="button"
                  size="sm"
                  disabled={!canApply}
                  onClick={() => onApplyDraft(draft.draft_id)}
                  aria-label={canApply ? `Apply draft ${draft.draft_id}` : `Apply disabled for ${draft.draft_id}`}
                >
                  {canApply ? "Apply Draft" : "Apply disabled"}
                </Button>
              </div>
            </article>
          )
        })}
      </CardContent>
    </Card>
  )
}
