import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { FileCode2, GripHorizontal, Maximize2 } from 'lucide-react'
import { SUBGRAPH_BRIDGE_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
import type { SubgraphGroupNodeData } from './types'
import { Spinner } from '../ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

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
    <div className="subgraph-dash-frame studio-subgraph-frame pointer-events-none relative flex size-full overflow-visible rounded-md">
      <div className="flex size-full min-h-0 flex-col overflow-hidden rounded-[inherit]">
        <div
          data-subgraph-group-drag-handle="true"
          className="subgraph-group-drag-handle studio-subgraph-header pointer-events-auto relative flex cursor-grab select-none items-center gap-2 border-b px-3 py-2 text-xs font-medium active:cursor-grabbing"
        >
          {/* Bridge target handle lives ON the header so React Flow measures its
              center at the header's real left-edge vertical center — no magic
              CONTAINER_HEADER/2 constant that drifts from the rendered height. */}
          <Handle
            id={SUBGRAPH_BRIDGE_TARGET_HANDLE_ID}
            type="target"
            position={Position.Left}
            isConnectable={false}
            className="subgraph-bridge-target-handle"
          />
          <GripHorizontal className="size-3.5 shrink-0 text-muted-foreground" />
          <FileCode2 className="size-3.5 shrink-0" />
          <span className="truncate">{title}</span>
          <span className="studio-subgraph-badge ml-auto shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            subgraph
          </span>
          {typeof data.onOpenCanvas === 'function' ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Open subgraph canvas"
                  onClick={(event) => {
                    event.stopPropagation()
                    data.onOpenCanvas?.(data.path, title)
                  }}
                  onDoubleClick={(event) => event.stopPropagation()}
                  className="nodrag nopan pointer-events-auto inline-flex size-5 shrink-0 items-center justify-center rounded border border-border bg-card text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
                >
                  <Maximize2 className="size-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>Open subgraph canvas</TooltipContent>
            </Tooltip>
          ) : null}
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
