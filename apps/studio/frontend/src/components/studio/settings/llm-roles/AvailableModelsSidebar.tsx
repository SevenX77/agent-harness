import {
  memo,
  useCallback,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
} from "react"
import { Search, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { CredentialsState } from "@/api/llm"
import {
  canonicalAvailableModelId,
  modelSupportsThinking,
} from "../role-utils"
import { ThinkingBadge } from "./RoleBadges"
import { useLazyRenderCount } from "./useLazyRenderCount"

export interface AvailableModelProvider {
  id: string
  label: string
}

export interface AvailableModelEntry {
  id: string
  vendor: string
  providers: AvailableModelProvider[]
  thinking: boolean
}

export interface AvailableModelGroup {
  vendor: string
  models: AvailableModelEntry[]
}

const collapsedProviderLabelLimit = 2
const availableModelsInitialRenderCount = 24
const availableModelsRenderStep = 24

export function AvailableModelsSidebar({
  credentials,
  onModelDragEnd,
  onModelDragStart,
  onModelPointerDown,
}: {
  credentials: CredentialsState
  onModelDragEnd?: () => void
  onModelDragStart?: (modelId: string) => void
  onModelPointerDown?: (modelId: string, event: PointerEvent<HTMLButtonElement>) => void
}) {
  const [query, setQuery] = useState("")
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  const pointerSelectedModelRef = useRef<string | null>(null)
  const selectedModelIdRef = useRef<string | null>(null)
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null)
  const groups = useMemo(() => buildAvailableModelGroups(credentials), [credentials])
  const filteredGroups = useMemo(() => filterAvailableModelGroups(groups, query), [groups, query])
  const hasModels = filteredGroups.some((group) => group.models.length > 0)
  const filteredModelCount = filteredGroups.reduce((total, group) => total + group.models.length, 0)
  const {
    hasMore: hasMoreModels,
    sentinelRef: availableModelsSentinelRef,
    visibleCount: visibleModelCount,
  } = useLazyRenderCount({
    total: filteredModelCount,
    initialCount: availableModelsInitialRenderCount,
    step: availableModelsRenderStep,
    resetKey: query.trim().toLowerCase(),
  })
  const visibleGroups = useMemo(
    () => sliceAvailableModelGroups(filteredGroups, visibleModelCount),
    [filteredGroups, visibleModelCount],
  )
  const applySelectedModel = useCallback((modelId: string, button: HTMLButtonElement) => {
    const nextSelectedModelId = selectedModelIdRef.current === modelId ? null : modelId
    const previousButton = selectedButtonRef.current

    if (previousButton && previousButton !== button) {
      previousButton.removeAttribute("data-selected")
      previousButton.setAttribute("aria-pressed", "false")
    }

    if (nextSelectedModelId) {
      button.dataset.selected = "true"
      button.setAttribute("aria-pressed", "true")
      selectedButtonRef.current = button
    } else {
      button.removeAttribute("data-selected")
      button.setAttribute("aria-pressed", "false")
      selectedButtonRef.current = null
    }

    selectedModelIdRef.current = nextSelectedModelId
    setSelectedModelId(nextSelectedModelId)
  }, [])
  const handleModelPointerDown = useCallback((modelId: string, event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    onModelPointerDown?.(modelId, event)
    if (event.pointerType === "touch") return
    pointerSelectedModelRef.current = modelId
    applySelectedModel(modelId, event.currentTarget)
  }, [applySelectedModel, onModelPointerDown])
  const handleModelClick = useCallback((modelId: string, event: MouseEvent<HTMLButtonElement>) => {
    if (pointerSelectedModelRef.current === modelId) {
      pointerSelectedModelRef.current = null
      return
    }
    applySelectedModel(modelId, event.currentTarget)
  }, [applySelectedModel])
  const handleModelDragStart = useCallback((modelId: string) => {
    onModelDragStart?.(modelId)
  }, [onModelDragStart])
  const handleModelDragEnd = useCallback(() => {
    onModelDragEnd?.()
  }, [onModelDragEnd])
  const handleClearSearch = useCallback(() => {
    setQuery("")
    searchInputRef.current?.focus()
  }, [])

  return (
    <aside className="w-full min-w-0 overflow-hidden lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 w-full min-w-0 flex-col gap-3 overflow-hidden lg:h-full">
        <div className="w-full min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Available Models</h3>
            <Badge
              variant="secondary"
              data-available-model-count="true"
              aria-label={`${filteredModelCount} available model${filteredModelCount === 1 ? "" : "s"}`}
              className="h-5 px-1.5 text-[10px]"
            >
              {filteredModelCount}
            </Badge>
          </div>
          <InputGroup className="h-8">
            <InputGroupAddon align="inline-start" className="pl-2 pr-1">
              <Search data-role-icon="true" className="size-3.5 text-muted-foreground" />
            </InputGroupAddon>
            <InputGroupInput
              ref={searchInputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search available models"
              placeholder="Search models"
              className="h-full text-xs"
            />
            <InputGroupAddon align="inline-end" className="pl-1 pr-1">
              <InputGroupButton
                type="button"
                size="icon-xs"
                aria-label="Clear model search"
                aria-hidden={!query}
                disabled={!query}
                onClick={handleClearSearch}
                className={cn(
                  "text-muted-foreground transition-[background-color,color,opacity] hover:text-foreground disabled:pointer-events-none disabled:opacity-0",
                  query ? "opacity-100" : "opacity-0",
                )}
              >
                <X data-role-icon="true" className="size-3 text-muted-foreground" />
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        </div>

        <ScrollArea className="h-72 w-full min-w-0 max-w-full overflow-hidden lg:h-auto lg:min-h-0 lg:flex-1 [&_[data-slot=scroll-area-scrollbar]]:hidden [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!w-full">
          {hasModels ? (
            <div className="w-full min-w-0 max-w-full space-y-4 overflow-hidden" data-lazy-list="available-models">
              {visibleGroups.map((group) => (
                <section key={group.vendor} className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
                  <div className="text-[11px] font-medium uppercase text-muted-foreground">{group.vendor}</div>
                  <div className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
                    {group.models.map((model) => (
                      <AvailableModelCard
                        key={model.id}
                        model={model}
                        selected={selectedModelId === model.id}
                        onClickSelect={handleModelClick}
                        onPointerSelect={handleModelPointerDown}
                        onDragStart={() => handleModelDragStart(model.id)}
                        onDragEnd={handleModelDragEnd}
                      />
                    ))}
                  </div>
                </section>
              ))}
              {hasMoreModels ? (
                <div
                  ref={availableModelsSentinelRef}
                  data-lazy-sentinel="available-models"
                  className="h-px w-full"
                  aria-hidden="true"
                />
              ) : null}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
              No models found.
            </div>
          )}
        </ScrollArea>
      </div>
    </aside>
  )
}

function sliceAvailableModelGroups(
  groups: AvailableModelGroup[],
  visibleCount: number,
): AvailableModelGroup[] {
  let remaining = visibleCount
  const visibleGroups: AvailableModelGroup[] = []

  for (const group of groups) {
    if (remaining <= 0) break
    const models = group.models.slice(0, remaining)
    if (models.length) visibleGroups.push({ ...group, models })
    remaining -= models.length
  }

  return visibleGroups
}

const AvailableModelCard = memo(function AvailableModelCard({
  model,
  selected,
  onClickSelect,
  onPointerSelect,
  onDragStart,
  onDragEnd,
}: {
  model: AvailableModelEntry
  selected: boolean
  onClickSelect: (modelId: string, event: MouseEvent<HTMLButtonElement>) => void
  onPointerSelect: (modelId: string, event: PointerEvent<HTMLButtonElement>) => void
  onDragStart: () => void
  onDragEnd: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      data-available-model-drag-source="true"
      data-available-model-pointer-drag-source="true"
      data-model-id={model.id}
      data-selected={selected ? "true" : undefined}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onPointerDown={(event) => onPointerSelect(model.id, event)}
      onClick={(event) => onClickSelect(model.id, event)}
      className={cn(
        "block w-full max-w-full cursor-grab select-none transform-gpu overflow-hidden rounded-md bg-card p-2 text-left ring-inset ring-1 ring-foreground/10 transition-[background-color,box-shadow,transform] duration-75 ease-out hover:bg-muted/25 active:scale-[0.99] active:cursor-grabbing active:bg-muted/40 data-[selected=true]:bg-muted/30 data-[selected=true]:ring-2 data-[selected=true]:ring-primary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none",
      )}
    >
      <div className="grid min-w-0 gap-1">
        <div className="flex min-w-0 items-start gap-2">
          <div className="min-w-0 flex-1 break-words font-mono text-xs leading-snug text-foreground [overflow-wrap:anywhere]">
            {model.id}
          </div>
          {model.thinking ? <ThinkingBadge /> : null}
        </div>
        <ProviderLabelBadges providers={model.providers} expanded={selected} />
      </div>
    </button>
  )
})

function ProviderLabelBadges({
  providers,
  expanded,
}: {
  providers: AvailableModelProvider[]
  expanded: boolean
}) {
  if (!providers.length) {
    return <div className="text-[11px] text-muted-foreground">No provider label</div>
  }

  const visibleProviders = expanded ? providers : providers.slice(0, collapsedProviderLabelLimit)
  const hiddenProviderCount = expanded ? 0 : providers.length - visibleProviders.length

  return (
    <div className="flex min-w-0 max-w-full flex-wrap gap-1 overflow-hidden">
      {visibleProviders.map((provider) => (
        <Badge
          key={provider.id}
          variant="outline"
          data-available-model-provider-label="true"
          className={cn(
            "max-w-full shrink-0 justify-start border-border/70 bg-muted/20 px-1.5 font-sans text-[10px] text-muted-foreground",
            expanded ? "whitespace-normal [overflow-wrap:anywhere]" : "whitespace-nowrap",
          )}
        >
          <span>{provider.label}</span>
        </Badge>
      ))}
      {hiddenProviderCount > 0 ? (
        <Badge
          variant="outline"
          data-available-model-provider-overflow="true"
          aria-label={`${hiddenProviderCount} more providers`}
          className="shrink-0 border-border/70 bg-muted/20 px-1.5 font-sans text-[10px] text-muted-foreground"
        >
          +{hiddenProviderCount}
        </Badge>
      ) : null}
    </div>
  )
}

export function buildAvailableModelGroups(credentials: CredentialsState): AvailableModelGroup[] {
  const byModelId = new Map<string, AvailableModelEntry>()

  for (const provider of credentials.providers) {
    const providerLabel = provider.name.trim() || provider.id
    for (const model of provider.available_models ?? []) {
      const modelId = canonicalAvailableModelId(model.id, provider)
      if (!modelId) continue
      const vendor = inferModelVendor(modelId, provider)
      const existing = byModelId.get(modelId)
      const next = existing ?? {
        id: modelId,
        vendor,
        providers: [],
        thinking: false,
      }
      if (!next.providers.some((item) => item.id === provider.id)) {
        next.providers.push({ id: provider.id, label: providerLabel })
      }
      next.thinking = next.thinking || modelSupportsThinking(model)
      byModelId.set(modelId, next)
    }
  }

  const byVendor = new Map<string, AvailableModelEntry[]>()
  for (const model of [...byModelId.values()].sort(compareModelEntries)) {
    const models = byVendor.get(model.vendor) ?? []
    models.push(model)
    byVendor.set(model.vendor, models)
  }

  return [...byVendor.entries()]
    .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }))
    .map(([vendor, models]) => ({ vendor, models }))
}

