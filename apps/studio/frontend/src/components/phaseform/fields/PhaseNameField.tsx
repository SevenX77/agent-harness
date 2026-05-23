import type { PhaseMode } from '../../../hooks/usePhaseForm'
import { Input } from '../../ui/input'
import { Label } from '../../ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../ui/select'

interface PhaseNameFieldProps {
  name: string
  mode: PhaseMode
  error?: string
  onNameChange: (name: string) => void
  onModeChange: (mode: PhaseMode) => void
}

export function PhaseNameField({
  name,
  mode,
  error,
  onNameChange,
  onModeChange,
}: PhaseNameFieldProps) {
  return (
    <div className="grid grid-cols-[1fr_8rem] gap-3">
      <Label className="block space-y-1">
        <span className="block text-xs font-semibold uppercase text-muted-foreground">
          Phase name
        </span>
        <Input
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
          className="font-medium"
        />
        {error ? <span className="block text-xs text-destructive">{error}</span> : null}
      </Label>
      <Label className="block space-y-1">
        <span className="block text-xs font-semibold uppercase text-muted-foreground">
          Mode
        </span>
        <Select
          value={mode}
          onValueChange={(value) => onModeChange(value as PhaseMode)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="llm">llm</SelectItem>
            <SelectItem value="logic">logic</SelectItem>
          </SelectContent>
        </Select>
      </Label>
    </div>
  )
}
