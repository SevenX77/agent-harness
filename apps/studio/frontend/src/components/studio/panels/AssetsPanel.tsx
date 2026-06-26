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
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tag } from "@/components/ui/tag"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { isTauriRuntime } from "@/config/runtime"
import { listWorkspaceDir, readWorkspaceFile, selectSkillDirectory, writeWorkspaceFile } from "@/lib/tauri"
import { errorMessage } from "@/utils/errors"
import { useWorkspaceContext } from "../WorkspaceContext"
import type { FileMeta } from "../file-types"
import { FileRow } from "./_shared/FileRow"
import { FolderRow } from "./_shared/FolderRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { applyPhaseFrontmatterForm, parsePhaseFrontmatter, phaseFrontmatterToForm } from "./phase-frontmatter"
import { fileFromDetail, languageForPath } from "./panel-files"
import { loadRecursiveSubgraphMembership, subgraphMembership, type SubgraphMembership } from "./subgraph-membership"
import { toast } from "sonner"

interface AssetsPanelProps {
  skillId?: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
}

interface AssetTreeNode {
  name: string
  path: string
  kind: "file" | "dir"
  file?: FileMeta
  children: Map<string, AssetTreeNode>
}

type DirectoryTreeStatus = "idle" | "loading" | "ready" | "error"

interface DirectoryTreeState {
  status: DirectoryTreeStatus
  tree: AssetTreeNode | null
  message?: string
}

const DEFAULT_SUBGRAPHS_PANEL_PERCENT = 36
const MIN_SUBGRAPHS_PANEL_PERCENT = 16
const MAX_SUBGRAPHS_PANEL_PERCENT = 50

function createAssetTreeNode(name: string, path: string, kind: "file" | "dir" = "dir"): AssetTreeNode {
  return {
    name,
    path,
    kind,
    children: new Map(),
  }
}

function createFileMeta({
  path,
  content = "",
  skillId,
  workspaceRoot,
  titlePrefix,
  saveEnabled = true,
}: {
  path: string
  content?: string
  skillId?: string | null
  workspaceRoot?: string | null
  titlePrefix?: string | null
  saveEnabled?: boolean
}): FileMeta {
  return {
    path,
    language: languageForPath(path),
    content,
    skillId,
    workspaceRoot,
    title: titlePrefix ? `${titlePrefix} / ${path}` : undefined,
    saveEnabled,
  }
}

function buildAssetTree(skillDetail?: SkillDetail, options: {
  skillId?: string | null
  workspaceRoot?: string | null
} = {}): AssetTreeNode {
  const root = createAssetTreeNode("", "")
  for (const path of Object.keys(skillDetail?.files ?? {}).sort((a, b) => a.localeCompare(b))) {
    const parts = path.split("/").filter(Boolean)
    if (parts.length === 0) continue

    let current = root
    parts.forEach((part, index) => {
      const nodePath = parts.slice(0, index + 1).join("/")
      let node = current.children.get(part)
      if (!node) {
        node = createAssetTreeNode(part, nodePath, index === parts.length - 1 ? "file" : "dir")
        current.children.set(part, node)
      }
      if (index === parts.length - 1) {
        node.kind = "file"
        node.file = {
          ...fileFromDetail(skillDetail, path),
          skillId: options.skillId,
          workspaceRoot: options.workspaceRoot,
        }
      }
      current = node
    })
  }
  return root
}

function sortedAssetChildren(node: AssetTreeNode): AssetTreeNode[] {
  return [...node.children.values()].sort((left, right) => {
    const leftIsFolder = left.kind === "dir"
    const rightIsFolder = right.kind === "dir"
    if (leftIsFolder !== rightIsFolder) return leftIsFolder ? -1 : 1
    return left.name.localeCompare(right.name)
  })
}

function AssetTreeRows({
  node,
  onOpen,
  emptyLabel,
}: {
  node: AssetTreeNode
  onOpen: (file: FileMeta) => void
  emptyLabel?: string
}) {
  const children = sortedAssetChildren(node)
  if (children.length === 0 && emptyLabel) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">{emptyLabel}</div>
  }

  return (
    <>
      {children.map((child) => {
        if (child.kind === "dir") {
          return (
            <FolderRow key={child.path} name={child.name}>
              <AssetTreeRows node={child} onOpen={onOpen} emptyLabel="Empty folder" />
            </FolderRow>
          )
        }
        return child.file ? <FileRow key={child.path} file={child.file} onOpen={onOpen} /> : null
      })}
    </>
  )
}

function sortedNativeEntries(entries: Awaited<ReturnType<typeof listWorkspaceDir>>) {
  return [...entries].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "dir" ? -1 : 1
    return left.name.localeCompare(right.name)
  })
}

