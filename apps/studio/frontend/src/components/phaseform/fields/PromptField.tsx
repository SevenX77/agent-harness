import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../../ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '../../ui/collapsible'
import { Textarea } from '../../ui/textarea'
import { PhaseTokenCounter } from './PhaseTokenCounter'

interface PromptFieldProps {
  label: string
  value: string
  error?: string
  onChange: (value: string) => void
}

export function PromptField({ label, value, error, onChange }: PromptFieldProps) {
  const [open, setOpen] = useState(true)

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border bg-background"
    >
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className="h-auto w-full justify-between px-3 py-2 text-start"
        >
          <span className="text-xs font-semibold uppercase text-muted-foreground">{label}</span>
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-2 border-t border-border p-3">
          <Textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            rows={Math.min(18, Math.max(6, value.split('\n').length + 2))}
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="none"
            className="min-h-32 resize-y font-mono text-xs leading-5"
          />
          <div className="flex items-center justify-between gap-3">
            <PhaseTokenCounter text={value} />
            {error ? <span className="text-xs text-destructive">{error}</span> : null}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
