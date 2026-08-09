import { ArrowLeft } from "lucide-react"
import { useEffect, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { ResumeRunOptions } from "@/api/client"
import { isStaticEdgeInference, type StaticEdgeField } from "@/lib/edge-static-inference"
import type { EdgeOperation, SelectedEdge } from "../WorkspaceContext"
import { edgeTamperResumeOptionsFromJson } from "./edge-tamper"
import { EdgeTamperEditor } from "./EdgeTamperEditor"

/**
 * Trace-owned dot/context view (D14 / properties F3).
 *
 * A graph-edge dot is the "node-to-node state-machine transition point": clicking
 * it shows the blackboard captured as state flows source -> target. The raw-JSON
 * dump that used to live in Properties is removed; trace owns this interpretation
 * (capability: trace-observability, region: timeline). We frame the carried
 * `contextJson` as the transition blackboard (not relabeled node I/O) and surface
 * `changed_keys` as the available "what mutated at this transition" signal.
 *
 * The reduce / dispatch / inject / persist operation log is driven by the real
 * micro-op events the engine emits on the run stream (blackboard_reduce /
 * input_dispatch / input_file_injected / artifact_saved), resolved by
 * edgeContextFromEvents into `contextJson.operations`. Nothing is fabricated:
 * an empty `operations` list renders an explicit empty state.
 */

function recordOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> {
  return contextJson && typeof contextJson === "object" ? (contextJson as Record<string, unknown>) : {}
}

function changedKeysOf(contextJson: SelectedEdge["contextJson"]): string[] {
  const raw = recordOf(contextJson).changed_keys
  return Array.isArray(raw) ? raw.filter((key): key is string => typeof key === "string") : []
}

function operationsOf(contextJson: SelectedEdge["contextJson"]): EdgeOperation[] {
  const raw = recordOf(contextJson).operations
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.filter((op): op is EdgeOperation =>
    op != null && typeof op === "object" && typeof (op as { kind?: unknown }).kind === "string",
  )
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
  // n5 atom #14: a static (pre-run) inference renders the declared-fields view
  // instead of the runtime transition body.
  const staticInference = isStaticEdgeInference(selectedEdge.contextJson) ? selectedEdge.contextJson : null
  const hasTransition = !staticInference && selectedEdge.contextJson != null
  const blackboard = blackboardOf(selectedEdge.contextJson)
  const tamperDiff = tamperDiffOf(selectedEdge.contextJson)
  const tamperAudit = tamperAuditOf(selectedEdge.contextJson)
  const disabledReason = resumeDisabledReason(selectedEdge.contextJson)
  const changedKeys = changedKeysOf(selectedEdge.contextJson)
  const operations = operationsOf(selectedEdge.contextJson)
  const entries = blackboard ? Object.entries(blackboard) : []
  const initialTamperJson = JSON.stringify(blackboard ?? {}, null, 2)
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
          aria-label="Back to run list"
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
              {staticInference
                ? "Fields inferred from the graph's io declarations — this edge has not run yet."
                : "Blackboard state dispatched across this edge during the run."}
            </div>
          </div>

          {staticInference ? (
            <StaticInferenceBody fields={staticInference.fields} target={selectedEdge.target} />
          ) : !hasTransition ? (
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

              <EdgeTamperEditor
                value={tamperJson}
                writable={tampering}
                onChange={setTamperJson}
                onStartTamper={() => setTampering(true)}
                onCancel={() => {
                  setTamperJson(initialTamperJson)
                  setTampering(false)
                  setTamperError(null)
                }}
                onResume={() => void handleResumeDownstream()}
                checkpointId={
                  recordOf(selectedEdge.contextJson).checkpoint_id
                    ? String(recordOf(selectedEdge.contextJson).checkpoint_id)
                    : null
                }
                disabledReason={disabledReason}
                resumeLoading={resumeLoading}
                resumeDisabled={!onResumeDownstream}
              />
              {tamperError ? (
                <div
                  role="alert"
                  className="rounded-md border border-destructive-border bg-destructive-background px-2 py-1 text-xs text-destructive-label"
                >
                  {tamperError}
                </div>
              ) : null}

              <div className="rounded-md border border-border bg-card p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Operations (end → start)
                </div>
                <div className="mb-3 text-xs text-muted-foreground">
                  Reduce / dispatch / inject / persist recorded between {selectedEdge.source} end and{" "}
                  {selectedEdge.target} start.
                </div>
                {operations.length > 0 ? (
                  <ol className="space-y-1.5">
                    {operations.map((operation, index) => (
                      <li key={index} className="flex items-start gap-2">
                        <span className="mt-0.5 w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                          {index + 1}
                        </span>
                        <OperationRow operation={operation} />
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    No operations recorded for this transition.
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

/**
 * n5 atom #14 static-inference body: which fields SHOULD be on the blackboard
 * when the run reaches this dot, derived purely from declarations (root
 * io.inputs + ancestor io.outputs + the target's runtime_config file injections).
 */
function StaticInferenceBody({ fields, target }: { fields: StaticEdgeField[]; target: string }) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Inferred blackboard fields
      </div>
      <div className="mb-3 text-xs text-muted-foreground">
        Root inputs, upstream outputs and file imports expected on the blackboard when the run
        reaches this dot. Run the skill to see the real dispatched values.
      </div>
      {fields.length > 0 ? (
        <dl className="space-y-2">
          {fields.map((field) => (
            <div key={field.name} className="flex flex-col gap-1">
              <dt className="flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-foreground">
                {field.name}
                {field.type ? (
                  <Badge variant="outline" className="px-1 py-0 text-[8px]">
                    {field.type}
                  </Badge>
                ) : null}
                {field.via_file ? (
                  <Badge variant="outline" className="px-1 py-0 text-[8px]">
                    file
                  </Badge>
                ) : null}
                {field.consumed_by_target ? (
                  <Badge variant="outline" className="px-1 py-0 text-[8px]">
                    → {target} input
                  </Badge>
                ) : null}
              </dt>
              <dd className="break-all rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground">
                from {field.from}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="text-xs text-muted-foreground">
          No fields are expected on the blackboard at this edge.
        </div>
      )}
    </div>
  )
}

function OperationLabel({ text }: { text: string }) {
  return (
    <Badge variant="outline" className="shrink-0 px-1.5 py-0 font-mono text-[9px] uppercase tracking-wider">
      {text}
    </Badge>
  )
}

function OperationRow({ operation }: { operation: EdgeOperation }) {
  if (operation.kind === "reduce") {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        <OperationLabel text="reduce" />
        <span className="font-mono text-foreground">{operation.reducer}</span>
        {operation.changed_keys.length > 0 ? (
          <span className="break-all font-mono">→ {operation.changed_keys.join(", ")}</span>
        ) : null}
      </div>
    )
  }
  if (operation.kind === "dispatch") {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        <OperationLabel text="dispatch" />
        <span className="break-all font-mono">
          {operation.dispatched_keys.length > 0 ? operation.dispatched_keys.join(", ") : "(no keys)"}
        </span>
      </div>
    )
  }
  if (operation.kind === "inject") {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        <OperationLabel text="inject" />
        <span className="break-all font-mono text-foreground">{operation.file_ref}</span>
        <span className="font-mono">→ {operation.target_field}</span>
      </div>
    )
  }
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
      <OperationLabel text="persist" />
      <span className="break-all font-mono text-foreground">{operation.name}</span>
      <span className="break-all font-mono">{operation.path}</span>
      {operation.size_bytes != null ? (
        <span className="font-mono">{operation.size_bytes} B</span>
      ) : null}
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
