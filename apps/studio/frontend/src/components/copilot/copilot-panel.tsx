import React, { useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { Bot, Loader2, Send } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useCopilot } from '../../hooks/useCopilot'
import type { CopilotMessage } from '../../types/copilot'

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
    </article>
  )
}

export const ChatMessageItem = React.memo(ChatMessageItemBase)

export function CopilotPanel() {
  const { skillId = null } = useParams()
  const [draft, setDraft] = useState('')
  const copilot = useCopilot(skillId)

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
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {copilot.messages.length > 0 ? (
          copilot.messages.map((message) => <ChatMessageItem key={message.id} message={message} />)
        ) : (
          <div className="rounded-md border border-dashed border-sidebar-border p-3 text-sm text-muted-foreground">
            Ask about this skill, workflow, or current screen. General questions are allowed.
          </div>
        )}
        {copilot.lastError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {copilot.lastError}
          </div>
        ) : null}
      </div>

      <form onSubmit={submit} className="border-t border-sidebar-border p-3">
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
