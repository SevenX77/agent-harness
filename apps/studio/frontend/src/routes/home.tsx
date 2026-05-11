import { AlertCircle, Clock3, FolderOpen, Layers3, Search, Sparkles } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { SkillSummary } from '../api/types'
import { useRecentSkills } from '../hooks/useRecentSkills'
import { useSkills } from '../hooks/useSkills'

function formatLastRun(value: string | null) {
  if (!value) {
    return 'No runs yet'
  }

  try {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
}

function sortRecent(skills: SkillSummary[], recentSkillIds: string[]) {
  const byId = new Map(skills.map((skill) => [skill.id, skill]))
  const recent = recentSkillIds.map((id) => byId.get(id)).filter((skill): skill is SkillSummary => Boolean(skill))
  const remaining = skills
    .filter((skill) => !recentSkillIds.includes(skill.id))
    .sort((a, b) => (b.last_run_at ?? '').localeCompare(a.last_run_at ?? ''))

  return [...recent, ...remaining].slice(0, 6)
}

export function HomeDashboard() {
  const navigate = useNavigate()
  const { skills, skillListError } = useSkills(null)
  const { recentSkills, rememberSkill } = useRecentSkills()

  const visibleSkills = useMemo(() => sortRecent(skills, recentSkills), [recentSkills, skills])

  const openSkill = (skillId: string) => {
    rememberSkill(skillId)
    void navigate(`/skill/${skillId}/edit`)
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-6 py-8 lg:px-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">
                <Sparkles className="size-3.5" />
                Studio Frontend V2
              </div>
              <h1 className="text-3xl font-semibold tracking-normal text-foreground">Skill Studio</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                Open a skill to edit the graph, compile prompts, and move into prediction or runs from the shared workspace.
              </p>
            </div>
            <button
              type="button"
              className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:opacity-90"
            >
              <FolderOpen className="size-4" />
              Import skill
            </button>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:px-8">
        <div className="min-w-0">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-foreground">Recent skills</h2>
              <p className="text-sm text-muted-foreground">Continue from the last opened skills or recently run projects.</p>
            </div>
            <div className="hidden h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground sm:flex">
              <Search className="size-4" />
              Filter arrives in Stage 4
            </div>
          </div>

          {skillListError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <div className="flex items-center gap-2 font-medium">
                <AlertCircle className="size-4" />
                Could not load skills
              </div>
              <p className="mt-1 text-destructive/80">Check the backend API and refresh this route.</p>
            </div>
          ) : null}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visibleSkills.map((skill) => (
              <button
                key={skill.id}
                type="button"
                onClick={() => openSkill(skill.id)}
                className="group flex min-h-40 flex-col justify-between rounded-md border border-border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/45 hover:bg-accent/50"
              >
                <div>
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="flex size-9 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                      <Layers3 className="size-4" />
                    </div>
                    {skill.has_golden ? (
                      <span className="rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">Golden</span>
                    ) : null}
                  </div>
                  <h3 className="line-clamp-2 text-sm font-semibold text-foreground group-hover:text-primary">
                    {skill.name}
                  </h3>
                  <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{skill.description}</p>
                </div>
                <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                  <span>{skill.phase_count} phases</span>
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="size-3.5" />
                    {formatLastRun(skill.last_run_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {!skillListError && visibleSkills.length === 0 ? (
            <div className="grid min-h-72 place-items-center rounded-md border border-dashed border-border bg-card p-8 text-center">
              <div>
                <FolderOpen className="mx-auto mb-3 size-8 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">No skills found</h3>
                <p className="mt-1 max-w-sm text-sm text-muted-foreground">Import a skill folder or start the backend API to populate this dashboard.</p>
              </div>
            </div>
          ) : null}
        </div>

        <aside className="rounded-md border border-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground">Workspace status</h2>
          <dl className="mt-4 grid gap-3 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Skills</dt>
              <dd className="font-medium text-foreground">{skills.length}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Recent</dt>
              <dd className="font-medium text-foreground">{recentSkills.length}</dd>
            </div>
          </dl>
        </aside>
      </section>
    </main>
  )
}

export default function Home() {
  return <HomeDashboard />
}
