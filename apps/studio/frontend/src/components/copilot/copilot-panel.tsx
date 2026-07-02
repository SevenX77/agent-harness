import React, { useCallback, useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { ArrowUp, Bot, CircleAlert, SquareTerminal } from 'lucide-react'
import { toast } from 'sonner'
import { prepareCopilotJudgeContext, type CopilotJudgeResponse } from '../../api/client'
import { getRegistry, getRoles, putRoles, type RegistryResponse, type RolesData } from '../../api/llm'
import { useCopilot, type CopilotJudgeContext } from '../../hooks/useCopilot'
import { resolveCopilotSendRole } from '../studio/settings/copilot/copilot-role-derivation'
import { useStudioEventStream } from '../../hooks/useStudioEventStream'
import { useTemplates } from '../../hooks/useTemplates'
import type { CopilotMessage } from '../../types/copilot'
import { openClaudeCode } from '../../lib/tauri'
import { Button } from '../ui/button'
import { Message, MessageContent } from '../ui/message'
import { Skeleton } from '../ui/skeleton'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '../ui/message-scroller'
import { BACKEND_UNAVAILABLE_MESSAGE, errorMessage } from '@/utils/errors'
import { AnalysisBar } from './analysis-bar'
import { BashApprovalCard } from './bash-approval-card'
import { DiffBubble } from './diff-bubble'
import { ModelPicker } from './model-picker'
import { PatchProposedBubble, type CopilotFileAction } from './patch-proposed-bubble'
import { RolePicker, copilotRoleOptions } from './role-picker'
import { SessionTabs } from './session-tabs'
import { ToolCallBubble } from './tool-call-bubble'
import { buildAssistantTranscript } from './transcript'

interface ChatMessageItemProps {
  message: CopilotMessage
  skillId: string | null
  workspaceRoot?: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

function ChatMessageItemBase({ message, skillId, workspaceRoot, onFileChanged }: ChatMessageItemProps) {
  const isUser = message.role === 'user'
  if (isUser) {
    return (
      <Message align="end" data-copilot-message-role="user">
        <MessageContent>
          <div className="max-w-[85%] self-end rounded-lg bg-muted px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>
        </MessageContent>
      </Message>
    )
  }
  const segments = buildAssistantTranscript(message)
  const streaming = message.status === 'running'
  // F6-7/F8: the wait shimmer covers everything up to the first VISIBLE
  // activity — the first thinking or answer token. context_resolved / tool
  // events alone don't clear it; once thinking streams, the live transcript
  // takes over as the waiting indicator.
  const waiting =
    streaming && !message.content && !message.events.some((event) => event.type === 'thinking_delta')
  return (
    <Message align="start" data-copilot-message-role="assistant">
      <MessageContent>
        {waiting ? <ThinkingRow /> : null}
        <div className="space-y-1.5">
          {segments.map((segment) => {
            if (segment.kind === 'text') {
              return (
                <div
                  key={segment.id}
                  className="prose prose-sm max-w-none text-sm leading-relaxed text-foreground dark:prose-invert prose-p:my-1.5 prose-li:my-0.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-pre:my-2"
                >
                  <ReactMarkdown>{segment.content}</ReactMarkdown>
                </div>
              )
            }
            if (segment.kind === 'thinking') {
              // F8: reasoning streams live — open while the turn is running so
              // the trace is visible as it arrives, collapsed once settled.
              return (
                <details
                  key={segment.id}
                  open={streaming}
                  className="border-l border-border/70 py-1 pl-3 text-xs text-muted-foreground"
                >
                  <summary className="cursor-pointer font-medium text-foreground">Thought</summary>
                  <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug">
                    {segment.content}
                  </pre>
                </details>
              )
            }
            const event = segment.event
            if (event.type === 'tool_use_start') {
              return <ToolCallBubble key={event.id} event={event} />
            }
            if (event.type === 'tool_use_result') {
              return (
                <div key={event.id}>
                  <ToolCallBubble event={event} />
                  <DiffBubble event={event} />
                </div>
              )
            }
            if (event.type === 'error') {
              return (
                <div key={event.id} className="border-l border-destructive/50 py-1 pl-3 text-xs text-destructive">
                  <div className="flex items-center gap-2 font-medium">
                    <CircleAlert className="size-3.5" />
                    Copilot error
                  </div>
                  <p className="mt-1 whitespace-pre-wrap leading-snug">{event.message}</p>
                </div>
              )
            }
            if (event.type === 'patch_proposed') {
              return (
                <PatchProposedBubble
                  key={event.id}
                  event={event}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onFileChanged={onFileChanged}
                />
              )
            }
            if (event.type === 'bash_approval_required') {
              return <BashApprovalCard key={event.id} event={event} skillId={skillId} />
            }
            if (event.type === 'context_resolved') {
              return (
                <details key={event.id} className="border-l border-border/70 py-1 pl-3 text-xs text-muted-foreground">
                  <summary className="cursor-pointer font-medium text-foreground">{event.summary}</summary>
                  <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug">
                    {event.detail}
                  </pre>
                </details>
              )
            }
            if (event.type === 'unknown') {
              return (
                <details key={event.id} className="border-l border-border/70 py-1 pl-3 text-xs text-muted-foreground">
                  <summary className="cursor-pointer font-medium text-foreground">Unknown Copilot event</summary>
                  <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug">
                    {JSON.stringify(event.payload, null, 2)}
                  </pre>
                </details>
              )
            }
            return null
          })}
        </div>
      </MessageContent>
    </Message>
  )
}

export const ChatMessageItem = React.memo(ChatMessageItemBase)

/** F6 R3/R4: visible wait for the first answer token (cold spawns take 10-30s).
 * shadcn `shimmer` utility — the official loading-text treatment. */
function ThinkingRow() {
  return (
    <div className="py-1 text-sm text-muted-foreground" data-copilot-thinking="true">
      <span className="shimmer">Thinking…</span>
    </div>
  )
}

interface CopilotPanelProps {
  skillId: string | null
  workspaceRoot?: string | null
  view?: 'edit' | 'eval'
  judgeRefs?: {
    runResultsRef: string
    baselineRef: string
  } | null
  // F7: id of the run that just finished (predict/run) — drives the analysis bar.
  completedRunId?: string | null
  onJudgePrepared?: (refs: CopilotJudgeResponse) => void
  // F5/DEF-025: a copilot edit hit disk — reload the editor buffer + recompile.
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

/** F6: Enter sends, Shift+Enter breaks the line, and an IME composition never sends. */
export function isComposerSendKey(event: {
  key: string
  shiftKey: boolean
  nativeEvent: { isComposing: boolean }
}): boolean {
  return event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing
}

export function copilotBackendErrorMessage(error: unknown, fallback: string): string {
  return errorMessage(error) === BACKEND_UNAVAILABLE_MESSAGE
    ? 'Copilot backend unavailable'
    : fallback
}

interface DraftJudgeContextScope {
  skillId: string | null
  view: 'edit' | 'eval'
  judgeRefs: {
    runResultsRef: string
    baselineRef: string
  } | null
}

function judgeContextMatchesScope(context: CopilotJudgeContext, scope?: DraftJudgeContextScope): boolean {
  if (!scope) {
    return true
  }
  if (!scope.skillId || scope.view !== 'eval' || !scope.judgeRefs) {
    return false
  }
  const skillPrefix = `${scope.skillId}/`
  return (
    context.baseline_ref === scope.judgeRefs.baselineRef
    && context.diff_summary.run_results_ref === scope.judgeRefs.runResultsRef
    && context.compare_result_ref.startsWith(skillPrefix)
    && context.judge_context_ref.startsWith(skillPrefix)
    && context.baseline_ref.startsWith(skillPrefix)
    && context.diff_summary.run_results_ref.startsWith(skillPrefix)
  )
}

export function nextDraftJudgeContext(
  nextDraft: string,
  context: CopilotJudgeContext | null,
  scope?: DraftJudgeContextScope,
): CopilotJudgeContext | null {
  if (!context) {
    return null
  }
  return nextDraft === buildCopilotJudgeDraft(context) && judgeContextMatchesScope(context, scope) ? context : null
}

export function CopilotPanel({
  skillId,
  workspaceRoot,
  view = 'edit',
  judgeRefs = null,
  completedRunId = null,
  onJudgePrepared,
  onFileChanged,
}: CopilotPanelProps) {
  const [draft, setDraft] = useState('')
  const [dismissedRunId, setDismissedRunId] = useState<string | null>(null)
  const [registry, setRegistry] = useState<RegistryResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  // R5-C: the role/route slot shows a skeleton until BOTH config fetches settle
  // (registry can take ~45s on cold probe). Settled = resolved OR failed — a
  // failed fetch must drop the skeleton (picker hides as before), never park it.
  const [registrySettled, setRegistrySettled] = useState(false)
  const [rolesSettled, setRolesSettled] = useState(false)
  const [selectedRole, setSelectedRole] = useState('')
  const [draftJudgeContext, setDraftJudgeContext] = useState<CopilotJudgeContext | null>(null)
  const [openingClaudeCode, setOpeningClaudeCode] = useState(false)
  const { templates, templatesLoading } = useTemplates()
  const copilot = useCopilot(skillId, workspaceRoot)
  const inEvalView = view === 'eval'
  const roleOptions = useMemo(
    () => copilotRoleOptions(rolesData, registry?.model_groups ?? []),
    [rolesData, registry],
  )
  const claudeCodeWorkspace = workspaceRoot?.trim() || null

  async function askCopilotJudge() {
    if (!skillId || !judgeRefs) {
      return
    }
    try {
      const refs = await prepareCopilotJudgeContext(skillId, judgeRefs)
      setDraft(buildCopilotJudgeDraft(refs))
      setDraftJudgeContext(refs)
      onJudgePrepared?.(refs)
    } catch (error) {
      toast.error(copilotBackendErrorMessage(error, 'Copilot Judge context unavailable'))
    }
  }

  function handleJudgePrepared(refs: CopilotJudgeResponse) {
    setDraft(buildCopilotJudgeDraft(refs))
    setDraftJudgeContext(refs)
    onJudgePrepared?.(refs)
  }

  useEffect(() => {
    setDraftJudgeContext((current) => nextDraftJudgeContext(draft, current, { skillId, view, judgeRefs }))
  }, [draft, skillId, view, judgeRefs])

  const refreshRegistry = useCallback(() => {
    getRegistry()
      .then((nextRegistry) => {
        setRegistry(nextRegistry)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot route config unavailable'))
      })
  }, [])

  const refreshRoles = useCallback(() => {
    getRoles()
      .then((nextRoles) => {
        setRolesData(nextRoles)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot roles unavailable'))
      })
  }, [])

  useStudioEventStream({
    onRegistryChanged: refreshRegistry,
    onRolesChanged: refreshRoles,
    onResync: () => {
      refreshRegistry()
      refreshRoles()
    },
  })

  useEffect(() => {
    let cancelled = false
    getRegistry()
      .then((nextRegistry) => {
        if (cancelled) {
          return
        }
        setRegistry(nextRegistry)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot route config unavailable'))
      })
      .finally(() => {
        if (!cancelled) {
          setRegistrySettled(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getRoles()
      .then((nextRoles) => {
        if (cancelled) {
          return
        }
        setRolesData(nextRoles)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot roles unavailable'))
      })
      .finally(() => {
        if (!cancelled) {
          setRolesSettled(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (roleOptions.length === 0) {
      return
    }
    if (roleOptions.some((option) => option.role === selectedRole)) {
      return
    }
    setSelectedRole(roleOptions[0].role)
  }, [roleOptions, selectedRole])

  // F3: the selected display role IS the single role/route truth for the
  // composer — same derivation Settings renders, never registry.roles.
  const selectedOption = roleOptions.find((option) => option.role === selectedRole) ?? roleOptions[0] ?? null
  const selectedRoleKey = selectedOption?.role ?? ''
  const defaultRouteId = selectedOption?.fallbackChain[0]?.route_id ?? ''
  const pickerRole = useMemo(
    () => (selectedOption ? { fallback_chain: selectedOption.fallbackChain } : null),
    [selectedOption],
  )

  useEffect(() => {
    setSelectedRouteId(defaultRouteId)
  }, [selectedRoleKey, defaultRouteId])

  function selectRoute(routeId: string) {
    if (routeId === selectedRouteId) {
      return
    }
    setSelectedRouteId(routeId)
    toast.info('Route switched. Future messages will use it.')
  }

  async function handleOpenClaudeCode() {
    setOpeningClaudeCode(true)
    try {
      await openClaudeCode(claudeCodeWorkspace)
    } finally {
      setOpeningClaudeCode(false)
    }
  }

  async function sendDraft() {
    if (!draft.trim() || copilot.connectionStatus !== 'open') {
      return
    }
    const activeJudgeContext = nextDraftJudgeContext(draft, draftJudgeContext, { skillId, view, judgeRefs })
    let roleKey = selectedOption?.role ?? null
    if (selectedOption && rolesData) {
      const resolution = resolveCopilotSendRole(rolesData, selectedOption, registry?.model_groups ?? [])
      roleKey = resolution.roleKey
      if (resolution.nextRoles) {
        // First use of a floated built-in materializes it (atom-56 ①) through
        // the same PUT path Settings uses, then the send carries the yaml key.
        try {
          const saved = await putRoles(resolution.nextRoles)
          setRolesData(saved)
          setSelectedRole(resolution.roleKey)
        } catch (error) {
          toast.error(copilotBackendErrorMessage(error, 'Copilot role could not be saved'))
          return
        }
      }
    }
    if (copilot.sendMessage(
      draft,
      selectedRouteId || defaultRouteId || null,
      roleKey,
      activeJudgeContext,
    )) {
      setDraft('')
      setDraftJudgeContext(null)
    }
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void sendDraft()
  }

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!isComposerSendKey(event)) {
      return
    }
    event.preventDefault()
    void sendDraft()
  }

  return (
    <aside className="studio-copilot-panel studio-canvas-panel z-copilot flex h-full min-h-0 flex-col border-l text-foreground">
      <header className="studio-canvas-panel-header border-b px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Bot className="size-4 shrink-0 text-[color:var(--studio-canvas-accent)]" />
            <h2 className="truncate text-sm font-semibold">Copilot</h2>
            {copilot.connectionStatus !== 'open' ? (
              <span className="inline-flex shrink-0 items-center rounded border border-destructive/40 bg-destructive/10 px-1.5 py-0.5 text-[0.625rem] text-muted-foreground">
                {copilot.connectionStatus}
                {copilot.reconnectInMs ? ` · retry ${Math.round(copilot.reconnectInMs / 1000)}s` : ''}
              </span>
            ) : null}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={openingClaudeCode || !claudeCodeWorkspace}
            aria-label="Open in Claude Code"
            onClick={() => {
              void handleOpenClaudeCode()
            }}
            className="studio-canvas-input-surface shrink-0"
          >
            <SquareTerminal data-icon="inline-start" />
            Open in Claude Code
          </Button>
        </div>
      </header>

      <SessionTabs
        sessions={copilot.sessions}
        activeSessionId={copilot.activeSessionId}
        onSwitch={copilot.switchSession}
        onNew={copilot.newSession}
        onClose={copilot.closeSession}
      />

      {inEvalView && judgeRefs ? (
        <div className="shrink-0 border-b px-3 py-2 [border-color:var(--studio-canvas-border-soft)]">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!skillId}
            onClick={() => {
              void askCopilotJudge()
            }}
            className="studio-canvas-input-surface w-full justify-start"
          >
            Ask Copilot Judge
          </Button>
        </div>
      ) : null}

      <MessageScrollerProvider autoScroll>
        <MessageScroller className="min-h-0 flex-1">
          <MessageScrollerViewport className="p-4">
            <MessageScrollerContent className="gap-3">
        {copilot.messages.length > 0 ? (
          <>
            {copilot.messages.map((message) => (
              <MessageScrollerItem key={message.id} messageId={message.id} scrollAnchor={message.role === 'user'}>
                <ChatMessageItem
                  message={message}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onFileChanged={onFileChanged}
                />
              </MessageScrollerItem>
            ))}
            {copilot.messages[copilot.messages.length - 1]?.role === 'user' ? (
              // Pre-event gap: the assistant message only exists once the first
              // ws event lands; until then the wait must still be visible.
              <MessageScrollerItem messageId="__thinking__">
                <ThinkingRow />
              </MessageScrollerItem>
            ) : null}
          </>
        ) : (
          <div className="studio-canvas-input-surface rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            <div className="prose prose-sm max-w-none text-muted-foreground dark:prose-invert">
              <ReactMarkdown>
                {skillId
                  ? inEvalView
                    ? '**Copilot Judge**\n\nAsk me to review the current artifact and golden diff. I use the Eval context endpoint, not a separate judge backend.'
                    : 'Ask about this skill, workflow, or current screen. General questions are allowed.'
                  : '**Create a skill with Copilot**\n\nUse Templates as a scaffold, or describe the Skill you want me to help create.'}
              </ReactMarkdown>
            </div>
            {!skillId ? (
              <div className="mt-3 space-y-2">
                <button
                  type="button"
                  onClick={() => setDraft('Help me create a new Skill. Ask clarifying questions, then propose a minimal skill.md.')}
                  className="studio-canvas-input-surface w-full rounded-md border px-2 py-1.5 text-start text-xs font-medium text-foreground hover:bg-muted"
                >
                  Describe my Skill
                </button>
                <div className="text-xs">
                  {templatesLoading ? 'Loading templates...' : 'Templates'}
                  <div className="mt-1 flex flex-wrap gap-1">
                    {templates.slice(0, 3).map((template) => (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => setDraft(`Use the "${template.name}" template as a scaffold and help me create a Skill.`)}
                        className="studio-canvas-input-surface rounded-md border px-2 py-1 text-xs text-foreground hover:bg-muted"
                      >
                        {template.name}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
        {copilot.lastError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {copilot.lastError}
          </div>
        ) : null}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      {skillId && completedRunId && completedRunId !== dismissedRunId ? (
        <div className="px-4 pt-1 shrink-0">
          <AnalysisBar
            skillId={skillId}
            runId={completedRunId}
            workspaceRoot={workspaceRoot}
            onJudgePrepared={handleJudgePrepared}
            onDismiss={() => setDismissedRunId(completedRunId)}
          />
        </div>
      ) : null}

      <form onSubmit={submit} className="shrink-0 space-y-1.5 px-4 pb-4 pt-2">
        <div className="studio-copilot-input studio-canvas-input-surface flex flex-col gap-1 rounded-md border px-2.5 py-2 transition-colors focus-within:[border-color:var(--studio-canvas-accent-muted)]">
          <textarea
            value={draft}
            onChange={(event) => {
              const nextDraft = event.target.value
              setDraft(nextDraft)
              setDraftJudgeContext((current) => nextDraftJudgeContext(nextDraft, current, { skillId, view, judgeRefs }))
            }}
            onKeyDown={handleComposerKeyDown}
            rows={3}
            className="min-h-[60px] max-h-[160px] w-full resize-none overflow-y-auto bg-transparent text-sm leading-relaxed outline-none field-sizing-content placeholder:text-muted-foreground"
            placeholder="Use '@' to mention nodes..."
          />
          {/* F6: inside the bordered box only the send action lives (stop joins it
              with F7-③ interrupt); every settings control sits BELOW the box. */}
          <div className="flex items-center justify-end">
            <button
              type="submit"
              disabled={!draft.trim() || copilot.connectionStatus !== 'open'}
              aria-label="Send message"
              className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                draft.trim() && copilot.connectionStatus === 'open'
                  ? 'bg-[color:var(--studio-canvas-accent)] text-primary-foreground hover:bg-primary/80'
                  : 'bg-secondary text-secondary-foreground'
              }`}
            >
              <ArrowUp className={`size-3.5 ${!draft.trim() ? 'text-muted-foreground' : ''}`} />
            </button>
          </div>
        </div>
        {/* F7 context actions (attach / @mention) join the left side of this row
            once they are functional — no dead placeholders. */}
        <div className="flex items-center justify-end gap-0.5">
          {registrySettled && rolesSettled ? (
            <>
              <ModelPicker
                role={pickerRole}
                registry={registry}
                selectedRouteId={selectedRouteId || defaultRouteId}
                onSelect={selectRoute}
              />
              <RolePicker
                options={roleOptions}
                selectedRole={selectedRoleKey}
                onSelect={setSelectedRole}
              />
            </>
          ) : (
            // R5-C: role/route slot placeholder while config loads (cold registry
            // probe can take ~45s) — shadcn Skeleton, sized like the picker chip.
            <Skeleton aria-label="Loading copilot roles" className="h-7 w-32 rounded-md" />
          )}
        </div>
      </form>
    </aside>
  )
}

export function buildCopilotJudgeDraft(refs: CopilotJudgeResponse): string {
  const contextJson = JSON.stringify(
    {
      compare_result_ref: refs.compare_result_ref,
      judge_context_ref: refs.judge_context_ref,
      baseline_ref: refs.baseline_ref,
      diff_summary: refs.diff_summary,
    },
    null,
    2,
  )
  return [
    'Judge the current Eval diff. Explain the likely cause, risk, and whether this should become a new golden baseline.',
    '',
    'Use this structured Copilot Judge context:',
    contextJson,
  ].join('\n')
}
