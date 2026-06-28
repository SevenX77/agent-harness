import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react"
import { ChevronDown, ChevronRight, ChevronUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { readWorkspaceFile, selectSkillDirectory, writeWorkspaceFile } from "@/lib/tauri"
import { errorMessage } from "@/utils/errors"
import { useWorkspaceContext } from "../WorkspaceContext"
import type { FileMeta } from "../file-types"
import { FileRow } from "./_shared/FileRow"
import { FolderRow } from "./_shared/FolderRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { applyPhaseFrontmatterForm, parsePhaseFrontmatter, phaseFrontmatterToForm } from "./phase-frontmatter"
import { subgraphMembership, type SubgraphMembership } from "./subgraph-membership"
import {
  type SubgraphMembershipTree,
  useSubgraphMembershipTree,
} from "./use-subgraph-membership-tree"
import {
  type DirectoryTreeState,
  type WorkspaceDirectoryTree,
  useWorkspaceDirectoryTree,
} from "./use-workspace-directory-tree"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

interface AssetsPanelProps {
  skillId?: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  directoryTree?: WorkspaceDirectoryTree
  subgraphTree?: SubgraphMembershipTree
}

const DEFAULT_SUBGRAPHS_PANEL_PERCENT = 36
const MIN_SUBGRAPHS_PANEL_PERCENT = 16
const MAX_SUBGRAPHS_PANEL_PERCENT = 50

function AssetTreeRows({
  directoryTree,
  directoryPath,
  onOpen,
  emptyLabel,
}: {
  directoryTree: WorkspaceDirectoryTree
  directoryPath: string
  onOpen: (file: FileMeta) => void
  emptyLabel?: string
}) {
  const directory = directoryTree.getDirectory(directoryPath)

  if (directory.status === "loading" && directory.entries.length === 0) {
    return <TreeStatusLine state={directory} />
  }

  if (directory.status === "error" && directory.entries.length === 0) {
    return <TreeStatusLine state={directory} />
  }

  if (directory.entries.length === 0 && emptyLabel) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">{emptyLabel}</div>
  }

  return (
    <>
      <TreeStatusLine state={directory} subtle />
      {directory.entries.map((child) => {
        if (child.kind === "dir") {
          return (
            <FolderRow
              key={child.path}
              name={child.name}
              onExpandedChange={(expanded) => {
                if (expanded) {
                  directoryTree.ensureDirectory(child.path)
                }
              }}
            >
              <AssetTreeRows
                directoryTree={directoryTree}
                directoryPath={child.path}
                onOpen={onOpen}
                emptyLabel="Empty folder"
              />
            </FolderRow>
          )
        }
        return child.file ? <FileRow key={child.path} file={child.file} onOpen={onOpen} /> : null
      })}
    </>
  )
}

function basenameFromPath(value?: string | null): string {
  const trimmed = value?.trim()
  if (!trimmed) return ""
  const normalized = trimmed.replace(/\\/g, "/").replace(/\/+$/, "")
  return normalized.split("/").filter(Boolean).pop() ?? trimmed
}

function skillRootLabel({
  skillDetail,
  skillId,
  workspaceRoot,
}: {
  skillDetail?: SkillDetail
  skillId?: string | null
  workspaceRoot?: string | null
}): string {
  return basenameFromPath(workspaceRoot)
    || basenameFromPath(skillId)
    || skillDetail?.manifest?.name
    || "Skill"
}

function SkillRootTree({
  rootLabel,
  directoryTree,
  onOpen,
}: {
  rootLabel: string
  directoryTree: WorkspaceDirectoryTree
  onOpen: (file: FileMeta) => void
}) {
  if (directoryTree.root.status === "loading" && directoryTree.root.entries.length === 0) {
    return <TreeStatusLine state={directoryTree.root} />
  }

  if (directoryTree.root.status === "error" && directoryTree.root.entries.length === 0) {
    return <TreeStatusLine state={directoryTree.root} />
  }

  if (directoryTree.root.entries.length === 0) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No files</div>
  }

  return (
    <FolderRow
      name={rootLabel}
      defaultExpanded
      rowClassName="rounded-none hover:bg-transparent"
      buttonClassName="py-1.5"
      labelClassName="font-medium text-foreground"
    >
      <AssetTreeRows directoryTree={directoryTree} directoryPath="" onOpen={onOpen} emptyLabel="No files" />
    </FolderRow>
  )
}

