import { describe, expect, it } from 'vitest'
import { containerAutoAction, subgraphProgress, subgraphProgressLabel } from './subgraph-run'

describe('containerAutoAction — a container opens while it runs (canvas F7)', () => {
  it('opens when the container starts running', () => {
    expect(containerAutoAction(undefined, 'running')).toBe('expand')
    expect(containerAutoAction('idle', 'running')).toBe('expand')
  })

  it('closes when the container finishes successfully', () => {
    expect(containerAutoAction('running', 'success')).toBe('collapse')
  })

  it('leaves a FAILED container open', () => {
    // Collapsing on failure would hide the only nodes that explain the failure.
    expect(containerAutoAction('running', 'error')).toBeNull()
    expect(containerAutoAction('running', 'paused')).toBeNull()
  })

  it('does nothing while the state holds, or on states it does not own', () => {
    expect(containerAutoAction('running', 'running')).toBeNull()
    expect(containerAutoAction('success', 'success')).toBeNull()
    expect(containerAutoAction('error', 'idle')).toBeNull()
    expect(containerAutoAction(undefined, 'success')).toBeNull()
  })
})

describe('subgraphProgress — how far the container got', () => {
  const statuses = {
    event_timeline: 'running' as const,
    'event_timeline.plan': 'success' as const,
    'event_timeline.extract': 'error' as const,
    'event_timeline.score': 'running' as const,
    'other.plan': 'success' as const,
    plan: 'success' as const,
  }

  it('counts only the phases directly inside THIS container', () => {
    expect(subgraphProgress(statuses, 'event_timeline', ['plan', 'extract', 'score', 'review']))
      .toEqual({ done: 2, total: 4 })
  })

  it('reports no total when the child topology is not loaded', () => {
    // The count of finished phases is a run fact; the denominator is a topology
    // fact, and the canvas only holds it while the child is (or has been) expanded.
    expect(subgraphProgress(statuses, 'event_timeline', null)).toEqual({ done: 2, total: null })
  })

  it('counts a nested container as ONE phase of this graph, not its insides', () => {
    const nested = {
      'outer.inner': 'success' as const,
      'outer.inner.deep': 'success' as const,
    }

    expect(subgraphProgress(nested, 'outer', ['inner'])).toEqual({ done: 1, total: 1 })
  })

  it('is null when the run never entered this container', () => {
    expect(subgraphProgress(statuses, 'untouched', ['a', 'b'])).toBeNull()
    expect(subgraphProgress({}, 'event_timeline', ['a'])).toBeNull()
  })
})

describe('subgraphProgressLabel', () => {
  it('reads as a fraction when the total is known', () => {
    expect(subgraphProgressLabel({ done: 3, total: 7 })).toEqual({
      short: '3/7',
      full: '3 of 7 phases finished',
    })
  })

  it('reports the count alone rather than inventing a denominator', () => {
    expect(subgraphProgressLabel({ done: 3, total: null }).short).toBe('3 done')
  })
})
