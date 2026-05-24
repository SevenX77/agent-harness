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
import { SubgraphCategory } from "./SubgraphCategory"

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
  for (const path of Object.keys(skillDetail?.files ?? {}).sort()) {
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

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Assets" />

      <ScrollArea className="flex-1">
        <div className="space-y-1 px-1.5 py-1 text-xs">
          <SubgraphCategory skillDetail={skillDetail} />
          <SectionHeading label="Skill Files" />
          <AssetTreeRows node={fileTree} onOpen={openFile} />
        </div>
      </ScrollArea>
    </div>
  )
}
