import type { ResumeRunOptions } from '@/api/client'
import type { TraceHitlResumeRequest } from '@/components/TracePanel'

function optionalString(value: string | null): string | undefined {
  return value && value.trim() !== '' ? value : undefined
}

export function hitlResumeOptionsFromRequest(request: TraceHitlResumeRequest): ResumeRunOptions {
  return {
    checkpointId: optionalString(request.checkpointId),
    checkpointNs: optionalString(request.checkpointNs),
    resumeFromNodeId: optionalString(request.phaseName),
    humanResponse: {
      content: request.content,
      toolCallId: optionalString(request.toolCallId),
    },
  }
}