function TreeStatusLine({ state, subtle = false }: { state: DirectoryTreeState; subtle?: boolean }) {
  if (state.status === "loading" && (!subtle || state.entries.length === 0)) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">Loading folder...</div>
  }
  if (state.status === "error") {
    return <div className="px-2 py-1.5 text-[11px] text-destructive">{state.message}</div>
  }
  return null
}

function AssetExplorerSection({
  sectionId,
  label,
  children,
  action,
  collapsed = false,
  onHeaderToggle,
  headerToggleLabel,
  headerIcon,
}: {
  sectionId: string
  label: string
  children: ReactNode
  action?: ReactNode
  collapsed?: boolean
  onHeaderToggle?: () => void
  headerToggleLabel?: string
  headerIcon?: ReactNode
}) {
  const headerClassName = "flex h-8 shrink-0 items-center bg-muted/55 px-2"
  const labelNode = (
    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
  )

  return (
    <section data-assets-section={sectionId} className="flex h-full min-h-0 flex-col overflow-hidden">
      {onHeaderToggle ? (
        <button
          type="button"
          data-assets-section-bar="true"
          data-assets-section-toggle="true"
          aria-label={headerToggleLabel}
          aria-expanded={!collapsed}
          onClick={onHeaderToggle}
          className={cn(
            headerClassName,
            "w-full cursor-pointer justify-between border-0 text-left outline-none transition-colors hover:bg-muted/70 focus-visible:ring-1 focus-visible:ring-ring",
          )}
        >
          {labelNode}
          {headerIcon ? <span className="ml-auto flex items-center text-muted-foreground">{headerIcon}</span> : null}
        </button>
      ) : (
        <div data-assets-section-bar="true" className={headerClassName}>
          {labelNode}
          {action ? <div className="ml-auto flex items-center gap-1">{action}</div> : null}
        </div>
      )}
      {collapsed ? null : <div className="min-h-0 flex-1">{children}</div>}
    </section>
  )
}

function SubgraphFilesList({
  subgraphs,
  onOpen,
  onChoosePath,
}: {
  subgraphs: SubgraphMembership[]
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
}) {
  const [expandedSubgraphKey, setExpandedSubgraphKey] = useState<string | null>(null)
  useEffect(() => {
    if (expandedSubgraphKey && !subgraphs.some((subgraph) => subgraphFilesKey(subgraph) === expandedSubgraphKey)) {
      setExpandedSubgraphKey(null)
    }
  }, [expandedSubgraphKey, subgraphs])

  if (subgraphs.length === 0) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No subgraphs</div>
  }

  return (
    <div className="w-full min-w-0 space-y-1 overflow-hidden py-1">
      {subgraphs.map((subgraph) => {
        const key = subgraphFilesKey(subgraph)
        return (
          <SubgraphFilesBlock
            key={key}
            subgraph={subgraph}
            expanded={expandedSubgraphKey === key}
            onToggle={() => setExpandedSubgraphKey((current) => (current === key ? null : key))}
            onOpen={onOpen}
            onChoosePath={onChoosePath}
          />
        )
      })}
    </div>
  )
}

