import type { CopilotBackend, CopilotCredentials } from '../../types/copilot'

interface ModelPickerProps {
  credentials: CopilotCredentials | null
  activeBackend: CopilotBackend
  onSelect: (backend: CopilotBackend) => void
}

const models: Array<{ id: CopilotBackend, label: string, v15?: boolean }> = [
  { id: 'claude', label: 'Claude' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'gemini', label: 'Gemini', v15: true },
  { id: 'openai', label: 'OpenAI', v15: true },
]

function isPlaceholder(credentials: CopilotCredentials | null, backend: CopilotBackend) {
  const status = credentials?.backends[backend]
  return Boolean(status?.V1_5_PLACEHOLDER || status?.v1_5_placeholder)
}

export function ModelPicker({ credentials, activeBackend, onSelect }: ModelPickerProps) {
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Copilot model picker">
      {models.map((model) => {
        const hasKey = Boolean(credentials?.backends[model.id]?.has_key)
        const disabled = model.v15 || !hasKey || isPlaceholder(credentials, model.id)
        return (
          <button
            key={model.id}
            type="button"
            disabled={disabled}
            title={disabled ? `${model.label} is unavailable in V1` : `Use ${model.label}`}
            onClick={() => onSelect(model.id)}
            className={`inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium ${
              activeBackend === model.id
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-sidebar-border bg-background text-foreground hover:bg-accent'
            } disabled:cursor-not-allowed disabled:opacity-45`}
          >
            {model.label}
            {model.v15 ? <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">V1.5</span> : null}
          </button>
        )
      })}
    </div>
  )
}
