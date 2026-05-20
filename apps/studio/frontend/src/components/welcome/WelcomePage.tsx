import { AlertCircle, AlertTriangle, Clock3, FolderOpen, Layers, Layers3, MoreVertical, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useRecentSkills } from '../../hooks/useRecentSkills'
import { useSkills } from '../../hooks/useSkills'
import { revealInFileManager, selectSkillDirectory } from '../../lib/tauri'
import { generateSkillMd } from '../../templates/skillMdGenerator'
import { errorMessage } from '../../utils/errors'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '../ui/card'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '../ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '../ui/empty'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { NewSkillDialog } from './NewSkillDialog'
import { formatLastRun, normalizeSkillId, shortPath, skillIdFromPath, sortRecent } from './utils'

interface WelcomePageProps {
  onSelectSkill: (skillId: string) => void
}


export function WelcomePage({ onSelectSkill }: WelcomePageProps) {
  const [importing, setImporting] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newSkillOpen, setNewSkillOpen] = useState(false)
  const [newSkillName, setNewSkillName] = useState('new-skill')
  const [newSkillError, setNewSkillError] = useState<string | null>(null)
  const { skills, skillListError, mutateSkills } = useSkills(null)
  const skillIds = useMemo(() => skills.map((skill) => skill.id), [skills])
  const { recentSkills, rememberSkill } = useRecentSkills(skillIds)
  const visibleSkills = useMemo(() => sortRecent(skills, recentSkills), [recentSkills, skills])

  const openSkill = (skillId: string) => {
    rememberSkill(skillId)
    onSelectSkill(skillId)
  }

  const openNewSkillDialog = () => {
    setNewSkillName('new-skill')
    setNewSkillError(null)
    setNewSkillOpen(true)
  }

  const handleReveal = (skill: SkillSummary) => {
    void revealInFileManager(skill.directory_path ?? '')
  }

  const handleDelete = async (skill: SkillSummary) => {
    if (!window.confirm(`Delete skill "${skill.name}"? This cannot be undone.`)) {
      return
    }
    try {
      await api.delete(`/skills/${skill.id}`)
      toast.success(`Deleted ${skill.name}`)
      await mutateSkills()
    } catch (error) {
      toast.error('Could not delete skill', { description: errorMessage(error) })
    }
  }

  const submitNewSkill = async (event?: FormEvent) => {
    event?.preventDefault()
    const trimmed = newSkillName.trim()
    if (!trimmed) {
      setNewSkillError('Name is required')
      return
    }
    const skillId = normalizeSkillId(trimmed)
    setCreating(true)
    setNewSkillError(null)
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
      setNewSkillOpen(false)
      openSkill(response.data.id)
    } catch (error) {
      setNewSkillError(errorMessage(error))
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
    <div className="flex size-full items-start justify-center overflow-y-auto bg-background">
      <section className="w-full max-w-3xl px-6 pb-16 pt-6">
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
          <div>
            <Button
              variant="outline"
              size="lg"
              disabled={creating}
              onClick={openNewSkillDialog}
              className="w-full justify-start"
            >
              <Plus />
              {creating ? 'Creating' : 'New skill'}
            </Button>
            <p className="mt-1 truncate text-xs text-muted-foreground">Default: AgentStudio/Skills</p>
          </div>
          <div>
            <Button
              variant="outline"
              size="lg"
              disabled={importing}
              onClick={() => void importSkillDirectory()}
              className="w-full justify-start"
            >
              <FolderOpen />
              {importing ? 'Importing' : 'Import skill'}
            </Button>
            <p className="mt-1 truncate text-xs text-muted-foreground">Choose any local folder</p>
          </div>
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

        <div className="grid gap-3 sm:grid-cols-2">
          {visibleSkills.map((skill) => (
            <ContextMenu key={skill.id}>
              <ContextMenuTrigger asChild>
                <Card
                  role="button"
                  tabIndex={0}
                  onClick={() => openSkill(skill.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      openSkill(skill.id)
                    }
                  }}
                  className="group cursor-pointer transition-colors hover:ring-primary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <CardHeader>
                    <div className="flex size-8 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                      <Layers3 className="size-4" />
                    </div>
                    <CardAction>
                      <div className="flex items-center gap-2">
                        {skill.has_golden ? <Badge>Golden</Badge> : null}
                        {skill.config_mismatch ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                aria-label="Repo URL mismatch"
                                onClick={(event) => event.stopPropagation()}
                                className="border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                              >
                                <AlertTriangle />
                                Config drift
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent className="max-w-xs text-xs">
                              <div className="space-y-1.5">
                                <div>
                                  <span className="font-medium">Actual:</span>{' '}
                                  <span className="break-all font-mono">{skill.config_mismatch.actual_remote_url}</span>
                                </div>
                                <div>
                                  <span className="font-medium">Expected:</span>{' '}
                                  <span className="break-all font-mono">{skill.config_mismatch.expected_remote_url}</span>
                                </div>
                                <div className="pt-1 text-muted-foreground">{skill.config_mismatch.recommendation}</div>
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        ) : null}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`More actions for ${skill.name}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              <MoreVertical />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align="end"
                            onClick={(event) => event.stopPropagation()}
                          >
                            <DropdownMenuItem onSelect={() => handleReveal(skill)}>
                              <FolderOpen />
                              Reveal in file manager
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => void handleDelete(skill)}
                            >
                              <Trash2 />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </CardAction>
                  </CardHeader>
                  <CardContent>
                    <CardTitle className="line-clamp-2 text-sm">{skill.name}</CardTitle>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{skill.description}</p>
                    <p className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                      {shortPath(skill.directory_path)}
                    </p>
                  </CardContent>
                  <CardFooter className="justify-between gap-3 text-xs text-muted-foreground">
                    <span>{skill.phase_count} phases</span>
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="size-3.5" />
                      {formatLastRun(skill.last_run_at)}
                    </span>
                  </CardFooter>
                </Card>
              </ContextMenuTrigger>
              <ContextMenuContent>
                <ContextMenuItem onSelect={() => handleReveal(skill)}>
                  <FolderOpen />
                  Reveal in file manager
                </ContextMenuItem>
                <ContextMenuSeparator />
                <ContextMenuItem
                  variant="destructive"
                  onSelect={() => void handleDelete(skill)}
                >
                  <Trash2 />
                  Delete
                </ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          ))}
        </div>

        {!skillListError && visibleSkills.length === 0 ? (
          <Empty className="min-h-40 border border-dashed border-border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FolderOpen />
              </EmptyMedia>
              <EmptyTitle>No skills found</EmptyTitle>
              <EmptyDescription>Create or import a skill to populate this workspace.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
      </section>

      <NewSkillDialog
        open={newSkillOpen}
        onOpenChange={setNewSkillOpen}
        newSkillName={newSkillName}
        onNewSkillNameChange={setNewSkillName}
        newSkillError={newSkillError}
        creating={creating}
        onSubmit={submitNewSkill}
      />
    </div>
  )
}