async function appendNativeDirectory({
  node,
  workspaceRoot,
  relativeDir,
  skillId,
  titlePrefix,
  saveEnabled,
}: {
  node: AssetTreeNode
  workspaceRoot: string
  relativeDir: string
  skillId?: string | null
  titlePrefix?: string | null
  saveEnabled: boolean
}) {
  const entries = sortedNativeEntries(await listWorkspaceDir(workspaceRoot, relativeDir || "."))
  for (const entry of entries) {
    const path = relativeDir ? `${relativeDir}/${entry.name}` : entry.name
    const child = createAssetTreeNode(entry.name, path, entry.kind)
    if (entry.kind === "file") {
      child.file = createFileMeta({
        path,
        skillId,
        workspaceRoot,
        titlePrefix,
        saveEnabled,
      })
    } else {
      try {
        await appendNativeDirectory({
          node: child,
          workspaceRoot,
          relativeDir: path,
          skillId,
          titlePrefix,
          saveEnabled,
        })
      } catch {
        // Keep the directory visible even when native-fs refuses one child path
        // (for example, a protected symlink). The Rust layer remains the guard.
      }
    }
    node.children.set(entry.name, child)
  }
}

async function loadNativeDirectoryTree({
  workspaceRoot,
  skillId,
  titlePrefix,
  saveEnabled,
}: {
  workspaceRoot: string
  skillId?: string | null
  titlePrefix?: string | null
  saveEnabled: boolean
}): Promise<AssetTreeNode> {
  const root = createAssetTreeNode("", "")
  await appendNativeDirectory({
    node: root,
    workspaceRoot,
    relativeDir: "",
    skillId,
    titlePrefix,
    saveEnabled,
  })
  return root
}

