import { useEffect, useMemo, useState } from 'react'
import { Cpu } from 'lucide-react'
import type { CredentialsState, RoleEntry } from '../../api/llm'

interface ModelPickerProps {
  role: RoleEntry | null
  credentials: CredentialsState | null
  selectedModel: string
  onSelect: (modelCode: string) => void
  variant?: 'icon' | 'full'
}

export interface ModelOption {
  modelCode: string
  providers: string[]
  available: boolean
  unavailableReason: string
}

const unavailableReason = 'No API key configured for any provider in this model'

export function getModelOptions(role: RoleEntry | null, credentials: CredentialsState | null): ModelOption[] {
  if (!role) {
    return []
  }

  const credentialsByProvider = new Map(
    (credentials?.providers ?? []).map((provider) => [provider.id, provider]),
  )

  return Object.entries(role.models).map(([modelCode, model]) => {
    const providers = model.providers ?? []
    const available = providers.some((providerCode) => credentialsByProvider.get(providerCode)?.has_key === true)
    return {
      modelCode,
      providers,
      available,
      unavailableReason,
    }
  })
}

export function firstAvailableModel(options: ModelOption[]): string | null {
  return options.find((option) => option.available)?.modelCode ?? null
}

interface ModelPickerMenuProps {
  options: ModelOption[]
  selectedModel: string
  onSelect: (modelCode: string) => void
  onClose?: () => void
}

export function ModelPickerMenu({ options, selectedModel, onSelect, onClose }: ModelPickerMenuProps) {
  return (
    <>
      {options.map((option) => (
        <button
          key={option.modelCode}
          type="button"
          disabled={!option.available}
          title={option.available ? `Use ${option.modelCode}` : option.unavailableReason}
          aria-label={`Select model ${option.modelCode}`}
          onClick={option.available ? () => {
            onSelect(option.modelCode)
            onClose?.()
          } : undefined}
          className={`flex h-7 items-center justify-between rounded-sm px-2 text-left text-xs font-medium ${
            selectedModel === option.modelCode
              ? 'bg-primary text-primary-foreground'
              : 'text-foreground hover:bg-accent'
          } disabled:cursor-not-allowed disabled:opacity-45`}
        >
          <span>{option.modelCode}</span>
          {!option.available ? (
            <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">No key</span>
          ) : null}
        </button>
      ))}
    </>
  )
}

export function ModelPicker({ role, credentials, selectedModel, onSelect, variant = 'icon' }: ModelPickerProps) {
  const [open, setOpen] = useState(false)
  const options = useMemo(() => getModelOptions(role, credentials), [credentials, role])
  const fallbackModel = firstAvailableModel(options)
  const effectiveModel = selectedModel || role?.active_model || ''

  useEffect(() => {
    if (!role || !effectiveModel || !fallbackModel) {
      return
    }
    const current = options.find((option) => option.modelCode === effectiveModel)
    if ((!current || !current.available) && fallbackModel !== effectiveModel) {
      onSelect(fallbackModel)
    }
  }, [effectiveModel, fallbackModel, onSelect, options, role])

  if (!role) {
    return (
      <button
        type="button"
        disabled
        title="Copilot model config unavailable"
        aria-label="Select Copilot model"
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground opacity-45"
      >
        <Cpu className="size-3.5" />
      </button>
    )
  }

  if (variant === 'full') {
    return (
      <div className="flex flex-wrap gap-1.5" aria-label="Copilot model picker">
        <ModelPickerMenu
          options={options}
          selectedModel={effectiveModel}
          onSelect={onSelect}
        />
      </div>
    )
  }

  return (
    <div className="relative" aria-label="Copilot model picker">
      <button
        type="button"
        title={effectiveModel ? `Model: ${effectiveModel}` : 'Select model'}
        aria-label="Select Copilot model"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Cpu className="size-3.5" />
      </button>
      {open ? (
        <div className="absolute bottom-8 left-0 z-50 flex w-48 flex-col gap-1 rounded-md bg-popover p-1.5 text-popover-foreground shadow-md ring-1 ring-foreground/10">
          <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground">Model</div>
          <ModelPickerMenu
            options={options}
            selectedModel={effectiveModel}
            onSelect={onSelect}
            onClose={() => setOpen(false)}
          />
        </div>
      ) : null}
    </div>
  )
}
