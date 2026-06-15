import { ArrowLeft } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { SelectedEdge } from "../WorkspaceContext"

/**
 * Trace-owned dot/context view (D14 / properties F3).
 *
 * A graph-edge dot is the "node-to-node state-machine transition point": clicking
 * it shows the blackboard captured as state flows source -> target. The raw-JSON
 * dump that used to live in Properties is removed; trace owns this interpretation
 * (capability: trace-observability, region: timeline). We frame the carried
 * `contextJson` as the transition blackboard (not relabeled node I/O) and surface
 * `changed_keys` as the available "what mutated at this transition" signal. The
 * detailed reduce/filter/inject/persist operation stream is a trace target-design
 * follow-up; it is not fabricated here.
 */

function recordOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> {
  return contextJson && typeof contextJson === "object" ? (contextJson as Record<string, unknown>) : {}
}

function changedKeysOf(contextJson: SelectedEdge["contextJson"]): string[] {
  const raw = recordOf(contextJson).changed_keys
  return Array.isArray(raw) ? raw.filter((key): key is string => typeof key === "string") : []
}

function blackboardOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> | null {
  const record = recordOf(contextJson)
  const snapshot = record.blackboard_snapshot ?? record.inputs
  if (snapshot && typeof snapshot === "object" && !Array.isArray(snapshot)) {
    return snapshot as Record<string, unknown>
  }
  return null
}

function renderValue(value: unknown): string {
  if (typeof value === "string") return value
  return JSON.stringify(value, null, 2)
}

export function EdgeContextView({
  selectedEdge,
  onClear,
}: {
  selectedEdge: SelectedEdge
  onClear: () => void
}) {
  const hasTransition = selectedEdge.contextJson != null
  const blackboard = blackboardOf(selectedEdge.contextJson)
  const changedKeys = changedKeysOf(selectedEdge.contextJson)
  const entries = blackboard ? Object.entries(blackboard) : []

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border px-3">
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={onClear}
          aria-label="Back to timeline"
        >
          <ArrowLeft className="size-4" />
        </Button>
        <span className="text-xs font-medium text-foreground">Blackboard transition</span>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 px-3 py-3">
          <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-3 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Transition
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span className="rounded border border-indigo-900/50 bg-indigo-950/40 px-2 py-0.5 font-mono text-xs text-indigo-400">
                {selectedEdge.source}
              </span>
              <span className="text-xs text-muted-foreground">→</span>
              <span className="rounded border border-emerald-900/50 bg-emerald-950/40 px-2 py-0.5 font-mono text-xs text-emerald-400">
                {selectedEdge.target}
              </span>
            </div>
            <div className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Blackboard state dispatched across this edge during the run.
            </div>
          </div>

          {!hasTransition ? (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              No transition recorded for this edge in the current run. Run the skill to capture the
              dispatched blackboard.
            </div>
          ) : (
            <>
              <div className="rounded-md border border-border bg-card p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Keys changed at this transition
                </div>
                {changedKeys.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {changedKeys.map((key) => (
                      <Badge key={key} variant="outline" className="font-mono text-[10px]">
                        {key}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-muted-foreground">No tracked key changes.</div>
                )}
              </div>

              <div className="rounded-md border border-border bg-card p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Blackboard dispatched into {selectedEdge.target}
                </div>
                {entries.length > 0 ? (
                  <dl className="space-y-2">
                    {entries.map(([key, value]) => (
                      <div key={key} className="flex flex-col gap-1">
                        <dt className="flex items-center gap-1.5 font-mono text-[11px] text-foreground">
                          {key}
                          {changedKeys.includes(key) ? (
                            <Badge variant="outline" className="px-1 py-0 text-[8px]">
                              changed
                            </Badge>
                          ) : null}
                        </dt>
                        <dd className="whitespace-pre-wrap break-all rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
                          {renderValue(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <div className="text-xs text-muted-foreground">Empty blackboard at this transition.</div>
                )}
              </div>

              <div className="text-[11px] leading-relaxed text-muted-foreground/80">
                Detailed reducer / filter / inject / persist operations are part of the run trace
                (target-design); only the dispatched blackboard and changed keys are shown here.
              </div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
