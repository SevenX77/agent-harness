import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import { FileCode2 } from 'lucide-react'
import type { ChildGraphTopology, ErrorResponse } from '@/api/types'
import { getChildGraphTopology } from '@/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'

type ChildPhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

interface ChildPhaseRow {
  name: string
  kind: ChildPhaseKind
}

function phaseKindFromMode(mode: string | undefined): ChildPhaseKind {
  if (mode === 'subgraph') return 'SUBGRAPH'
  if (mode === 'agent' || mode === 'skill' || mode === 'llm') return 'AGENT'
  return 'LOGIC'
}

/**
 * Join a resolved child topology's phase names against its topology rows to
 * produce the real (name + kind) preview rows. Phase names are the source of
 * truth for ordering/presence; the row's `mode` supplies the kind. Never
 * fabricates a phase that the child graph does not declare.
 */
export function childPhaseRows(topology: ChildGraphTopology): ChildPhaseRow[] {
  const modeById = new Map(topology.graph_topology.map((row) => [row.id, row.mode]))
  return topology.phases.map((name) => ({ name, kind: phaseKindFromMode(modeById.get(name)) }))
}

type ViewState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'empty'; childName: string }
  | { status: 'loaded'; childName: string; rows: ChildPhaseRow[] }

interface SubgraphInlineViewProps {
  path: string
  parentLabel: string
  state: ViewState
}

const KIND_BADGE_CLASS = 'rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase text-muted-foreground'

/**
 * Pure presentational shell for the inline subgraph preview. Renders the real
 * child phase rows (or loading / error / empty states) inside the existing
 * dashed/bordered inline container. Kept side-effect free so it is rendered
 * synchronously in tests.
 */
export function SubgraphInlineView({ path, parentLabel, state }: SubgraphInlineViewProps) {
  return (
    <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-2 text-xs">
      <div className="flex items-center gap-2 font-medium text-primary">
        <FileCode2 className="size-3.5" />
        {parentLabel} subgraph
      </div>
      <div className="mt-2 rounded-md border border-border bg-background px-2 py-1 font-mono text-muted-foreground">
        {path}
      </div>
      {state.status === 'loading' ? (
        <div className="mt-2 grid gap-1" aria-busy="true">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner className="size-3" />
            <span>Loading subgraph…</span>
          </div>
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
        </div>
      ) : null}
      {state.status === 'error' ? (
        <div className="mt-2 rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-destructive">
          {state.message}
        </div>
      ) : null}
      {state.status === 'empty' ? (
        <div className="mt-2 rounded border border-border bg-card px-2 py-1 text-muted-foreground">
          {state.childName} has no phases
        </div>
      ) : null}
      {state.status === 'loaded' ? (
        <div className="mt-2 grid gap-1 text-muted-foreground">
          {state.rows.map((row) => (
            <div
              key={row.name}
              className="flex items-center justify-between gap-2 rounded border border-border bg-card px-2 py-1"
            >
              <span className="truncate font-medium text-foreground">{row.name}</span>
              <span className={KIND_BADGE_CLASS}>{row.kind}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

interface SubgraphInlineProps {
  skillId: string
  path: string
  parentLabel: string
}

function errorMessageFor(error: unknown, path: string): string {
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const body = error.response?.data as Partial<ErrorResponse> | undefined
    if (status === 404) {
      return `subgraph not found at ${path}`
    }
    if (body?.message) {
      return body.message
    }
  }
  return `Failed to load subgraph at ${path}`
}

export function SubgraphInline({ skillId, path, parentLabel }: SubgraphInlineProps) {
  const [state, setState] = useState<ViewState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getChildGraphTopology(skillId, path)
      .then((topology) => {
        if (cancelled) return
        const rows = childPhaseRows(topology)
        if (rows.length === 0) {
          setState({ status: 'empty', childName: topology.name })
          return
        }
        setState({ status: 'loaded', childName: topology.name, rows })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState({ status: 'error', message: errorMessageFor(error, path) })
      })
    return () => {
      cancelled = true
    }
  }, [skillId, path])

  return <SubgraphInlineView path={path} parentLabel={parentLabel} state={state} />
}
