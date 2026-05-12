import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getCopilotCredentials, updateCopilotCredentials } from '../../api/copilot'
import type { CopilotBackend, CopilotCredentials } from '../../types/copilot'

const BACKENDS: Array<{ id: CopilotBackend; label: string; disabled?: boolean }> = [
  { id: 'claude', label: 'Claude' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'gemini', label: 'Gemini', disabled: true },
  { id: 'openai', label: 'OpenAI', disabled: true },
]

export function SettingsModal() {
  const [status, setStatus] = useState<CopilotCredentials | null>(null)
  const [activeBackend, setActiveBackend] = useState<CopilotBackend>('claude')
  const [apiKey, setApiKey] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    getCopilotCredentials()
      .then((credentials) => {
        if (cancelled) {
          return
        }
        setStatus(credentials)
        setActiveBackend(credentials.active_backend)
      })
      .catch(() => {
        if (!cancelled) {
          setMessage('Credentials status unavailable.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('Saving...')
    const credentials = await updateCopilotCredentials(activeBackend, apiKey || undefined, true)
    setStatus(credentials)
    setApiKey('')
    setMessage('Credentials saved through backend.')
  }

  return (
    <main className="min-h-screen bg-background p-6 text-foreground">
      <section className="mx-auto max-w-xl rounded-md border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase text-muted-foreground">Settings</p>
            <h1 className="mt-1 text-lg font-semibold">Copilot credentials</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              API keys are sent to the Python backend for storage. The frontend does not write credential files.
            </p>
          </div>
          <button
            type="button"
            className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Close
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <label className="block text-sm font-medium">
            Backend
            <select
              value={activeBackend}
              onChange={(event) => setActiveBackend(event.target.value as CopilotBackend)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
            >
              {BACKENDS.map((backend) => (
                <option key={backend.id} value={backend.id} disabled={backend.disabled}>
                  {backend.label}
                  {backend.disabled ? ' (V1.5)' : status?.backends?.[backend.id]?.has_key ? ' (configured)' : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-medium">
            API key
            <input
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              type="password"
              placeholder="Paste a key to update"
            />
          </label>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">{message}</p>
            <button
              type="submit"
              className="h-8 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              Save
            </button>
          </div>
        </form>
      </section>
    </main>
  )
}
