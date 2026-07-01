import { UserCog } from 'lucide-react'
import type { CredentialsState, ModelGroup, RolesData } from '../../api/llm'
import { deriveCopilotDisplayRoles } from '../studio/settings/copilot/copilot-role-derivation'
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
const emptyCredentials: CredentialsState = { providers: [] }

/**
 * Filter the roles registry down to the active Copilot roles shown in Settings.
 * Labels come from the bound model group when available, so the composer menu
 * stays aligned with the Copilot settings cards.
 */
export function copilotRoleOptions(
  data: RolesData | null,
  modelGroups: ModelGroup[] = [],
  credentials: CredentialsState = emptyCredentials,
): CopilotRoleOption[] {
  if (!data) {
    return []
  }
  return deriveCopilotDisplayRoles(data, modelGroups, credentials)
    .filter((role) => Boolean(data.roles[role.id]))
    .map((role) => ({ role: role.id, label: role.title }))
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
