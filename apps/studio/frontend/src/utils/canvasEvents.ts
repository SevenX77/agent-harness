import type { Node } from 'reactflow'
import type { StudioNodeData } from '../CustomNodes'

export interface OpenPhaseFileDetail {
  skill_id: string
  phase_id: string
  file: string
  readonly: boolean
}

export function phaseFileForNode(node: Node<StudioNodeData>): string | null {
  if (!node.data.src) {
    return null
  }
  return `${node.data.src}/${node.data.mode === 'logic' ? 'LOGIC.md' : 'SKILL.md'}`
}

export function dispatchOpenPhaseFileEvent(detail: OpenPhaseFileDetail): void {
  window.dispatchEvent(new CustomEvent('canvas:open-phase-file', {
    bubbles: true,
    cancelable: true,
    detail,
  }))
}
