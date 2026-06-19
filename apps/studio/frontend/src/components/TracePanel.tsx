import type { CallbackEvent, EventEnvelope } from '../api/types'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { BadgeCheck, GitCompareArrows, Play } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { TraceFilter } from './trace/TraceFilter'
import { TraceSearchBar } from './trace/TraceSearchBar'
import { VirtualTraceList } from './trace/VirtualTraceList'
import { Button } from './ui/button'
import { RadioGroup, RadioGroupItem } from './ui/radio-group'
import { Textarea } from './ui/textarea'

export interface TraceHitlResumeRequest {
  content: string
  phaseName: string | null
  toolCallId: string | null
  checkpointId: string | null
  checkpointNs: string | null
}

interface PendingHitlPrompt {
  phaseName: string | null
  question: string
  options: string[]
  toolCallId: string | null
  pendingToolCalls: PendingHitlToolCall[]
  checkpointId: string | null
  checkpointNs: string | null
}

interface PendingHitlToolCall {
  toolCallId: string
  question: string
  options: string[]
}

interface TracePanelProps {
  traceLogs: EventEnvelope[]
  activePhase?: string | null
  selectedEventId?: string | null
  linkEnabled?: boolean
  onToggleLink?: (enabled: boolean) => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
  canCompare?: boolean
  compareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
  canResume?: boolean
  resumeLoading?: boolean
  onResume?: () => void
  hitlSubmitting?: boolean
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
}

function envelopePayload(event: EventEnvelope): CallbackEvent {
  return event.payload as CallbackEvent
}

function stringField(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function stringArrayField(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.trim() !== '') : []
}

function pendingToolCallsField(value: unknown): PendingHitlToolCall[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item): PendingHitlToolCall[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const toolCallId = stringField(record.id) ?? stringField(record.tool_call_id)
    if (!toolCallId) return []
    return [{
      toolCallId,
      question: stringField(record.question)
        ?? stringField(record.prompt)
        ?? stringField(record.message)
        ?? toolCallId,
      options: stringArrayField(record.options),
    }]
  })
}

function isHitlEvent(eventType: string, status: string | undefined): boolean {
  if (eventType === 'interrupted' || eventType === 'hitl' || eventType === 'human_input_required') return true
  if (eventType === 'pause' || eventType === 'paused') return true
  if (eventType.includes('hitl') || eventType.includes('interrupt')) return true
  return status === 'paused' || status === 'waiting_for_human'
}

