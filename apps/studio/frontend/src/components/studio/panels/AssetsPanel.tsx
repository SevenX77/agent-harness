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
import { AssetPathContextMenu, absoluteAssetPath } from "./_shared/AssetPathContextMenu"
import { FileRow } from "./_shared/FileRow"
import { FolderRow } from "./_shared/FolderRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { RootPathSuffix } from "./_shared/RootPathSuffix"
import { applyPhaseFrontmatterForm, parsePhaseFrontmatter, phaseFrontmatterToForm } from "./phase-frontmatter"
import {
  ancestorDirsForFile,
  assetTreeTargetForNode,
  phaseIdFromFilePath,
  subgraphChildPhaseChainForFile,
  subgraphGraphChainForFile,
} from "./asset-tree-target"
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

/**
 * Drives expand-to + highlight of the file for the canvas-selected node. When
 * present, folders are controlled by `expandedDirs` (so the panel can reveal a
 * deep path on open) and the matching file row is highlighted. Omit it for plain
 * uncontrolled browsing.
 */
interface AssetTreeReveal {
  expandedDirs: Set<string>
  setDirExpanded: (path: string, expanded: boolean) => void
  highlightPath: string | null
}

function AssetTreeRows({
  directoryTree,
  directoryPath,
  onOpen,
  emptyLabel,
  reveal,
  workspaceRoot,
}: {
  directoryTree: WorkspaceDirectoryTree
  directoryPath: string
  onOpen: (file: FileMeta) => void
  emptyLabel?: string
  reveal?: AssetTreeReveal
  workspaceRoot?: string | null
}) {
  const directory = directoryTree.getDirectory(directoryPath)
  const treeRoot = workspaceRoot ?? directoryTree.workspaceRoot ?? null

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
          const childAbsolutePath = absoluteAssetPath(treeRoot, child.path)
          return (
            <FolderRow
              key={child.path}
              name={child.name}
              absolutePath={childAbsolutePath}
              expanded={reveal ? reveal.expandedDirs.has(child.path) : undefined}
              onExpandedChange={(expanded) => {
                if (expanded) {
                  directoryTree.ensureDirectory(child.path)
                }
                reveal?.setDirExpanded(child.path, expanded)
              }}
            >
              <AssetTreeRows
                directoryTree={directoryTree}
                directoryPath={child.path}
                onOpen={onOpen}
                emptyLabel="Empty folder"
                reveal={reveal}
                workspaceRoot={treeRoot}
              />
            </FolderRow>
          )
        }
        const fileAbsolutePath = absoluteAssetPath(child.file?.workspaceRoot ?? treeRoot, child.path)
        return child.file
          ? <FileRow key={child.path} file={child.file} onOpen={onOpen} active={reveal?.highlightPath === child.path} absolutePath={fileAbsolutePath} />
          : null
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
  rootPath,
  directoryTree,
  onOpen,
  reveal,
}: {
  rootLabel: string
  rootPath?: string | null
  directoryTree: WorkspaceDirectoryTree
  onOpen: (file: FileMeta) => void
  reveal?: AssetTreeReveal
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
      rootPath={rootPath}
      absolutePath={rootPath}
      defaultExpanded
      expanded={reveal ? reveal.expandedDirs.has("") : undefined}
      onExpandedChange={(expanded) => reveal?.setDirExpanded("", expanded)}
      rowClassName="rounded-none hover:bg-transparent"
      buttonClassName="py-1.5"
      labelClassName="font-medium text-foreground"
    >
      <AssetTreeRows
        directoryTree={directoryTree}
        directoryPath=""
        onOpen={onOpen}
        emptyLabel="No files"
        reveal={reveal}
        workspaceRoot={rootPath ?? directoryTree.workspaceRoot}
      />
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

/**
 * A file to reveal inside a Subgraphs Files block, matched to a block by its
 * child workspace root. Sourced from the open editor file and the canvas-selected
 * node (same inputs Skill Files uses) so subgraph highlight uses ONE method with
 * Skill Files — stable, derived, never an object rebuilt per render.
 */
interface SubgraphHighlightSource {
  root: string
  filePath: string
  /** True when the source is a canvas node selection (focus the tree: collapse
   * other folders), false/absent when it is just the open editor file (expand
   * only, so browsing stays fluid). Mirrors the Skill Files forward behavior. */
  fromNode?: boolean
}

function SubgraphFilesList({
  subgraphs,
  onOpen,
  onChoosePath,
  highlightSources,
  onRevealChildNode,
  onRevealSubgraphGraph,
}: {
  subgraphs: SubgraphMembership[]
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
  /** Files to reveal/highlight, matched to a block by child workspace root. */
  highlightSources: SubgraphHighlightSource[]
  /** Expand + select a child node on the canvas when its file is clicked here.
   * `phaseChain` is the root→leaf chain of phase ids (handles nested subgraphs). */
  onRevealChildNode?: (phaseChain: string[]) => void
  /** Expand a subgraph's own topology when its GRAPH.md is clicked here. */
  onRevealSubgraphGraph?: (phaseChain: string[]) => void
}) {
  const [expandedSubgraphKey, setExpandedSubgraphKey] = useState<string | null>(null)
  useEffect(() => {
    if (expandedSubgraphKey && !subgraphs.some((subgraph) => subgraphFilesKey(subgraph) === expandedSubgraphKey)) {
      setExpandedSubgraphKey(null)
    }
  }, [expandedSubgraphKey, subgraphs])

  // The block that owns a file to reveal (its child root matches a source), so it
  // auto-opens. `revealKey` is a stable string, so this never loops.
  const revealKey = useMemo(() => {
    for (const source of highlightSources) {
      const match = subgraphs.find(
        (subgraph) => normalizeComparableRoot(subgraph.path) === normalizeComparableRoot(source.root),
      )
      if (match) return subgraphFilesKey(match)
    }
    return null
  }, [highlightSources, subgraphs])
  useEffect(() => {
    if (revealKey) {
      setExpandedSubgraphKey(revealKey)
    }
  }, [revealKey])

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
            highlightSources={highlightSources}
            onRevealChildNode={onRevealChildNode}
            onRevealSubgraphGraph={onRevealSubgraphGraph}
          />
        )
      })}
    </div>
  )
}

