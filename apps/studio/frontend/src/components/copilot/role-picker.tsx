import { BrainCircuit, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CredentialsState, ModelGroup, RoleRouteEntry, RolesData } from '../../api/llm'
import { deriveCopilotDisplayRoles } from '../studio/settings/copilot/copilot-role-derivation'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
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
  /** Config still loading — show the fixed default anchor with a spinner instead
   *  of hiding the whole picker behind a skeleton block (R7-C, PM 2026-07-02). */
  loading?: boolean
}

/** R7-C: the fixed default label shown while roles load (PM 2026-08-06: deepseek-v4-flash). */
const LOADING_DEFAULT_LABEL = 'DeepSeek V4 Flash'

/**
 * The words the picker renders, in the reader's language.
 *
 * Props rather than a hook inside the view, for the same reason
 * `SessionTabsView` takes them: the view is a pure function of props and its
 * interaction test calls it as one.
 */
export interface RolePickerCopy {
  loading: string
  loadingTooltip: string
  loadingList: string
  label: string
  none: string
  addHint: string
  select: string
  current: (role: string) => string
  selectRole: (role: string) => string
}

export function RolePicker(props: RolePickerProps) {
  const { t } = useTranslation('copilot')
  const copy: RolePickerCopy = {
    loading: t('role.loading'),
    loadingTooltip: t('role.loadingTooltip'),
    loadingList: t('role.loadingList'),
    label: t('role.label'),
    none: t('role.none'),
    addHint: t('role.addHint'),
    select: t('role.select'),
    current: (role) => t('role.current', { role }),
    selectRole: (role) => t('role.selectRole', { role }),
  }
  return <RolePickerView {...props} copy={copy} />
}

/** Hook-free presentational picker — see `RolePickerCopy`. */
export function RolePickerView({
  options,
  selectedRole,
  onSelect,
  loading = false,
  copy,
}: RolePickerProps & { copy: RolePickerCopy }) {
  // R7-C (PM 2026-07-02): the picker anchor is ALWAYS present. While config loads
  // it shows the fixed default (opus4.8) with a spinning icon — the skeleton moves
  // INTO the dropdown options, not the trigger — so the selector never vanishes or
  // gets swapped out for a placeholder block.
  if (loading) {
    return (
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={copy.loading}
                className="h-7 gap-1 px-2 text-xs text-muted-foreground"
              >
                <Loader2 className="size-3.5 animate-spin" />
                <span className="min-w-0 truncate">{LOADING_DEFAULT_LABEL}</span>
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>{copy.loadingTooltip}</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="start" side="top" className="w-56">
          <DropdownMenuLabel>{copy.label}</DropdownMenuLabel>
          <div className="space-y-1.5 px-2 py-1.5" aria-label={copy.loadingList}>
            <Skeleton className="h-5 w-full rounded-sm" />
            <Skeleton className="h-5 w-3/4 rounded-sm" />
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }
  // R6-1 (PM 2026-07-02, overrides the old F6 "render nothing until there is a
  // role" rule): the model/role anchor is ALWAYS visible. Deleting roles down
  // to a single floated default used to make the whole selector vanish, which
  // read as "the model picker is gone". With zero roles we show an explicit
  // empty state; with one we still show the active role (no dropdown affordance
  // to switch, but the anchor never disappears).
  if (options.length === 0) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled
            aria-label={copy.none}
            className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          >
            <BrainCircuit className="size-3.5" />
            <span className="min-w-0 truncate">{copy.none}</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copy.addHint}</TooltipContent>
      </Tooltip>
    )
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
              aria-label={copy.select}
              className="h-7 gap-1 px-2 text-xs text-muted-foreground"
            >
              {/* R5-C: the picker chooses which model persona backs THIS chat —
                  a brain, not a user-settings gear (UserCog read as "配置用户"). */}
              <BrainCircuit className="size-3.5" />
              <span className="min-w-0 truncate">{selectedLabel}</span>
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>
          {selectedRole ? copy.current(selectedRole) : copy.select}
        </TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuLabel>{copy.label}</DropdownMenuLabel>
        {options.map((option) => (
          <DropdownMenuItem
            key={option.role}
            aria-label={copy.selectRole(option.role)}
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
