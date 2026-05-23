import { useEffect, useMemo } from 'react'
import { Cpu } from 'lucide-react'
import type { CredentialsState, RoleEntry } from '../../api/llm'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'

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
    const available = providers.some((providerCode) => Boolean(credentialsByProvider.get(providerCode)?.api_key.trim()))
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
        <Button
          key={option.modelCode}
          type="button"
          disabled={!option.available}
          variant={selectedModel === option.modelCode ? 'default' : 'ghost'}
          size="sm"
          title={option.available ? `Use ${option.modelCode}` : option.unavailableReason}
          aria-label={`Select model ${option.modelCode}`}
          onClick={option.available ? () => {
            onSelect(option.modelCode)
            onClose?.()
          } : undefined}
          className={`h-7 w-full justify-between px-2 text-left ${
            selectedModel === option.modelCode
              ? 'bg-primary text-primary-foreground'
              : 'text-foreground hover:bg-accent'
          } disabled:cursor-not-allowed disabled:opacity-45`}
        >
          <span>{option.modelCode}</span>
          {!option.available ? (
            <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">No key</span>
          ) : null}
        </Button>
      ))}
    </>
  )
}

function ModelPickerDropdownItems({ options, selectedModel, onSelect }: ModelPickerMenuProps) {
  return (
    <>
      {options.map((option) => (
        <DropdownMenuItem
          key={option.modelCode}
          disabled={!option.available}
          title={option.available ? `Use ${option.modelCode}` : option.unavailableReason}
          aria-label={`Select model ${option.modelCode}`}
          onSelect={() => onSelect(option.modelCode)}
          className={`justify-between ${
            selectedModel === option.modelCode ? 'bg-accent text-accent-foreground' : ''
          }`}
        >
          <span>{option.modelCode}</span>
          {!option.available ? (
            <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">No key</span>
          ) : null}
        </DropdownMenuItem>
      ))}
    </>
  )
}

export function ModelPicker({ role, credentials, selectedModel, onSelect, variant = 'icon' }: ModelPickerProps) {
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
      <Button
        type="button"
        disabled
        variant="ghost"
        size="icon"
        title="Copilot model config unavailable"
        aria-label="Select Copilot model"
        className="opacity-45"
      >
        <Cpu className="size-3.5" />
      </Button>
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
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          title={effectiveModel ? `Model: ${effectiveModel}` : 'Select model'}
          aria-label="Select Copilot model"
        >
          <Cpu className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-48">
        <DropdownMenuLabel>Model</DropdownMenuLabel>
        <ModelPickerDropdownItems
          options={options}
          selectedModel={effectiveModel}
          onSelect={onSelect}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
