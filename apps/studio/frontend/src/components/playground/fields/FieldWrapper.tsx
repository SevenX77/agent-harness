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
      className="block rounded-md border border-gray-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
    >
      <span className="mb-1 flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">{input.name}</span>
        <span className="font-mono text-xs text-gray-400">{input.type ?? 'str'}</span>
      </span>
      {input.description ? (
        <span className="mb-2 block text-xs text-gray-500 dark:text-gray-400">{input.description}</span>
      ) : null}
      {children}
      {error ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{error}</span> : null}
    </label>
  )
}
