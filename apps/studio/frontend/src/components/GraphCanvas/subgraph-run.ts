import type { SkillNodeStatus } from '@/components/nodes'

// ————————————————————————————————————————————————————————————————————————————
// subgraph-run: what a SUBGRAPH container does while its own graph executes
// (canvas F7). Pure rules over the run projection, so the canvas holds only the
// React state and this file holds the decisions.
// ————————————————————————————————————————————————————————————————————————————

/** What the canvas should do to a container whose status just changed. */
export type ContainerAutoAction = 'expand' | 'collapse' | null

/**
 * Open a container when it starts running, close it when it finishes clean, and
 * LEAVE A FAILED ONE OPEN.
 *
 * Modelled on GitHub Actions' log groups, which expand the running step, fold it
 * away on success and keep failed ones unfolded — folding on failure hides the
 * only nodes that explain the failure, at the moment the reader most needs them.
 * What is deliberately NOT borrowed is Actions' habit of writing the fold state
 * into the URL: here it is a way of looking at the board within one session, not
 * a location to share.
 *
 * Reacting to the TRANSITION, not to the steady state, is what lets a reader
 * collapse a still-running container and have it stay collapsed.
 */
export function containerAutoAction(
  previous: SkillNodeStatus | undefined,
  next: SkillNodeStatus,
): ContainerAutoAction {
  if (next === previous) return null
  if (next === 'running') return 'expand'
  if (previous === 'running' && next === 'success') return 'collapse'
  return null
}

/**
 * How much of a container's own graph has finished.
 *
 * `total` is null when the child topology is not loaded: the finished count is a
 * fact of the run, but the denominator is a fact of the child graph, and the
 * canvas only holds that while the child is (or has been) expanded. A fraction
 * needs both, so without the second half the UI reports the count alone rather
 * than inventing a total (same discipline as F3's runtime clock).
 *
 * Null overall means the run never entered this container — nothing to report,
 * as opposed to `0/7`, which would claim it started and got nowhere.
 */
export interface SubgraphProgress {
  done: number
  total: number | null
}

const FINISHED: ReadonlySet<SkillNodeStatus> = new Set<SkillNodeStatus>(['success', 'error'])

export function subgraphProgress(
  statusByNodeId: Record<string, SkillNodeStatus>,
  containerPath: string,
  childPhases: readonly string[] | null,
): SubgraphProgress | null {
  let seen = 0
  let done = 0
  for (const [path, status] of Object.entries(statusByNodeId)) {
    // Direct children only: a phase nested deeper belongs to ITS container's
    // progress, and counts here only through the one phase that encloses it.
    const separator = path.lastIndexOf('.')
    if (separator === -1 || path.slice(0, separator) !== containerPath) continue
    seen += 1
    if (FINISHED.has(status)) done += 1
  }
  if (seen === 0) return null
  return { done, total: childPhases ? childPhases.length : null }
}

/** The short form shown on the container chip, and the sentence behind it. */
export function subgraphProgressLabel(progress: SubgraphProgress): { short: string; full: string } {
  if (progress.total === null) {
    return {
      short: `${progress.done} done`,
      full: `${progress.done} phases finished — open the subgraph to count the rest`,
    }
  }
  return {
    short: `${progress.done}/${progress.total}`,
    full: `${progress.done} of ${progress.total} phases finished`,
  }
}
