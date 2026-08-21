import { useTranslation } from 'react-i18next'
import type {
  EventFact,
  FactValue,
  RouteDecisionDetails,
  SettingOutcome,
  ToolCallSummary,
  TraceHeadline,
  TransitionEnds,
} from '../../utils/trace'
import { routeName, settingsThatMoved } from '../../utils/trace'

/**
 * The ONE place a trace fact becomes a sentence.
 *
 * `utils/trace.ts` is a pure projection: it knows which event happened and what
 * it carried, and it has no idea who is reading. So it returns descriptors —
 * `TraceHeadline`, `ToolCallSummary.verb`, `EventFact.label` — and every word
 * the reader sees is chosen here, from the `trace` namespace. This is the same
 * shape the canvas uses for its edit problems (`graphEditProblemMessage`, K4c)
 * and the backend uses for its error codes (`errorMessage`, K4a): one exit, so
 * one code can never read as two different sentences on two surfaces.
 *
 * Two namespaces, not one. A transition that starts at the graph's input
 * boundary must call that boundary exactly what the canvas calls it, so the
 * word comes from `canvas:boundary.*` rather than from a second copy here that
 * could drift.
 */
export type TraceCopy = (key: string, options?: Record<string, unknown>) => string

/**
 * The trace's translator, as the narrow thing this module actually needs.
 *
 * Half the keys here are BUILT — `fact.${label}`, `decision.${decision}`,
 * `settings.${verdict}` — because the descriptor already names which case it
 * is, and writing thirty switch arms to turn that name back into the same
 * string would be the table twice. i18next's own `t` type rejects a computed
 * key outright (it wants a literal it can look up), so the translator is
 * narrowed once, HERE, to "something that turns a key into a sentence"; every
 * caller then gets a plain, honest signature.
 *
 * What that gives up is TypeScript checking key NAMES. That is covered better
 * elsewhere: `trace-copy.test.tsx` renders every headline kind, every route
 * decision, every setting verdict and every fact label in both languages and
 * fails if any of them comes back as its own key — which catches a typo the
 * compiler never could, in the language the reader actually gets.
 */
export function useTraceCopy(): TraceCopy {
  const { t } = useTranslation(['trace', 'canvas'])
  return t as unknown as TraceCopy
}

/** A transition as one line: the phases it joins, in the direction it ran. */
export function transitionText(ends: TransitionEnds, t: TraceCopy): string {
  const from = ends.from.length > 0 ? ends.from.join(' + ') : t('canvas:boundary.input')
  return `${from} → ${ends.to}`
}

function routeText(details: RouteDecisionDetails, t: TraceCopy): string {
  return routeName(details) ?? t('route.unknown')
}

function routeDecisionText(details: RouteDecisionDetails, t: TraceCopy): string {
  const route = routeText(details, t)
  switch (details.decision) {
    case 'answered':
      return t('message.routeAnswered', { route })
    case 'skipped_circuit_open':
      return t('message.routeSkipped', { route })
    case 'probe_failed':
      return t('message.routeProbeFailed', { route })
    case 'retried_same_route':
      return t('message.routeRetried', { route })
    case 'dropped_rejected_settings':
      return t('message.routeDroppedSettings', { route })
    case 'escalated_budget':
      return t('message.routeEscalated', { route })
    case 'fell_back':
      return t('message.routeFellBack', {
        route,
        next: details.nextRouteId ?? t('route.unknown'),
      })
    case 'failed_terminal':
      return t('message.routeFailedTerminal', { route })
    case 'exhausted':
      return t('message.routeExhausted')
  }
}

function callSettingsText(settings: readonly SettingOutcome[], t: TraceCopy): string {
  const count = settings.length
  const moved = settingsThatMoved(settings)
  return moved === 0
    ? t('message.settingsAsAsked', { count })
    : t('message.settingsMoved', { count, moved })
}

/**
 * What the row says under its kind badge.
 *
 * Empty string means the event has nothing to add beyond its own type, and the
 * row drops the line rather than printing the type twice.
 */
export function traceHeadlineText(headline: TraceHeadline, t: TraceCopy): string {
  switch (headline.kind) {
    case 'nothingToAdd':
      return ''
    case 'enginesOwnWords':
      return headline.text
    case 'predictStarted':
      return t('message.predictStarted')
    case 'phaseStarted':
      return t('message.phaseStarted', { phase: headline.phase })
    case 'phaseFailed':
      return t('message.phaseFailed', { phase: headline.phase })
    case 'phaseFinished':
      return t('message.phaseFinished', { phase: headline.phase })
    case 'transitionStarted':
      return t('message.transitionStarted', { transition: transitionText(headline.ends, t) })
    case 'transitionFinished':
      return t('message.transitionFinished', { transition: transitionText(headline.ends, t) })
    case 'promptCaptured':
      return headline.source === null
        ? t('message.promptCaptured')
        : t('message.promptCapturedFrom', { source: headline.source })
    case 'llmCallCompleted':
      return headline.model === null
        ? t('message.llmCallCompleted')
        : t('message.llmCallCompletedWith', { model: headline.model })
    case 'runEnded':
      return t('message.runEnded', { status: headline.status })
    case 'routeDecision':
      return routeDecisionText(headline.details, t)
    case 'callSettings':
      return callSettingsText(headline.details.settings, t)
  }
}

/** The headline of a folded tool call: what it did, and to what. */
export function toolCallHeadline(summary: ToolCallSummary, t: TraceCopy): string {
  return t('tool.headline', { verb: t(`tool.${summary.verb}`), tool: summary.toolName })
}

export function toolDurationText(summary: ToolCallSummary, t: TraceCopy): string | null {
  return summary.durationMs === null ? null : t('tool.duration', { ms: summary.durationMs })
}

export function factLabelText(fact: EventFact, t: TraceCopy): string {
  return t(`fact.${fact.label}`)
}

export function factValueText(value: FactValue, t: TraceCopy): string {
  switch (value.kind) {
    case 'data':
      return value.text
    case 'word':
      return t(`factValue.${value.word}`)
    case 'transition':
      return transitionText(value.ends, t)
  }
}
