import React, { useEffect, useMemo, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { ArrowUp, Bot, CircleAlert, Paperclip, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { prepareCopilotJudgeContext, type CopilotJudgeResponse } from '../../api/client'
import { getRegistry, getRoles, type RegistryResponse, type RoleEntry, type RolesData } from '../../api/llm'
import { useCopilot, type CopilotJudgeContext } from '../../hooks/useCopilot'
import { useTemplates } from '../../hooks/useTemplates'
import type { CopilotMessage } from '../../types/copilot'
import { Button } from '../ui/button'
import { BACKEND_UNAVAILABLE_MESSAGE, errorMessage } from '@/utils/errors'
import { AnalysisBar } from './analysis-bar'
import { BashApprovalCard } from './bash-approval-card'
import { DiffBubble } from './diff-bubble'
import { ModelPicker } from './model-picker'
import { PatchProposedBubble, type CopilotFileAction } from './patch-proposed-bubble'
import { DEFAULT_COPILOT_ROLE, RolePicker, copilotRoleOptions } from './role-picker'
import { SessionTabs } from './session-tabs'
import { ToolCallBubble } from './tool-call-bubble'

interface ChatMessageItemProps {
  message: CopilotMessage
  skillId: string | null
  workspaceRoot?: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

function ChatMessageItemBase({ message, skillId, workspaceRoot, onFileChanged }: ChatMessageItemProps) {
  const isUser = message.role === 'user'
  return (
    <article className={`rounded-md border p-3 text-sm ${isUser ? 'border-primary/30 bg-primary/10' : 'border-border bg-background'}`}>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="font-medium">{isUser ? 'You' : 'Copilot'}</span>
        <span>{message.status}</span>
      </div>
      <div className="prose prose-sm max-w-none text-foreground dark:prose-invert">
        <ReactMarkdown>{message.content || (message.status === 'running' ? 'Thinking...' : '')}</ReactMarkdown>
      </div>
      {message.events.map((event) => {
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
            <div key={event.id} className="mt-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
              <div className="flex items-center gap-2 font-medium">
                <CircleAlert className="size-3.5" />
                Copilot error
              </div>
              <p className="mt-1 whitespace-pre-wrap">{event.message}</p>
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
            <details key={event.id} className="mt-2 rounded-md border border-border bg-muted/30 p-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">{event.summary}</summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background/70 p-2">
                {event.detail}
              </pre>
            </details>
          )
        }
        if (event.type === 'thinking_delta') {
          return (
            <details key={event.id} className="mt-2 rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">Thought</summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background/70 p-2">
                {event.content}
              </pre>
            </details>
          )
        }
        if (event.type === 'unknown') {
          return (
            <details key={event.id} className="mt-2 rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">Unknown Copilot event</summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background/70 p-2">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </details>
          )
        }
        return null
      })}
    </article>
  )
}

export const ChatMessageItem = React.memo(ChatMessageItemBase)

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
  const [roleData, setRoleData] = useState<RoleEntry | null>(null)
  const [registry, setRegistry] = useState<RegistryResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  const [selectedRole, setSelectedRole] = useState(DEFAULT_COPILOT_ROLE)
  const [draftJudgeContext, setDraftJudgeContext] = useState<CopilotJudgeContext | null>(null)
  const { templates, templatesLoading } = useTemplates()
  const copilot = useCopilot(skillId, workspaceRoot)
  const inEvalView = view === 'eval'
  const roleOptions = useMemo(() => copilotRoleOptions(rolesData), [rolesData])

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

  useEffect(() => {
    let cancelled = false
    getRegistry()
      .then((nextRegistry) => {
        if (cancelled) {
          return
        }
        const role = nextRegistry.roles.copilot_chat ?? null
        setRoleData(role)
        setRegistry(nextRegistry)
        setSelectedRouteId(role?.fallback_chain?.[0]?.route_id ?? '')
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot route config unavailable'))
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
        const options = copilotRoleOptions(nextRoles)
        // Keep the default when present; otherwise fall back to the first copilot role.
        if (!options.some((option) => option.role === DEFAULT_COPILOT_ROLE) && options[0]) {
          setSelectedRole(options[0].role)
        }
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot roles unavailable'))
      })
    return () => {
      cancelled = true
    }
  }, [])

  function selectRoute(routeId: string) {
    if (routeId === selectedRouteId) {
      return
    }
    setSelectedRouteId(routeId)
    toast.info('Route switched. Future messages will use it.')
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const activeJudgeContext = nextDraftJudgeContext(draft, draftJudgeContext, { skillId, view, judgeRefs })
    if (copilot.sendMessage(
      draft,
      selectedRouteId || roleData?.fallback_chain?.[0]?.route_id || null,
      selectedRole || null,
      activeJudgeContext,
    )) {
      setDraft('')
      setDraftJudgeContext(null)
    }
  }

  return (
    <aside className="studio-copilot-panel studio-canvas-panel z-copilot flex h-full min-h-0 flex-col border-l text-foreground">
      <header className="studio-canvas-panel-header border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-[color:var(--studio-canvas-accent)]" />
          <h2 className="text-sm font-semibold">Copilot</h2>
        </div>
        <p className="mt-1 inline-flex rounded border border-border/60 bg-background/30 px-1.5 py-0.5 text-xs text-muted-foreground">
          {copilot.connectionStatus}
          {copilot.reconnectInMs ? `, retry ${Math.round(copilot.reconnectInMs / 1000)}s` : ''}
        </p>
      </header>

      <SessionTabs
        sessions={copilot.sessions}
        activeSessionId={copilot.activeSessionId}
        onSwitch={copilot.switchSession}
        onNew={copilot.newSession}
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

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {copilot.messages.length > 0 ? (
          copilot.messages.map((message) => (
            <ChatMessageItem
              key={message.id}
              message={message}
              skillId={skillId}
              workspaceRoot={workspaceRoot}
              onFileChanged={onFileChanged}
            />
          ))
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
      </div>

      {skillId && completedRunId && completedRunId !== dismissedRunId ? (
        <div className="px-3 pt-1 shrink-0">
          <AnalysisBar
            skillId={skillId}
            runId={completedRunId}
            workspaceRoot={workspaceRoot}
            onJudgePrepared={handleJudgePrepared}
            onDismiss={() => setDismissedRunId(completedRunId)}
          />
        </div>
      ) : null}

      <form onSubmit={submit} className="p-3 shrink-0">
        <div className="studio-copilot-input studio-canvas-input-surface flex flex-col gap-2 rounded-md border px-2.5 py-2 transition-colors focus-within:[border-color:var(--studio-canvas-accent-muted)]">
          <textarea
            value={draft}
            onChange={(event) => {
              const nextDraft = event.target.value
              setDraft(nextDraft)
              setDraftJudgeContext((current) => nextDraftJudgeContext(nextDraft, current, { skillId, view, judgeRefs }))
            }}
            rows={1}
            className="min-h-[20px] max-h-[160px] w-full resize-none overflow-y-auto bg-transparent text-xs leading-relaxed outline-none field-sizing-content placeholder:text-muted-foreground"
            placeholder="Use '@' to mention nodes..."
          />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                aria-label="Attach file"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
              >
                <Paperclip className="size-3.5" />
              </button>
              <button
                type="button"
                aria-label="Add context"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
              >
                <Plus className="size-3.5" />
              </button>
              <ModelPicker
                role={roleData}
                registry={registry}
                selectedRouteId={selectedRouteId || roleData?.fallback_chain?.[0]?.route_id || ''}
                onSelect={selectRoute}
              />
              <RolePicker
                options={roleOptions}
                selectedRole={selectedRole}
                onSelect={setSelectedRole}
              />
            </div>
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
