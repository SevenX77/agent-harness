import { useState, type FormEvent } from 'react'
import { putCopilotCredentials, type CopilotCredentials } from '../../api/copilot'
import type { CopilotBackend } from '../../types/copilot'

interface CopilotSettingsProps {
  credentials: CopilotCredentials | null
  backend: CopilotBackend
  onUpdated: (credentials: CopilotCredentials) => void
}

const providerIdByBackend: Record<CopilotBackend, string> = {
  claude: 'default-claude',
  deepseek: 'default-deepseek',
  gemini: 'default-gemini',
  openai: 'default-openai',
}

export function CopilotSettings({ credentials, backend, onUpdated }: CopilotSettingsProps) {
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const providerId = providerIdByBackend[backend]
  const configured = Boolean(credentials?.providers.find((provider) => provider.id === providerId)?.api_key)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!apiKey.trim()) {
      return
    }
    setSaving(true)
    setMessage('Saving...')
    try {
      if (!credentials) return
      const next = {
        ...credentials,
        active_provider_id: providerId,
        providers: credentials.providers.map((provider) =>
          provider.id === providerId ? { ...provider, api_key: apiKey.trim() } : provider,
        ),
      }
      await putCopilotCredentials(next)
      onUpdated(next)
      setApiKey('')
      setMessage('Saved')
    } catch {
      setMessage('Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <label className="block text-xs font-medium text-muted-foreground">
        {backend} API key {configured ? '(configured)' : ''}
        <input
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          type="password"
          placeholder="Paste a key to update"
          className="mt-1 h-8 w-full rounded-md border border-sidebar-border bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
        />
      </label>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{message}</span>
        <button
          type="submit"
          disabled={saving || !apiKey.trim()}
          className="h-7 rounded-md bg-primary px-2 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-45"
        >
          Save
        </button>
      </div>
    </form>
  )
}
