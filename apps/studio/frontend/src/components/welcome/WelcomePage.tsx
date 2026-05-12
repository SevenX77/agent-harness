import { AlertCircle, Clock3, FolderOpen, Layers, Layers3, Plus, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useRecentSkills } from '../../hooks/useRecentSkills'
import { useSkills } from '../../hooks/useSkills'
import { selectSkillDirectory } from '../../lib/tauri'
import { generateSkillMd } from '../../templates/skillMdGenerator'
import { errorMessage } from '../../utils/errors'

interface WelcomePageProps {
  onSelectSkill: (skillId: string) => void
}

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

  return [...recent, ...remaining]
}

function cleanupWorkspaceLayoutStorage(validSkillIds: string[]) {
  if (typeof window === 'undefined') {
    return
  }

  const valid = new Set(validSkillIds)
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index)
    if (!key?.startsWith('workspace-layout-')) {
      continue
    }

    const skillId = key.replace('workspace-layout-', '')
    if (skillId === 'new' || valid.has(skillId)) {
      continue
    }

    localStorage.removeItem(key)
  }
}

function skillIdFromPath(path: string) {
  const name = path.split(/[\\/]/).filter(Boolean).pop() ?? 'imported-skill'
  const normalized = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const withLetter = /^[a-z]/.test(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'imported-skill'
}

function normalizeSkillId(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const withLetter = /^[a-z]/.test(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'new-skill'
}

export function WelcomePage({ onSelectSkill }: WelcomePageProps) {
  const [importing, setImporting] = useState(false)
  const [creating, setCreating] = useState(false)
  const { skills, skillListError, mutateSkills } = useSkills(null)
  const skillIds = useMemo(() => skills.map((skill) => skill.id), [skills])
  const { recentSkills, rememberSkill } = useRecentSkills(skillIds)
  const visibleSkills = useMemo(() => sortRecent(skills, recentSkills), [recentSkills, skills])

  useEffect(() => {
    cleanupWorkspaceLayoutStorage(skillIds)
  }, [skillIds])

  const openSkill = (skillId: string) => {
    rememberSkill(skillId)
    onSelectSkill(skillId)
  }

  const createSkill = async () => {
    const name = window.prompt('Skill name', 'new-skill')
    if (!name) {
      return
    }
    const skillId = normalizeSkillId(name)
    setCreating(true)
    try {
      const response = await api.post<SkillSummary>('/skills', {
        skill_id: skillId,
        content: generateSkillMd({
          templateId: 'empty-agent',
          templateContent: null,
          type: 'agent',
          skillId,
          name: skillId,
          description: `Created in Studio`,
          tags: '',
          inputs: [{ id: 'input', name: 'input_text', type: 'str', defaultValue: '' }],
          phaseId: 'draft',
          llmRole: 'analyst',
          prompt: 'Use {input_text} to complete the task.',
        }),
      })
      await mutateSkills()
      openSkill(response.data.id)
    } catch (error) {
      window.alert(errorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  const importSkillDirectory = async () => {
    setImporting(true)
    try {
      const directory = await selectSkillDirectory()
      if (!directory) {
        return
      }
      const skillId = skillIdFromPath(directory)
      const response = await api.post<SkillSummary>('/skills', {
        skill_id: skillId,
        directory_path: directory,
        content: generateSkillMd({
          templateId: 'empty-agent',
          templateContent: null,
          type: 'agent',
          skillId,
          name: skillId,
          description: `Imported from ${directory}`,
          tags: '',
          inputs: [{ id: 'input', name: 'input_text', type: 'str', defaultValue: '' }],
          phaseId: 'draft',
          llmRole: 'analyst',
          prompt: 'Use {input_text} to complete the task.',
        }),
      })
      await mutateSkills()
      openSkill(response.data.id)
    } catch (error) {
      window.alert(errorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="flex size-full items-center justify-center bg-background p-6">
      <section className="w-full max-w-3xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-foreground">
            <Layers className="size-6 text-background" strokeWidth={2} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">GSkill Studio</h1>
            <p className="text-sm text-muted-foreground">Open a skill to start editing.</p>
          </div>
        </div>

        <div className="mb-6 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            disabled={creating}
            onClick={() => void createSkill()}
            className="flex h-11 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="size-4" />
            {creating ? 'Creating' : 'New skill'}
          </button>
          <button
            type="button"
            disabled={importing}
            onClick={() => void importSkillDirectory()}
            className="flex h-11 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FolderOpen className="size-4" />
            {importing ? 'Importing' : 'Import skill'}
          </button>
        </div>

        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Recent skills</h2>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Sparkles className="size-3.5" />
            Desktop workspace
          </span>
        </div>

        {skillListError ? (
          <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <div className="flex items-center gap-2 font-medium">
              <AlertCircle className="size-4" />
              Could not load skills
            </div>
          </div>
        ) : null}

        <div className="grid max-h-[50vh] gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
          {visibleSkills.map((skill) => (
            <button
              key={skill.id}
              type="button"
              onClick={() => openSkill(skill.id)}
              className="group flex min-h-32 flex-col justify-between rounded-md border border-border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/45 hover:bg-accent/50"
            >
              <div>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="flex size-8 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                    <Layers3 className="size-4" />
                  </div>
                  {skill.has_golden ? (
                    <span className="rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">Golden</span>
                  ) : null}
                </div>
                <h3 className="line-clamp-2 text-sm font-semibold text-foreground group-hover:text-primary">
                  {skill.name}
                </h3>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{skill.description}</p>
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
          <div className="grid min-h-40 place-items-center rounded-md border border-dashed border-border bg-card p-6 text-center">
            <div>
              <FolderOpen className="mx-auto mb-3 size-8 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">No skills found</h3>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">Create or import a skill to populate this workspace.</p>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  )
}
