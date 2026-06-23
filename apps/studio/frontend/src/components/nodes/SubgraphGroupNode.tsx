import { type Node, type NodeProps } from '@xyflow/react'
import { FileCode2 } from 'lucide-react'
import type { SubgraphGroupNodeData } from './types'
import { Spinner } from '../ui/spinner'

type SubgraphGroupNode = Node<SubgraphGroupNodeData, 'subgraphGroup'>

/**
 * N2 atom #13 (subgraph-inline-preview): the dashed container that frames an
 * expanded subgraph's inline child topology. It is a passive, full-size backdrop
 * — the real child phase nodes/edges render as siblings ON TOP of it (emitted by
 * subgraph-expansion.ts), so this node only draws the border + header and the
 * loading / error affordance. Sized via node width/height; renders to 100% so it
 * exactly bounds the child sub-layout.
 */
export function SubgraphGroupNode({ data }: NodeProps<SubgraphGroupNode>) {
  return (
    <div className="pointer-events-none flex size-full flex-col rounded-lg border-2 border-dashed border-primary/30 bg-primary/5">
      <div className="flex items-center gap-2 border-b border-primary/20 px-3 py-2 text-xs font-medium text-primary">
        <FileCode2 className="size-3.5 shrink-0" />
        <span className="truncate">{data.parentLabel} subgraph</span>
        <span className="ml-auto truncate rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {data.path}
        </span>
      </div>
      {data.status === 'loading' ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-xs text-muted-foreground">
          <Spinner className="size-3" />
          <span>Loading subgraph…</span>
        </div>
      ) : null}
      {data.status === 'error' ? (
        <div className="flex flex-1 items-center justify-center px-3 text-center text-xs text-destructive">
          {data.message ?? `Failed to load subgraph at ${data.path}`}
        </div>
      ) : null}
    </div>
  )
}