export function filterAvailableModelGroups(
  groups: AvailableModelGroup[],
  query: string,
): AvailableModelGroup[] {
  const normalizedQuery = query.trim().toLowerCase()
  const compactQuery = compactSearchText(query)

  if (!normalizedQuery) return groups

  return groups
    .map((group) => {
      const vendorMatches = matchesSearchText(group.vendor, normalizedQuery, compactQuery)
      const models = group.models.filter((model) => (
        vendorMatches ||
        matchesSearchText(model.id, normalizedQuery, compactQuery) ||
        model.providers.some((provider) => matchesSearchText(provider.label, normalizedQuery, compactQuery))
      ))
      return { ...group, models }
    })
    .filter((group) => group.models.length > 0)
}

function matchesSearchText(value: string, normalizedQuery: string, compactQuery: string): boolean {
  const normalizedValue = value.toLowerCase()
  return (
    normalizedValue.includes(normalizedQuery) ||
    (compactQuery.length > 0 && compactSearchText(value).includes(compactQuery))
  )
}

function compactSearchText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "")
}

function compareModelEntries(left: AvailableModelEntry, right: AvailableModelEntry): number {
  const vendorCompare = left.vendor.localeCompare(right.vendor, undefined, { numeric: true, sensitivity: "base" })
  if (vendorCompare !== 0) return vendorCompare
  return left.id.localeCompare(right.id, undefined, { numeric: true, sensitivity: "base" })
}

