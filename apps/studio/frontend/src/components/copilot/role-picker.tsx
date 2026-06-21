import { UserCog } from 'lucide-react'
import type { RolesData } from '../../api/llm'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'

export interface CopilotRoleOption {
  role: string
  label: string
}

/** Default copilot role the composer falls back to when nothing is selected. */
export const DEFAULT_COPILOT_ROLE = 'copilot_chat'

/**
 * Filter the roles registry down to copilot-kind roles (each is its own model
 * group). Returns one option per role, labelled from its name (snake_case →
 * Title Case), mirroring the Copilot settings tab derivation.
 */
export function copilotRoleOptions(data: RolesData | null): CopilotRoleOption[] {
  if (!data) {
    return []
  }
  return Object.entries(data.roles)
    .filter(([, role]) => role.role_kind === 'copilot')
    .map(([role]) => ({ role, label: roleLabel(role) }))
}

function roleLabel(role: string): string {
  return role.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

interface RolePickerProps {
  options: CopilotRoleOption[]
  selectedRole: string
  onSelect: (role: string) => void
}

export function RolePicker({ options, selectedRole, onSelect }: RolePickerProps) {
  // Hide the picker entirely when there is nothing to choose between.
  if (options.length <= 1) {
    return null
  }

  const selectedLabel = options.find((option) => option.role === selectedRole)?.label ?? selectedRole

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          title={selectedRole ? `Role: ${selectedRole}` : 'Select copilot role'}
          aria-label="Select copilot role"
          className="h-7 gap-1 px-2 text-xs text-muted-foreground"
        >
          <UserCog className="size-3.5" />
          <span className="min-w-0 truncate">{selectedLabel}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuLabel>Copilot role</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem
            key={option.role}
            title={`Use ${option.role}`}
            aria-label={`Select role ${option.role}`}
            onSelect={() => onSelect(option.role)}
            className={`justify-between ${
              selectedRole === option.role ? 'bg-accent text-accent-foreground' : ''
            }`}
          >
            <span className="min-w-0 truncate">{option.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
