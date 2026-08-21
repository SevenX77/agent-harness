import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { useTranslation } from 'react-i18next'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { NodeCompileErrorBadge } from './NodeCompileErrorBadge'
import { nodeStatusLabel, StatusCapsule } from './StatusCapsule'
import { NODE_CAPSULE_BASE, nodeCardClass } from './node-card'
import { GLOBAL_INPUT_SOURCE_HANDLE_ID, GLOBAL_OUTPUT_TARGET_HANDLE_ID } from './subgraph-bridge-handles'
import type { GlobalNodeData } from './types'

export type { GlobalNodeData } from './types'

type GlobalNode = Node<GlobalNodeData>

// The boundary card is the same card a phase node is (decision 2026-08-13 D8:
// shared node-card module, no bare-card copies) — only width and content differ.
export function GlobalInputOutputNode({ data, selected }: NodeProps<GlobalNode>) {
  const { t } = useTranslation('canvas')
  const isInput = data.type === 'global-input'
  const compileErrors = data.compileErrors ?? []
  // canvas F8: the endpoints wear the same status capsule and the same running
  // frame as a phase card. They are not phases, but from the reader's side of
  // the screen they are nodes on the board, and a board where two of the nodes
  // are permanently blank is not one status system.
  const status = data.status ?? 'idle'
  const isRunning = status === 'running'

  return (
    <div
      className={nodeCardClass({
        minWidth: 'min-w-[220px]',
        ring: selected ? 'selected' : 'none',
        extra: ['text-sm', isRunning && 'studio-running-dash-frame'],
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
            {isInput ? t('boundary.input') : t('boundary.output')}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <NodeCompileErrorBadge errors={compileErrors} scope="boundary" />
          <span className={[NODE_CAPSULE_BASE, 'border-border bg-card text-muted-foreground'].join(' ')}>
            {isInput ? 'INPUT' : 'OUTPUT'}
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <StatusCapsule status={status} />
            </TooltipTrigger>
            <TooltipContent side="top">
              {isInput ? t('boundary.inputTooltip') : t('boundary.outputTooltip')}: {nodeStatusLabel(status)}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}

export const GlobalInputNode = GlobalInputOutputNode
export const GlobalOutputNode = GlobalInputOutputNode
