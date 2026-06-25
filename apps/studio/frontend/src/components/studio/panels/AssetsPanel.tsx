import { useCallback, useEffect, useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
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
import { SectionHeading } from "./_shared/SectionHeading"
import { applyPhaseFrontmatterForm, parsePhaseFrontmatter, phaseFrontmatterToForm } from "./phase-frontmatter"
import { fileFromDetail, languageForPath } from "./panel-files"
import { subgraphMembership, type SubgraphMembership } from "./subgraph-membership"
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

function SubgraphFolder({
  subgraph,
  onOpen,
  onChoosePath,
}: {
  subgraph: SubgraphMembership
  onOpen: (file: FileMeta) => void
  onChoosePath: (subgraph: SubgraphMembership) => void
}) {
  const treeState = useNativeDirectoryTree({
    workspaceRoot: subgraph.path,
    skillId: subgraph.label,
    titlePrefix: subgraph.label,
    saveEnabled: false,
  })

  return (
    <FolderRow
      name={subgraph.label}
      endAdornment={<SubgraphLinkBadge subgraph={subgraph} onChoosePath={() => onChoosePath(subgraph)} />}
      defaultExpanded={true}
    >
      <div className="space-y-1 pb-1">
        <TreeStatusLine state={treeState} />
        {treeState.tree ? (
          <AssetTreeRows node={treeState.tree} onOpen={onOpen} emptyLabel="Empty subgraph folder" />
        ) : null}
      </div>
    </FolderRow>
  )
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
  const className = linked
    ? "inline-flex h-5 items-center rounded border border-success-border bg-success-background px-1.5 text-[10px] font-medium leading-none text-success-foreground"
    : "inline-flex h-5 items-center rounded border border-destructive-border bg-destructive-background px-1.5 text-[10px] font-medium leading-none text-destructive"

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {linked ? (
          <span title={label} aria-label={label} className={className}>
            link
          </span>
        ) : (
          <button
            type="button"
            title={label}
            aria-label={`${subgraphStatusLabel(subgraph)} - choose subgraph folder`}
            onClick={onChoosePath}
            className={className}
          >
            link
          </button>
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
  const subgraphs = useMemo(() => subgraphMembership(skillDetail), [skillDetail])
  const displayedSubgraphs = useMemo(
    () => subgraphs.map((subgraph) => {
      const override = subgraphPathOverrides[subgraph.id]
      return override
        ? { ...subgraph, path: override, legacyTargetSkill: null, status: "resolved" as const }
        : subgraph
    }),
    [subgraphPathOverrides, subgraphs],
  )
  const chooseSubgraphPath = useCallback(async (subgraph: SubgraphMembership) => {
    if (!rootTarget) {
      toast.error("Open a skill before linking a subgraph.")
      return
    }

    const selected = await selectSkillDirectory(subgraph.path ?? workspaceRoot ?? rootTarget)
    if (!selected) return

    try {
      const current = await readWorkspaceFile(rootTarget, subgraph.filePath)
      const parsed = parsePhaseFrontmatter(current.content)
      if (!parsed.ok) {
        throw new Error(parsed.message)
      }
      const form = phaseFrontmatterToForm(parsed.frontmatter)
      const next = applyPhaseFrontmatterForm(current.content, { ...form, path: selected }, "subgraph")
      if (!next.ok) {
        throw new Error(next.message)
      }
      await writeWorkspaceFile(rootTarget, subgraph.filePath, next.markdown, current.hash)
      setSubgraphPathOverrides((currentOverrides) => ({ ...currentOverrides, [subgraph.id]: selected }))
      toast.success(`Linked ${subgraph.label}`, { description: selected })
    } catch (error) {
      toast.error("Could not link subgraph", { description: errorMessage(error) })
    }
  }, [rootTarget, workspaceRoot])

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col bg-background">
        <PanelHeader title="Assets" />

        <ScrollArea className="flex-1">
          <div className="space-y-4 px-1.5 py-2 text-xs">
            <div>
              <SectionHeading label="Skill Files" />
              <div className="space-y-0.5 mt-1">
                <TreeStatusLine state={nativeFileTree} />
                <AssetTreeRows node={fileTree} onOpen={openFile} emptyLabel="No files" />
              </div>
            </div>

            <div className="border-t border-border/40 pt-3">
              <div className="mt-1 space-y-0.5">
                <FolderRow name="Subgraphs" defaultExpanded={true}>
                  {displayedSubgraphs.length === 0 ? (
                    <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No subgraphs</div>
                  ) : null}
                  {displayedSubgraphs.map((sub) => (
                    <SubgraphFolder key={sub.id} subgraph={sub} onOpen={openFile} onChoosePath={chooseSubgraphPath} />
                  ))}
                </FolderRow>
              </div>
            </div>
          </div>
        </ScrollArea>
      </div>
    </TooltipProvider>
  )
}
