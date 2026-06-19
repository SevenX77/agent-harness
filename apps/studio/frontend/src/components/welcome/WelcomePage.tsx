import { AlertCircle, Clock3, FolderOpen, Layers, Layers3, MoreVertical, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useAppSettings } from '../../hooks/useAppSettings'
import { useRecentSkills } from '../../hooks/useRecentSkills'
import { useSkills } from '../../hooks/useSkills'
import { getRuntimeConfig } from '../../config/runtime'
import { revealInFileManager, selectSkillDirectory, addRecentWorkspace, ensureWorkspaceSupportDirs } from '../../lib/tauri'
import { errorMessage, isRecord } from '../../utils/errors'
import { joinDirectoryPath } from '../../utils/skill-paths'
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
  ContextMenuTrigger,
} from '../ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '../ui/empty'
import { Skeleton } from '../ui/skeleton'
import { createLocalWorkspaceSelection, isAbsolutePath } from '../studio/workspace-identity'
import { NewSkillDialog } from './NewSkillDialog'
import { formatLastRun, normalizeSkillId, shortPath, skillIdFromPath } from './utils'

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

export function defaultSkillsDirectory(customDirectory?: string | null): string | null {
  if (customDirectory) return customDirectory
  const config = getRuntimeConfig()
  if (config?.configDir) {
    return `${config.configDir}/Skills`
  }
  return '/studio/config/Skills'
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

function ignorePromise(promise: Promise<unknown>) {
  promise.catch(() => undefined)
}

export function registeredSkillIdForImport(directoryPath: string, skills: SkillSummary[]): string | null
export function registeredSkillIdForImport(): string | null {
  return null
}

interface WorkspaceCardModel {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
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

function relativeLintFile(value: string): string | null {
  const match = value.match(/(?:^|[\\/])?((?:phases[\\/][A-Za-z0-9_-]+[\\/](?:LOGIC|SUBGRAPH|SKILL)\.md)|GRAPH\.md|io[\\/]inputs\.json|io[\\/]outputs\.json)/)
  return match ? match[1].replace(/\\/g, '/') : null
}

function lineFromLintMessage(value: string): string | null {
  const match = value.match(/(?:GRAPH\.md|io[\\/](?:inputs|outputs)\.json|phases[\\/][A-Za-z0-9_-]+[\\/](?:LOGIC|SUBGRAPH|SKILL)\.md):(?<line>\d+)/)
  return match?.groups?.line ?? null
}

function isMissingPythonCallable(message: string) {
  return /python_callable/.test(message) && /(Input should be a valid string|required)/.test(message)
}

function cleanLintMessage(message: string): string {
  if (isMissingPythonCallable(message)) {
    return 'LOGIC.md hit a legacy python_callable validator. MVP1 logic phases use actions/<phase>.py, not LOGIC.md python callable blocks.'
  }
  return message
    .replace(/\s*For further information visit https:\/\/errors\.pydantic\.dev\/\S+/g, '')
    .replace(/\[F-[^\]]+\]\s*/g, '')
    .replace(/^.*(?:GRAPH\.md|io[\\/](?:inputs|outputs)\.json|phases[\\/][A-Za-z0-9_-]+[\\/](?:LOGIC|SUBGRAPH|SKILL)\.md):\d+\s*/s, '')
    .trim()
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
  const file = typeof first.file === 'string'
    ? relativeLintFile(first.file)
    : relativeLintFile(first.message)
  const line = typeof first.line === 'number'
    ? String(first.line)
    : lineFromLintMessage(first.message)
  const location = [
    file,
    line,
  ].filter(Boolean).join(':')
  const message = cleanLintMessage(first.message)
  return location ? `${location} ${message}` : message
}

function requestValidationMessage(payload: StudioErrorPayload): string {
  const errors = payload.details?.errors
  const first = Array.isArray(errors) && isRecord(errors[0]) ? errors[0] : null
  const location = first && Array.isArray(first.loc) ? first.loc.join('.') : ''
  if (location.includes('import_existing')) {
    return 'the running backend does not support folder import yet. Quit and restart Studio so the updated sidecar is loaded.'
  }
  return 'the request did not match the /skills API contract.'
}

function existingSkillIdFromError(error: unknown): string | null {
  const payload = studioErrorPayload(error)
  if (payload?.error_code !== 'SKILL_ALREADY_EXISTS') {
    return null
  }
  const existingSkillId = payload.details?.skill_id
  return typeof existingSkillId === 'string' ? existingSkillId : null
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
    if (payload.message?.toLowerCase() === 'request validation failed') {
      return `Cannot create "${skillId}": ${requestValidationMessage(payload)}`
    }
    return `Cannot create "${skillId}": ${firstLintErrorMessage(payload) ?? sentenceFragment(payload.message ?? 'manifest validation failed')}`
  }
  return errorMessage(error)
}

