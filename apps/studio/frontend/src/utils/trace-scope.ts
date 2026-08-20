import type { CallbackEvent } from '../api/types'
import {
  crossesInputBoundary,
  downstreamPhaseOf,
  eventCrossesEdge,
  isInputBoundaryId,
  isOutputBoundaryId,
} from './edge-identity'
import { eventPhase } from './trace'

// 选中即范围 (decision 2026-08-13 D6, overturning 2026-08-09 D2/#657): the
// canvas selection IS the trace's display scope. The filter is visibly
// anchored to the selection ring, announced by the panel's scope chip, and
// exits with one click (or a blank-canvas click) — the three objections that
// killed the previous invisible filter are answered, not dodged.
//
// Which events an EDGE scope admits is not decided here: `edge-identity` owns
// that question for every surface that asks it (canvas dot, edge steps, this
// scope), because two modules answering it apart is how they came to disagree.

export type TraceScope =
  | { kind: 'node'; phase: string }
  | { kind: 'edge'; source: string; target: string }
  | { kind: 'input' }
  | { kind: 'output' }

export function eventInScope(event: CallbackEvent, scope: TraceScope): boolean {
  switch (scope.kind) {
    case 'node':
      return eventPhase(event) === scope.phase
    case 'edge':
      return eventCrossesEdge(event, scope.source, scope.target)
    case 'input':
      return crossesInputBoundary(event)
    case 'output': {
      const downstream = downstreamPhaseOf(event)
      return downstream !== null && isOutputBoundaryId(downstream)
    }
  }
}

function boundaryAwareName(id: string): string {
  if (isInputBoundaryId(id)) return 'Input'
  if (isOutputBoundaryId(id)) return 'Output'
  return id
}

/** What the scope chip says — the same names the canvas shows. */
export function scopeLabel(scope: TraceScope): string {
  switch (scope.kind) {
    case 'node':
      return scope.phase
    case 'edge':
      return `${boundaryAwareName(scope.source)} → ${boundaryAwareName(scope.target)}`
    case 'input':
      return 'Input'
    case 'output':
      return 'Output'
  }
}