function normalizeComparableRoot(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null
  return trimmed.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase()
}

function SubgraphFilesBlock({
  subgraph,
  expanded,
  onToggle,
  onOpen,
  onChoosePath,
  highlightSources,
  onRevealChildNode,
  onRevealSubgraphGraph,
}: {
  subgraph: SubgraphMembership
  expanded: boolean
  onToggle: () => void
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
  highlightSources: SubgraphHighlightSource[]
  onRevealChildNode?: (phaseChain: string[]) => void
  onRevealSubgraphGraph?: (phaseChain: string[]) => void
}) {
  const directoryTree = useWorkspaceDirectoryTree({
    workspaceRoot: subgraph.path,
    skillId: subgraph.label,
    titlePrefix: subgraph.label,
    // Editability is NOT decided by how a file is opened. Open subgraph files editable
    // like any other; the backend (403 SKILL_READ_ONLY) is the single source of truth
    // and flips the editor read-only only when the skill is genuinely not writable.
    enabled: expanded,
  })
  const [innerExpandedDirs, setInnerExpandedDirs] = useState<Set<string>>(() => new Set([""]))
  const setInnerDirExpanded = useCallback((path: string, isExpanded: boolean) => {
    setInnerExpandedDirs((current) => {
      const next = new Set(current)
      if (isExpanded) next.add(path)
      else next.delete(path)
      return next
    })
  }, [])
  const directoryTreeRef = useRef(directoryTree)
  directoryTreeRef.current = directoryTree
  // Highlight = the source file whose child root matches THIS subgraph. PURELY
  // DERIVED (no setState), so it can never feed an update loop — the same model
  // Skill Files uses. `innerHighlight` is a stable string, changing only when the
  // matched file actually changes.
  const innerHighlight = useMemo(() => {
    const blockRoot = normalizeComparableRoot(subgraph.path)
    if (!blockRoot) return null
    const source = highlightSources.find((candidate) => normalizeComparableRoot(candidate.root) === blockRoot)
    return source ? { path: source.filePath, fromNode: source.fromNode === true } : null
  }, [highlightSources, subgraph.path])
  const innerHighlightPath = innerHighlight?.path ?? null
  const innerHighlightFromNode = innerHighlight?.fromNode ?? false
  // Reveal the path down to the highlighted file. A node selection FOCUSES the
  // tree (collapse every other folder so the path stands alone — same as Skill
  // Files); an open-editor file only expands (never collapses), so browsing stays
  // fluid. Primitive deps → no render loop.
  useEffect(() => {
    if (!expanded || !innerHighlightPath) return
    const ancestors = ancestorDirsForFile(innerHighlightPath)
    setInnerExpandedDirs((current) => {
      if (innerHighlightFromNode) return new Set(ancestors)
      const next = new Set(current)
      for (const dir of ancestors) next.add(dir)
      return next
    })
    for (const dir of ancestors) {
      directoryTreeRef.current.ensureDirectory(dir)
    }
  }, [expanded, innerHighlightFromNode, innerHighlightPath])
  // Clicking a file in THIS subgraph: highlight it here (expand-only so browsing
  // is fluid), open it, and reveal+select its node inside the inline topology on
  // the canvas — at ANY nesting depth. `subgraph.id` is already the root→here
  // chain of phase ids ("a/b/c"); append the clicked file's phase id to get the
  // full chain GraphCanvas expands + selects.
  const openInnerFile = useCallback((file: FileMeta) => {
    // Expand to the clicked file immediately; its highlight is derived from the
    // open editor file once it loads (innerHighlight above).
    setInnerExpandedDirs((current) => {
      const next = new Set(current)
      for (const dir of ancestorDirsForFile(file.path)) next.add(dir)
      return next
    })
    onOpen(file)
    const chain = subgraph.id.split("/").filter(Boolean)
    // This subgraph's OWN GRAPH.md (root of its tree) → expand its topology.
    if (file.path.replace(/\\/g, "/").toLowerCase() === "graph.md") {
      onRevealSubgraphGraph?.(chain)
      return
    }
    const childPhaseId = phaseIdFromFilePath(file.path)
    if (childPhaseId) {
      onRevealChildNode?.([...chain, childPhaseId])
    }
  }, [onOpen, onRevealChildNode, onRevealSubgraphGraph, subgraph.id])
  const levelClassName = subgraphLevelTagClassName(subgraph.level)
  const rootPath = subgraph.path?.trim() || null
  const rootAriaLabel = rootPath ? `${subgraph.label} (${rootPath})` : undefined
  const rootButton = (
    <button
      type="button"
      aria-expanded={expanded}
      aria-label={rootAriaLabel}
      onClick={onToggle}
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
      <span className="flex min-w-0 items-baseline gap-1.5">
        <span data-subgraph-name="true" className={cn("truncate font-medium text-foreground", rootPath ? "shrink-0" : undefined)}>
          {subgraph.label}
        </span>
        {rootPath ? <RootPathSuffix path={rootPath} className="flex-1" /> : null}
      </span>
    </button>
  )
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
        <AssetPathContextMenu absolutePath={rootPath}>{rootButton}</AssetPathContextMenu>
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
              onOpen={openInnerFile}
              emptyLabel="Empty subgraph folder"
              workspaceRoot={rootPath ?? directoryTree.workspaceRoot}
              reveal={{
                expandedDirs: innerExpandedDirs,
                setDirExpanded: setInnerDirExpanded,
                highlightPath: innerHighlightPath,
              }}
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
  selectedNode,
  directoryTree: providedDirectoryTree,
  subgraphTree: providedSubgraphTree,
}: AssetsPanelProps) {
  const { onFileOpen, onRevealNodeForFile, onRevealSubgraphChildNode, onRevealSubgraphGraph, activeFileDetails } = useWorkspaceContext()
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

  // Reveal the canvas-selected node's file: expand the tree to it and highlight
  // it when the Assets panel is shown (or the selection changes). A node from the
  // open skill reveals in the Skill Files tree; a child-graph node routes to its
  // Subgraphs Files block instead (see SubgraphFilesList revealTarget).
  const revealTarget = useMemo(
    () => assetTreeTargetForNode(selectedNode, { rootTarget, skillId }),
    [selectedNode, rootTarget, skillId],
  )
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(() => new Set([""]))
  const [highlightSkillPath, setHighlightSkillPath] = useState<string | null>(null)
  const setDirExpanded = useCallback((path: string, expanded: boolean) => {
    setExpandedDirs((current) => {
      const next = new Set(current)
      if (expanded) next.add(path)
      else next.delete(path)
      return next
    })
  }, [])
  const directoryTreeRef = useRef(directoryTree)
  directoryTreeRef.current = directoryTree
  // Reveal a file in the Skill Files tree: highlight it and expand the path down
  // to it. Expand-only (never collapse siblings) so the highlight following a
  // selection/click never "locks" the tree to one path or fights browsing.
  const revealSkillPath = useCallback((filePath: string) => {
    setHighlightSkillPath(filePath)
    setExpandedDirs((current) => {
      const next = new Set(current)
      for (const dir of ancestorDirsForFile(filePath)) next.add(dir)
      return next
    })
    for (const dir of ancestorDirsForFile(filePath)) {
      directoryTreeRef.current.ensureDirectory(dir)
    }
  }, [])
  // Reverse/robust: the file actually OPEN in the editor. Opening a file always
  // updates this (it is core editor state, independent of the node round-trip), so
  // clicking any file in the tree — which opens it — moves the highlight.
  const openLeftPath = activeFileDetails.left?.path
  const openLeftSkillId = activeFileDetails.left?.skillId
  useEffect(() => {
    if (openLeftPath && (!openLeftSkillId || openLeftSkillId === skillId)) {
      revealSkillPath(openLeftPath)
    }
  }, [openLeftPath, openLeftSkillId, revealSkillPath, skillId])
  // Forward: the canvas-selected node FOCUSES the tree — highlight its file and
  // collapse every other folder so the path stands alone. Declared after the
  // open-file effect so a node selection wins ties (opening Assets with a node
  // selected reveals THAT node's file). File clicks go through the open-file
  // effect above, which expands WITHOUT collapsing so browsing stays fluid.
  useEffect(() => {
    if (revealTarget?.section !== "skill") return
    setHighlightSkillPath(revealTarget.filePath)
    for (const dir of revealTarget.ancestorDirs) {
      directoryTreeRef.current.ensureDirectory(dir)
    }
    setExpandedDirs(new Set(revealTarget.ancestorDirs))
  }, [revealTarget])
  const skillReveal = useMemo<AssetTreeReveal>(
    () => ({ expandedDirs, setDirExpanded, highlightPath: highlightSkillPath }),
    [expandedDirs, setDirExpanded, highlightSkillPath],
  )
  // Files the Subgraphs Files blocks should reveal/highlight — the open editor
  // file and the canvas-selected node, matched to a block by child workspace
  // root. Same inputs as Skill Files (one unified method); a stable array (keyed
  // on primitive deps), so the blocks derive highlight without any update loop.
  const openLeftWorkspaceRoot = activeFileDetails.left?.workspaceRoot ?? null
  const selectedNodeFilePath = selectedNode?.data.filePath ?? null
  const selectedNodeWorkspaceRoot = selectedNode?.data.workspaceRoot ?? null
  const subgraphHighlightSources = useMemo<SubgraphHighlightSource[]>(() => {
    const sources: SubgraphHighlightSource[] = []
    // Node selection listed FIRST so it wins when both match a block: a node
    // focus collapses other folders, an open file only expands.
    if (selectedNodeFilePath && selectedNodeWorkspaceRoot) {
      sources.push({ root: selectedNodeWorkspaceRoot, filePath: selectedNodeFilePath, fromNode: true })
    }
    if (openLeftPath && openLeftWorkspaceRoot) {
      sources.push({ root: openLeftWorkspaceRoot, filePath: openLeftPath })
    }
    return sources
  }, [openLeftPath, openLeftWorkspaceRoot, selectedNodeFilePath, selectedNodeWorkspaceRoot])

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
  const openFile = useCallback(async (file: FileMeta) => {
    // Drive the canvas from this file click. Priority:
    //  1. a subgraph's own GRAPH.md → expand that subgraph's topology (+ deselect)
    //  2. a subgraph child node file → reveal + select the (nested) child node
    //  3. any other node file → reverse-select a root-graph node
    // All no-ops for non-node files, and independent of the content read.
    const graphChain = subgraphGraphChainForFile(file.path, rootTarget, displayedSubgraphs)
    const childChain = graphChain ? null : subgraphChildPhaseChainForFile(file.path, rootTarget, displayedSubgraphs)
    if (graphChain && onRevealSubgraphGraph) {
      onRevealSubgraphGraph(graphChain)
    } else if (childChain && onRevealSubgraphChildNode) {
      onRevealSubgraphChildNode(childChain)
    } else {
      onRevealNodeForFile?.(file)
    }
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
  }, [displayedSubgraphs, onFileOpen, onRevealNodeForFile, onRevealSubgraphChildNode, onRevealSubgraphGraph, rootTarget])
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
                  <SkillRootTree
                    rootLabel={rootLabel}
                    rootPath={rootTarget}
                    directoryTree={directoryTree}
                    onOpen={openFile}
                    reveal={skillReveal}
                  />
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
                  highlightSources={subgraphHighlightSources}
                  onRevealChildNode={onRevealSubgraphChildNode}
                  onRevealSubgraphGraph={onRevealSubgraphGraph}
                />
              </ScrollArea>
            </AssetExplorerSection>
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}
