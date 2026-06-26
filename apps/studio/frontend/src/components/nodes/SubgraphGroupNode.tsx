import { type Node, type NodeProps } from '@xyflow/react'
import { FileCode2 } from 'lucide-react'
import type { SubgraphGroupNodeData } from './types'
import { Spinner } from '../ui/spinner'

type SubgraphGroupNode = Node<SubgraphGroupNodeData, 'subgraphGroup'>

function pathBasename(path: string): string {
  return path.replace(/\\/g, '/').split('/').filter(Boolean).pop()?.trim() ?? ''
}

export function subgraphGroupTitle(data: SubgraphGroupNodeData): string {
  return data.childName?.trim() || pathBasename(data.path) || data.parentLabel
}

export function SubgraphGroupNode({ data }: NodeProps<SubgraphGroupNode>) {
  const title = subgraphGroupTitle(data)

  return (
    <div className="subgraph-dash-frame pointer-events-none relative flex size-full overflow-visible rounded-lg bg-transparent">
      <div className="flex size-full min-h-0 flex-col overflow-hidden rounded-[inherit]">
        <div className="flex items-center gap-2 border-b border-primary/20 px-3 py-2 text-xs font-medium text-primary">
          <FileCode2 className="size-3.5 shrink-0" />
          <span className="truncate">{title}</span>
          <span className="ml-auto shrink-0 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            subgraph
          </span>
        </div>
        {data.status === 'loading' ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-xs text-muted-foreground">
            <Spinner className="size-3" />
            <span>Loading subgraph...</span>
          </div>
        ) : null}
        {data.status === 'error' ? (
          <div className="flex flex-1 items-center justify-center px-3 text-center text-xs text-destructive">
            {data.message ?? `Failed to load subgraph at ${data.path}`}
          </div>
        ) : null}
      </div>
    </div>
  )
}
