import React, { useEffect, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { Bot, CircleAlert, Loader2, Send } from 'lucide-react'
import { useLocation, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { getCopilotCredentials, updateCopilotCredentials } from '../../api/copilot'
import { useCopilot } from '../../hooks/useCopilot'
import { useTemplates } from '../../hooks/useTemplates'
import type { CopilotBackend, CopilotCredentials, CopilotMessage } from '../../types/copilot'
import { CopilotSettings } from './copilot-settings'
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

export function CopilotPanel() {
  const { skillId = null } = useParams()
  const location = useLocation()
  const [draft, setDraft] = useState('')
  const [credentials, setCredentials] = useState<CopilotCredentials | null>(null)
  const [activeBackend, setActiveBackend] = useState<CopilotBackend>('claude')
  const { templates, templatesLoading } = useTemplates()
  const copilot = useCopilot(skillId, activeBackend)
  const inEvalView = location.pathname.includes('/eval')

  useEffect(() => {
    let cancelled = false
    getCopilotCredentials()
      .then((next) => {
        if (cancelled) {
          return
        }
        setCredentials(next)
        setActiveBackend(next.active_backend)
      })
      .catch(() => {
        toast.error('Copilot credentials unavailable')
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function selectBackend(backend: CopilotBackend) {
    if (backend === activeBackend) {
      return
    }
    try {
      const next = await updateCopilotCredentials(backend, undefined, true)
      setCredentials(next)
      setActiveBackend(backend)
      copilot.setBackend(backend)
      toast.info('已切换模型, 聊天历史清空')
    } catch {
      toast.error('模型切换失败')
    }
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (copilot.sendMessage(draft)) {
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
        <div className="mt-3">
          <ModelPicker credentials={credentials} activeBackend={activeBackend} onSelect={selectBackend} />
        </div>
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

      <form onSubmit={submit} className="border-t border-sidebar-border p-3">
        <div className="mb-3">
          <CopilotSettings credentials={credentials} backend={activeBackend} onUpdated={setCredentials} />
        </div>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="h-20 w-full resize-none rounded-md border border-input bg-background p-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
          placeholder="Ask Copilot..."
        />
        <button
          type="submit"
          disabled={!draft.trim() || copilot.connectionStatus !== 'open'}
          className="mt-2 inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-45"
        >
          {copilot.connectionStatus === 'connecting' ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          Send
        </button>
      </form>
    </aside>
  )
}
