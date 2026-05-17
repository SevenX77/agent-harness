import { File, Folder, FolderOpen } from 'lucide-react'
import { Tree, type NodeRendererProps } from 'react-arborist'

interface FileTreeNode {
  id: string
  name: string
  path: string
  kind: 'directory' | 'file'
  children?: FileTreeNode[]
}

interface FileTreeProps {
  files: Record<string, string>
  activeFile: string | null
  dirty: Record<string, boolean>
  errorFiles?: Record<string, boolean>
  onSelect: (path: string) => void
}

function insertPath(nodes: FileTreeNode[], filePath: string): void {
  const parts = filePath.split('/').filter(Boolean)
  let siblings = nodes
  let currentPath = ''

  parts.forEach((part, index) => {
    currentPath = currentPath ? `${currentPath}/${part}` : part
    const isFile = index === parts.length - 1
    let node = siblings.find((item) => item.name === part)
    if (!node) {
      node = {
        id: currentPath,
        name: part,
        path: currentPath,
        kind: isFile ? 'file' : 'directory',
        children: isFile ? undefined : [],
      }
      siblings.push(node)
      siblings.sort((left, right) => {
        if (left.kind !== right.kind) {
          return left.kind === 'directory' ? -1 : 1
        }
        return left.name.localeCompare(right.name)
      })
    }
    if (!isFile) {
      node.children ??= []
      siblings = node.children
    }
  })
}

function buildTree(files: Record<string, string>): FileTreeNode[] {
  const nodes: FileTreeNode[] = []
  Object.keys(files).sort().forEach((path) => insertPath(nodes, path))
  return nodes
}

function FileTreeRow({
  node,
  style,
  dirty,
  errorFiles,
}: NodeRendererProps<FileTreeNode> & Pick<FileTreeProps, 'dirty' | 'errorFiles'>) {
  const Icon = node.isLeaf ? File : node.isOpen ? FolderOpen : Folder
  const isDirty = node.data.kind === 'file' && dirty[node.data.path] === true
  const fileHasError = node.data.kind === 'file' && errorFiles?.[node.data.path] === true

  return (
    <div
      style={style}
      className={`flex h-full items-center gap-2 px-2 text-sm ${
        node.isSelected ? 'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-100' : 'text-slate-700 dark:text-slate-200'
      }`}
      title={node.data.path}
    >
      <Icon className="h-4 w-4 shrink-0 text-slate-500" />
      <span className="min-w-0 flex-1 truncate">{node.data.name}</span>
      {isDirty ? <span aria-label="dirty" className="h-2 w-2 shrink-0 rounded-full bg-red-500" /> : null}
      {fileHasError ? <span aria-label="error" className="h-2 w-2 shrink-0 rounded-full bg-amber-500" /> : null}
    </div>
  )
}

export function FileTree({ files, activeFile, dirty, errorFiles, onSelect }: FileTreeProps) {
  const data = buildTree(files)

  return (
    <div className="h-full min-h-0 border-r border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <Tree<FileTreeNode>
        data={data}
        height={600}
        width="100%"
        rowHeight={28}
        indent={18}
        selection={activeFile ?? undefined}
        openByDefault
        disableDrag
        disableDrop
        onActivate={(node) => {
          if (node.data.kind === 'file') {
            onSelect(node.data.path)
          }
        }}
        idAccessor={(node) => node.id}
        childrenAccessor={(node) => node.children ?? null}
      >
        {(props) => <FileTreeRow {...props} dirty={dirty} errorFiles={errorFiles} />}
      </Tree>
    </div>
  )
}
