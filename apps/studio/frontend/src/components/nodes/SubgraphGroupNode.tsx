import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { FileCode2, GripHorizontal } from 'lucide-react'
import type { CSSProperties } from 'react'
import { SUBGRAPH_BRIDGE_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
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
  const bridgeTargetStyle = typeof data.bridgeTargetOffsetY === 'number' && Number.isFinite(data.bridgeTargetOffsetY)
    ? ({ '--subgraph-bridge-target-y': `${Math.max(0, data.bridgeTargetOffsetY)}px` } as CSSProperties)
    : undefined

  return (
    <div className="subgraph-dash-frame studio-subgraph-frame pointer-events-none relative flex size-full overflow-visible rounded-md" style={bridgeTargetStyle}>
      <Handle
        id={SUBGRAPH_BRIDGE_TARGET_HANDLE_ID}
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="subgraph-bridge-target-handle"
      />
      <div className="flex size-full min-h-0 flex-col overflow-hidden rounded-[inherit]">
        <div
          data-subgraph-group-drag-handle="true"
          className="subgraph-group-drag-handle studio-subgraph-header pointer-events-auto flex cursor-grab select-none items-center gap-2 border-b px-3 py-2 text-xs font-medium active:cursor-grabbing"
        >
          <GripHorizontal className="size-3.5 shrink-0 text-muted-foreground" />
          <FileCode2 className="size-3.5 shrink-0" />
          <span className="truncate">{title}</span>
          <span className="studio-subgraph-badge ml-auto shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
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