function inferModelVendor(modelId: string, provider: CredentialsState["providers"][number]): string {
  const normalizedModelId = modelId.toLowerCase()
  const slashVendor = normalizedModelId.includes("/") ? normalizedModelId.split("/", 1)[0] : ""
  if (slashVendor && slashVendor !== "models") return normalizeVendor(slashVendor)

  if (normalizedModelId.startsWith("gpt-") || normalizedModelId.startsWith("o1") || normalizedModelId.startsWith("o3")) {
    return "openai"
  }
  if (normalizedModelId.startsWith("gemini-")) return "gemini"
  if (normalizedModelId.startsWith("deepseek-")) return "deepseek"
  if (normalizedModelId.startsWith("claude-")) return "anthropic"
  if (normalizedModelId.startsWith("doubao-")) return "ark"
  if (normalizedModelId.startsWith("qwen-")) return "qwen"

  return providerVendor(provider)
}

function providerVendor(provider: CredentialsState["providers"][number]): string {
  const haystack = `${provider.id} ${provider.name} ${provider.base_url ?? ""}`.toLowerCase()
  const knownVendors = [
    "openai",
    "gemini",
    "deepseek",
    "anthropic",
    "ark",
    "openrouter",
    "wavespeed",
    "qiniu",
    "onechats",
    "jiekou",
  ]
  return knownVendors.find((vendor) => haystack.includes(vendor)) ?? normalizeVendor(provider.name || provider.id)
}

function normalizeVendor(vendor: string): string {
  return vendor.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unknown"
}
