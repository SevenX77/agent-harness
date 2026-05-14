import { useState } from 'react'
import { Cpu } from 'lucide-react'
import type { CopilotCredentials } from '../../api/copilot'
import type { CopilotBackend } from '../../types/copilot'

interface ModelPickerProps {
  credentials: CopilotCredentials | null
  activeBackend: CopilotBackend
  onSelect: (backend: CopilotBackend) => void
  variant?: 'icon' | 'full'
}

const models: Array<{ id: CopilotBackend, label: string, v15?: boolean }> = [
  { id: 'claude', label: 'Claude' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'gemini', label: 'Gemini', v15: true },
  { id: 'openai', label: 'OpenAI', v15: true },
]

const providerIdByBackend: Record<CopilotBackend, string> = {
  claude: 'default-claude',
  deepseek: 'default-deepseek',
  gemini: 'default-gemini',
  openai: 'default-openai',
}

function hasProviderKey(credentials: CopilotCredentials | null, backend: CopilotBackend) {
  const providerId = providerIdByBackend[backend]
  return Boolean(credentials?.providers.find((provider) => provider.id === providerId)?.api_key)
}

export function ModelPicker({ credentials, activeBackend, onSelect, variant = 'icon' }: ModelPickerProps) {
  const [open, setOpen] = useState(false)
  const activeModel = models.find((model) => model.id === activeBackend)

  if (variant === 'full') {
    return (
      <div className="flex flex-wrap gap-1.5" aria-label="Copilot model picker">
        {models.map((model) => {
          const hasKey = hasProviderKey(credentials, model.id)
          const disabled = model.v15 || !hasKey
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

  return (
    <div className="relative" aria-label="Copilot model picker">
      <button
        type="button"
        title={activeModel ? `Model: ${activeModel.label}` : 'Select model'}
        aria-label="Select Copilot model"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Cpu className="size-3.5" />
      </button>
      {open ? (
        <div className="absolute bottom-8 left-0 z-50 flex w-44 flex-col gap-1 rounded-md bg-popover p-1.5 text-popover-foreground shadow-md ring-1 ring-foreground/10">
          <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground">Model</div>
          {models.map((model) => {
            const hasKey = hasProviderKey(credentials, model.id)
            const disabled = model.v15 || !hasKey
            return (
              <button
                key={model.id}
                type="button"
                disabled={disabled}
                title={disabled ? `${model.label} is unavailable in V1` : `Use ${model.label}`}
                onClick={() => {
                  onSelect(model.id)
                  setOpen(false)
                }}
                className={`flex h-7 items-center justify-between rounded-sm px-2 text-left text-xs font-medium ${
                  activeBackend === model.id
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground hover:bg-accent'
                } disabled:cursor-not-allowed disabled:opacity-45`}
              >
                <span>{model.label}</span>
                {model.v15 ? <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">V1.5</span> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
