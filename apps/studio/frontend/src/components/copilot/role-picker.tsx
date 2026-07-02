import { UserCog } from 'lucide-react'
import type { CredentialsState, ModelGroup, RoleRouteEntry, RolesData } from '../../api/llm'
import { deriveCopilotDisplayRoles } from '../studio/settings/copilot/copilot-role-derivation'
import { Button } from '../ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'

export interface CopilotRoleOption {
  /** UI role id: persisted yaml key, or the model-group canonical id for a floated built-in. */
  role: string
  label: string
  /** Fallback chain of the display role — the single route truth for the composer route picker. */
  fallbackChain: RoleRouteEntry[]
  /** False for a floated built-in that has not been materialized into the roles yaml yet. */
  persisted: boolean
  modelGroupId: string
}

const emptyCredentials: CredentialsState = { providers: [] }

/**
 * F3 sync contract (docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md):
 * the composer role menu is the SAME derivation as the Settings Copilot cards
 * (deriveCopilotDisplayRoles), narrowed to the roles that are actually usable
 * for chat — i.e. with a bound model group / non-empty fallback chain. Empty
 * drafts ("Drop model" cards) are not chat roles; floated built-ins ARE
 * offered and get materialized on first send (resolveCopilotSendRole).
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
    .filter((role) => (role.fallback_chain ?? []).length > 0)
    .map((role) => ({
      role: role.id,
      label: role.title,
      fallbackChain: role.fallback_chain ?? [],
      persisted: Boolean(data.roles[role.id]),
      modelGroupId: role.modelGroupId,
    }))
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
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Select copilot role"
              className="h-7 gap-1 px-2 text-xs text-muted-foreground"
            >
              <UserCog className="size-3.5" />
              <span className="min-w-0 truncate">{selectedLabel}</span>
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>{selectedRole ? `Role: ${selectedRole}` : 'Select copilot role'}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuLabel>Copilot role</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem
            key={option.role}
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
