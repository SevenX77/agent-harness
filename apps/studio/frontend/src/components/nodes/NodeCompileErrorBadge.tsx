import { AlertTriangle } from 'lucide-react'
import type { CompileError } from '@/api/types'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export type NodeCompileErrorScope = 'node' | 'boundary'

export function formatNodeCompileError(error: CompileError): string {
  const segments: string[] = []
  if (error.field) {
    segments.push(error.field)
  }
  if (typeof error.line === 'number') {
    segments.push(`L${error.line}`)
  }
  const locator = segments.join(' ')
  return locator ? `${locator} - ${error.message}` : error.message
}

interface NodeCompileErrorBadgeProps {
  errors: readonly CompileError[]
  scope: NodeCompileErrorScope
}

export function NodeCompileErrorBadge({ errors, scope }: NodeCompileErrorBadgeProps) {
  const count = errors.length
  if (count === 0) {
    return null
  }
  const noun = `compile error${count === 1 ? '' : 's'}`
  const summary = `${count} ${noun} on this ${scope}: ${errors.map(formatNodeCompileError).join('; ')}`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          aria-label={summary}
          data-node-compile-error-badge="true"
          className="inline-flex h-5 items-center gap-0.5 rounded-md border border-destructive/40 bg-destructive/10 px-1.5 text-[11px] font-medium leading-none text-destructive"
        >
          <AlertTriangle className="size-3" />
          {count}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        <div className="mb-1 font-medium">
          {count} {noun} on this {scope}
        </div>
        <ul className="space-y-0.5">
          {errors.map((error, index) => (
            <li key={`${error.field ?? scope}:${error.line ?? '?'}:${index}`}>
              {formatNodeCompileError(error)}
            </li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  )
}
