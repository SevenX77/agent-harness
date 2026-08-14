import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import type { ResumeRunOptions } from "@/api/client"
import { isStaticEdgeInference, type StaticEdgeField } from "@/lib/edge-static-inference"
import type { SelectedEdge } from "../studio/WorkspaceContext"
import { edgeTamperResumeOptionsFromJson } from "../studio/panels/edge-tamper"
import { EdgeTamperEditor } from "../studio/panels/EdgeTamperEditor"

/**
 * The edge-scope OPERATOR section (decision 2026-08-13 D5): what remains of
 * the old EdgeContextView after its semantic display retired into the trace
 * rows below it. EdgeTamperEditor is an operation — edit the dispatched
 * blackboard, resume downstream — not a display, so it stays in the panel;
 * the pre-run static inference stays too, because before a run exists there
 * are no events for the rows to show (F4's static half).
 */

function recordOf(contextJson: SelectedEdge["contextJson"]): Record<string, unknown> {
  return contextJson && typeof contextJson === "object" ? (contextJson as Record<string, unknown>) : {}
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

export function EdgeTamperSection({
  selectedEdge,
  onResumeDownstream,
  resumeLoading = false,
}: {
  selectedEdge: SelectedEdge
  onResumeDownstream?: (options: ResumeRunOptions) => Promise<void> | void
  resumeLoading?: boolean
}) {
  const staticInference = isStaticEdgeInference(selectedEdge.contextJson) ? selectedEdge.contextJson : null
  const blackboard = blackboardOf(selectedEdge.contextJson)
  const disabledReason = resumeDisabledReason(selectedEdge.contextJson)
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

  if (staticInference) {
    return <StaticInferenceBody fields={staticInference.fields} target={selectedEdge.target} />
  }
  if (selectedEdge.contextJson == null) {
    return (
      <div className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        No transition recorded for this edge in the current run. Run the skill to capture the
        dispatched blackboard.
      </div>
    )
  }
  return (
    <div className="space-y-2">
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
