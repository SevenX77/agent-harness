import { AlertTriangle } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { SkillNode } from '../../components/studio/skill-node'
import { useSkills } from '../../hooks/useSkills'

export default function Debug() {
  const { skillId = '' } = useParams()
  const { skillDetail } = useSkills(skillId)

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

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <SkillNode
            name="draft"
            state="paused"
            summary="Waiting for human review before continuing."
            onResume={() => undefined}
          />
          <SkillNode
            name="validate"
            state="error"
            summary="Validator failed; inspect edge context before recompiling."
            onResume={() => undefined}
          />
        </div>
      </section>
    </main>
  )
}
