import { useMemo, useState } from 'react'
import type { CallbackEvent } from '../api/types'
import type { TraceCategory } from '../components/trace/trace-category'
import { traceHeadlineText, useTraceCopy } from '../components/trace/trace-copy'
import { eventHeadline, RUN_SCOPE } from '../utils/trace'
import {
  isNarrowingActive,
  narrowTraceSteps,
  type TraceNarrowing,
} from '../utils/trace-narrowing'
import type { TraceStep } from '../utils/trace-steps'

/**
 * The reader's own 取景 over a built step list: what they typed, which type and
 * node tags they turned on, and whether they asked for route issues only.
 *
 * It takes STEPS rather than events because that is the unit it hands back —
 * narrowing events and rebuilding steps afterwards tears a step in half the
 * moment only one of its halves matches (trace-observability F9). Canvas focus
 * is deliberately absent: focus scrolls, only the reader hides anything
 * (decision 2026-08-09 D2).
 */
export function useTraceNarrowing(steps: TraceStep[]) {
  const t = useTraceCopy()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<TraceCategory[]>([])
  const [selectedPhases, setSelectedPhases] = useState<string[]>([])
  const [routeIssuesOnly, setRouteIssuesOnly] = useState(false)

  // Only real nodes are offered as filters: the run scope is not a node, and a
  // chip for it would filter to "the steps that belong to no node".
  const phases = useMemo(
    () => Array.from(new Set(steps.map((step) => step.phase)))
      .filter((phase) => phase !== RUN_SCOPE)
      .sort(),
    [steps],
  )

  const narrowing: TraceNarrowing = useMemo(
    () => ({ searchTerm, selectedCategories, selectedPhases, routeIssuesOnly }),
    [searchTerm, selectedCategories, selectedPhases, routeIssuesOnly],
  )

  const narrowedSteps = useMemo(
    () => narrowTraceSteps(
      steps,
      narrowing,
      (event: CallbackEvent) => traceHeadlineText(eventHeadline(event), t),
    ),
    [steps, narrowing, t],
  )

  return {
    searchTerm,
    selectedCategories,
    selectedPhases,
    routeIssuesOnly,
    phases,
    narrowedSteps,
    /**
     * Whether anything is being held back right now. Read by everything whose
     * subject is "this list" rather than "this run" — the run's outcome row
     * above all, which is a verdict on the whole trace and must not sit at the
     * end of a list that is not the whole trace (F3, 2026-08-20 revision).
     */
    isNarrowed: isNarrowingActive(narrowing),
    setSearchTerm,
    setSelectedCategories,
    setSelectedPhases,
    setRouteIssuesOnly,
  }
}
