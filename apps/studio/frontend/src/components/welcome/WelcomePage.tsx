import { AlertCircle, AlertTriangle, Clock3, FolderOpen, Layers, Layers3, MoreVertical, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useRecentSkills } from '../../hooks/useRecentSkills'
import { useSkills } from '../../hooks/useSkills'
import { revealInFileManager, selectSkillDirectory } from '../../lib/tauri'
import { errorMessage, isRecord } from '../../utils/errors'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import {
  Card,
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

export const REVEAL_ACTION_LABEL = 'Show in folder'
export const ACTION_MENU_CLASSNAME = 'w-48'

interface WelcomePageProps {
  onSelectSkill: (skillId: string) => void
}

interface CreateSkillPayload {
  skill_id: string
  directory_path?: string
  import_existing?: boolean
}

function joinDirectoryPath(parentDirectory: string, folderName: string) {
  const separator = parentDirectory.includes('\\') && !parentDirectory.includes('/') ? '\\' : '/'
  return `${parentDirectory.replace(/[\\/]+$/, '')}${separator}${folderName}`
}

export function buildSkillCreatePayload(name: string, parentDirectory?: string | null): CreateSkillPayload {
  const skillId = normalizeSkillId(name)
  return {
    skill_id: skillId,
    ...(parentDirectory ? { directory_path: joinDirectoryPath(parentDirectory, skillId) } : {}),
  }
}

export function buildSkillImportPayload(directoryPath: string): CreateSkillPayload {
  return {
    skill_id: skillIdFromPath(directoryPath),
    directory_path: directoryPath,
    import_existing: true,
  }
}

interface StudioErrorPayload {
  error_code?: string
  message?: string
  details?: Record<string, unknown>
}

function studioErrorPayload(error: unknown): StudioErrorPayload | null {
  if (!isRecord(error) || !isRecord(error.response) || !isRecord(error.response.data)) {
    return null
  }
  return error.response.data as StudioErrorPayload
}

function sentenceFragment(message: string) {
  return message ? `${message[0].toLowerCase()}${message.slice(1)}` : message
}

function firstLintErrorMessage(payload: StudioErrorPayload): string | null {
  const errors = payload.details?.errors
  if (!Array.isArray(errors) || errors.length === 0) {
    return null
  }
  const first = errors[0]
  if (!isRecord(first) || typeof first.message !== 'string') {
    return null
  }
  const location = [
    typeof first.file === 'string' ? first.file : null,
    typeof first.line === 'number' ? String(first.line) : null,
  ].filter(Boolean).join(':')
  return location ? `${location} ${first.message}` : first.message
}

export function formatCreateSkillError(error: unknown, skillId: string): string {
  const payload = studioErrorPayload(error)
  if (payload?.error_code === 'SKILL_ALREADY_EXISTS') {
    return `Cannot create "${skillId}": a skill with this name already exists. Choose a different name.`
  }
  if (payload?.error_code === 'INVALID_DIRECTORY_PATH' && payload.message) {
    return `Cannot create "${skillId}": ${sentenceFragment(payload.message)}`
  }
  if (payload?.error_code === 'MANIFEST_VALIDATION_FAILED') {
    return `Cannot create "${skillId}": ${firstLintErrorMessage(payload) ?? sentenceFragment(payload.message ?? 'manifest validation failed')}`
  }
  return errorMessage(error)
}

export function formatImportSkillError(error: unknown): string {
  const payload = studioErrorPayload(error)
  if (payload?.error_code === 'INVALID_DIRECTORY_PATH' && payload.message) {
    return `Cannot import this folder: ${sentenceFragment(payload.message)}`
  }
  if (payload?.error_code === 'SKILL_ALREADY_EXISTS') {
    const existingSkillId = payload.details?.skill_id
    return typeof existingSkillId === 'string'
      ? `Cannot import this folder: it is already registered as "${existingSkillId}".`
      : 'Cannot import this folder: it is already registered.'
  }
  if (payload?.error_code === 'MANIFEST_VALIDATION_FAILED') {
    return `Cannot import this folder: ${firstLintErrorMessage(payload) ?? sentenceFragment(payload.message ?? 'manifest validation failed')}`
  }
  return errorMessage(error)
}


export function WelcomePage({ onSelectSkill }: WelcomePageProps) {
  const [importing, setImporting] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newSkillOpen, setNewSkillOpen] = useState(false)
  const [newSkillName, setNewSkillName] = useState('new-skill')
  const [newSkillParentDirectory, setNewSkillParentDirectory] = useState<string | null>(null)
  const [selectingNewSkillParent, setSelectingNewSkillParent] = useState(false)
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
    setNewSkillParentDirectory(null)
    setNewSkillError(null)
    setNewSkillOpen(true)
  }

  const chooseNewSkillParentDirectory = async () => {
    setSelectingNewSkillParent(true)
    try {
      const directory = await selectSkillDirectory()
      if (directory) {
        setNewSkillParentDirectory(directory)
      }
    } finally {
      setSelectingNewSkillParent(false)
    }
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
      const response = await api.post<SkillSummary>('/skills', buildSkillCreatePayload(skillId, newSkillParentDirectory))
      await mutateSkills()
      setNewSkillOpen(false)
      openSkill(response.data.id)
    } catch (error) {
      setNewSkillError(formatCreateSkillError(error, skillId))
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
      const response = await api.post<SkillSummary>('/skills', buildSkillImportPayload(directory))
      await mutateSkills()
      openSkill(response.data.id)
    } catch (error) {
      toast.error('Import failed', { description: formatImportSkillError(error) })
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
                  size="sm"
                  role="button"
                  tabIndex={0}
                  onClick={() => openSkill(skill.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      openSkill(skill.id)
                    }
                  }}
                  className="group min-h-24 cursor-pointer gap-2 rounded-md border border-border py-2.5 ring-1 ring-border/70 transition-colors hover:border-primary/50 hover:bg-accent/30 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <CardHeader className="px-3 pb-0">
                    <div className="flex items-start gap-3">
                      <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                        <Layers3 className="size-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <CardTitle className="truncate text-sm">{skill.name}</CardTitle>
                        <p className="mt-1 truncate font-mono text-[11px] leading-5 text-muted-foreground">
                          {shortPath(skill.directory_path)}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {skill.has_golden ? <Badge>Golden</Badge> : null}
                        {skill.config_mismatch ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                aria-label="Repo URL mismatch"
                                onClick={(event) => event.stopPropagation()}
                                className="border-destructive/40 bg-destructive/10 text-destructive"
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
                            className={ACTION_MENU_CLASSNAME}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <DropdownMenuItem onSelect={() => handleReveal(skill)}>
                              <FolderOpen />
                              {REVEAL_ACTION_LABEL}
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
                    </div>
                  </CardHeader>
                  <CardFooter className="justify-between gap-3 px-3 pt-0 text-xs text-muted-foreground">
                    <span>{skill.phase_count} phases</span>
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="size-3.5" />
                      {formatLastRun(skill.last_run_at)}
                    </span>
                  </CardFooter>
                </Card>
              </ContextMenuTrigger>
              <ContextMenuContent className={ACTION_MENU_CLASSNAME}>
                <ContextMenuItem onSelect={() => handleReveal(skill)}>
                  <FolderOpen />
                  {REVEAL_ACTION_LABEL}
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
        parentDirectory={newSkillParentDirectory}
        selectingParentDirectory={selectingNewSkillParent}
        onChooseParentDirectory={() => void chooseNewSkillParentDirectory()}
        newSkillError={newSkillError}
        creating={creating}
        onSubmit={submitNewSkill}
      />
    </div>
  )
}
