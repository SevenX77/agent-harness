import React, { useEffect, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { ArrowUp, Bot, CircleAlert, Paperclip, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { getRegistry, type RegistryResponse, type RoleEntry } from '../../api/llm'
import { useCopilot } from '../../hooks/useCopilot'
import { useTemplates } from '../../hooks/useTemplates'
import type { CopilotMessage } from '../../types/copilot'
import { DiffBubble } from './diff-bubble'
import { ModelPicker } from './model-picker'
import { ToolCallBubble } from './tool-call-bubble'

interface ChatMessageItemProps {
  message: CopilotMessage
}

function ChatMessageItemBase({ message }: ChatMessageItemProps) {
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
  view?: 'edit' | 'eval'
}

export function CopilotPanel({ skillId, view = 'edit' }: CopilotPanelProps) {
  const [draft, setDraft] = useState('')
  const [roleData, setRoleData] = useState<RoleEntry | null>(null)
  const [registry, setRegistry] = useState<RegistryResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const { templates, templatesLoading } = useTemplates()
  const copilot = useCopilot(skillId)
  const inEvalView = view === 'eval'

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
        setSelectedRouteId(role?.fallback_chain[0]?.route_id ?? '')
      })
      .catch(() => {
        toast.error('Copilot route config unavailable')
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
    if (copilot.sendMessage(draft, selectedRouteId || roleData?.fallback_chain[0]?.route_id || null)) {
      setDraft('')
    }
  }

  return (
    <aside className="z-copilot flex h-full min-h-0 flex-col bg-sidebar text-sidebar-foreground">
      <header className="border-b border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-primary" />
          <h2 className="text-sm font-semibold">Copilot</h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {copilot.connectionStatus}
          {copilot.reconnectInMs ? `, retry ${Math.round(copilot.reconnectInMs / 1000)}s` : ''}
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {copilot.messages.length > 0 ? (
          copilot.messages.map((message) => <ChatMessageItem key={message.id} message={message} />)
        ) : (
          <div className="rounded-md border border-dashed border-sidebar-border p-3 text-sm text-muted-foreground">
            <div className="prose prose-sm max-w-none text-muted-foreground dark:prose-invert">
              <ReactMarkdown>
                {skillId
                  ? inEvalView
                    ? '**Copilot Judge**\n\nAsk me to review the current artifact and golden diff. I use the Eval context endpoint, not a separate judge backend.'
                    : 'Ask about this skill, workflow, or current screen. General questions are allowed.'
                  : '**Create a skill with Copilot**\n\nUse Templates as a scaffold, or describe the Skill you want me to help create.'}
              </ReactMarkdown>
            </div>
            {inEvalView ? (
              <button
                type="button"
                onClick={() => setDraft('Judge the current Eval diff. Explain the likely cause, risk, and whether this should become a new golden baseline.')}
                className="mt-3 w-full rounded-md border border-sidebar-border bg-background px-2 py-1.5 text-start text-xs font-medium text-foreground hover:bg-accent"
              >
                Ask Copilot Judge
              </button>
            ) : null}
            {!skillId ? (
              <div className="mt-3 space-y-2">
                <button
                  type="button"
                  onClick={() => setDraft('Help me create a new Skill. Ask clarifying questions, then propose a minimal skill.md.')}
                  className="w-full rounded-md border border-sidebar-border bg-background px-2 py-1.5 text-start text-xs font-medium text-foreground hover:bg-accent"
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
                        className="rounded-md border border-sidebar-border bg-background px-2 py-1 text-xs text-foreground hover:bg-accent"
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

      <form onSubmit={submit} className="p-3 shrink-0">
        <div className="flex flex-col gap-2 rounded-md border border-transparent bg-sidebar-accent/60 px-2.5 py-2 transition-colors focus-within:border-border">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={1}
            className="min-h-[20px] max-h-[160px] w-full resize-none overflow-y-auto bg-transparent text-xs leading-relaxed outline-none field-sizing-content placeholder:text-muted-foreground"
            placeholder="Use '@' to mention nodes..."
          />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                aria-label="Attach file"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <Paperclip className="size-3.5" />
              </button>
              <button
                type="button"
                aria-label="Add context"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <Plus className="size-3.5" />
              </button>
              <ModelPicker
                role={roleData}
                registry={registry}
                selectedRouteId={selectedRouteId || roleData?.fallback_chain[0]?.route_id || ''}
                onSelect={selectRoute}
              />
            </div>
            <button
              type="submit"
              disabled={!draft.trim() || copilot.connectionStatus !== 'open'}
              aria-label="Send message"
              className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                draft.trim() && copilot.connectionStatus === 'open'
                  ? 'bg-primary text-primary-foreground hover:bg-primary/80'
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
