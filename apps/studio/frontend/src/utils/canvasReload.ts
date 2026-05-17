import type { StudioGlobalEvent } from '../api/types'

export type CanvasReloadDecision = 'ignore' | 'reload' | 'prompt'

export function decideGraphReload(
  event: StudioGlobalEvent,
  selectedSkillId: string | null,
  isDirty: boolean,
): CanvasReloadDecision {
  if (event.type !== 'skill_changed' || event.skill_id !== selectedSkillId || event.file !== 'GRAPH.md') {
    return 'ignore'
  }
  return isDirty ? 'prompt' : 'reload'
}
