import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../ui/select'
import { Label } from '../../ui/label'

const LLM_ROLES = [
  'analyst',
  'planner',
  'critic',
  'writer',
  'reviewer',
  'researcher',
  'coder',
]
const DEFAULT_ROLE_VALUE = '__default__'

interface LlmRoleFieldProps {
  value: string
  onChange: (value: string) => void
}

export function LlmRoleField({ value, onChange }: LlmRoleFieldProps) {
  return (
    <Label className="block space-y-1">
      <span className="block text-xs font-semibold uppercase text-muted-foreground">
        LLM role
      </span>
      <Select
        value={value || DEFAULT_ROLE_VALUE}
        onValueChange={(nextValue) => onChange(nextValue === DEFAULT_ROLE_VALUE ? '' : nextValue)}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Default" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_ROLE_VALUE}>Default</SelectItem>
          {LLM_ROLES.map((role) => (
            <SelectItem key={role} value={role}>{role}</SelectItem>
          ))}
          {value && !LLM_ROLES.includes(value) ? <SelectItem value={value}>{value}</SelectItem> : null}
        </SelectContent>
      </Select>
    </Label>
  )
}
