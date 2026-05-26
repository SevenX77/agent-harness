import { useEffect, useMemo } from 'react'
import { Route } from 'lucide-react'
import type { RegistryResponse, RoleEntry } from '../../api/llm'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'

interface ModelPickerProps {
  role: RoleEntry | null
  registry: RegistryResponse | null
  selectedRouteId: string
  onSelect: (routeId: string) => void
  variant?: 'icon' | 'full'
}

export interface RouteOption {
  routeId: string
  label: string
  available: boolean
  unavailableReason: string
}

const unavailableReason = 'Route is missing, disabled, or failed in the active registry'

export function getRouteOptions(role: RoleEntry | null, registry: RegistryResponse | null): RouteOption[] {
  if (!role) {
    return []
  }

  return (role.fallback_chain ?? []).map((entry) => {
    const route = registry?.provider_routes[entry.route_id] ?? null
    const available = Boolean(route && route.status !== 'disabled' && route.status !== 'failed')
    return {
      routeId: entry.route_id,
      label: route?.display_name ?? entry.route_id,
      available,
      unavailableReason,
    }
  })
}

export function firstAvailableRoute(options: RouteOption[]): string | null {
  return options.find((option) => option.available)?.routeId ?? null
}

interface ModelPickerMenuProps {
  options: RouteOption[]
  selectedRouteId: string
  onSelect: (routeId: string) => void
  onClose?: () => void
}

export function ModelPickerMenu({ options, selectedRouteId, onSelect, onClose }: ModelPickerMenuProps) {
  return (
    <>
      {options.map((option) => (
        <Button
          key={option.routeId}
          type="button"
          disabled={!option.available}
          variant={selectedRouteId === option.routeId ? 'default' : 'ghost'}
          size="sm"
          title={option.available ? `Use ${option.routeId}` : option.unavailableReason}
          aria-label={`Select route ${option.routeId}`}
          onClick={option.available ? () => {
            onSelect(option.routeId)
            onClose?.()
          } : undefined}
          className={`h-7 w-full justify-between px-2 text-left ${
            selectedRouteId === option.routeId
              ? 'bg-primary text-primary-foreground'
              : 'text-foreground hover:bg-accent'
          } disabled:cursor-not-allowed disabled:opacity-45`}
        >
          <span className="min-w-0 truncate">{option.routeId}</span>
          {!option.available ? (
            <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">Off</span>
          ) : null}
        </Button>
      ))}
    </>
  )
}

function ModelPickerDropdownItems({ options, selectedRouteId, onSelect }: ModelPickerMenuProps) {
  return (
    <>
      {options.map((option) => (
        <DropdownMenuItem
          key={option.routeId}
          disabled={!option.available}
          title={option.available ? `Use ${option.routeId}` : option.unavailableReason}
          aria-label={`Select route ${option.routeId}`}
          onSelect={() => onSelect(option.routeId)}
          className={`justify-between ${
            selectedRouteId === option.routeId ? 'bg-accent text-accent-foreground' : ''
          }`}
        >
          <span className="min-w-0 truncate">{option.routeId}</span>
          {!option.available ? (
            <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">Off</span>
          ) : null}
        </DropdownMenuItem>
      ))}
    </>
  )
}

export function ModelPicker({ role, registry, selectedRouteId, onSelect, variant = 'icon' }: ModelPickerProps) {
  const options = useMemo(() => getRouteOptions(role, registry), [registry, role])
  const fallbackRoute = firstAvailableRoute(options)
  const effectiveRouteId = selectedRouteId || role?.fallback_chain?.[0]?.route_id || ''

  useEffect(() => {
    if (!role || !effectiveRouteId || !fallbackRoute) {
      return
    }
    const current = options.find((option) => option.routeId === effectiveRouteId)
    if ((!current || !current.available) && fallbackRoute !== effectiveRouteId) {
      onSelect(fallbackRoute)
    }
  }, [effectiveRouteId, fallbackRoute, onSelect, options, role])

  if (!role) {
    return (
      <Button
        type="button"
        disabled
        variant="ghost"
        size="icon"
        title="Copilot route config unavailable"
        aria-label="Select Copilot route"
        className="opacity-45"
      >
        <Route className="size-3.5" />
      </Button>
    )
  }

  if (variant === 'full') {
    return (
      <div className="flex flex-wrap gap-1.5" aria-label="Copilot route picker">
        <ModelPickerMenu
          options={options}
          selectedRouteId={effectiveRouteId}
          onSelect={onSelect}
        />
      </div>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          title={effectiveRouteId ? `Route: ${effectiveRouteId}` : 'Select route'}
          aria-label="Select Copilot route"
        >
          <Route className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-64">
        <DropdownMenuLabel>Route</DropdownMenuLabel>
        <ModelPickerDropdownItems
          options={options}
          selectedRouteId={effectiveRouteId}
          onSelect={onSelect}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
