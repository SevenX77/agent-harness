import {
  memo,
  useCallback,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type MouseEvent,
  type PointerEvent,
} from "react"
import { Search, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tag } from "@/components/ui/tag"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { ModelGroup, ProviderUiState } from "@/api/llm"
import { ThinkingBadge } from "./RoleBadges"
import { useLazyRenderCount } from "./useLazyRenderCount"

export interface AvailableModelProvider {
  id: string
  label: string
  state: ProviderUiState
  detail?: string | null
  providerModelId: string
  retryAt?: string | null
}

export interface AvailableModelEntry {
  id: string
  label: string
  section: string
  providers: AvailableModelProvider[]
  thinking: boolean
}

export interface AvailableModelGroup {
  section: string
  models: AvailableModelEntry[]
}

const collapsedProviderLabelLimit = 2
const availableModelsInitialRenderCount = 24
const availableModelsRenderStep = 24

export function AvailableModelsSidebar({
  modelGroups,
  onModelPointerDown,
}: {
  modelGroups: ModelGroup[]
  onModelPointerDown?: (modelId: string, event: PointerEvent<HTMLButtonElement>) => void
}) {
  const [query, setQuery] = useState("")
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  const pointerSelectedModelRef = useRef<string | null>(null)
  const selectedModelIdRef = useRef<string | null>(null)
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null)
  const groups = useMemo(() => buildAvailableModelGroups(modelGroups), [modelGroups])
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
                <section key={group.section} className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
                  <div className="text-[11px] font-medium uppercase text-muted-foreground">{group.section}</div>
                  <div className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
                    {group.models.map((model) => (
                      <AvailableModelCard
                        key={model.id}
                        model={model}
                        selected={selectedModelId === model.id}
                        onClickSelect={handleModelClick}
                        onPointerSelect={handleModelPointerDown}
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
}: {
  model: AvailableModelEntry
  selected: boolean
  onClickSelect: (modelId: string, event: MouseEvent<HTMLButtonElement>) => void
  onPointerSelect: (modelId: string, event: PointerEvent<HTMLButtonElement>) => void
}) {
  return (
    <button
      type="button"
      draggable={false}
      aria-pressed={selected}
      data-available-model-drag-source="true"
      data-available-model-pointer-drag-source="true"
      data-available-model-native-dnd="off"
      data-model-id={model.id}
      data-selected={selected ? "true" : undefined}
      onPointerDown={(event) => onPointerSelect(model.id, event)}
      onClick={(event) => onClickSelect(model.id, event)}
      className={cn(
        "block w-full max-w-full cursor-grab select-none transform-gpu overflow-hidden rounded-md bg-card p-2 text-left ring-inset ring-1 ring-foreground/10 transition-[background-color,box-shadow,transform] duration-75 ease-out hover:bg-muted/25 active:scale-[0.99] active:cursor-grabbing active:bg-muted/40 data-[selected=true]:bg-muted/30 data-[selected=true]:ring-2 data-[selected=true]:ring-primary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none",
      )}
    >
      <div className="grid min-w-0 gap-1">
        <div className="flex min-w-0 items-start gap-2">
          <div
            data-available-model-title="true"
            className="min-w-0 flex-1 break-words text-xs font-medium leading-snug text-foreground [overflow-wrap:anywhere]"
          >
            {model.label}
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
  const hiddenProviders = expanded ? [] : providers.slice(visibleProviders.length)
  const hiddenProviderCount = hiddenProviders.length
  const hiddenProviderState = dominantProviderState(hiddenProviders)

  return (
    <div className="flex min-w-0 max-w-full flex-wrap gap-1 overflow-hidden">
      {visibleProviders.map((provider) => (
        <Tag
          key={provider.id}
          variant={providerStateTagVariant(provider.state)}
          size="xs"
          data-available-model-provider-label="true"
          data-provider-state={provider.state}
          aria-label={`${provider.label} ${providerStateLabel(provider.state)}`}
          className={cn(
            "max-w-full justify-start font-sans",
            expanded ? "whitespace-normal [overflow-wrap:anywhere]" : "whitespace-nowrap",
          )}
        >
          <span>{provider.label}</span>
        </Tag>
      ))}
      {hiddenProviderCount > 0 ? (
        <Tag
          variant={providerStateTagVariant(hiddenProviderState)}
          size="xs"
          data-available-model-provider-overflow="true"
          data-provider-state={hiddenProviderState}
          aria-label={`${hiddenProviderCount} more providers`}
          className="font-sans"
        >
          +{hiddenProviderCount}
        </Tag>
      ) : null}
    </div>
  )
}

export function buildAvailableModelGroups(modelGroups: ModelGroup[]): AvailableModelGroup[] {
  const models = modelGroups
    .map((group): AvailableModelEntry => {
      return {
        id: group.canonical_id,
        label: group.display_name || group.canonical_id,
        section: group.section_label || fallbackModelGroupSection(group),
        providers: group.provider_models
          .map((providerModel) => ({
            id: providerModel.route_id,
            label: providerModel.provider_label,
            state: providerModel.ui_state,
            detail: providerModel.ui_detail,
            providerModelId: providerModel.provider_model_id,
            retryAt: providerModel.retry_at,
          }))
          .sort(compareAvailableModelProviders),
        thinking: group.capability_summary.thinking === "supported" ||
          group.capability_summary.thinking === "mixed" ||
          group.provider_models.some((providerModel) => Boolean(
            providerModel.capabilities.thinking?.value ||
            providerModel.capabilities.reasoning?.value ||
            providerModel.capabilities.supports_thinking?.value,
          )),
      }
    })
    .sort(compareModelEntries)

  const bySection = new Map<string, AvailableModelEntry[]>()
  for (const model of models) {
    const sectionModels = bySection.get(model.section) ?? []
    sectionModels.push(model)
    bySection.set(model.section, sectionModels)
  }

  return [...bySection.entries()]
    .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }))
    .map(([section, sectionModels]) => ({ section, models: sectionModels }))
}

