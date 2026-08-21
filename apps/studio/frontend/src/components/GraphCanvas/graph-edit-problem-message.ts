import i18n from '@/i18n'
import { GraphEditError, type GraphEditProblem } from './canvas-authoring'

/**
 * The one place a graph-edit problem becomes a sentence.
 *
 * Every canvas surface that reports a refused edit — the name dialog's inline
 * error, the reconnect toast, the rejected-promise toasts — comes through here,
 * so a code has exactly one wording per language and no surface can invent its
 * own. Mirrors `utils/errors.ts:errorMessage`, which does the same for backend
 * `error_code`s (`04_platform/i18n.md` §4).
 */
export function graphEditProblemMessage(problem: GraphEditProblem): string {
  if (problem.code === 'name_taken') {
    return i18n.t('problem.name_taken', { ns: 'canvas', phaseId: problem.phaseId })
  }
  return i18n.t(`problem.${problem.code}`, { ns: 'canvas' })
}

/**
 * The message for a failed canvas edit, whatever went wrong.
 *
 * A rejected edit is either a rule the canvas itself refused (a
 * `GraphEditError`, which still knows its code) or something further down the
 * stack — a native-fs write, an HTTP call — whose `Error.message` is already a
 * finished string. `fallback` covers the third case, a rejection that is
 * neither: the caller supplies what the reader should be told the action was.
 */
export function graphEditErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof GraphEditError) {
    return graphEditProblemMessage(error.problem)
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}
