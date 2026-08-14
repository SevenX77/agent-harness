import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { NodeCompileErrorBadge } from './NodeCompileErrorBadge'
import { NODE_CAPSULE_BASE, nodeCardClass } from './node-card'
import { GLOBAL_INPUT_SOURCE_HANDLE_ID, GLOBAL_OUTPUT_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
import type { GlobalNodeData } from './types'

export type { GlobalNodeData } from './types'

type GlobalNode = Node<GlobalNodeData>

// The boundary card is the same card a phase node is (decision 2026-08-13 D8:
// shared node-card module, no bare-card copies) — only width and content differ.
export function GlobalInputOutputNode({ data, selected }: NodeProps<GlobalNode>) {
  const isInput = data.type === 'global-input'
  const compileErrors = data.compileErrors ?? []

  return (
    <div
      className={nodeCardClass({
        minWidth: 'min-w-[220px]',
        ring: selected ? 'selected' : 'none',
        extra: ['text-sm'],
      })}
    >
      {isInput ? (
        <Handle
          id={GLOBAL_INPUT_SOURCE_HANDLE_ID}
          type="source"
          position={Position.Bottom}
          className="global-input-source-handle !size-2.5 !border-background !bg-primary opacity-60 transition-opacity duration-200 group-hover:opacity-100"
        />
      ) : (
        <Handle
          id={GLOBAL_OUTPUT_TARGET_HANDLE_ID}
          type="target"
          position={Position.Top}
          className="global-output-target-handle !size-2.5 !border-background !bg-primary opacity-60 transition-opacity duration-200 group-hover:opacity-100"
        />
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            {isInput ? 'Input' : 'Output'}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <NodeCompileErrorBadge errors={compileErrors} scope="boundary" />
          <span className={[NODE_CAPSULE_BASE, 'border-border bg-card text-muted-foreground'].join(' ')}>
            {isInput ? 'INPUT' : 'OUTPUT'}
          </span>
        </div>
      </div>
    </div>
  )
}

export const GlobalInputNode = GlobalInputOutputNode
export const GlobalOutputNode = GlobalInputOutputNode
