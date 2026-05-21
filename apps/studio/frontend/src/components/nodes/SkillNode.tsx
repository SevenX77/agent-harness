import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertTriangle, Bot, Briefcase, CheckCircle2, Circle, Code, Minus, Network, Pause, Plus, Radio, Workflow } from 'lucide-react'
import { SubgraphInline } from '@/components/studio/SubgraphInline'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { SkillGraphNode, SkillGraphNodeData, SkillNodeStatus } from './types'

type PhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

const STATUS_STYLE: Record<SkillNodeStatus, { label: string, className: string, icon: typeof Circle }> = {
  idle: {
    label: 'Idle',
    className: 'border-border bg-card text-muted-foreground',
    icon: Circle,
  },
  running: {
    label: 'Running',
    className: 'animate-pulse-primary border-primary bg-primary/10 text-primary',
    icon: Radio,
  },
  success: {
    label: 'Success',
    className: 'border-emerald-500/45 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  paused: {
    label: 'Paused',
    className: 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    icon: Pause,
  },
  breakpoint: {
    label: 'Breakpoint',
    className: 'border-fuchsia-500/45 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
    icon: Workflow,
  },
}

function phaseKindLabel(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): PhaseKind {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH'
  if (data.mode === 'skill' || data.mode === 'llm') return 'AGENT'
  return 'LOGIC'
}

function phaseKindIcon(kind: PhaseKind): typeof Bot {
  if (kind === 'LOGIC') return Code
  if (kind === 'SUBGRAPH') return Network
  return Bot
}

export function SkillNode({ data, selected }: NodeProps<SkillGraphNode>) {
  const style = STATUS_STYLE[data.status]
  const StatusIcon = style.icon
  const kind = phaseKindLabel(data)
  const KindIcon = phaseKindIcon(kind)
  const subagentCount = data.subagents?.length ?? 0

  return (
    <div
      className={[
        'relative min-w-[240px] cursor-pointer rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors',
        data.subgraphPath ? 'pb-5' : '',
        selected ? 'border-primary ring-2 ring-primary/30' : 'border-border',
      ].join(' ')}
      onDoubleClick={(event) => {
        if (data.subgraphPath) {
          event.stopPropagation()
        }
      }}
    >
      <Handle type="target" position={Position.Left} className="!size-2.5 !border-background !bg-primary" />
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <KindIcon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{data.label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{kind}</span>
            {subagentCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={`${subagentCount} subagents available`}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <Briefcase className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{subagentCount} subagents available</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={['inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', style.className].join(' ')}>
              <StatusIcon className="size-3" />
              {style.label}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">{style.label}</TooltipContent>
        </Tooltip>
      </div>
      {data.subgraphPath ? (
        <button
          type="button"
          aria-label={data.isExpanded ? 'Collapse subgraph' : 'Expand subgraph'}
          onClick={(event) => {
            event.stopPropagation()
            data.onToggleSubgraph?.()
          }}
          className="absolute bottom-0 left-1/2 inline-flex size-5 -translate-x-1/2 translate-y-1/2 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-primary"
        >
          {data.isExpanded ? <Minus className="size-3" /> : <Plus className="size-3" />}
        </button>
      ) : null}
      {data.subgraphPath && data.isExpanded ? (
        <SubgraphInline path={data.subgraphPath} parentLabel={data.label} />
      ) : null}
      <Handle type="source" position={Position.Right} className="!size-2.5 !border-background !bg-primary" />
    </div>
  )
}