function useNativeDirectoryTree({
  workspaceRoot,
  skillId,
  titlePrefix,
  saveEnabled = true,
}: {
  workspaceRoot?: string | null
  skillId?: string | null
  titlePrefix?: string | null
  saveEnabled?: boolean
}): DirectoryTreeState {
  const [state, setState] = useState<DirectoryTreeState>({ status: "idle", tree: null })

  useEffect(() => {
    if (!workspaceRoot || !isTauriRuntime()) {
      setState({ status: "idle", tree: null })
      return undefined
    }

    let cancelled = false
    setState((current) => ({ status: "loading", tree: current.tree }))
    void loadNativeDirectoryTree({ workspaceRoot, skillId, titlePrefix, saveEnabled })
      .then((tree) => {
        if (!cancelled) {
          setState({ status: "ready", tree })
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setState({
            status: "error",
            tree: null,
            message: error instanceof Error ? error.message : String(error || "Could not read folder"),
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [saveEnabled, skillId, titlePrefix, workspaceRoot])

  return state
}

function TreeStatusLine({ state }: { state: DirectoryTreeState }) {
  if (state.status === "loading") {
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
}: {
  sectionId: string
  label: string
  children: ReactNode
  action?: ReactNode
  collapsed?: boolean
}) {
  return (
    <section data-assets-section={sectionId} className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex h-7 shrink-0 items-center bg-muted/20 px-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        {action ? <div className="ml-auto flex items-center gap-1">{action}</div> : null}
      </div>
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
  if (subgraphs.length === 0) {
    return <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No subgraphs</div>
  }

  return (
    <div className="w-full min-w-0 space-y-1 overflow-hidden py-1">
      {subgraphs.map((subgraph) => (
        <SubgraphFilesBlock
          key={`${subgraph.level}:${subgraph.id}:${subgraph.filePath}`}
          subgraph={subgraph}
          showLevelTag={subgraphs.some((candidate) => candidate.level > 1)}
          onOpen={onOpen}
          onChoosePath={onChoosePath}
        />
      ))}
    </div>
  )
}

function SubgraphFilesBlock({
  subgraph,
  showLevelTag,
  onOpen,
  onChoosePath,
}: {
  subgraph: SubgraphMembership
  showLevelTag: boolean
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
}) {
  const treeState = useNativeDirectoryTree({
    workspaceRoot: subgraph.path,
    skillId: subgraph.label,
    titlePrefix: subgraph.label,
    saveEnabled: false,
  })
  const [expanded, setExpanded] = useState(false)
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
          onClick={() => setExpanded((value) => !value)}
          title={subgraph.label}
          className={`grid min-w-0 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-left text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring ${
            showLevelTag ? "grid-cols-[auto_auto_minmax(0,1fr)]" : "grid-cols-[auto_minmax(0,1fr)]"
          }`}
        >
          {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          {showLevelTag ? (
            <Tag
              size="xs"
              variant="muted"
              className="shrink-0"
              data-subgraph-level-tag="true"
              aria-label={`Recursive level ${subgraph.level}`}
            >
              L{subgraph.level}
            </Tag>
          ) : null}
          <span data-subgraph-name="true" className="truncate font-medium text-foreground">{subgraph.label}</span>
        </button>
        <div className="min-w-max justify-self-end">{endAdornment}</div>
      </div>
      {expanded ? (
        <div
          data-subgraph-folder-contents="true"
          className="space-y-0.5 pb-1 pl-4"
        >
          <TreeStatusLine state={treeState} />
          {!subgraph.path && treeState.status === "idle" ? (
            <div className="px-2 py-1 text-[11px] text-muted-foreground">{subgraphLinkTooltip(subgraph)}</div>
          ) : null}
          {treeState.tree ? (
            <AssetTreeRows node={treeState.tree} onOpen={onOpen} emptyLabel="Empty subgraph folder" />
          ) : null}
        </div>
      ) : null}
    </div>
  )
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

export function AssetsPanel({ skillId = null, workspaceRoot = null, skillDetail }: AssetsPanelProps) {
  const { onFileOpen } = useWorkspaceContext()
  const [subgraphPathOverrides, setSubgraphPathOverrides] = useState<Record<string, string>>({})
  const [subgraphsCollapsed, setSubgraphsCollapsed] = useState(false)
  const [subgraphsPanelPercent, setSubgraphsPanelPercent] = useState(DEFAULT_SUBGRAPHS_PANEL_PERCENT)
  const splitContainerRef = useRef<HTMLDivElement | null>(null)
  const rootTarget = workspaceRoot ?? skillId
  const fallbackFileTree = useMemo(
    () => buildAssetTree(skillDetail, { skillId, workspaceRoot: rootTarget }),
    [rootTarget, skillDetail, skillId],
  )
  const nativeFileTree = useNativeDirectoryTree({
    workspaceRoot: rootTarget,
    skillId,
  })
  const fileTree = nativeFileTree.tree ?? fallbackFileTree
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
  const topLevelSubgraphKey = useMemo(
    () => topLevelSubgraphs.map((subgraph) => [
      subgraph.id,
      subgraph.level,
      subgraph.filePath,
      subgraph.workspaceRoot ?? "",
      subgraph.path ?? "",
      subgraph.status,
    ].join("\u0001")).join("\u0002"),
    [topLevelSubgraphs],
  )
  const [recursiveSubgraphs, setRecursiveSubgraphs] = useState<{
    key: string
    items: SubgraphMembership[]
  } | null>(null)
  useEffect(() => {
    let cancelled = false
    setRecursiveSubgraphs({ key: topLevelSubgraphKey, items: topLevelSubgraphs })

    if (!isTauriRuntime() || topLevelSubgraphs.length === 0) {
      return () => {
        cancelled = true
      }
    }

    void loadRecursiveSubgraphMembership(topLevelSubgraphs, readWorkspaceFile)
      .then((memberships) => {
        if (!cancelled) {
          setRecursiveSubgraphs({ key: topLevelSubgraphKey, items: memberships })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecursiveSubgraphs({ key: topLevelSubgraphKey, items: topLevelSubgraphs })
        }
      })

    return () => {
      cancelled = true
    }
  }, [topLevelSubgraphKey, topLevelSubgraphs])
  const displayedSubgraphs = recursiveSubgraphs?.key === topLevelSubgraphKey
    ? recursiveSubgraphs.items
    : topLevelSubgraphs
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
      <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background">
        <PanelHeader title="Assets" />

        <div
          ref={splitContainerRef}
          data-assets-split-container="true"
          className="grid h-full min-h-0 overflow-hidden px-0 pb-2"
          style={{
            gridTemplateRows: subgraphsCollapsed
              ? "minmax(0, 1fr) 1.75rem"
              : `minmax(0, ${100 - subgraphsPanelPercent}fr) 0.5rem minmax(0, ${subgraphsPanelPercent}fr)`,
          }}
        >
          <div className="min-h-0 overflow-hidden">
            <AssetExplorerSection sectionId="skill-files" label="Skill Files">
              <ScrollArea className="h-full min-h-0">
                <div className="space-y-0.5 px-0.5 py-1 text-xs">
                  <TreeStatusLine state={nativeFileTree} />
                  <AssetTreeRows node={fileTree} onOpen={openFile} emptyLabel="No files" />
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

          <div className="min-h-0 overflow-hidden">
            <AssetExplorerSection
              sectionId="subgraphs-files"
              label="Subgraphs Files"
              collapsed={subgraphsCollapsed}
              action={(
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      aria-label={subgraphsToggleLabel}
                      onClick={toggleSubgraphsPanel}
                    >
                      {subgraphsCollapsed ? <ChevronUp /> : <ChevronDown />}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">{subgraphsToggleLabel}</TooltipContent>
                </Tooltip>
              )}
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
