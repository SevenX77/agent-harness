import { Check, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '../../ui/badge'
import { Button } from '../../ui/button'
import { Input } from '../../ui/input'

interface ToolsMultiSelectProps {
  selected: string[]
  options: string[]
  onChange: (tools: string[]) => void
}

export function ToolsMultiSelect({ selected, options, onChange }: ToolsMultiSelectProps) {
  const [customTool, setCustomTool] = useState('')
  const allOptions = Array.from(new Set([...selected, ...options])).sort()

  const toggle = (tool: string) => {
    onChange(selected.includes(tool) ? selected.filter((item) => item !== tool) : [...selected, tool])
  }

  return (
    <section className="space-y-2">
      <div className="text-xs font-semibold uppercase text-muted-foreground">Tools</div>
      <div className="flex flex-wrap gap-2">
        {allOptions.length === 0 ? (
          <span className="text-xs text-muted-foreground">No tools discovered in this skill.</span>
        ) : null}
        {allOptions.map((tool) => {
          const active = selected.includes(tool)
          return (
            <Button
              key={tool}
              type="button"
              onClick={() => toggle(tool)}
              variant={active ? 'default' : 'outline'}
              size="sm"
              className="rounded-full"
            >
              {active ? <Check className="h-3 w-3" /> : null}
              {tool}
            </Button>
          )
        })}
      </div>
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((tool) => (
            <Badge
              key={`selected-${tool}`}
              variant="outline"
              className="gap-1 font-mono"
            >
              {tool}
              <button
                type="button"
                onClick={() => toggle(tool)}
                aria-label={`Remove ${tool}`}
                className="rounded-sm text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
      <div className="flex gap-2">
        <Input
          value={customTool}
          onChange={(event) => setCustomTool(event.target.value)}
          placeholder="script.module.tool"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
          className="min-w-0 flex-1 font-mono"
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            const next = customTool.trim()
            if (!next || selected.includes(next)) {
              return
            }
            onChange([...selected, next])
            setCustomTool('')
          }}
        >
          <Plus className="h-3.5 w-3.5" />
          Add
        </Button>
      </div>
    </section>
  )
}
