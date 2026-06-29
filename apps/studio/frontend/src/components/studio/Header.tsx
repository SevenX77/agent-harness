import { useEffect, useRef, useState } from "react"
import { ChevronDown, Layers, Loader2, Package, Sparkles } from "lucide-react"
import { toast, type ExternalToast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { usePublishSkill } from "@/hooks/usePublishSkill"
import { useSkillSync } from "@/hooks/useSkillSync"
import { revealInFileManager, writePublishPackage, type WritePublishPackageResult } from "@/lib/tauri"
import type { CollaborateResult, PublishResult, ReleaseArtifactRef } from "@/api/types"

interface HeaderProps {
  skillId: string | null
  workspaceRoot?: string | null
  navStack?: string[]
  copilotOpen: boolean
  onCopilotToggle: () => void
  onHome: () => void
  onBreadcrumbClick?: (index: number) => void
  // Single-click the current-skill title: clear node selection + show the
  // graph.md / global panel. Double-click: open graph.md in the editor.
  onTitleSelect?: () => void
  onTitleEdit?: () => void
  onSyncSuccess?: (result: CollaborateResult) => void
  onOpenSettings?: () => void
}

export interface HeaderReleaseIdentity {
  releaseVersion: string
  artifactId: string
  contentHash: string
  manifestRef: string
  artifactRef: ReleaseArtifactRef
  remoteSyncLabel: string
  a11yLabel: string
}

interface PackageToastApi {
  success: (message: string, options?: ExternalToast) => unknown
  error: (message: string, options?: ExternalToast) => unknown
}

interface ExecutePackageReleaseOptions {
  skillId: string
  workspaceRoot: string | null
  releaseIdentity: HeaderReleaseIdentity
  relativePath?: string
  toastApi?: PackageToastApi
  chooseTargetPath?: (currentPath: string) => string | null | Promise<string | null>
}

interface PackageTargetPathRequest {
  currentPath: string
  resolve: (path: string | null) => void
}

export function Header({
  skillId,
  workspaceRoot = null,
  navStack = skillId ? [skillId] : [],
  copilotOpen,
  onCopilotToggle,
  onHome,
  onBreadcrumbClick,
  onTitleSelect,
  onTitleEdit,
  onSyncSuccess,
  onOpenSettings,
}: HeaderProps) {
  const skillSync = useSkillSync(skillId, { onSyncSuccess })
  const publish = usePublishSkill(skillId, onOpenSettings)
  const [isPackaging, setIsPackaging] = useState(false)
  const [packageTargetRequest, setPackageTargetRequest] = useState<PackageTargetPathRequest | null>(null)
  const [packageTargetDraft, setPackageTargetDraft] = useState("")
  // A double-click on the title would otherwise fire single-click (open the
  // graph.md panel) AND double-click (open the editor). Defer the single-click
  // action so a double-click can cancel it and open the editor alone.
  const titleClickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (titleClickTimerRef.current) clearTimeout(titleClickTimerRef.current)
  }, [])
  const handleTitleClick = () => {
    if (titleClickTimerRef.current) clearTimeout(titleClickTimerRef.current)
    titleClickTimerRef.current = setTimeout(() => {
      titleClickTimerRef.current = null
      onTitleSelect?.()
    }, 220)
  }
  const handleTitleDoubleClick = () => {
    if (titleClickTimerRef.current) {
      clearTimeout(titleClickTimerRef.current)
      titleClickTimerRef.current = null
    }
    onTitleEdit?.()
  }

  const isSaving = skillSync.status === "saving"
  const isSyncing = skillSync.status === "syncing"
  const isSubmitting = skillSync.status === "submitting"
  const isPublishing = publish.status === "publishing"
  const isBusy = isSaving || isSyncing || isSubmitting || isPackaging
  const releaseIdentity = getReleaseIdentity(publish.lastResult)

  const handleSubmitForReview = () => {
    if (!skillId) return
    const devBranch = window.prompt("Dev branch", `review/${skillId}`)
    if (!devBranch) return
    const prTitle = window.prompt("PR title", `Review ${skillId}`)
    if (!prTitle) return
    void skillSync.submit(devBranch, prTitle)
  }

  const handlePackageRelease = async () => {
    if (!skillId || !releaseIdentity) return
    setIsPackaging(true)
    try {
      await executePackageRelease({
        skillId,
        workspaceRoot,
        releaseIdentity,
        chooseTargetPath: choosePackageTargetPath,
      })
    } finally {
      setIsPackaging(false)
    }
  }

  const choosePackageTargetPath = (currentPath: string) => {
    return new Promise<string | null>((resolve) => {
      setPackageTargetDraft(nextPackageRelativePath(currentPath))
      setPackageTargetRequest({ currentPath, resolve })
    })
  }

  const settlePackageTargetPath = (nextPath: string | null) => {
    if (!packageTargetRequest) return
    const resolve = packageTargetRequest.resolve
    setPackageTargetRequest(null)
    setPackageTargetDraft("")
    resolve(nextPath?.trim() || null)
  }

  return (
    <>
    <header className="grid h-11 shrink-0 grid-cols-3 items-center border-b border-border bg-background px-3">
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onHome}
              aria-label="Back to Home"
              className="flex size-6 items-center justify-center rounded-md bg-foreground transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <Layers className="size-3.5 text-background" strokeWidth={2} />
            </button>
          </TooltipTrigger>
          <TooltipContent>Back to Home</TooltipContent>
        </Tooltip>
        <span className="text-sm font-semibold tracking-tight text-foreground">
          GSkill Studio
        </span>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        {navStack.length > 0 ? (
          <nav className="flex min-w-0 items-center gap-1 text-sm font-medium text-foreground">
            {navStack.map((item, index) => {
              // The LAST item is the current-skill title: single-click clears the
              // node selection and shows the graph.md/global panel, double-click
              // opens graph.md in the editor. Earlier crumbs keep navigation.
              const isTitle = index === navStack.length - 1
              return (
                <span key={`${item}-${index}`} className="flex min-w-0 items-center gap-1">
                  {index > 0 ? <span className="text-muted-foreground">/</span> : null}
                  <button
                    type="button"
                    onClick={() => (isTitle && onTitleSelect ? handleTitleClick() : onBreadcrumbClick?.(index))}
                    onDoubleClick={isTitle && onTitleEdit ? handleTitleDoubleClick : undefined}
                    className="truncate rounded-sm px-1 hover:bg-accent"
                  >
                    {item}
                  </button>
                </span>
              )
            })}
          </nav>
        ) : (
          <span className="truncate text-sm font-medium text-foreground">Studio Workspace</span>
        )}
        <Badge variant="outline" className="uppercase">
          Draft
        </Badge>
        {releaseIdentity ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge
                variant="secondary"
                className="max-w-48 truncate"
                aria-label={releaseIdentity.a11yLabel}
              >
                Release {releaseIdentity.releaseVersion}
              </Badge>
            </TooltipTrigger>
            <TooltipContent className="max-w-sm">
              <div className="space-y-1 break-words">
                <div>{releaseIdentity.artifactId}</div>
                <div>{releaseIdentity.contentHash}</div>
                <div>{releaseIdentity.manifestRef}</div>
                <div>{releaseIdentity.remoteSyncLabel}</div>
              </div>
            </TooltipContent>
          </Tooltip>
        ) : null}
        {releaseIdentity ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label="Package release"
                disabled={isPackaging}
                onClick={() => void handlePackageRelease()}
              >
                {isPackaging ? <Loader2 className="size-3 animate-spin" /> : <Package className="size-3.5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Package release</TooltipContent>
          </Tooltip>
        ) : null}
      </div>

      <div className="flex items-center justify-end gap-1.5">
        {skillId ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-7 gap-1 text-xs" disabled={isBusy || isPublishing}>
                {(isBusy || isPublishing) ? <Loader2 className="size-3 animate-spin" /> : null}
                Team
                <ChevronDown className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-44">
              <DropdownMenuItem disabled={isBusy} onClick={() => void skillSync.save()}>
                {isSaving ? <Loader2 className="size-3 animate-spin" /> : null}
                Save to Team
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isBusy} onClick={() => void skillSync.sync()}>
                {isSyncing ? <Loader2 className="size-3 animate-spin" /> : null}
                Sync from Team
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isBusy} onClick={handleSubmitForReview}>
                {isSubmitting ? <Loader2 className="size-3 animate-spin" /> : null}
                Submit for Review
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                Artifact Registry (not git push)
              </DropdownMenuLabel>
              <DropdownMenuItem disabled={isPublishing || isPackaging} onClick={() => void publish.publish()}>
                {isPublishing ? <Loader2 className="size-3 animate-spin" /> : null}
                Release
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!releaseIdentity || isPackaging}
                onClick={() => void handlePackageRelease()}
              >
                {isPackaging ? <Loader2 className="size-3 animate-spin" /> : null}
                Package release
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onCopilotToggle}
              aria-label={copilotOpen ? "Hide Copilot" : "Show Copilot"}
              aria-pressed={copilotOpen}
            >
              <Sparkles />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {copilotOpen ? "Hide Copilot" : "Show Copilot"}
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
    <Dialog
      open={packageTargetRequest !== null}
      onOpenChange={(open) => {
        if (!open) settlePackageTargetPath(null)
      }}
    >
      <DialogContent className="rounded-md">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            settlePackageTargetPath(packageTargetDraft)
          }}
        >
          <DialogHeader>
            <DialogTitle>Package target</DialogTitle>
            <DialogDescription>
              Choose a workspace-relative package file path.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="package-target-path">Path</FieldLabel>
            <Input
              id="package-target-path"
              value={packageTargetDraft}
              onChange={(event) => setPackageTargetDraft(event.target.value)}
              autoFocus
            />
            <FieldDescription>
              Current target: {packageTargetRequest?.currentPath ?? ""}
            </FieldDescription>
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => settlePackageTargetPath(null)}>
              Cancel
            </Button>
            <Button type="submit">Package</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    </>
  )
}