export function formatImportSkillError(error: unknown): string {
  const payload = studioErrorPayload(error)
  if (payload?.error_code === 'INVALID_DIRECTORY_PATH' && payload.message) {
    if (payload.message.includes('missing GRAPH.md or SKILL.md')) {
      return `Cannot import this folder: ${sentenceFragment(payload.message.replace(/: missing GRAPH\.md or SKILL\.md\./, ''))}`
    }
    return `Cannot import this folder: ${sentenceFragment(payload.message)}`
  }
  if (payload?.error_code === 'SKILL_ALREADY_EXISTS') {
    const existingSkillId = payload.details?.skill_id
    return typeof existingSkillId === 'string'
      ? `Cannot import this folder: it is already registered as "${existingSkillId}".`
      : 'Cannot import this folder: it is already registered.'
  }
  if (payload?.error_code === 'MANIFEST_VALIDATION_FAILED') {
    if (payload.message?.toLowerCase() === 'request validation failed') {
      return requestValidationMessage(payload)
    }
    return firstLintErrorMessage(payload) ?? sentenceFragment(payload.message ?? 'manifest validation failed')
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
  const appSettings = useAppSettings()
  const defaultSkillParentDirectory = defaultSkillsDirectory(appSettings.settings.default_skills_directory)
  const { skillListError, mutateSkills } = useSkills(null)
  const { recentWorkspaces, rememberWorkspace, isHydrating } = useRecentSkills()

  // Recent is a pure MRU projection (D11/D-1-1): each card is one localStorage
  // recentWorkspaces entry, no registry-derived fields and no registry merge.
  const visibleWorkspaces: WorkspaceCardModel[] = recentWorkspaces.map((w) => ({
    absolutePath: w.absolutePath,
    displayName: w.displayName,
    identity: w.identity,
    lastOpenedAt: w.lastOpenedAt,
  }))

  const resolveBackendSkillIdForWorkspace = async (workspaceRoot: string, backendSkillId?: string) => {
    if (backendSkillId) {
      return backendSkillId
    }
    if (!isAbsolutePath(workspaceRoot)) {
      return workspaceRoot
    }
    try {
      const response = await api.post<SkillSummary>('/skills', buildSkillImportPayload(workspaceRoot))
      await mutateSkills()
      return response.data.id
    } catch (error) {
      const existingSkillId = existingSkillIdFromError(error)
      if (existingSkillId) {
        await mutateSkills()
        return existingSkillId
      }
      throw error
    }
  }

  const openSkill = async (workspaceRoot: string, displayName?: string, backendSkillId?: string) => {
    const name = displayName || skillIdFromPath(workspaceRoot)
    const resolvedSkillId = await resolveBackendSkillIdForWorkspace(workspaceRoot, backendSkillId)
    rememberWorkspace({ absolutePath: workspaceRoot, displayName: name })
    ignorePromise(addRecentWorkspace(workspaceRoot, name, `local:${workspaceRoot}`, new Date().toISOString()))
    ignorePromise(ensureWorkspaceSupportDirs(workspaceRoot))
    onSelectSkill(
      isAbsolutePath(workspaceRoot)
        ? createLocalWorkspaceSelection(resolvedSkillId, workspaceRoot)
        : resolvedSkillId
    )
  }

  const openWorkspace = (workspace: WorkspaceCardModel) => {
    openSkill(workspace.absolutePath, workspace.displayName).catch((error) => {
      toast.error('Open folder failed', { description: formatImportSkillError(error) })
    })
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
      const directory = await selectSkillDirectory(defaultSkillParentDirectory)
      if (directory) {
        setNewSkillParentDirectory(directory)
      }
    } finally {
      setSelectingNewSkillParent(false)
    }
  }

  const handleReveal = (workspace: { absolutePath: string }) => {
    ignorePromise(revealInFileManager(workspace.absolutePath))
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
      await openSkill(response.data.directory_path || response.data.id, response.data.name, response.data.id)
    } catch (error) {
      setNewSkillError(formatCreateSkillError(error, skillId))
    } finally {
      setCreating(false)
    }
  }

  const importSkillDirectory = async () => {
    setImporting(true)
    try {
      const directory = await selectSkillDirectory(defaultSkillParentDirectory)
      if (!directory) {
        return
      }
      await openSkill(directory)
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
            <p
              title={defaultSkillParentDirectory ?? undefined}
              className="mt-1 truncate text-xs text-muted-foreground"
            >
              {defaultSkillParentDirectory ? `Default: ${defaultSkillParentDirectory}` : 'Default: AgentStudio/Skills'}
            </p>
          </div>
          <div>
            <Button
              variant="outline"
              size="lg"
              disabled={importing}
              onClick={() => {
                ignorePromise(importSkillDirectory())
              }}
              className="w-full justify-start"
            >
              <FolderOpen />
              {importing ? 'Opening' : 'Open folder'}
            </Button>
            <p className="mt-1 truncate text-xs text-muted-foreground">Choose any local folder</p>
          </div>
        </div>

        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Recent</h2>
        </div>

        {skillListError ? (
          <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <div className="flex items-center gap-2 font-medium">
              <AlertCircle className="size-4" />
              Could not load skills
            </div>
          </div>
        ) : null}

        {!skillListError && isHydrating ? (
          <RecentSkeleton />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {visibleWorkspaces.map((workspace) => (
              <ContextMenu key={workspace.identity}>
                <ContextMenuTrigger asChild>
                  <Card
                    size="sm"
                    role="button"
                    tabIndex={0}
                    onClick={() => openWorkspace(workspace)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        openWorkspace(workspace)
                      }
                    }}
                    className="relative cursor-pointer select-none transition-colors hover:ring-2 hover:ring-primary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  >
                    <CardHeader className="px-3 pb-0">
                      <div className="flex items-start gap-3">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                          <Layers3 className="size-4" />
                        </div>
                        <div className="min-w-0 flex-1 pr-12">
                          <CardTitle className="truncate text-sm">{workspace.displayName}</CardTitle>
                          <p className="mt-1 line-clamp-2 min-h-10 break-all font-mono text-[11px] leading-5 text-muted-foreground">
                            {shortPath(workspace.absolutePath)}
                          </p>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`More actions for ${workspace.displayName}`}
                              className="absolute right-2 top-2 z-10"
                              onClick={(event) => event.stopPropagation()}
                              onPointerDown={(event) => event.stopPropagation()}
                              onKeyDown={(event) => event.stopPropagation()}
                            >
                              <MoreVertical />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align="end"
                            className={ACTION_MENU_CLASSNAME}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <DropdownMenuItem onSelect={() => handleReveal(workspace)}>
                              <FolderOpen />
                              {REVEAL_ACTION_LABEL}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </CardHeader>
                    <CardFooter className="justify-end gap-3 px-3 pt-0 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <Clock3 className="size-3.5" />
                        {formatLastRun(workspace.lastOpenedAt || null)}
                      </span>
                    </CardFooter>
                  </Card>
                </ContextMenuTrigger>
                <ContextMenuContent className={ACTION_MENU_CLASSNAME}>
                  <ContextMenuItem onSelect={() => handleReveal(workspace)}>
                    <FolderOpen />
                    {REVEAL_ACTION_LABEL}
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            ))}
          </div>
        )}

        {!skillListError && !isHydrating && visibleWorkspaces.length === 0 ? (
          <Empty className="min-h-40 border border-dashed border-border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FolderOpen />
              </EmptyMedia>
              <EmptyTitle>No recent skills</EmptyTitle>
              <EmptyDescription>Create a new skill or open a folder to get started.</EmptyDescription>
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
        defaultParentDirectory={defaultSkillParentDirectory}
        selectingParentDirectory={selectingNewSkillParent}
        onChooseParentDirectory={() => {
          ignorePromise(chooseNewSkillParentDirectory())
        }}
        newSkillError={newSkillError}
        creating={creating}
        onSubmit={submitNewSkill}
      />
    </div>
  )
}

/**
 * N1 Home · atom #8 (recent-skeleton).
 *
 * Loading placeholder for the Recent grid during the cold-start / pre-hydration
 * window (D6), shown by WelcomePage while useRecentSkills reports isHydrating.
 * Mirrors the recent-card shape — icon tile + name + path bars — using the
 * shared shadcn Skeleton, the same primitive ProviderListSkeleton uses, so the
 * first paint reads as the Recent grid rather than a blank flash.
 */
export function RecentSkeleton({ count = 2 }: { count?: number }) {
  return (
    <div data-recent-skeleton="true" className="grid gap-3 sm:grid-cols-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-md border p-3">
          <div className="flex items-start gap-3">
            <Skeleton className="size-8 shrink-0 rounded-md" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
