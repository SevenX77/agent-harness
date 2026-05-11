import { AlertTriangle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { EdgeContextViewer } from '../../components/studio/edge-context-viewer'
import { SkillNode } from '../../components/studio/skill-node'
import { fingerprintText, useCopilotContext } from '../../hooks/useCopilotContext'
import { clearEdgeDraft, readEdgeDraft, writeEdgeDraft } from '../../hooks/useDraftPersist'
import { useSkills } from '../../hooks/useSkills'

export default function Debug() {
  const { skillId = '' } = useParams()
  const { skillDetail } = useSkills(skillId)
  const edgeId = 'draft-to-validate'
  const baseEdge = useMemo(() => JSON.stringify({
    from: 'draft',
    to: 'validate',
    working_memory: { status: 'paused' },
    validator: { status: 'failed', reason: 'sample checkpoint' },
  }, null, 2), [])
  const [edgeDraft, setEdgeDraft] = useState(() => readEdgeDraft(skillId, edgeId) ?? baseEdge)
  const [edgeViewerOpen, setEdgeViewerOpen] = useState(false)
  const edgeDirty = edgeDraft !== baseEdge
  const overrideFingerprint = fingerprintText(edgeDraft)

  useCopilotContext({
    skillId,
    view: 'Run',
    context: {
      debug_view: true,
      paused_node: 'draft',
      error_node: 'validate',
      error_summary: 'Validator failed; backend resume is out of scope for V2.',
      override_dirty: edgeDirty,
      override_fingerprint: overrideFingerprint,
      edge_context: edgeDraft,
    },
  })

  const showResumePlaceholder = () => {
    if (edgeDirty) {
      toast.warning('Edge draft changed; recompile before Resume placeholder is available.')
      return
    }
    // Backend resume remains OOS for V2; this UI deliberately degrades to an informational toast.
    toast.info('HitL Resume 待 backend 实现 (V3 范围)')
  }

  return (
    <main className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background text-foreground">
      <header className="border-b border-border bg-card px-5 py-4">
        <div className="flex items-start gap-3 rounded-md border border-amber-400/40 bg-amber-500/10 p-3 text-amber-700 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          <div>
            <h1 className="text-sm font-semibold">HitL / Error checkpoint</h1>
            <p className="mt-1 text-sm">
              Debug is a V2 UI placeholder. Nodes can show paused/error lock state, but backend resume remains out of scope.
            </p>
          </div>
        </div>
      </header>

      <section className="min-h-0 overflow-auto p-5">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-foreground">{skillDetail?.manifest.name ?? skillId}</h2>
          <p className="mt-1 text-sm text-muted-foreground">Paused nodes are locked until the run is recompiled or backend resume exists.</p>
        </div>
        {edgeDirty ? (
          <div className="mb-4 rounded-md border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
            Edge context draft is dirty. Resume placeholder is disabled until you clear the local draft and recompile.
          </div>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <SkillNode
            name="draft"
            state="paused"
            summary="Waiting for human review before continuing."
            resumeDisabled={edgeDirty}
            onResume={showResumePlaceholder}
          />
          <SkillNode
            name="validate"
            state="error"
            summary="Validator failed; inspect edge context before recompiling."
            resumeDisabled={edgeDirty}
            onResume={showResumePlaceholder}
          />
          <div className="rounded-md border border-border bg-card p-4">
            <h3 className="text-sm font-semibold text-foreground">Edge context draft</h3>
            <p className="mt-1 text-xs text-muted-foreground">Editable localStorage draft only; no backend write.</p>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => setEdgeViewerOpen(true)}
                className="h-8 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground hover:bg-accent"
              >
                Edit JSON
              </button>
              <button
                type="button"
                disabled={!edgeDirty}
                onClick={() => {
                  clearEdgeDraft(skillId, edgeId)
                  setEdgeDraft(baseEdge)
                }}
                className="h-8 rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-45"
              >
                Clear draft
              </button>
            </div>
          </div>
        </div>
      </section>
      <EdgeContextViewer
        title="Editable edge context draft"
        value={edgeDraft}
        open={edgeViewerOpen}
        editable
        onClose={() => setEdgeViewerOpen(false)}
        onChange={(value) => {
          setEdgeDraft(value)
          writeEdgeDraft(skillId, edgeId, value)
        }}
      />
    </main>
  )
}
