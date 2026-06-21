import { useMemo } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { useWorkspaceContext } from "../WorkspaceContext"
import type { FileMeta } from "../file-types"
import { FileRow } from "./_shared/FileRow"
import { FolderRow } from "./_shared/FolderRow"
import { PanelHeader } from "./_shared/PanelHeader"
import { SectionHeading } from "./_shared/SectionHeading"
import { fileFromDetail } from "./panel-files"
import { subgraphMembership } from "./subgraph-membership"
import { AlertCircle, CheckCircle2, Workflow } from "lucide-react"

interface AssetsPanelProps {
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
}

interface AssetTreeNode {
  name: string
  path: string
  file?: FileMeta
  children: Map<string, AssetTreeNode>
}

function createAssetTreeNode(name: string, path: string): AssetTreeNode {
  return {
    name,
    path,
    children: new Map(),
  }
}

function buildAssetTree(skillDetail?: SkillDetail): AssetTreeNode {
  const root = createAssetTreeNode("", "")
  for (const path of Object.keys(skillDetail?.files ?? {}).sort((a, b) => a.localeCompare(b))) {
    const parts = path.split("/").filter(Boolean)
    if (parts.length === 0) continue

    let current = root
    parts.forEach((part, index) => {
      const nodePath = parts.slice(0, index + 1).join("/")
      let node = current.children.get(part)
      if (!node) {
        node = createAssetTreeNode(part, nodePath)
        current.children.set(part, node)
      }
      if (index === parts.length - 1) {
        node.file = fileFromDetail(skillDetail, path)
      }
      current = node
    })
  }
  return root
}

function sortedAssetChildren(node: AssetTreeNode): AssetTreeNode[] {
  return [...node.children.values()].sort((left, right) => {
    const leftIsFolder = left.children.size > 0
    const rightIsFolder = right.children.size > 0
    if (leftIsFolder !== rightIsFolder) return leftIsFolder ? -1 : 1
    return left.name.localeCompare(right.name)
  })
}

function AssetTreeRows({ node, onOpen }: { node: AssetTreeNode; onOpen: (file: FileMeta) => void }) {
  return (
    <>
      {sortedAssetChildren(node).map((child) => {
        if (child.children.size > 0) {
          return (
            <FolderRow key={child.path} name={child.name}>
              <AssetTreeRows node={child} onOpen={onOpen} />
            </FolderRow>
          )
        }
        return child.file ? <FileRow key={child.path} file={child.file} onOpen={onOpen} /> : null
      })}
    </>
  )
}

export function AssetsPanel({ skillDetail }: AssetsPanelProps) {
  const { onFileOpen } = useWorkspaceContext()
  const fileTree = useMemo(() => buildAssetTree(skillDetail), [skillDetail])
  const openFile = (file: FileMeta) => onFileOpen(file)

  // Real path-based membership: the subgraphs this skill actually references,
  // derived from the backend topology (R4). No fake in-memory "registered" cache.
  const subgraphs = useMemo(() => subgraphMembership(skillDetail), [skillDetail])

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Assets" />

      <ScrollArea className="flex-1">
        <div className="space-y-4 px-1.5 py-2 text-xs">
          <div>
            <SectionHeading label="Skill Files" />
            <div className="space-y-0.5 mt-1">
              <AssetTreeRows node={fileTree} onOpen={openFile} />
            </div>
          </div>

          <div className="border-t border-border/40 pt-3">
            <SectionHeading label="Subgraphs" />
            <div className="mt-1 space-y-0.5">
              <FolderRow name="Subgraph Library" defaultExpanded={true}>
                {subgraphs.length === 0 ? (
                  <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No subgraphs</div>
                ) : null}
                {subgraphs.map((sub) => (
                  <div
                    key={sub.id}
                    className="group/sub relative flex flex-col gap-1 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-zinc-900/60 text-muted-foreground hover:text-foreground animate-in fade-in duration-200"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Workflow className="size-3.5 text-indigo-400 shrink-0" strokeWidth={1.5} />
                        <span className="truncate font-medium">{sub.label}</span>
                        {sub.status === "resolved" ? (
                          <CheckCircle2 className="size-3.5 text-emerald-500 shrink-0" strokeWidth={2} />
                        ) : (
                          <AlertCircle className="size-3.5 text-rose-500 shrink-0" strokeWidth={2} />
                        )}
                      </div>

                      <div className="flex items-center shrink-0">
                        {sub.status === "resolved" ? (
                          <span className="text-[10px] text-emerald-500 bg-emerald-950/40 border border-emerald-900/40 px-1.5 py-0.5 rounded leading-none">
                            Linked
                          </span>
                        ) : sub.status === "migration-required" ? (
                          <span className="text-[10px] text-foreground bg-muted border border-border px-1.5 py-0.5 rounded leading-none">
                            Migration needed
                          </span>
                        ) : (
                          <span className="text-[10px] text-rose-400 bg-rose-950/40 border border-rose-900/40 px-1.5 py-0.5 rounded leading-none">
                            Missing path
                          </span>
                        )}
                      </div>
                    </div>

                    {sub.path ? (
                      <div className="truncate pl-5 font-mono text-[10px] text-muted-foreground/80" title={sub.path}>
                        {sub.path}
                      </div>
                    ) : sub.status === "migration-required" && sub.legacyTargetSkill ? (
                      <div className="pl-5 text-[10px] text-muted-foreground">
                        Legacy child reference: <span className="font-mono">{sub.legacyTargetSkill}</span>. Save an absolute path to migrate this phase.
                      </div>
                    ) : (
                      <div className="pl-5 text-[10px] text-rose-400/80">
                        No path declared in SUBGRAPH.md — unresolvable.
                      </div>
                    )}
                  </div>
                ))}
              </FolderRow>
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}