function latestHitlPrompt(events: EventEnvelope[]): PendingHitlPrompt | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const payload = envelopePayload(event)
    const eventType = event.event_type || payload.event_type || ''
    if (!isHitlEvent(eventType, payload.status)) continue
    const toolCallId = stringField(payload.tool_call_id) ?? stringField(payload.pending_tool_call_id)
    const pendingToolCalls = pendingToolCallsField(payload.pending_tool_calls)
    return {
      phaseName: payload.phase_name ?? payload.current_phase ?? null,
      question: stringField(payload.question)
        ?? stringField(payload.prompt)
        ?? stringField(payload.message)
        ?? 'Run paused for human input.',
      options: stringArrayField(payload.options),
      toolCallId,
      pendingToolCalls: pendingToolCalls.length > 0
        ? pendingToolCalls
        : toolCallId
          ? [{
              toolCallId,
              question: stringField(payload.question)
                ?? stringField(payload.prompt)
                ?? stringField(payload.message)
                ?? toolCallId,
              options: stringArrayField(payload.options),
            }]
          : [],
      checkpointId: stringField(payload.checkpoint_id),
      checkpointNs: stringField(payload.checkpoint_ns),
    }
  }
  return null
}

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedEventId = null,
  linkEnabled = true,
  onToggleLink,
  onSelectPrompt,
  onSelectEvent,
  canCompare = false,
  compareLoading = false,
  onCompareToGolden,
  onPromoteToGolden,
  canResume = false,
  resumeLoading = false,
  onResume,
  hitlSubmitting = false,
  onSubmitHitlResponse,
}: TracePanelProps) {
  const traceEvents = traceLogs.map(envelopePayload)
  const filter = useTraceFilter(traceEvents, linkEnabled ? activePhase : null)
  const hitlPrompt = useMemo(() => latestHitlPrompt(traceLogs), [traceLogs])
  const [hitlDraft, setHitlDraft] = useState('')
  const [selectedToolCallId, setSelectedToolCallId] = useState<string | null>(null)
  const hitlPromptKey = hitlPrompt
    ? `${hitlPrompt.phaseName ?? ''}:${hitlPrompt.checkpointId ?? ''}:${hitlPrompt.pendingToolCalls.map((toolCall) => toolCall.toolCallId).join('|')}`
    : ''

  useEffect(() => {
    setSelectedToolCallId(null)
    setHitlDraft('')
  }, [hitlPromptKey])

  const selectedPendingToolCall = hitlPrompt?.pendingToolCalls.find((toolCall) => toolCall.toolCallId === selectedToolCallId) ?? null
  const effectiveToolCallId = hitlPrompt?.pendingToolCalls.length === 1
    ? hitlPrompt.pendingToolCalls[0].toolCallId
    : selectedToolCallId
  const activeHitlOptions = selectedPendingToolCall?.options ?? hitlPrompt?.options ?? []
  const needsToolCallSelection = Boolean(hitlPrompt && hitlPrompt.pendingToolCalls.length > 1 && !selectedToolCallId)

  const submitHitlResponse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const content = hitlDraft.trim()
    if (!hitlPrompt || !content || needsToolCallSelection) return
    onSubmitHitlResponse?.({
      content,
      phaseName: hitlPrompt.phaseName,
      toolCallId: effectiveToolCallId ?? hitlPrompt.toolCallId,
      checkpointId: hitlPrompt.checkpointId,
      checkpointNs: hitlPrompt.checkpointNs,
    })
  }

  if (traceEvents.length === 0) {
    return (
      <div
        role="log"
        aria-live="polite"
        aria-label="Trace Timeline"
        className="flex h-full items-center justify-center text-sm font-medium text-slate-400 dark:text-slate-500"
      >
        Waiting for run events
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Trace Timeline" className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-foreground">Trace Timeline</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Resume run from last checkpoint"
              title="Continue this run from its last checkpoint"
              disabled={!canResume || resumeLoading}
              onClick={onResume}
              className="flex items-center gap-1 rounded-md border border-emerald-200 px-2 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
            >
              <Play className="h-3.5 w-3.5" />
              {resumeLoading ? 'Resuming' : 'Resume'}
            </button>
            <button
              type="button"
              aria-label="Compare trace to golden baseline"
              disabled={!canCompare || compareLoading}
              onClick={onCompareToGolden}
              className="flex items-center gap-1 rounded-md border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-900 dark:text-sky-300 dark:hover:bg-sky-950/40"
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              {compareLoading ? 'Comparing' : 'Compare'}
            </button>
            <button
              type="button"
              aria-label="Promote run to golden baseline"
              disabled={!canCompare}
              onClick={onPromoteToGolden}
              className="flex items-center gap-1 rounded-md border border-amber-200 px-2 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/40"
            >
              <BadgeCheck className="h-3.5 w-3.5" />
              Golden
            </button>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
              <input
                type="checkbox"
                checked={linkEnabled}
                onChange={(event) => onToggleLink?.(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
              />
              Link views
            </label>
          </div>
        </div>
        <TraceSearchBar value={filter.searchTerm} onChange={filter.setSearchTerm} />
        <TraceFilter
          eventTypes={filter.eventTypes}
          phases={filter.phases}
          selectedTypes={filter.selectedTypes}
          selectedPhases={filter.selectedPhases}
          activePhase={activePhase}
          onToggleType={filter.toggleType}
          onTogglePhase={filter.togglePhase}
          onClear={filter.clearFilters}
        />
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          <span
            className="rounded-full border border-border bg-muted/40 px-2 py-0.5"
            title={
              linkEnabled && activePhase
                ? `Focused on node "${activePhase}" — showing this node's executions`
                : 'Whole-run trace — focus a node to narrow to its executions'
            }
          >
            {linkEnabled && activePhase ? `Focus: ${activePhase}` : 'Focus: whole run'}
          </span>
          <span>
            Showing {filter.filteredEvents.length} of {traceEvents.length} events
          </span>
        </div>
        {hitlPrompt ? (
          <form
            className="space-y-3 rounded-md border border-border bg-muted/30 p-3"
            onSubmit={submitHitlResponse}
          >
            <div className="space-y-1">
              <div className="text-xs font-semibold uppercase text-muted-foreground">Human input required</div>
              <div className="text-sm font-medium text-foreground">{hitlPrompt.question}</div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                {hitlPrompt.phaseName ? <span>{hitlPrompt.phaseName}</span> : null}
                {(effectiveToolCallId ?? hitlPrompt.toolCallId) ? <span>{effectiveToolCallId ?? hitlPrompt.toolCallId}</span> : null}
                {hitlPrompt.checkpointId ? <span>{hitlPrompt.checkpointId}</span> : null}
              </div>
            </div>
            {hitlPrompt.pendingToolCalls.length > 1 ? (
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Pending tool calls</div>
                <RadioGroup value={selectedToolCallId ?? ''} onValueChange={setSelectedToolCallId}>
                  {hitlPrompt.pendingToolCalls.map((toolCall) => (
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
                {needsToolCallSelection ? (
                  <div className="text-xs text-destructive">Select a pending tool call before submitting.</div>
                ) : null}
              </div>
            ) : null}
            {activeHitlOptions.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {activeHitlOptions.map((option) => (
                  <Button
                    key={option}
                    type="button"
                    variant="outline"
                    size="xs"
                    onClick={() => setHitlDraft(option)}
                  >
                    {option}
                  </Button>
                ))}
              </div>
            ) : null}
            <Textarea
              aria-label={`Human response for ${hitlPrompt.phaseName ?? 'paused run'}`}
              value={hitlDraft}
              onChange={(event) => setHitlDraft(event.target.value)}
              placeholder="Type the answer to resume this run"
            />
            <div className="flex justify-end">
              <Button
                type="submit"
                size="sm"
                disabled={!hitlDraft.trim() || needsToolCallSelection || hitlSubmitting || !onSubmitHitlResponse}
              >
                {hitlSubmitting ? 'Submitting' : 'Submit answer'}
              </Button>
            </div>
          </form>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 p-4">
        <VirtualTraceList
          events={filter.filteredEvents}
          activePhase={activePhase}
          selectedEventId={selectedEventId}
          linkEnabled={linkEnabled}
          onSelectPrompt={onSelectPrompt}
          onSelectEvent={onSelectEvent}
        />
      </div>
    </div>
  )
}
