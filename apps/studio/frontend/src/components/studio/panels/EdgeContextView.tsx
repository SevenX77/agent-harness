import { ArrowLeft } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import type { ResumeRunOptions } from "@/api/client"
import type { SelectedEdge } from "../WorkspaceContext"
import { edgeTamperResumeOptionsFromJson } from "./edge-tamper"

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

function objectField(contextJson: SelectedEdge["contextJson"], key: string): Record<string, unknown> | null {
  const raw = recordOf(contextJson)[key]
  return raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : null
}

function blackboardOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> | null {
  const record = recordOf(contextJson)
  const snapshot = record.blackboard_snapshot ?? record.inputs
  if (snapshot && typeof snapshot === "object" && !Array.isArray(snapshot)) {
    return snapshot as Record<string, unknown>
  }
  return null
}

function tamperDiffOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> | null {
  return objectField(contextJson, "tamper_diff") ?? objectField(contextJson, "resume_tamper_diff")
}

function tamperAuditOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> | null {
  return objectField(contextJson, "tamper_audit") ?? objectField(contextJson, "resume_audit")
}

function resumeDisabledReason(contextJson: SelectedEdge["contextJson"]): string | null {
  const validity = objectField(contextJson, "resume_validity")
  const allowed = validity?.resume_allowed
  const reason = validity?.reason
  if (allowed === false && typeof reason === "string" && reason) {
    return reason
  }
  const legacyReason = recordOf(contextJson).resume_disabled_reason
  return typeof legacyReason === "string" && legacyReason ? legacyReason : null
}

function renderValue(value: unknown): string {
  if (typeof value === "string") return value
  return JSON.stringify(value, null, 2)
}

export function EdgeContextView({
  selectedEdge,
  onClear,
  onResumeDownstream,
  resumeLoading = false,
}: {
  selectedEdge: SelectedEdge
  onClear: () => void
  onResumeDownstream?: (options: ResumeRunOptions) => Promise<void> | void
  resumeLoading?: boolean
}) {
  const hasTransition = selectedEdge.contextJson != null
  const blackboard = blackboardOf(selectedEdge.contextJson)
  const tamperDiff = tamperDiffOf(selectedEdge.contextJson)
  const tamperAudit = tamperAuditOf(selectedEdge.contextJson)
  const disabledReason = resumeDisabledReason(selectedEdge.contextJson)
  const changedKeys = changedKeysOf(selectedEdge.contextJson)
  const entries = blackboard ? Object.entries(blackboard) : []
  const initialTamperJson = useMemo(() => JSON.stringify(blackboard ?? {}, null, 2), [blackboard])
  const [tampering, setTampering] = useState(false)
  const [tamperJson, setTamperJson] = useState(initialTamperJson)
  const [tamperError, setTamperError] = useState<string | null>(null)

  useEffect(() => {
    setTampering(false)
    setTamperJson(initialTamperJson)
    setTamperError(null)
  }, [initialTamperJson, selectedEdge.id])

  const handleResumeDownstream = async () => {
    const result = edgeTamperResumeOptionsFromJson(selectedEdge, tamperJson)
    if (!result.ok) {
      setTamperError(result.error)
      return
    }
    setTamperError(null)
    await onResumeDownstream?.(result.options)
  }

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
              <span className="rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-xs text-foreground">
                {selectedEdge.source}
              </span>
              <span className="text-xs text-muted-foreground">→</span>
              <span className="rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-xs text-foreground">
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
                  Original trace frame
                </div>
                <div className="mb-3 text-xs text-muted-foreground">
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

              {tamperDiff ? (
                <div className="rounded-md border border-border bg-card p-3">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Tamper diff
                  </div>
                  {Array.isArray(tamperDiff.changed_keys) ? (
                    <div className="mb-3 flex flex-wrap gap-1.5">
                      {tamperDiff.changed_keys
                        .filter((key): key is string => typeof key === "string")
                        .map((key) => (
                          <Badge key={key} variant="outline" className="font-mono text-[10px]">
                            {key}
                          </Badge>
                        ))}
                    </div>
                  ) : null}
                  <div className="grid gap-2">
                    <DiffBlock label="Before" value={tamperDiff.before} />
                    <DiffBlock label="After" value={tamperDiff.after} />
                  </div>
                </div>
              ) : null}

              {tamperAudit ? (
                <div className="rounded-md border border-border bg-card p-3">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Tamper audit
                  </div>
                  <pre className="whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 px-2 py-2 font-mono text-[11px] text-muted-foreground">
                    {JSON.stringify(tamperAudit, null, 2)}
                  </pre>
                </div>
              ) : null}

              <div className="space-y-3 rounded-md border border-border bg-card p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Tamper downstream resume context
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Edit resume input only; the historical trace above stays read-only.
                    </div>
                    {recordOf(selectedEdge.contextJson).checkpoint_id ? (
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {String(recordOf(selectedEdge.contextJson).checkpoint_id)}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button type="button" variant="outline" size="xs" onClick={() => setTampering(true)}>
                      Tamper
                    </Button>
                    {tampering ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={() => {
                          setTamperJson(initialTamperJson)
                          setTampering(false)
                          setTamperError(null)
                        }}
                      >
                        Cancel
                      </Button>
                    ) : null}
                  </div>
                </div>
                {disabledReason ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <Badge variant="destructive">{disabledReason}</Badge>
                    <span>Checkpoint validity blocks downstream resume.</span>
                  </div>
                ) : null}
                <Textarea
                  aria-label="Tampered edge context JSON"
                  value={tamperJson}
                  readOnly={!tampering}
                  onChange={(event) => setTamperJson(event.target.value)}
                  className="min-h-32 font-mono text-xs"
                />
                {tamperError ? (
                  <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                    {tamperError}
                  </div>
                ) : null}
                <div className="flex justify-end">
                  <Button
                    type="button"
                    size="sm"
                    disabled={Boolean(disabledReason) || !tampering || resumeLoading || !onResumeDownstream}
                    onClick={() => void handleResumeDownstream()}
                  >
                    {disabledReason ? "Resume disabled" : resumeLoading ? "Resuming" : "Resume downstream"}
                  </Button>
                </div>
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

function DiffBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined) {
    return null
  }
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <pre className="whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 px-2 py-2 font-mono text-[11px] text-muted-foreground">
        {renderValue(value)}
      </pre>
    </div>
  )
}
