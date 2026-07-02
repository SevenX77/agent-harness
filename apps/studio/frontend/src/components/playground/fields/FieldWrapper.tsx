import type { ReactNode } from 'react'
import type { PlaygroundInputSpec } from '../../../hooks/useInputPlayground'

interface FieldWrapperProps {
  input: PlaygroundInputSpec
  error?: string
  children: ReactNode
}

export function FieldWrapper({ input, error, children }: FieldWrapperProps) {
  return (
    <label
      data-testid={`playground-field-${input.name}`}
      className="block rounded-md border border-border bg-card p-3"
    >
      <span className="mb-1 flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-foreground">{input.name}</span>
        <span className="font-mono text-xs text-muted-foreground">{input.type ?? 'str'}</span>
      </span>
      {input.description ? (
        <span className="mb-2 block text-xs text-muted-foreground">{input.description}</span>
      ) : null}
      {children}
      {error ? <span className="mt-1 block text-xs text-destructive">{error}</span> : null}
    </label>
  )
}