function fallbackModelGroupSection(group: ModelGroup): string {
  const haystack = [
    group.display_name,
    group.canonical_id,
    ...group.provider_models.flatMap((providerModel) => [
      providerModel.provider_label,
      providerModel.provider_model_id,
    ]),
  ].join(" ").toLowerCase()

  if (haystack.includes("anthropic") || haystack.includes("claude")) return "anthropic"
  if (haystack.includes("deepseek")) return "deepseek"
  if (haystack.includes("openai") || /\bgpt[-_\s.]?\d/.test(haystack)) return "openai"
  if (haystack.includes("gemini") || haystack.includes("antigravity") || /\baqa\b/.test(haystack)) return "gemini"
  if (haystack.includes("qwen") || haystack.includes("dashscope") || haystack.includes("alibaba")) return "qwen"
  if (haystack.includes("doubao") || haystack.includes("volcengine") || haystack.includes("ark")) return "ark"
  return group.canonical_id.split(/[-_.]/)[0] || "unknown"
}

export function filterAvailableModelGroups(
  groups: AvailableModelGroup[],
  query: string,
): AvailableModelGroup[] {
  const normalizedQuery = query.trim().toLowerCase()
  const compactQuery = compactSearchText(query)
  const queryTokens = searchTokens(query)

  if (!normalizedQuery) return groups

  return groups
    .map((group) => {
      const sectionMatches = matchesSearchText(group.section, normalizedQuery, compactQuery, queryTokens)
      const models = group.models.filter((model) => (
        sectionMatches ||
        matchesSearchText(model.label, normalizedQuery, compactQuery, queryTokens) ||
        matchesSearchText(model.id, normalizedQuery, compactQuery, queryTokens) ||
        model.providers.some((provider) => (
          matchesSearchText(provider.label, normalizedQuery, compactQuery, queryTokens) ||
          matchesSearchText(provider.id, normalizedQuery, compactQuery, queryTokens) ||
          matchesSearchText(provider.providerModelId, normalizedQuery, compactQuery, queryTokens)
        ))
      ))
      return { ...group, models }
    })
    .filter((group) => group.models.length > 0)
}

function matchesSearchText(
  value: string,
  normalizedQuery: string,
  compactQuery: string,
  queryTokens: string[],
): boolean {
  const normalizedValue = value.toLowerCase()
  const compactValue = compactSearchText(value)
  return (
    normalizedValue.includes(normalizedQuery) ||
    (compactQuery.length > 0 && compactValue.includes(compactQuery)) ||
    (queryTokens.length > 1 && queryTokens.every((token) => compactValue.includes(token)))
  )
}

function compactSearchText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "")
}

function searchTokens(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9.]+/g)
    .map(compactSearchText)
    .filter(Boolean)
}

function compareModelEntries(left: AvailableModelEntry, right: AvailableModelEntry): number {
  const sectionCompare = left.section.localeCompare(right.section, undefined, { numeric: true, sensitivity: "base" })
  if (sectionCompare !== 0) return sectionCompare
  const labelCompare = left.label.localeCompare(right.label, undefined, { numeric: true, sensitivity: "base" })
  if (labelCompare !== 0) return labelCompare
  return left.id.localeCompare(right.id, undefined, { numeric: true, sensitivity: "base" })
}

function compareAvailableModelProviders(
  left: AvailableModelProvider,
  right: AvailableModelProvider,
): number {
  const stateCompare = providerDisplayStatePriority(left.state) - providerDisplayStatePriority(right.state)
  if (stateCompare !== 0) return stateCompare
  const labelCompare = left.label.localeCompare(right.label, undefined, { numeric: true, sensitivity: "base" })
  if (labelCompare !== 0) return labelCompare
  return left.id.localeCompare(right.id, undefined, { numeric: true, sensitivity: "base" })
}

function providerDisplayStatePriority(state: ProviderUiState): number {
  if (state === "ready") return 0
  if (state === "untested") return 1
  if (state === "cooling_down") return 2
  if (state === "needs_setup") return 3
  return 4
}

function providerStateTagVariant(state: ProviderUiState): ComponentProps<typeof Tag>["variant"] {
  if (state === "ready") return "success"
  if (state === "needs_setup") return "destructive"
  if (state === "cooling_down") return "warning"
  return "muted"
}

function providerStateLabel(state: ProviderUiState): string {
  if (state === "ready") return "Ready"
  if (state === "cooling_down") return "Cooling Down"
  if (state === "needs_setup") return "Needs Setup"
  if (state === "off") return "Off"
  return "Untested"
}

function dominantProviderState(providers: AvailableModelProvider[]): ProviderUiState {
  return providers
    .map((provider) => provider.state)
    .sort((left, right) => providerStatePriority(left) - providerStatePriority(right))[0] ?? "untested"
}

function providerStatePriority(state: ProviderUiState): number {
  if (state === "needs_setup") return 0
  if (state === "cooling_down") return 1
  if (state === "off") return 2
  if (state === "untested") return 3
  return 4
}
