import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import {
  buildHitlResumeRequest,
  effectiveToolCallId,
  needsToolCallSelection,
  type PendingHitlPrompt,
  type TraceHitlResumeRequest,
} from './hitl-prompt'

interface HitlPromptFormProps {
  prompt: PendingHitlPrompt
  submitting?: boolean
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
}

/**
 * The HitL answer form content, shared by the side-panel TracePanel and the
 * node-anchored NodeToolbar box (F4). Single source of truth for the form
 * markup + submit wiring; the prompt is derived upstream via latestHitlPrompt.
 */
export function HitlPromptForm({ prompt, submitting = false, onSubmitHitlResponse }: HitlPromptFormProps) {
  const [hitlDraft, setHitlDraft] = useState('')
  const [selectedToolCallId, setSelectedToolCallId] = useState<string | null>(null)
  const hitlPromptKey = `${prompt.phaseName ?? ''}:${prompt.checkpointId ?? ''}:${prompt.pendingToolCalls
    .map((toolCall) => toolCall.toolCallId)
    .join('|')}`

  useEffect(() => {
    setSelectedToolCallId(null)
    setHitlDraft('')
  }, [hitlPromptKey])

  const selectedPendingToolCall = prompt.pendingToolCalls.find((toolCall) => toolCall.toolCallId === selectedToolCallId) ?? null
  const activeToolCallId = effectiveToolCallId(prompt, selectedToolCallId)
  const activeHitlOptions = selectedPendingToolCall?.options ?? prompt.options
  const mustSelectToolCall = needsToolCallSelection(prompt, selectedToolCallId)

  const submitHitlResponse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const request = buildHitlResumeRequest({ prompt, draft: hitlDraft, selectedToolCallId })
    if (!request) return
    onSubmitHitlResponse?.(request)
  }

  return (
    <form className="space-y-3 rounded-md border border-border bg-muted/30 p-3" onSubmit={submitHitlResponse}>
      <div className="space-y-1">
        <div className="text-xs font-semibold uppercase text-muted-foreground">Human input required</div>
        <div className="text-sm font-medium text-foreground">{prompt.question}</div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {prompt.phaseName ? <span>{prompt.phaseName}</span> : null}
          {(activeToolCallId ?? prompt.toolCallId) ? <span>{activeToolCallId ?? prompt.toolCallId}</span> : null}
          {prompt.checkpointId ? <span>{prompt.checkpointId}</span> : null}
        </div>
      </div>
      {prompt.pendingToolCalls.length > 1 ? (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Pending tool calls</div>
          <RadioGroup value={selectedToolCallId ?? ''} onValueChange={setSelectedToolCallId}>
            {prompt.pendingToolCalls.map((toolCall) => (
              <label
                key={toolCall.toolCallId}
                className="flex cursor-pointer items-start gap-2 rounded-md border border-border bg-card px-2 py-2 text-xs text-foreground"
              >
                <RadioGroupItem value={toolCall.toolCallId} />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{toolCall.question}</span>
                  <span className="block text-muted-foreground">{toolCall.toolCallId}</span>
                </span>
              </label>
            ))}
          </RadioGroup>
          {mustSelectToolCall ? (
            <div className="text-xs text-destructive">Select a pending tool call before submitting.</div>
          ) : null}
        </div>
      ) : null}
      {activeHitlOptions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {activeHitlOptions.map((option) => (
            <Button key={option} type="button" variant="outline" size="xs" onClick={() => setHitlDraft(option)}>
              {option}
            </Button>
          ))}
        </div>
      ) : null}
      <Textarea
        aria-label={`Human response for ${prompt.phaseName ?? 'paused run'}`}
        value={hitlDraft}
        onChange={(event) => setHitlDraft(event.target.value)}
        placeholder="Type the answer to resume this run"
      />
      <div className="flex justify-end">
        <Button
          type="submit"
          size="sm"
          disabled={!hitlDraft.trim() || mustSelectToolCall || submitting || !onSubmitHitlResponse}
        >
          {submitting ? 'Submitting' : 'Submit answer'}
        </Button>
      </div>
    </form>
  )
}
