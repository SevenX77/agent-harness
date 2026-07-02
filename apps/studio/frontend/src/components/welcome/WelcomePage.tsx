import { AlertTriangle, Clock3, FolderOpen, Layers, Layers3, MoreVertical, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import type { SkillSummary } from '../../api/types'
import { useAppSettings } from '../../hooks/useAppSettings'
import { useRecentSkills } from '../../hooks/useRecentSkills'
import { getRuntimeConfig } from '../../config/runtime'
import { revealInFileManager, selectSkillDirectory, ensureWorkspaceSupportDirs, createSkillWorkspace, openSkillWorkspace } from '../../lib/tauri'
import { errorMessage, isRecord } from '../../utils/errors'
import { joinDirectoryPath } from '../../utils/skill-paths'
import { Alert, AlertDescription, AlertTitle } from '../ui/alert'
import { Button } from '../ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
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
export const REMOVE_ACTION_LABEL = 'Remove from recent'
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
  // No real default folder is known yet (no app setting, no runtime config dir).
  // Return null so the UI shows an honest "Default: AgentStudio/Skills" hint and
  // the Rust native-fs writer picks the OS config Skills dir at create time —
  // never a fabricated, non-existent `/studio/config/Skills` placeholder path.
  return null
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

export function formatCreateSkillError(error: unknown, skillId: string): string {
  const payload = studioErrorPayload(error)
  if (payload?.error_code === 'SKILL_ALREADY_EXISTS') {
    return `Cannot create "${skillId}": a skill with this name already exists. Choose a different name.`
  }
  if (payload?.error_code === 'INVALID_DIRECTORY_PATH' && payload.message) {
    return `Cannot create "${skillId}": ${sentenceFragment(payload.message)}`
  }
  // D2 (不卡导入): new-skill creation now writes via the Studio Rust native-fs
  // command, which rejects OS-level failures with a plain error string and emits
  // no structured error_code. Manifest/lint validation copy belongs only to the
  // Open-folder/import path, so the create path surfaces only OS-level reasons
  // (SKILL_ALREADY_EXISTS, INVALID_DIRECTORY_PATH) and otherwise falls through to
  // the raw error message.
  return errorMessage(error)
}

/**
 * Format an Open-folder failure for the toast description.
 *
 * Under D2 (open any local folder, never reject for a missing GRAPH.md/SKILL.md)
 * and D12 (local writes go through the Studio Rust native-fs writer), the open
 * path runs openSkillWorkspace, whose Tauri `invoke` rejects with a PLAIN STRING
 * (or plain object) on OS-level failure only — never the structured
 * StudioErrorPayload that the retired Python POST /skills import returned. So the
 * old manifest/registry rejection branches ("Cannot import this folder", missing
 * GRAPH.md/SKILL.md, lint, request-validation) were unreachable dead copy and are
 * removed. errorMessage surfaces the raw Rust reason directly (errors.ts handles
 * both string and plain-object Tauri rejections).
 */
export function formatImportSkillError(error: unknown): string {
  return errorMessage(error)
}

export function WelcomePage({ onSelectSkill }: WelcomePageProps) {
  const [openingFolder, setOpeningFolder] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newSkillOpen, setNewSkillOpen] = useState(false)
  const [newSkillName, setNewSkillName] = useState('new-skill')
  const [newSkillParentDirectory, setNewSkillParentDirectory] = useState<string | null>(null)
  const [selectingNewSkillParent, setSelectingNewSkillParent] = useState(false)
  const [newSkillError, setNewSkillError] = useState<string | null>(null)
  const appSettings = useAppSettings()
  const defaultSkillParentDirectory = defaultSkillsDirectory(appSettings.settings.default_skills_directory)
  const { recentWorkspaces, rememberWorkspace, removeWorkspace, isHydrating, recentError } = useRecentSkills()

  // Recent is a pure MRU projection (D11/D-1-1): each card is one entry from the
  // Rust native-fs recent_workspaces store, no registry-derived fields and no
  // registry merge.
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
    // D2/D12: opening a folder = register it via the Rust native-fs writer (OS
    // checks only, no manifest validation, no backend registry). Rust derives the
    // skill id from the path and writes the skill_index entry so the read-detail
    // sidecar GET /api/skills/{id} resolves; we encode the SAME id into the
    // local-workspace selection token below.
    const result = await openSkillWorkspace(workspaceRoot)
    return result.skillId
  }

  const openSkill = async (workspaceRoot: string, displayName?: string, backendSkillId?: string) => {
    const name = displayName || skillIdFromPath(workspaceRoot)
    const resolvedSkillId = await resolveBackendSkillIdForWorkspace(workspaceRoot, backendSkillId)
    // Single source of truth: rememberWorkspace writes the MRU entry to the Rust
    // native-fs store (recent_workspaces.json) AND updates the local projection.
    // No second localStorage write — the prior dual-write could diverge.
    rememberWorkspace({ absolutePath: workspaceRoot, displayName: name })
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

  const handleRemove = (workspace: { identity: string; displayName: string }) => {
    removeWorkspace(workspace.identity)
    toast.success(`Removed "${workspace.displayName}" from recent`)
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
      // D12: build dir + scaffold + git init via the Rust native-fs sole writer
      // (no Python POST /skills, no copilot, no manifest lint). Rust writes the
      // skill_index entry keyed by skillId and returns {root, skillId}; openSkill
      // encodes that same id into the local-workspace token so the detail GET
      // resolves. Parent blank -> Rust defaults to the config Skills dir.
      const result = await createSkillWorkspace(newSkillParentDirectory ?? '', skillId)
      setNewSkillOpen(false)
      await openSkill(result.root, trimmed, result.skillId)
    } catch (error) {
      setNewSkillError(formatCreateSkillError(error, skillId))
    } finally {
      setCreating(false)
    }
  }

  // D2/D12: "Open folder" = pick any local folder, then open it through the Rust
  // native-fs writer (no manifest validation, no registry import). On OS-level
  // failure the toast surfaces the raw Rust reason via formatImportSkillError.
  const openFolder = async () => {
    setOpeningFolder(true)
    try {
      const directory = await selectSkillDirectory(defaultSkillParentDirectory)
      if (!directory) {
        return
      }
      await openSkill(directory)
    } catch (error) {
      toast.error('Open folder failed', { description: formatImportSkillError(error) })
    } finally {
      setOpeningFolder(false)
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
            {defaultSkillParentDirectory ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    Default: {defaultSkillParentDirectory}
                  </p>
                </TooltipTrigger>
                <TooltipContent>{defaultSkillParentDirectory}</TooltipContent>
              </Tooltip>
            ) : (
              <p className="mt-1 truncate text-xs text-muted-foreground">Default: AgentStudio/Skills</p>
            )}
          </div>
          <div>
            <Button
              variant="outline"
              size="lg"
              disabled={openingFolder}
              onClick={() => {
                ignorePromise(openFolder())
              }}
              className="w-full justify-start"
            >
              <FolderOpen />
              {openingFolder ? 'Opening' : 'Open folder'}
            </Button>
            <p className="mt-1 truncate text-xs text-muted-foreground">Choose any local folder</p>
          </div>
        </div>

        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Recent</h2>
        </div>

        {/*
          N1 atom #9: when the Recent MRU read / path-validation fails, surface a
          LOCAL red box here. It sits below the always-available New skill / Open
          folder entries, so a Recent failure never blocks creating or opening a
          workspace (D11 不阻塞入口). The reason comes from useRecentSkills, which
          logs the failure rather than swallowing it.
        */}
        {recentError ? (
          <Alert variant="destructive" className="mb-3 border-destructive-border bg-destructive-background">
            <AlertTriangle />
            <AlertTitle>Could not load recent skills</AlertTitle>
            <AlertDescription>{recentError}</AlertDescription>
          </Alert>
        ) : null}

        {isHydrating ? (
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
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => handleRemove(workspace)}
                            >
                              <Trash2 />
                              {REMOVE_ACTION_LABEL}
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
                  <ContextMenuItem
                    variant="destructive"
                    onSelect={() => handleRemove(workspace)}
                  >
                    <Trash2 />
                    {REMOVE_ACTION_LABEL}
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            ))}
          </div>
        )}

        {!isHydrating && visibleWorkspaces.length === 0 ? (
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