function getReleaseIdentity(result: PublishResult | null): HeaderReleaseIdentity | null {
  if (!result || result.status !== "ok") {
    return null
  }
  const extra = result.extra
  const artifactRef = isReleaseArtifactRef(extra?.artifact_ref) ? extra.artifact_ref : null
  const releaseVersion = stringValue(extra?.release_version)
  const artifactId = stringValue(artifactRef?.artifact_id)
  const contentHash = stringValue(extra?.content_hash) ?? stringValue(artifactRef?.content_hash)
  const manifestRef = stringValue(extra?.manifest_ref) ?? stringValue(artifactRef?.manifest_ref)
  if (!artifactRef || !releaseVersion || !artifactId || !contentHash || !manifestRef) {
    return null
  }
  const remoteLabel = remoteSyncLabel(extra?.remote_sync)
  return {
    releaseVersion,
    artifactId,
    contentHash,
    manifestRef,
    artifactRef,
    remoteSyncLabel: remoteLabel,
    a11yLabel: [
      `Release ${releaseVersion}`,
      artifactId,
      contentHash,
      manifestRef,
      remoteLabel,
    ].join(', '),
  }
}

function isReleaseArtifactRef(value: unknown): value is ReleaseArtifactRef {
  if (typeof value !== "object" || value === null) {
    return false
  }
  const ref = value as Partial<ReleaseArtifactRef>
  return (
    stringValue(ref.artifact_id) !== null &&
    stringValue(ref.content_hash) !== null &&
    stringValue(ref.manifest_ref) !== null &&
    ref.store === "product" &&
    (ref.source_map_ref === undefined || ref.source_map_ref === null || typeof ref.source_map_ref === "string")
  )
}

