import { Input } from '../../ui/input'
import { Label } from '../../ui/label'

interface ModelOverrideFieldProps {
  value: string
  onChange: (value: string) => void
}

export function ModelOverrideField({ value, onChange }: ModelOverrideFieldProps) {
  return (
    <Label className="block space-y-1">
      <span className="block text-xs font-semibold uppercase text-muted-foreground">
        Model override
      </span>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Use role default"
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="none"
        className="font-mono"
      />
    </Label>
  )
}
