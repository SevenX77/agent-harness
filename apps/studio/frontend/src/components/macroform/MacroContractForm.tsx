import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Textarea } from '../ui/textarea'
import { LlmRoleField } from '../phaseform/fields/LlmRoleField'
import type { GraphHeaderFormData } from './graph-header'

/**
 * GRAPH.md macro-contract form (n2 atom #22).
 *
 * Structured editing for the integral graph's global contract:
 * name / schema_version / llm_role / description (controlled scalar fields) and
 * a `phases` add/remove list. FROZEN: there is no `type` entry — node type is
 * decided by file name, so this form deliberately never renders a type/mode
 * control for the header.
 *
 * The component is presentational/controlled. The host (Workspace) splits the
 * save into two paths: scalar header fields are re-rendered into the GRAPH.md
 * frontmatter and written directly (onSaveHeader); phases changes flow through
 * the preserving serialize endpoint (onSavePhases).
 */
interface MacroContractFormProps {
  data: GraphHeaderFormData
  onChange: <Key extends keyof GraphHeaderFormData>(field: Key, value: GraphHeaderFormData[Key]) => void
  onSaveHeader: () => void
  onSavePhases: () => void
  saving?: boolean
}

export function MacroContractForm({
  data,
  onChange,
  onSaveHeader,
  onSavePhases,
  saving = false,
}: MacroContractFormProps) {
  const [newPhase, setNewPhase] = useState('')

  const addPhase = () => {
    const next = newPhase.trim()
    if (!next || data.phases.includes(next)) {
      return
    }
    onChange('phases', [...data.phases, next])
    setNewPhase('')
  }

  const removePhase = (phaseId: string) => {
    onChange('phases', data.phases.filter((item) => item !== phaseId))
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-[1fr_10rem] gap-3">
        <Label className="block space-y-1">
          <span className="block text-xs font-semibold uppercase text-muted-foreground">
            Name
          </span>
          <Input
            value={data.name}
            onChange={(event) => onChange('name', event.target.value)}
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="none"
            className="font-medium"
          />
        </Label>
        <Label className="block space-y-1">
          <span className="block text-xs font-semibold uppercase text-muted-foreground">
            Schema version
          </span>
          <Input
            value={data.schemaVersion}
            onChange={(event) => onChange('schemaVersion', event.target.value)}
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="none"
            className="font-mono"
          />
        </Label>
      </div>

      <LlmRoleField value={data.llmRole} onChange={(value) => onChange('llmRole', value)} />

      <Label className="block space-y-1">
        <span className="block text-xs font-semibold uppercase text-muted-foreground">
          Description
        </span>
        <Textarea
          value={data.description}
          onChange={(event) => onChange('description', event.target.value)}
          rows={Math.max(3, data.description.split('\n').length)}
          className="resize-y text-xs leading-5"
        />
      </Label>

      <div className="flex justify-end">
        <Button type="button" onClick={onSaveHeader} disabled={saving} size="sm">
          Save header
        </Button>
      </div>

      <section className="space-y-2 border-t border-border pt-4">
        <div className="text-xs font-semibold uppercase text-muted-foreground">Phases</div>
        <div className="flex flex-wrap gap-1.5">
          {data.phases.length === 0 ? (
            <span className="text-xs text-muted-foreground">No phases yet.</span>
          ) : null}
          {data.phases.map((phaseId) => (
            <Badge key={`phase-${phaseId}`} variant="outline" className="gap-1 font-mono">
              {phaseId}
              <button
                type="button"
                onClick={() => removePhase(phaseId)}
                title={`Remove ${phaseId}`}
                className="rounded-sm text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            value={newPhase}
            onChange={(event) => setNewPhase(event.target.value)}
            placeholder="phase-id"
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="none"
            className="min-w-0 flex-1 font-mono"
          />
          <Button type="button" variant="outline" onClick={addPhase}>
            <Plus className="h-3.5 w-3.5" />
            Add
          </Button>
        </div>
        <div className="flex justify-end">
          <Button type="button" onClick={onSavePhases} disabled={saving} size="sm" variant="outline">
            Save phases
          </Button>
        </div>
      </section>
    </div>
  )
}