export async function executePackageRelease({
  skillId,
  workspaceRoot,
  releaseIdentity,
  relativePath = packageRelativePath(skillId, releaseIdentity.releaseVersion),
  toastApi = toast,
  chooseTargetPath = () => null,
}: ExecutePackageReleaseOptions): Promise<WritePublishPackageResult | null> {
  try {
    const result = await writePublishPackage({
      workspaceRoot: workspaceRoot ?? skillId,
      relativePath,
      releaseVersion: releaseIdentity.releaseVersion,
      contentHash: releaseIdentity.contentHash,
      manifestRef: releaseIdentity.manifestRef,
      artifactRef: releaseIdentity.artifactRef,
    })
    showPackageSuccessToast(toastApi, releaseIdentity, result)
    return result
  } catch (error) {
    const message = nativePackageErrorMessage(error)
    if (isRetryableNativePackageError(error)) {
      toastApi.error(message, {
        action: {
          label: "Choose path",
          onClick: async () => {
            const failedPath = nativePackageErrorPath(error) ?? relativePath
            const nextPath = await chooseTargetPath(failedPath)
            if (!nextPath) return
            void executePackageRelease({
              skillId,
              workspaceRoot,
              releaseIdentity,
              relativePath: nextPath,
              toastApi,
              chooseTargetPath,
            })
          },
        },
      })
      return null
    }
    toastApi.error(message)
    return null
  }
}