function SubgraphFilesBlock({
  subgraph,
  expanded,
  onToggle,
  onOpen,
  onChoosePath,
}: {
  subgraph: SubgraphMembership
  expanded: boolean
  onToggle: () => void
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
}) {
  const directoryTree = useWorkspaceDirectoryTree({
    workspaceRoot: subgraph.path,
    skillId: subgraph.label,
    titlePrefix: subgraph.label,
    saveEnabled: false,
    enabled: expanded,
  })
  const levelClassName = subgraphLevelTagClassName(subgraph.level)
  const endAdornment = (
    <div
      data-subgraph-status-slot="true"
      className="flex shrink-0 items-center justify-end gap-1"
    >
      <SubgraphLinkBadge subgraph={subgraph} onChoosePath={() => onChoosePath(subgraph)} />
    </div>
  )

  return (
    <div
      data-subgraph-row="true"
      data-subgraph-level={subgraph.level}
      data-subgraph-folder="true"
      data-subgraph-default-expanded="false"
      className="w-full min-w-0"
    >
      <div
        data-subgraph-row-grid="true"
        className="grid w-full min-w-0 grid-cols-[minmax(0,1fr)_max-content] items-center gap-2 rounded-md px-2 py-1 text-xs transition-colors hover:bg-accent"
      >
        <button
          type="button"
          aria-expanded={expanded}
          onClick={onToggle}
          title={subgraph.label}
          className="grid min-w-0 cursor-pointer grid-cols-[auto_auto_minmax(0,1fr)] items-center gap-2 border-0 bg-transparent p-0 text-left text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
        >
          {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          <span
            className={cn(
              "grid h-4 w-6 min-w-6 max-w-6 shrink-0 grid-cols-[auto_auto] items-center justify-center gap-px overflow-hidden rounded-sm px-0.5 text-[9px] leading-none",
              levelClassName,
            )}
            data-subgraph-level-tag="true"
            aria-label={`Recursive level ${subgraph.level}`}
          >
            <span
              data-subgraph-level-prefix="true"
              className="justify-self-center text-center font-medium"
            >
              L
            </span>
            <span
              data-subgraph-level-number="true"
              className="justify-self-center text-center font-semibold tabular-nums"
            >
              {subgraph.level}
            </span>
          </span>
          <span data-subgraph-name="true" className="truncate font-medium text-foreground">{subgraph.label}</span>
        </button>
        <div className="min-w-max justify-self-end">{endAdornment}</div>
      </div>
      {expanded ? (
        <div
          data-subgraph-folder-contents="true"
          className="space-y-0.5 pb-1 pl-6"
        >
          {!subgraph.path && directoryTree.root.status === "idle" ? (
            <div className="px-2 py-1 text-[11px] text-muted-foreground">{subgraphLinkTooltip(subgraph)}</div>
          ) : null}
          {subgraph.path ? (
            <AssetTreeRows
              directoryTree={directoryTree}
              directoryPath=""
              onOpen={onOpen}
              emptyLabel="Empty subgraph folder"
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function subgraphLevelTagClassName(level: number): string {
  if (level === 1) return "bg-foreground/15 text-foreground"
  if (level === 2) return "bg-muted/55 text-muted-foreground"
  if (level === 3) return "bg-muted/35 text-muted-foreground/80"
  return "bg-muted/20 text-muted-foreground/60"
}

function subgraphFilesKey(subgraph: SubgraphMembership): string {
  return `${subgraph.level}:${subgraph.id}:${subgraph.filePath}`
}

function clampSubgraphsPanelPercent(value: number): number {
  return Math.min(MAX_SUBGRAPHS_PANEL_PERCENT, Math.max(MIN_SUBGRAPHS_PANEL_PERCENT, value))
}

function subgraphStatusLabel(subgraph: SubgraphMembership): string {
  if (subgraph.status === "resolved") return "Linked"
  if (subgraph.status === "migration-required") return "Migration needed"
  return "Missing path"
}

function subgraphLinkTooltip(subgraph: SubgraphMembership): string {
  if (subgraph.path) {
    return `Linked - ${subgraph.path}`
  }
  if (subgraph.legacyTargetSkill) {
    return `Migration needed - legacy child reference: ${subgraph.legacyTargetSkill}. Choose a folder.`
  }
  return "Missing path - unresolvable. Choose a folder."
}

function SubgraphLinkBadge({
  subgraph,
  onChoosePath,
}: {
  subgraph: SubgraphMembership
  onChoosePath: () => void
}) {
  const linked = Boolean(subgraph.path)
  const label = subgraphLinkTooltip(subgraph)
  const visibleLabel = subgraphStatusLabel(subgraph)
  const variant = linked ? "success" : subgraph.status === "migration-required" ? "warning" : "destructive"

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {linked ? (
          <Badge variant={variant} aria-label={label}>
            {visibleLabel}
          </Badge>
        ) : (
          <Badge asChild variant={variant}>
            <button
              type="button"
              aria-label={label}
              onClick={onChoosePath}
            >
              {visibleLabel}
            </button>
          </Badge>
        )}
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-80 break-all">
        {label}
      </TooltipContent>
    </Tooltip>
  )
}

export function AssetsPanel({
  skillId = null,
  workspaceRoot = null,
  skillDetail,
  directoryTree: providedDirectoryTree,
  subgraphTree: providedSubgraphTree,
}: AssetsPanelProps) {
  const { onFileOpen } = useWorkspaceContext()
  const [subgraphPathOverrides, setSubgraphPathOverrides] = useState<Record<string, string>>({})
  const [subgraphsCollapsed, setSubgraphsCollapsed] = useState(false)
  const [subgraphsPanelPercent, setSubgraphsPanelPercent] = useState(DEFAULT_SUBGRAPHS_PANEL_PERCENT)
  const splitContainerRef = useRef<HTMLDivElement | null>(null)
  const rootTarget = workspaceRoot ?? skillId
  const localDirectoryTree = useWorkspaceDirectoryTree({
    workspaceRoot: rootTarget,
    skillId,
    skillDetail,
    enabled: !providedDirectoryTree,
  })
  const directoryTree = providedDirectoryTree ?? localDirectoryTree
  const rootLabel = skillRootLabel({ skillDetail, skillId, workspaceRoot: rootTarget })
  const openFile = useCallback(async (file: FileMeta) => {
    const targetRoot = file.workspaceRoot ?? rootTarget
    if (targetRoot) {
      try {
        const result = await readWorkspaceFile(targetRoot, file.path)
        onFileOpen({
          ...file,
          content: result.content,
          hash: result.hash,
        })
        return
      } catch (error) {
        if (!file.content) {
          toast.error(error instanceof Error ? error.message : "Could not open file")
          return
        }
      }
    }
    onFileOpen(file)
  }, [onFileOpen, rootTarget])

  // Real path-based membership: the subgraphs this skill actually references,
  // derived from the backend topology (R4). No fake in-memory "registered" cache.
  const subgraphs = useMemo(() => {
    const ownerRoot = rootTarget ?? null
    return subgraphMembership(skillDetail, ownerRoot).map((subgraph) => ({ ...subgraph, workspaceRoot: ownerRoot }))
  }, [rootTarget, skillDetail])
  const topLevelSubgraphs = useMemo(
    () => subgraphs.map((subgraph) => {
      const override = subgraphPathOverrides[subgraph.id]
      return override
        ? { ...subgraph, path: override, legacyTargetSkill: null, status: "resolved" as const }
        : subgraph
    }),
    [subgraphPathOverrides, subgraphs],
  )
  const hasSubgraphOverrides = Object.keys(subgraphPathOverrides).length > 0
  const localSubgraphTree = useSubgraphMembershipTree({
    topLevel: topLevelSubgraphs,
    enabled: !providedSubgraphTree || hasSubgraphOverrides,
  })
  const activeSubgraphTree = providedSubgraphTree && !hasSubgraphOverrides
    ? providedSubgraphTree
    : localSubgraphTree
  const displayedSubgraphs = activeSubgraphTree.items
  const chooseSubgraphPath = useCallback(async (subgraph: SubgraphMembership) => {
    const writeRoot = subgraph.workspaceRoot ?? rootTarget ?? workspaceRoot
    if (!writeRoot) {
      toast.error("Open a skill before linking a subgraph.")
      return
    }

    const selected = await selectSkillDirectory(subgraph.path ?? writeRoot)
    if (!selected) return

    try {
      const current = await readWorkspaceFile(writeRoot, subgraph.filePath)
      const parsed = parsePhaseFrontmatter(current.content)
      if (!parsed.ok) {
        throw new Error(parsed.message)
      }
      const form = phaseFrontmatterToForm(parsed.frontmatter)
      const next = applyPhaseFrontmatterForm(current.content, { ...form, path: selected }, "subgraph")
      if (!next.ok) {
        throw new Error(next.message)
      }
      await writeWorkspaceFile(writeRoot, subgraph.filePath, next.markdown, current.hash)
      setSubgraphPathOverrides((currentOverrides) => ({ ...currentOverrides, [subgraph.id]: selected }))
      toast.success(`Linked ${subgraph.label}`, { description: selected })
    } catch (error) {
      toast.error("Could not link subgraph", { description: errorMessage(error) })
    }
  }, [rootTarget, workspaceRoot])
  const resizeSubgraphsPanel = useCallback((clientY: number) => {
    const rect = splitContainerRef.current?.getBoundingClientRect()
    if (!rect || rect.height <= 0) return

    const nextPercent = ((rect.bottom - clientY) / rect.height) * 100
    setSubgraphsPanelPercent(clampSubgraphsPanelPercent(nextPercent))
    setSubgraphsCollapsed(false)
  }, [])
  const startSubgraphsResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (subgraphsCollapsed) return

    event.preventDefault()
    const target = event.currentTarget
    const pointerId = event.pointerId
    target.setPointerCapture(pointerId)

    const handleMove = (moveEvent: PointerEvent) => resizeSubgraphsPanel(moveEvent.clientY)
    const stopResize = () => {
      target.removeEventListener("pointermove", handleMove)
      if (target.hasPointerCapture(pointerId)) {
        target.releasePointerCapture(pointerId)
      }
    }

    target.addEventListener("pointermove", handleMove)
    target.addEventListener("pointerup", stopResize, { once: true })
    target.addEventListener("pointercancel", stopResize, { once: true })
  }, [resizeSubgraphsPanel, subgraphsCollapsed])
  const handleSplitterKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (subgraphsCollapsed) return

    if (event.key === "ArrowUp") {
      event.preventDefault()
      setSubgraphsPanelPercent((value) => clampSubgraphsPanelPercent(value + 4))
    } else if (event.key === "ArrowDown") {
      event.preventDefault()
      setSubgraphsPanelPercent((value) => clampSubgraphsPanelPercent(value - 4))
    } else if (event.key === "Home") {
      event.preventDefault()
      setSubgraphsPanelPercent(MIN_SUBGRAPHS_PANEL_PERCENT)
    } else if (event.key === "End") {
      event.preventDefault()
      setSubgraphsPanelPercent(MAX_SUBGRAPHS_PANEL_PERCENT)
    }
  }, [subgraphsCollapsed])
  const toggleSubgraphsPanel = useCallback(() => {
    setSubgraphsCollapsed((value) => !value)
  }, [])
  const subgraphsToggleLabel = subgraphsCollapsed ? "Expand Subgraphs Files" : "Collapse Subgraphs Files"

  return (
    <TooltipProvider>
      <div
        data-assets-panel-stable-height="true"
        className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background"
      >
        <PanelHeader title="Assets" />

        <div
          ref={splitContainerRef}
          data-assets-split-container="true"
          className="flex h-full min-h-0 flex-col overflow-hidden px-0 pb-2"
        >
          <div className="min-h-0 flex-1 overflow-hidden">
            <AssetExplorerSection sectionId="skill-files" label="Skill Files">
              <ScrollArea className="h-full min-h-0">
                <div className="space-y-0.5 px-0.5 py-1 text-xs">
                  <SkillRootTree rootLabel={rootLabel} directoryTree={directoryTree} onOpen={openFile} />
                </div>
              </ScrollArea>
            </AssetExplorerSection>
          </div>

          {subgraphsCollapsed ? null : (
            <div
              role="separator"
              aria-label="Resize Subgraphs Files"
              aria-orientation="horizontal"
              tabIndex={0}
              onPointerDown={startSubgraphsResize}
              onKeyDown={handleSplitterKeyDown}
              className="group flex h-2 shrink-0 cursor-row-resize items-center outline-none"
            >
              <div className="h-px w-full bg-transparent transition-colors group-hover:bg-border/50 group-focus-visible:bg-ring" />
            </div>
          )}

          <div
            data-assets-subgraphs-drawer="true"
            className={cn("min-h-0 shrink-0 overflow-hidden", subgraphsCollapsed ? "h-8" : "min-h-36")}
            style={subgraphsCollapsed ? undefined : { height: `${subgraphsPanelPercent}%` }}
          >
            <AssetExplorerSection
              sectionId="subgraphs-files"
              label="Subgraphs Files"
              collapsed={subgraphsCollapsed}
              onHeaderToggle={toggleSubgraphsPanel}
              headerToggleLabel={subgraphsToggleLabel}
              headerIcon={subgraphsCollapsed ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            >
              <ScrollArea className="h-full min-h-0">
                <SubgraphFilesList
                  subgraphs={displayedSubgraphs}
                  onOpen={openFile}
                  onChoosePath={chooseSubgraphPath}
                />
              </ScrollArea>
            </AssetExplorerSection>
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}