export function packageRelativePath(skillId: string, releaseVersion: string): string {
  const safeSkillId = skillId.replace(/[^A-Za-z0-9._-]/g, "_")
  const safeVersion = releaseVersion.replace(/[^A-Za-z0-9._-]/g, "_")
  return `.workspace/releases/${safeSkillId}-${safeVersion}.package.json`
}

function showPackageSuccessToast(
  toastApi: PackageToastApi,
  releaseIdentity: HeaderReleaseIdentity,
  result: WritePublishPackageResult,
) {
  toastApi.success(
    `Packaged release ${releaseIdentity.releaseVersion}: ${releaseIdentity.contentHash}, ${releaseIdentity.manifestRef}`,
    {
      description: result.nativePath,
      action: {
        label: "Reveal",
        onClick: () => {
          void revealInFileManager(result.nativePath)
        },
      },
    },
  )
}

function nativePackageErrorMessage(error: unknown): string {
  const type = nativePackageErrorType(error)
  const data = nativePackageErrorData(error)
  const path = typeof data?.path === "string" ? `: ${data.path}` : ""
  if (type === "Conflict") return `native-fs conflict${path}`
  if (type === "PermissionDenied") return `native-fs permission${path}`
  if (type === "PathEscape") return `native-fs path_escape${path}`
  if (error instanceof Error && error.message.trim()) return error.message
  return "native-fs package failed"
}

function nativePackageErrorType(error: unknown): string | null {
  const value = typeof error === "object" && error !== null ? error as Record<string, unknown> : null
  return typeof value?.type === "string" ? value.type : null
}

function nativePackageErrorData(error: unknown): Record<string, unknown> | null {
  const value = typeof error === "object" && error !== null ? error as Record<string, unknown> : null
  const data = typeof value?.data === "object" && value.data !== null
    ? value.data as Record<string, unknown>
    : null
  return data
}

function nativePackageErrorPath(error: unknown): string | null {
  const data = nativePackageErrorData(error)
  return typeof data?.path === "string" && data.path.trim() ? data.path : null
}

function isRetryableNativePackageError(error: unknown): boolean {
  const type = nativePackageErrorType(error)
  return type === "Conflict" || type === "PermissionDenied" || type === "PathEscape"
}

function nextPackageRelativePath(currentPath: string): string {
  if (currentPath.endsWith(".package.json")) {
    return `${currentPath.slice(0, -".package.json".length)}-copy.package.json`
  }
  return `${currentPath}-copy`
}

function remoteSyncLabel(value: unknown): string {
  if (typeof value !== "object" || value === null) {
    return "remote sync pending"
  }
  const status = stringValue((value as Record<string, unknown>).status)
  return status ? `remote sync ${status}` : "remote sync pending"
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}
