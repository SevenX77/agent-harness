import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from "react"
import useSWR from "swr"
import { AxiosError } from "axios"
import { AlertTriangle, ChevronsUpDown, CircleHelp, FlaskConical, FolderOpen, GitCompareArrows, Loader2, Pencil, Plus, Settings, Settings2, ShieldCheck, Trash2 } from "lucide-react"
import yaml from "js-yaml"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { LintError, ResumeValidityResponse, SkillDetail } from "@/api/types"
import { fieldErrorsByKey } from "@/components/studio/field-compile-errors"
import type { SkillGraphNodeData, SkillNodeStatus, SubagentRef } from "@/components/GraphCanvas"
import { isSafePhaseId } from "@/components/GraphCanvas/canvas-authoring"
import type { ResumeRunOptions } from "@/api/client"
import { isPathInsideWorkspaceRoot, subgraphPathFieldState, subgraphPathValueFromSelection } from "@/components/studio/subgraph-path"
import { nodeResumeOptionsFromValidity } from "@/components/studio/node-resume"
import { getChildGraphTopology, getCompareCandidates, getNodeLlmParams, putNodeCompareCandidates, putNodeLlmParams } from "@/api/client"
import type { CompareCandidate, NodeLlmParams } from "@/api/types"
import { getModelGroups, getRoles, startCompareCandidateTestJob, type ModelGroup, type ProviderModelOption, type RoleEntry, type RolesData, type RoleTestResponse, type RoleTestStatus } from "@/api/llm"
import { roleTokenLimitSummary } from "@/components/studio/settings/llm-roles/RoleCard"
import { selectSkillDirectory } from "@/lib/tauri"
import { sha256Hex } from "@/lib/hash"
import { cn } from "@/lib/utils"
import { errorMessage } from "@/utils/errors"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { runRoleTestJobToResult } from "../settings/llm-roles/role-test-store"
import { formatThousands, stripThousands } from "../settings/llm-roles/RoleSettingsDialog"
import { RoleRouteStatusLight, roleRouteStatusSurfaceClass, type RoleRouteStatus } from "../settings/llm-roles/role-route-status"
import type { SettingsTab } from "../SettingsPage"
import type { FileOpenInput } from "../file-types"
import { hashConflictPayloadFromSaveError } from "../save-conflicts"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelActions, PanelBody, PanelFieldRow } from "./_shared/PanelSection"
import { roleTestDetailsFromResult, roleTestStatusBadge, type RoleTestStatusInput } from "./role-test-status"
import {
  applyPhaseFrontmatterForm,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
  type IterateMergeMode,
  type IterateMode,
  type PhaseFrontmatter,
  type PhaseFrontmatterFormData,
  type PhaseFrontmatterKind,
  type PhaseIterateFormData,
  type PhaseResourceRef,
  type PhaseSubagentRef,
  type PhaseSubgraphRef,
} from "./phase-frontmatter"
import { actionFilePath, isValidActionName, readActionsList, scanActionFiles } from "./phase-actions"
import { validatorFilePath } from "./phase-validator"

// Node KIND is owned by the physical phase FILE (SKILL/LOGIC/SUBGRAPH.md) that
// exists in the phase directory - `data.mode` is derived from that file in
// build-nodes (phaseModeFromFiles), NOT from any author-writable `mode:`
// frontmatter field (the engine rejects that). This label and the file picker
// below therefore reflect the file on disk, never a settable mode property.
function phaseKindLabel(data: Pick<SkillGraphNodeData, "mode" | "subgraphPath">): "LOGIC" | "AGENT" | "SUBGRAPH" {
  if (data.subgraphPath || data.mode === "subgraph") return "SUBGRAPH"
  if (data.mode === "skill" || data.mode === "llm" || data.mode === "agent") return "AGENT"
  return "LOGIC"
}

function phaseKindFile(data: Pick<SkillGraphNodeData, "mode" | "subgraphPath">): "LOGIC.md" | "SKILL.md" | "SUBGRAPH.md" {
  const kind = phaseKindLabel(data)
  if (kind === "SUBGRAPH") return "SUBGRAPH.md"
  if (kind === "AGENT") return "SKILL.md"
  return "LOGIC.md"
}

// Node kind is derived from the phase FILE KIND, never a `mode:` frontmatter field.
function phaseFrontmatterKind(label: "LOGIC" | "AGENT" | "SUBGRAPH"): PhaseFrontmatterKind {
  if (label === "SUBGRAPH") return "subgraph"
  if (label === "AGENT") return "agent"
  return "logic"
}

const YAML_FIELD_LABEL_CLASS = "!text-sm !font-semibold !leading-5 !text-foreground/70"
const YAML_READONLY_VALUE_CLASS =
  "min-w-0 flex-1 cursor-default select-text truncate border-border/70 bg-secondary/25 font-mono text-xs text-foreground/80 focus-visible:border-input focus-visible:ring-0"
const PROPERTIES_AUTOSAVE_DELAY_MS = 300
const YAML_ICON_BUTTON_CLASS = "size-7 rounded-md bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-foreground"

interface AllowOverwriteCandidate {
  field: string
  upstreamPhaseIds: string[]
}

interface LlmCompareRouteOption {
  value: string
  label: string
  detail?: string
}

interface SearchableComboboxOption {
  value: string
  label: string
  section?: string
  searchValue?: string
  detail?: string
  unconfigured?: boolean
}

export function graphAgentRoleNamesForProperties(data: Pick<RolesData, "roles">): string[] {
  return Object.entries(data.roles)
    .filter(([, role]: [string, RoleEntry]) => role.role_kind !== "copilot")
    .map(([name]) => name)
    .sort((left, right) => left.localeCompare(right))
}

function modelGroupPickerLabel(group: ModelGroup): string {
  return group.display_name.trim() || group.canonical_id.trim()
}

function modelGroupSectionLabel(group: ModelGroup): string {
  const explicit = group.section_label?.trim()
  if (explicit) return explicit
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

export function compareModelGroupsForPicker(groups: readonly ModelGroup[]): ModelGroup[] {
  return [...groups]
    .filter((group) => {
      const id = group.canonical_id.trim()
      const label = modelGroupPickerLabel(group)
      const hasRoute = group.provider_models.some((model) => model.route_id.trim().length > 0)
      return Boolean(id && label && hasRoute)
    })
    .sort((left, right) => (
      modelGroupSectionLabel(left).localeCompare(modelGroupSectionLabel(right), undefined, { numeric: true, sensitivity: "base" })
      || modelGroupPickerLabel(left).localeCompare(modelGroupPickerLabel(right), undefined, { numeric: true, sensitivity: "base" })
    ))
}

export function modelGroupRouteOptions(group: ModelGroup | null): LlmCompareRouteOption[] {
  const seen = new Set<string>()
  const options: LlmCompareRouteOption[] = []
  for (const model of group?.provider_models ?? []) {
    const routeId = model.route_id.trim()
    if (!routeId || seen.has(routeId)) {
      continue
    }
    seen.add(routeId)
    const endpointId = model.endpoint_id?.trim()
    const providerLabel = model.provider_label.trim()
    const providerModelId = model.provider_model_id.trim()
    options.push({
      value: `route:${routeId}`,
      label: providerLabel || endpointId || routeId,
      detail: [
        endpointId ? `Endpoint: ${endpointId}` : null,
        providerModelId ? `Model: ${providerModelId}` : null,
        `Route: ${routeId}`,
      ].filter(Boolean).join("\n"),
    })
  }
  return options
}

function providerModelsByRouteId(modelGroups: readonly ModelGroup[]): Map<string, ModelGroup["provider_models"][number]> {
  const byRouteId = new Map<string, ModelGroup["provider_models"][number]>()
  for (const group of modelGroups) {
    for (const providerModel of group.provider_models) {
      byRouteId.set(providerModel.route_id, providerModel)
    }
  }
  return byRouteId
}

function routeOptionFromRouteId(
  routeId: string,
  providerModelByRouteId: ReadonlyMap<string, ModelGroup["provider_models"][number]>,
): LlmCompareRouteOption | null {
  const trimmedRouteId = routeId.replace(/^route:/, "").trim()
  if (!trimmedRouteId) return null
  const providerModel = providerModelByRouteId.get(trimmedRouteId)
  const endpointId = providerModel?.endpoint_id?.trim()
  const providerLabel = providerModel?.provider_label.trim()
  const providerModelId = providerModel?.provider_model_id.trim()
  return {
    value: `route:${trimmedRouteId}`,
    label: providerLabel || endpointId || trimmedRouteId,
    detail: [
      endpointId ? `Endpoint: ${endpointId}` : null,
      providerModelId ? `Model: ${providerModelId}` : null,
      `Route: ${trimmedRouteId}`,
    ].filter(Boolean).join("\n"),
  }
}

export function roleEndpointRouteOptions(
  role: RoleEntry | null | undefined,
  modelGroups: readonly ModelGroup[],
): LlmCompareRouteOption[] {
  const routeIds = role?.fallback_chain?.length
    ? role.fallback_chain.map((entry) => entry.route_id)
    : Object.values(role?.models ?? {}).flatMap((model) => model.providers)
  const providerModelByRouteId = providerModelsByRouteId(modelGroups)
  const seen = new Set<string>()
  const options: LlmCompareRouteOption[] = []
  for (const routeId of routeIds) {
    const option = routeOptionFromRouteId(routeId, providerModelByRouteId)
    if (!option || seen.has(option.value)) continue
    seen.add(option.value)
    options.push(option)
  }
  return options
}

function endpointComboboxOptions(options: readonly LlmCompareRouteOption[]): SearchableComboboxOption[] {
  return [
    { value: "auto", label: "Auto fallback", searchValue: "auto fallback" },
    ...options.map((option) => {
      const next: SearchableComboboxOption = {
        value: option.value,
        label: option.label,
        searchValue: [option.label, option.detail ?? "", option.value].join(" "),
      }
      if (option.detail) {
        next.detail = option.detail
      }
      return next
    }),
  ]
}

export function normalizeCompareSearch(value: string): string {
  return value.toLowerCase().replace(/[\s\-_.:/()]+/g, "")
}

export function llmCompareModelGroupSearchValue(group: ModelGroup): string {
  return [
    modelGroupPickerLabel(group),
    group.canonical_id,
    ...group.provider_models.flatMap((model) => [
      model.provider_label,
      model.provider_model_id,
      model.endpoint_id ?? "",
      model.route_id,
    ]),
  ].join(" ")
}

export function llmCompareModelGroupFilter(value: string, search: string): number {
  const tokens = search
    .split(/\s+/)
    .map((token) => normalizeCompareSearch(token))
    .filter(Boolean)
  if (tokens.length === 0) {
    return 1
  }
  const haystack = normalizeCompareSearch(value)
  return tokens.every((token) => haystack.includes(token)) ? 1 : 0
}

export function subagentSkillFilePath(skillId: string, subagent: SubagentRef): string {
  return `${skillId}/${subagent.path}/SKILL.md`
}

interface PropertiesPanelProps {
  skillId?: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  runId?: string | null
  selectedNodeStatus?: SkillNodeStatus | null
  resumeValidity?: ResumeValidityResponse | null
  resumeValidityLoading?: boolean
  resumeValidityError?: string | null
  resumeLoading?: boolean
  // Realtime lint diagnostics (engine field axis). Projected per-field by `field_path`
  // onto the matching frontmatter field below; no-field errors degrade to the node badge.
  lintErrors?: LintError[] | null
  onFileOpen?: (fileOrPath: FileOpenInput) => void
  onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
  /** Add a LOGIC action: scaffolds actions/<name>.py + syncs frontmatter/body, then opens it. */
  onActionCreate?: (phaseId: string, name: string) => Promise<void> | void
  /** Delete a LOGIC action: removes it from frontmatter/body and deletes its .py file. */
  onActionDelete?: (phaseId: string, name: string) => Promise<void> | void
  /** Create a phase validator.py (passing stub) + enable validator: true, then open it. */
  onValidatorCreate?: (phaseId: string) => Promise<void> | void
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
  /** Per-node golden promote (atom #32): write golden for just this node from the active run. */
  onPromoteNode?: (nodeId: string) => Promise<void> | void
  onOpenSettings?: (tab?: SettingsTab) => void
  /** Deselect the node so the panel shows the graph (GRAPH.md) properties. */
  onSelectGraph?: () => void
  /** Launch this node's Compare LLMs off the current base run. */
  onStartNodeCompare?: (nodeId: string) => void
}

export function PropertiesPanel({
  skillId = null,
  workspaceRoot = null,
  skillDetail,
  selectedNode,
  runId = null,
  selectedNodeStatus = null,
  resumeValidity = null,
  resumeValidityLoading = false,
  resumeValidityError = null,
  resumeLoading = false,
  lintErrors = null,
  onFileOpen,
  onPhaseFileSave,
  onPhaseRename,
  onActionCreate,
  onActionDelete,
  onValidatorCreate,
  onResumeNode,
  onPromoteNode,
  onOpenSettings,
  onSelectGraph,
  onStartNodeCompare,
}: PropertiesPanelProps) {

  // Configured LLM roles for the llm_role dropdown (GET /llm/roles) via SWR so
  // the list revalidates (focus/reconnect + shared-key mutations) instead of
  // going permanently stale after one on-mount fetch. On failure both stay
  // empty — the field still shows the current stored value, nothing is lost.
  const { data: rolesData } = useSWR("llm/roles", getRoles, { shouldRetryOnError: false })
  const roleNames = useMemo(
    () => (rolesData ? graphAgentRoleNamesForProperties(rolesData) : []),
    [rolesData],
  )
  const { data: modelGroupsData } = useSWR("llm/model-groups", getModelGroups, { shouldRetryOnError: false })
  const modelGroups = useMemo(
    () => (modelGroupsData ? compareModelGroupsForPicker(modelGroupsData) : []),
    [modelGroupsData],
  )

  const graphContent = skillDetail?.files?.["GRAPH.md"]
  const [graphSourceContent, setGraphSourceContent] = useState<string | undefined>(graphContent)
  useEffect(() => {
    setGraphSourceContent(graphContent)
  }, [graphContent])
  const graphFormState = useMemo(() => {
    if (graphSourceContent === undefined) {
      return { key: `graph:${skillId ?? "unknown"}:none`, ok: false as const, message: "GRAPH.md is not available in the loaded skill detail." }
    }
    const parsed = parsePhaseFrontmatter(graphSourceContent)
    if (!parsed.ok) {
      return { key: `graph:${skillId ?? "unknown"}:${graphSourceContent}`, ok: false as const, message: parsed.message }
    }
    return {
      key: `graph:${skillId ?? "unknown"}:${graphSourceContent}`,
      ok: true as const,
      form: graphFrontmatterToForm(parsed.frontmatter),
    }
  }, [graphSourceContent, skillId])
  const [loadedGraphFormKey, setLoadedGraphFormKey] = useState(graphFormState.key)
  const [graphDraft, setGraphDraft] = useState<GraphFrontmatterFormData | null>(() => (
    graphFormState.ok ? graphFormState.form : null
  ))
  const [graphSaving, setGraphSaving] = useState(false)
  const [graphSavedKey, setGraphSavedKey] = useState<string | null>(null)
  const [graphSaveFailedKey, setGraphSaveFailedKey] = useState<string | null>(null)
  const previousGraphFormStateRef = useRef(graphFormState)

  useEffect(() => {
    const previous = previousGraphFormStateRef.current
    setLoadedGraphFormKey(graphFormState.key)
    setGraphDraft((current) => {
      if (!graphFormState.ok) return null
      if (previous.ok && current && !graphFormsEqual(current, previous.form)) {
        return current
      }
      return graphFormState.form
    })
    setGraphSaving(false)
    previousGraphFormStateRef.current = graphFormState
  }, [graphFormState])

  const activeGraphDraft = graphFormState.ok
    ? loadedGraphFormKey === graphFormState.key
      ? graphDraft ?? graphFormState.form
      : graphFormState.form
    : null
  const graphDirty = Boolean(activeGraphDraft && graphFormState.ok && !graphFormsEqual(activeGraphDraft, graphFormState.form))
  const graphAutosaveAvailable = Boolean(onPhaseFileSave && graphSourceContent !== undefined && activeGraphDraft && graphFormState.ok)
  const graphSaveFailed = graphSaveFailedKey === graphFormState.key
  const graphAutosaveStatus: SaveStatus = graphSaveFailed
    ? "error"
    : graphSaving
      ? "saving"
      : graphDirty && graphAutosaveAvailable
        ? "pending"
        : graphSavedKey === graphFormState.key
          ? "saved"
          : "idle"

  const setGraphField = <Key extends keyof GraphFrontmatterFormData>(field: Key, value: GraphFrontmatterFormData[Key]) => {
    setGraphSaveFailedKey(null)
    setGraphDraft((current) => current ? { ...current, [field]: value } : current)
  }

  const handleGraphReset = () => {
    if (graphFormState.ok) {
      setGraphSaveFailedKey(null)
      setGraphDraft(graphFormState.form)
    }
  }

  const handleGraphSave = useCallback(async () => {
    if (!onPhaseFileSave || graphSourceContent === undefined || !activeGraphDraft) {
      return
    }
    const next = applyGraphFrontmatterForm(graphSourceContent, activeGraphDraft)
    if (!next.ok) {
      toast.error(`Frontmatter error: ${next.message}`)
      return
    }
    setGraphSaving(true)
    setGraphSaveFailedKey(null)
    try {
      await onPhaseFileSave({
        path: "GRAPH.md",
        content: next.markdown,
        expectedHash: await sha256Hex(graphSourceContent),
      })
      setGraphSourceContent(next.markdown)
      setGraphSavedKey(`graph:${skillId ?? "unknown"}:${next.markdown}`)
    } catch (error) {
      let errorToReport: unknown = error
      const conflict = hashConflictPayloadFromSaveError(error)
      if (conflict?.remoteHash) {
        const retry = applyGraphFrontmatterForm(conflict.remoteContent, activeGraphDraft)
        if (retry.ok) {
          try {
            await onPhaseFileSave({
              path: "GRAPH.md",
              content: retry.markdown,
              expectedHash: conflict.remoteHash,
            })
            setGraphSourceContent(retry.markdown)
            setGraphSavedKey(`graph:${skillId ?? "unknown"}:${retry.markdown}`)
            return
          } catch (retryError) {
            errorToReport = retryError
          }
        } else {
          errorToReport = new Error(`Frontmatter error: ${retry.message}`)
        }
      }
      setGraphSaveFailedKey(graphFormState.key)
      toast.error(errorToReport instanceof Error ? errorToReport.message : "Could not save graph properties")
    } finally {
      setGraphSaving(false)
    }
  }, [activeGraphDraft, graphFormState.key, graphSourceContent, onPhaseFileSave, skillId])

  useEffect(() => {
    if (!graphDirty || !graphAutosaveAvailable || graphSaving || graphSaveFailed) {
      return
    }
    const timer = setTimeout(() => {
      void handleGraphSave()
    }, PROPERTIES_AUTOSAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [graphAutosaveAvailable, graphDirty, graphSaveFailed, graphSaving, handleGraphSave])

  const modeLabel = selectedNode ? phaseKindLabel(selectedNode.data) : null
  const headerFileLabel = selectedNode ? phaseKindFile(selectedNode.data) : "GRAPH.md"
  const effectiveNodeStatus = selectedNodeStatus ?? selectedNode?.data.status ?? null
  const kind: PhaseFrontmatterKind = phaseFrontmatterKind(modeLabel ?? "LOGIC")
  const selectedPhaseId = selectedNode?.data.phaseId ?? selectedNode?.id ?? null
  const filePath = selectedNode?.data.filePath ?? (selectedNode && selectedPhaseId ? `phases/${selectedPhaseId}/${phaseKindFile(selectedNode.data)}` : null)
  const headerFilePath = filePath ?? "GRAPH.md"
  const loadedFileContent = filePath ? skillDetail?.files?.[filePath] : undefined
  const [phaseSourceContent, setPhaseSourceContent] = useState<string | undefined>(loadedFileContent)
  useEffect(() => {
    setPhaseSourceContent(loadedFileContent)
  }, [filePath, loadedFileContent])
  const fileContent = phaseSourceContent
  // Field-level near-projection (atom #5): group THIS node's lint errors by the engine's
  // `field_path` so each frontmatter field can show its own marker; no-field errors are
  // dropped here and stay on the node badge (atom #4).
  const fieldErrors = useMemo(
    () => (selectedNode ? fieldErrorsByKey(lintErrors, selectedNode.id) : {}),
    [lintErrors, selectedNode],
  )
  const phaseFormState = useMemo(() => {
    if (!filePath) {
      return { key: `phase:${skillId ?? "unknown"}:none`, ok: false as const, reason: "missing-node" as const, message: "Select a phase node to edit frontmatter." }
    }
    if (fileContent === undefined) {
      return { key: `phase:${skillId ?? "unknown"}:${filePath}:missing-file`, ok: false as const, reason: "missing-file" as const, message: "Phase file is not available in the loaded skill detail." }
    }
    const parsed = parsePhaseFrontmatter(fileContent)
    if (!parsed.ok) {
      return { key: `phase:${skillId ?? "unknown"}:${filePath}:${fileContent}`, ok: false as const, reason: parsed.reason, message: parsed.message }
    }
    const form = phaseFrontmatterToForm(parsed.frontmatter)
    return {
      key: `phase:${skillId ?? "unknown"}:${filePath}:${fileContent}`,
      ok: true as const,
      form,
    }
  }, [fileContent, filePath, skillId])
  const [loadedFormKey, setLoadedFormKey] = useState(phaseFormState.key)
  const [draft, setDraft] = useState<PhaseFrontmatterFormData | null>(() => (
    phaseFormState.ok ? phaseFormState.form : null
  ))
  const [saving, setSaving] = useState(false)
  const [phaseSavedKey, setPhaseSavedKey] = useState<string | null>(null)
  const [phaseSaveFailedKey, setPhaseSaveFailedKey] = useState<string | null>(null)
  const [roleTest, setRoleTest] = useState<RoleTestStatusInput>({ running: false })
  // Separate test state for the GRAPH.md default role (graph panel flask).
  const [graphRoleTest, setGraphRoleTest] = useState<RoleTestStatusInput>({ running: false })
  const previousPhaseFormStateRef = useRef(phaseFormState)

  useEffect(() => {
    const previous = previousPhaseFormStateRef.current
    setLoadedFormKey(phaseFormState.key)
    setDraft((current) => {
      if (!phaseFormState.ok) return null
      if (previous.ok && current && !formsEqual(current, previous.form)) {
        return current
      }
      return phaseFormState.form
    })
    setSaving(false)
    setRoleTest({ running: false })
    previousPhaseFormStateRef.current = phaseFormState
  }, [phaseFormState])

  const activeDraft = phaseFormState.ok
    ? loadedFormKey === phaseFormState.key
      ? draft ?? phaseFormState.form
      : phaseFormState.form
    : null
  const effectiveWorkspaceRoot = workspaceRoot ?? selectedNode?.data.workspaceRoot ?? null
  const allowOverwriteCandidates = useMemo(
    () => (selectedNode && filePath
      ? inferAllowOverwriteCandidates(skillDetail, selectedPhaseId ?? selectedNode.id, filePath)
      : []),
    [filePath, selectedNode, selectedPhaseId, skillDetail],
  )
  const dirty = Boolean(activeDraft && phaseFormState.ok && !formsEqual(activeDraft, phaseFormState.form))
  const phaseAutosaveAvailable = Boolean(onPhaseFileSave && filePath && fileContent !== undefined && activeDraft && phaseFormState.ok)
  const phaseSaveFailed = phaseSaveFailedKey === phaseFormState.key
  const phaseAutosaveStatus: SaveStatus = phaseSaveFailed
    ? "error"
    : saving
      ? "saving"
      : dirty && phaseAutosaveAvailable
        ? "pending"
        : phaseSavedKey === phaseFormState.key
          ? "saved"
          : "idle"

  const setField = <Key extends keyof PhaseFrontmatterFormData>(field: Key, value: PhaseFrontmatterFormData[Key]) => {
    setPhaseSaveFailedKey(null)
    setDraft((current) => current ? { ...current, [field]: value } : current)
  }

  const handleReset = () => {
    if (phaseFormState.ok) {
      setPhaseSaveFailedKey(null)
      setDraft(phaseFormState.form)
    }
  }

  const handleSave = useCallback(async () => {
    if (!onPhaseFileSave || !filePath || fileContent === undefined || !activeDraft) {
      return
    }
    const next = applyPhaseFrontmatterForm(fileContent, activeDraft, kind)
    if (!next.ok) {
      toast.error(`Frontmatter error: ${next.message}`)
      return
    }
    setSaving(true)
    setPhaseSaveFailedKey(null)
    try {
      await onPhaseFileSave({
        path: filePath,
        content: next.markdown,
        expectedHash: await sha256Hex(fileContent),
      })
      setPhaseSourceContent(next.markdown)
      setPhaseSavedKey(`phase:${skillId ?? "unknown"}:${filePath}:${next.markdown}`)
    } catch (error) {
      let errorToReport: unknown = error
      const conflict = hashConflictPayloadFromSaveError(error)
      if (conflict?.remoteHash) {
        const retry = applyPhaseFrontmatterForm(conflict.remoteContent, activeDraft, kind)
        if (retry.ok) {
          try {
            await onPhaseFileSave({
              path: filePath,
              content: retry.markdown,
              expectedHash: conflict.remoteHash,
            })
            setPhaseSourceContent(retry.markdown)
            setPhaseSavedKey(`phase:${skillId ?? "unknown"}:${filePath}:${retry.markdown}`)
            return
          } catch (retryError) {
            errorToReport = retryError
          }
        } else {
          errorToReport = new Error(`Frontmatter error: ${retry.message}`)
        }
      }
      setPhaseSaveFailedKey(phaseFormState.key)
      toast.error(errorToReport instanceof Error ? errorToReport.message : "Could not save phase properties")
    } finally {
      setSaving(false)
    }
  }, [activeDraft, fileContent, filePath, kind, onPhaseFileSave, phaseFormState.key, skillId])

  useEffect(() => {
    if (!dirty || !phaseAutosaveAvailable || saving || phaseSaveFailed) {
      return
    }
    const timer = setTimeout(() => {
      void handleSave()
    }, PROPERTIES_AUTOSAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [dirty, handleSave, phaseAutosaveAvailable, phaseSaveFailed, saving])

  // Reuses the settings role-test job runner (runRoleTestJobToResult) verbatim so
  // the node Properties Test button verifies the same backend job + status the
  // Settings page does (settings-ux-spec §2.7). No re-implementation. The node
  // form and the graph form each keep their own status state via `setState`.
  const runRoleTest = useCallback(async (
    roleName: string,
    setState: (next: RoleTestStatusInput) => void,
  ) => {
    const trimmed = roleName.trim()
    if (!trimmed) {
      toast.error("Set an LLM role before testing.")
      return
    }
    setState({ running: true, status: null, error: null })
    try {
      const result = await runRoleTestJobToResult(trimmed)
      setState({
        running: false,
        status: result.status,
        error: null,
        details: roleTestDetailsFromResult(result),
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Role test failed"
      setState({ running: false, status: null, error: message, details: [message] })
      toast.error(message)
    }
  }, [])
  const handleRoleTest = useCallback(
    (roleName: string) => runRoleTest(roleName, setRoleTest),
    [runRoleTest],
  )
  const handleGraphRoleTest = useCallback(
    (roleName: string) => runRoleTest(roleName, setGraphRoleTest),
    [runRoleTest],
  )

  // Subgraph "import folder" affordance (n2-properties #20 / F4-R5): when the
  // child-graph path is missing/unresolvable, let the author pick the child
  // graph root via the native OS directory picker (Rust `select_directory`,
  // Desktop-only with a graceful toast off-desktop) and write the chosen
  // path straight into the editable `path` field.
  const handleReconnectSubgraphFolder = useCallback(async () => {
    const currentTarget = activeDraft?.path
      ? subgraphPathFieldState(activeDraft.path, null, effectiveWorkspaceRoot).path
      : null
    const selected = await selectSkillDirectory(currentTarget ?? effectiveWorkspaceRoot)
    if (!selected) {
      return
    }
    if (!isPathInsideWorkspaceRoot(selected, effectiveWorkspaceRoot)) {
      toast.error("Select a child graph folder inside the current skill root.")
      return
    }
    const nextPath = subgraphPathValueFromSelection(selected, effectiveWorkspaceRoot)
    if (nextPath === ".") {
      toast.error("Select a child graph folder, not the current skill root.")
      return
    }
    if (skillId) {
      try {
        await getChildGraphTopology(skillId, selected)
      } catch (error) {
        toast.error("Selected folder is not a usable child graph", { description: errorMessage(error) })
        return
      }
    }
    setField("path", nextPath)
  }, [activeDraft?.path, effectiveWorkspaceRoot, skillId])

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader
        title="Properties"
        extra={<PropertiesHeaderHint />}
        right={<PropertiesFileBadge fileLabel={headerFileLabel} filePath={headerFilePath} onFileOpen={onFileOpen} />}
      />

      <ScrollArea className="flex-1">
        {selectedNode ? (
          <PanelBody>
            <NodeResumeDebugBar
              runId={runId}
              nodeId={selectedNode.id}
              nodeStatus={effectiveNodeStatus}
              resumeValidity={resumeValidity}
              loading={resumeValidityLoading}
              error={resumeValidityError}
              resumeLoading={resumeLoading}
              onResumeNode={onResumeNode}
            />
            {modeLabel === "AGENT" ? (
              <NodeGoldenSection
                runId={runId}
                nodeId={selectedNode.id}
                hasGolden={selectedNode.data.goldenState === "has-golden"}
                onPromoteNode={onPromoteNode}
              />
            ) : null}
            {phaseFormState.ok && activeDraft ? (
              <PhaseFrontmatterForm
                value={activeDraft}
                kind={kind}
                saveStatus={phaseAutosaveStatus}
                canReset={dirty && !saving}
                roleTest={roleTest}
                roleNames={roleNames}
                modelGroups={modelGroups}
                fieldErrors={fieldErrors}
                allowOverwriteCandidates={allowOverwriteCandidates}
                skillId={skillId}
                workspaceRoot={effectiveWorkspaceRoot}
                phaseId={selectedPhaseId ?? selectedNode.id}
                files={skillDetail?.files}
                onFileOpen={onFileOpen}
                onPhaseRename={onPhaseRename}
                onActionCreate={onActionCreate}
                onActionDelete={onActionDelete}
                onValidatorCreate={onValidatorCreate}
                onReconnectSubgraphFolder={handleReconnectSubgraphFolder}
                onFieldChange={setField}
                onReset={handleReset}
                onRoleTest={(roleName) => {
                  void handleRoleTest(roleName)
                }}
                onOpenSettings={onOpenSettings}
                onSelectGraph={onSelectGraph}
                onStartNodeCompare={onStartNodeCompare}
              />
            ) : (
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <div className="text-xs font-medium text-destructive">Frontmatter error</div>
                <div className="mt-1 text-xs text-muted-foreground">{phaseFormState.message}</div>
                <PanelActions>
                  {filePath ? (
                    <Button type="button" size="sm" variant="secondary" onClick={() => onFileOpen?.(filePath)}>
                      Open file
                    </Button>
                  ) : null}
                </PanelActions>
              </div>
            )}
          </PanelBody>
        ) : (
          <PanelBody>
            {graphFormState.ok && activeGraphDraft ? (
              <GraphFrontmatterForm
                value={activeGraphDraft}
                roleNames={roleNames}
                saveStatus={graphAutosaveStatus}
                canReset={graphDirty && !graphSaving}
                roleTest={graphRoleTest}
                onFieldChange={setGraphField}
                onReset={handleGraphReset}
                onRoleTest={(roleName) => {
                  void handleGraphRoleTest(roleName)
                }}
                onOpenSettings={onOpenSettings}
              />
            ) : (
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <div className="text-xs font-medium text-destructive">Frontmatter error</div>
                <div className="mt-1 text-xs text-muted-foreground">{graphFormState.message}</div>
                <PanelActions>
                  <Button type="button" size="sm" variant="secondary" onClick={() => onFileOpen?.("GRAPH.md")}>
                    Open file
                  </Button>
                </PanelActions>
              </div>
            )}
          </PanelBody>
        )}
      </ScrollArea>
    </div>
  )
}

interface GraphFrontmatterFormData {
  name: string
  description: string
  llmRole: string
}

function YamlFieldLabel({ className, ...props }: ComponentProps<typeof FieldLabel>) {
  return (
    <FieldLabel
      className={`${YAML_FIELD_LABEL_CLASS}${className ? ` ${className}` : ""}`}
      {...props}
    />
  )
}

function YamlNestedFieldLabel({ className, ...props }: ComponentProps<typeof FieldLabel>) {
  return (
    <FieldLabel
      className={`!text-xs !font-normal !leading-4 !text-foreground/80${className ? ` ${className}` : ""}`}
      {...props}
    />
  )
}

function YamlInputField({
  id,
  label,
  value,
  placeholder,
  readOnly = false,
  invalid = false,
  inputClassName,
  action,
  children,
  onChange,
}: {
  id: string
  label: ReactNode
  value: string
  placeholder?: string
  readOnly?: boolean
  invalid?: boolean
  inputClassName?: string
  action?: ReactNode
  children?: ReactNode
  onChange?: (value: string) => void
}) {
  return (
    <Field>
      <YamlFieldLabel htmlFor={id}>{label}</YamlFieldLabel>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          value={value}
          placeholder={placeholder}
          readOnly={readOnly}
          aria-readonly={readOnly || undefined}
          aria-invalid={invalid || undefined}
          className={`${action ? "min-w-0 flex-1" : ""}${readOnly ? ` ${YAML_READONLY_VALUE_CLASS}` : ""}${inputClassName ? ` ${inputClassName}` : ""}`}
          onChange={onChange ? (event) => onChange(event.currentTarget.value) : undefined}
        />
        {action}
      </div>
      {children}
    </Field>
  )
}

function PropertiesHeaderHint() {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex size-5 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Properties panel source"
          >
            <CircleHelp className="size-3.5" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" align="start" className="max-w-64">
          This panel edits the front matter YAML fields in the selected Markdown file.
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function PropertiesFileBadge({
  fileLabel,
  filePath,
  onFileOpen,
}: {
  fileLabel: "GRAPH.md" | "LOGIC.md" | "SKILL.md" | "SUBGRAPH.md"
  filePath: string
  onFileOpen?: (fileOrPath: FileOpenInput) => void
}) {
  return (
    <button
      type="button"
      className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      aria-label={`Open ${fileLabel}`}
      onClick={() => onFileOpen?.(filePath)}
    >
      <Badge variant="secondary" className="cursor-pointer transition-colors hover:bg-secondary/80">
        {fileLabel}
      </Badge>
    </button>
  )
}

const GRAPH_LLM_ROLE_NONE_SENTINEL = "__none__"

function GraphFrontmatterForm({
  value,
  roleNames,
  saveStatus,
  canReset,
  roleTest,
  onFieldChange,
  onReset,
  onRoleTest,
  onOpenSettings,
}: {
  value: GraphFrontmatterFormData
  roleNames: string[]
  saveStatus: SaveStatus
  canReset: boolean
  roleTest: RoleTestStatusInput
  onFieldChange: <Key extends keyof GraphFrontmatterFormData>(field: Key, value: GraphFrontmatterFormData[Key]) => void
  onReset: () => void
  onRoleTest: (roleName: string) => void
  onOpenSettings?: (tab?: SettingsTab) => void
}) {
  const trimmedGraphRole = value.llmRole.trim()
  const graphComboboxOptions = useMemo<SearchableComboboxOption[]>(
    () => {
      const graphRoleOptions = trimmedGraphRole && !roleNames.includes(trimmedGraphRole)
        ? [trimmedGraphRole, ...roleNames]
        : roleNames
      return [
        { value: GRAPH_LLM_ROLE_NONE_SENTINEL, label: "(none)", searchValue: "none" },
        ...graphRoleOptions.map((name) => llmRoleComboboxOption(name, roleNames.includes(name))),
      ]
    },
    [roleNames, trimmedGraphRole],
  )
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
      }}
    >
      <FieldSet>
        <FieldGroup>
          <PanelFieldRow>
            <YamlInputField
              id="graph-name"
              label="name"
              value={value.name}
              onChange={(next) => onFieldChange("name", next)}
            />
          </PanelFieldRow>
          <PanelFieldRow>
            <Field>
              <YamlFieldLabel htmlFor="graph-description">description</YamlFieldLabel>
              <Textarea
                id="graph-description"
                value={value.description}
                rows={3}
                onChange={(event) => onFieldChange("description", event.currentTarget.value)}
              />
            </Field>
          </PanelFieldRow>
          <PanelFieldRow>
            <Field>
              <YamlFieldLabel htmlFor="graph-llm-role">
                llm_role
                <HelpTooltip label="About llm_role">
                  The default LLM role for the whole graph; agent phases inherit it unless they set their own.
                  Manage roles in Settings &rsaquo; LLM Roles.
                </HelpTooltip>
              </YamlFieldLabel>
              <div className="flex items-center gap-2">
                <SearchableOptionCombobox
                  id="graph-llm-role"
                  value={trimmedGraphRole || GRAPH_LLM_ROLE_NONE_SENTINEL}
                  options={graphComboboxOptions}
                  onChange={(next) => onFieldChange("llmRole", next === GRAPH_LLM_ROLE_NONE_SENTINEL ? "" : next)}
                  ariaLabel="llm_role"
                  placeholder="Select a role"
                  searchPlaceholder="Search roles"
                  emptyLabel="No role found."
                  triggerClassName="min-w-0 flex-1"
                />
                <LlmRoleSettingsButton onOpenSettings={onOpenSettings} />
                <RoleTestControl
                  roleName={trimmedGraphRole}
                  roleTest={roleTest}
                  onRoleTest={onRoleTest}
                />
              </div>
            </Field>
          </PanelFieldRow>
        </FieldGroup>
      </FieldSet>
      <PropertiesAutosaveActions saveStatus={saveStatus} canReset={canReset} onReset={onReset} />
    </form>
  )
}

function graphFrontmatterToForm(frontmatter: PhaseFrontmatter): GraphFrontmatterFormData {
  return {
    name: graphStringValue(frontmatter.name),
    description: graphStringValue(frontmatter.description),
    llmRole: graphStringValue(frontmatter.llm_role),
  }
}

function PropertiesAutosaveActions({
  saveStatus,
  canReset,
  onReset,
}: {
  saveStatus: SaveStatus
  canReset: boolean
  onReset: () => void
}) {
  if (saveStatus === "idle" && !canReset) {
    return null
  }
  return (
    <PanelActions>
      <div className="flex items-center justify-end gap-2">
        <SaveStatusBadge status={saveStatus} />
        {canReset ? (
          <Button type="button" size="sm" variant="secondary" onClick={onReset}>
            Reset
          </Button>
        ) : null}
      </div>
    </PanelActions>
  )
}

function graphFormsEqual(left: GraphFrontmatterFormData, right: GraphFrontmatterFormData): boolean {
  return left.name === right.name
    && left.description === right.description
    && left.llmRole === right.llmRole
}

function applyGraphFrontmatterForm(
  markdown: string,
  form: GraphFrontmatterFormData,
): { ok: true; markdown: string } | { ok: false; message: string } {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return { ok: false, message: parsed.message }
  }
  const next: PhaseFrontmatter = { ...parsed.frontmatter }
  next.name = form.name
  setGraphOptionalString(next, "description", form.description)
  setGraphOptionalString(next, "llm_role", form.llmRole)
  return { ok: true, markdown: serializeGraphMarkdown(next, parsed.body) }
}

function serializeGraphMarkdown(frontmatter: PhaseFrontmatter, bodyContent: string): string {
  const dumped = yaml.dump(frontmatter, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { "!!null": "empty" },
  }).trimEnd()
  const trimmedBody = bodyContent.replace(/^\n+/, "")
  const body = trimmedBody.length > 0 ? `\n${trimmedBody}` : "\n"
  return `---\n${dumped}\n---${body}`
}

function setGraphOptionalString(target: PhaseFrontmatter, key: string, value: string) {
  if (value.trim().length === 0) {
    delete target[key]
  } else {
    target[key] = value
  }
}

function graphStringValue(value: unknown): string {
  return typeof value === "string" ? value : ""
}

function RenamePhaseDialog({
  phaseId,
  onPhaseRename,
}: {
  phaseId: string
  onPhaseRename: (phaseId: string, nextPhaseId: string) => Promise<void> | void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(phaseId)
  const [renaming, setRenaming] = useState(false)
  const nextId = draft.trim()
  const invalid = nextId.length > 0 && !isSafePhaseId(nextId)
  const unchanged = nextId === phaseId
  const canRename = Boolean(nextId && !invalid && !unchanged && !renaming)

  useEffect(() => {
    if (open) {
      setDraft(phaseId)
      setRenaming(false)
    }
  }, [open, phaseId])

  const handleSubmit = async () => {
    if (!canRename) {
      return
    }
    setRenaming(true)
    try {
      await onPhaseRename(phaseId, nextId)
      setOpen(false)
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setRenaming(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className={YAML_ICON_BUTTON_CLASS}
          aria-label="Rename phase"
        >
          <Pencil className="size-3.5" aria-hidden />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename phase</DialogTitle>
          <DialogDescription>
            This changes the phase id in GRAPH.md and renames the matching folder under phases.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <form className="contents" autoComplete="off" onSubmit={(event) => {
            event.preventDefault()
            void handleSubmit()
          }}>
          <FieldLabel htmlFor="phase-rename-input">New name</FieldLabel>
          <Input
            id="phase-rename-input"
            name="phase-id-draft"
            value={draft}
            autoFocus
            autoComplete="new-password"
            autoCorrect="off"
            spellCheck={false}
            aria-invalid={invalid || undefined}
            onChange={(event) => setDraft(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                void handleSubmit()
              }
            }}
          />
          <FieldDescription>Use letters, numbers, underscores, or hyphens. The first character must be a letter or underscore.</FieldDescription>
          {invalid ? <p className="text-xs text-destructive">Invalid phase name.</p> : null}
          </form>
        </Field>
        <DialogFooter>
          <Button type="button" variant="secondary" disabled={renaming} onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={!canRename} onClick={() => void handleSubmit()}>
            {renaming ? "Renaming" : "Rename"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Per-node golden promote (N4 atom #32). For an agent node, this writes a golden
 * baseline for THIS node only from the active run (via the node_id-aware
 * saveGoldenBaseline). Disabled until a run exists to promote from; once the node
 * has a golden case it shows the captured state instead of the button.
 */
function NodeGoldenSection({
  runId,
  nodeId,
  hasGolden,
  onPromoteNode,
}: {
  runId: string | null
  nodeId: string
  hasGolden: boolean
  onPromoteNode?: (nodeId: string) => Promise<void> | void
}) {
  const [promoting, setPromoting] = useState(false)

  const handlePromote = async () => {
    if (!onPromoteNode || !runId) return
    setPromoting(true)
    try {
      await onPromoteNode(nodeId)
    } finally {
      setPromoting(false)
    }
  }

  if (hasGolden) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-success-border/60 bg-success/10 px-3 py-2 text-xs text-success">
        <ShieldCheck className="size-3.5" />
        <span>Golden captured for this node</span>
      </div>
    )
  }

  return (
    <div className="rounded-md border border-border bg-card px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">No golden for this node yet</span>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!onPromoteNode || !runId || promoting}
          onClick={() => {
            void handlePromote()
          }}
        >
          {promoting ? <Loader2 className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}
          Promote to golden
        </Button>
      </div>
      {!runId ? (
        <p className="mt-1 text-[11px] text-muted-foreground">Run this skill first to capture a golden from its output.</p>
      ) : null}
    </div>
  )
}

function NodeResumeDebugBar({
  runId,
  nodeId,
  nodeStatus,
  resumeValidity,
  loading,
  error,
  resumeLoading,
  onResumeNode,
}: {
  runId: string | null
  nodeId: string
  nodeStatus: SkillNodeStatus | null
  resumeValidity: ResumeValidityResponse | null
  loading: boolean
  error: string | null
  resumeLoading: boolean
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
}) {
  if (!runId || nodeStatus !== "error") {
    return null
  }
  const allowed = Boolean(resumeValidity?.resume_allowed)
  const reason = loading
    ? "checking"
    : error
      ? "checkpoint.invalid"
      : resumeValidity?.reason ?? "checkpoint.not_found"
  const dirtyFields = resumeValidity?.dirty_fields ?? []
  const disabled = !allowed || loading || resumeLoading || !onResumeNode
  const buttonLabel = allowed ? (resumeLoading ? "Resuming" : "Resume node") : "Resume disabled"

  const handleResume = () => {
    if (!allowed || !resumeValidity || !onResumeNode) {
      return
    }
    void onResumeNode(nodeResumeOptionsFromValidity(resumeValidity, nodeId))
  }

  return (
    <section className="rounded-md border border-border bg-card px-3 py-2" aria-label="Checkpoint validity">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Checkpoint validity
          </div>
          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-foreground">
            <Badge variant={allowed ? "secondary" : "destructive"}>{reason}</Badge>
            {dirtyFields.map((field) => (
              <Badge key={field} variant="outline">{field}</Badge>
            ))}
          </div>
          {error ? <div className="mt-1 text-xs text-muted-foreground">{error}</div> : null}
        </div>
        <Button
          type="button"
          size="sm"
          disabled={disabled}
          onClick={handleResume}
        >
          {loading ? (
            <Loader2 className="size-3 animate-spin" data-icon="inline-start" />
          ) : null}
          {buttonLabel}
        </Button>
      </div>
    </section>
  )
}

function PhaseFrontmatterForm({
  value,
  kind,
  saveStatus,
  canReset,
  roleTest,
  roleNames,
  modelGroups,
  fieldErrors,
  allowOverwriteCandidates,
  skillId,
  workspaceRoot,
  phaseId,
  files,
  onFileOpen,
  onPhaseRename,
  onActionCreate,
  onActionDelete,
  onValidatorCreate,
  onReconnectSubgraphFolder,
  onFieldChange,
  onReset,
  onRoleTest,
  onOpenSettings,
  onSelectGraph,
  onStartNodeCompare,
}: {
  value: PhaseFrontmatterFormData
  kind: PhaseFrontmatterKind
  saveStatus: SaveStatus
  canReset: boolean
  roleTest: RoleTestStatusInput
  roleNames: string[]
  modelGroups: ModelGroup[]
  fieldErrors: Record<string, LintError[]>
  allowOverwriteCandidates: AllowOverwriteCandidate[]
  skillId: string | null
  workspaceRoot: string | null
  phaseId: string
  files?: Record<string, string>
  onFileOpen?: (fileOrPath: FileOpenInput) => void
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
  onActionCreate?: (phaseId: string, name: string) => Promise<void> | void
  onActionDelete?: (phaseId: string, name: string) => Promise<void> | void
  onValidatorCreate?: (phaseId: string) => Promise<void> | void
  onReconnectSubgraphFolder: () => void
  onFieldChange: <Key extends keyof PhaseFrontmatterFormData>(field: Key, value: PhaseFrontmatterFormData[Key]) => void
  onReset: () => void
  onRoleTest: (roleName: string) => void
  onOpenSettings?: (tab?: SettingsTab) => void
  onSelectGraph?: () => void
  onStartNodeCompare?: (nodeId: string) => void
}) {
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
      }}
    >
      <FieldSet>
        <FieldGroup>
          {kind === "agent" ? (
            <>
              <PanelFieldRow>
                <PhaseNameField
                  phaseId={phaseId}
                  onPhaseRename={onPhaseRename}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <LlmRoleField
                  key={phaseId}
                  value={value.llmRole}
                  useGraphDefault={value.useGraphLlmRole}
                  roleNames={roleNames}
                  modelGroups={modelGroups}
                  roleTest={roleTest}
                  errors={fieldErrors.llm_role}
                  skillId={skillId}
                  nodeId={phaseId}
                  onChange={(next) => onFieldChange("llmRole", next)}
                  onUseGraphDefaultChange={(next) => onFieldChange("useGraphLlmRole", next)}
                  onRoleTest={onRoleTest}
                  onOpenSettings={onOpenSettings}
                  onSelectGraph={onSelectGraph}
                  onStartNodeCompare={onStartNodeCompare}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ValidatorField
                  value={value.validator}
                  errors={fieldErrors.validator}
                  phaseId={phaseId}
                  files={files}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onChange={(next) => onFieldChange("validator", next)}
                  onValidatorCreate={onValidatorCreate}
                  onFileOpen={onFileOpen}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <MaxIterationsField
                  value={value.maxIterations}
                  errors={fieldErrors.max_iterations}
                  onChange={(next) => onFieldChange("maxIterations", next)}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ToolsField
                  value={value.tools}
                  errors={fieldErrors.tools}
                  onChange={(next) => onFieldChange("tools", next)}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <SubagentsField
                  value={value.subagents}
                  onChange={(next) => onFieldChange("subagents", next)}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <SubgraphRefsField
                  value={value.subgraphs}
                  errors={fieldErrors.subgraphs}
                  workspaceRoot={workspaceRoot}
                  onChange={(next) => onFieldChange("subgraphs", next)}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ResourceRefField
                  fieldKey="references"
                  value={value.references}
                  errors={fieldErrors.references}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  files={files}
                  onFileOpen={onFileOpen}
                  onChange={(next) => onFieldChange("references", next)}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ResourceRefField
                  fieldKey="examples"
                  value={value.examples}
                  errors={fieldErrors.examples}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  files={files}
                  onFileOpen={onFileOpen}
                  onChange={(next) => onFieldChange("examples", next)}
                />
              </PanelFieldRow>
            </>
          ) : null}
          {kind === "logic" ? (
            <>
              <PanelFieldRow>
                <PhaseNameField
                  phaseId={phaseId}
                  onPhaseRename={onPhaseRename}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ActionsField
                  phaseId={phaseId}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  files={files}
                  errors={fieldErrors.actions}
                  onOpenFile={onFileOpen}
                  onActionCreate={onActionCreate}
                  onActionDelete={onActionDelete}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ValidatorField
                  value={value.validator}
                  errors={fieldErrors.validator}
                  phaseId={phaseId}
                  files={files}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onChange={(next) => onFieldChange("validator", next)}
                  onValidatorCreate={onValidatorCreate}
                  onFileOpen={onFileOpen}
                />
              </PanelFieldRow>
            </>
          ) : null}
          {kind === "subgraph" ? (
            <>
              <PanelFieldRow>
                <PhaseNameField
                  phaseId={phaseId}
                  onPhaseRename={onPhaseRename}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <SubgraphPathField
                  value={value.path}
                  errors={fieldErrors.path}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onReconnectFolder={onReconnectSubgraphFolder}
                />
              </PanelFieldRow>
              <PanelFieldRow>
                <ValidatorField
                  value={value.validator}
                  errors={fieldErrors.validator}
                  phaseId={phaseId}
                  files={files}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onChange={(next) => onFieldChange("validator", next)}
                  onValidatorCreate={onValidatorCreate}
                  onFileOpen={onFileOpen}
                />
              </PanelFieldRow>
            </>
          ) : null}
          <PanelFieldRow>
            <AllowSequentialOverwriteField
              value={value.allowSequentialOverwrite}
              candidates={allowOverwriteCandidates}
              errors={fieldErrors.allow_sequential_overwrite}
              onChange={(next) => onFieldChange("allowSequentialOverwrite", next)}
            />
          </PanelFieldRow>
          <PanelFieldRow>
            <IterateField
              value={value.iterate}
              errors={fieldErrors.iterate}
              onChange={(next) => onFieldChange("iterate", next)}
            />
          </PanelFieldRow>
        </FieldGroup>
      </FieldSet>
      <PropertiesAutosaveActions saveStatus={saveStatus} canReset={canReset} onReset={onReset} />
    </form>
  )
}

// LOGIC actions manager. The list reflects the SAVED LOGIC.md (add/delete are
// immediate file operations, not part of the form draft), reconciled with the
// `actions/*.py` files on disk. Add scaffolds a file + opens it; Delete removes
// the registration and the file. Frontmatter/body sync is done in the handler.
function ActionsField({
  phaseId,
  skillId,
  workspaceRoot,
  files,
  errors,
  onOpenFile,
  onActionCreate,
  onActionDelete,
}: {
  phaseId: string
  skillId: string | null
  workspaceRoot: string | null
  files?: Record<string, string>
  errors?: LintError[]
  onOpenFile?: (fileOrPath: FileOpenInput) => void
  onActionCreate?: (phaseId: string, name: string) => Promise<void> | void
  onActionDelete?: (phaseId: string, name: string) => Promise<void> | void
}) {
  const logicPath = `phases/${phaseId}/LOGIC.md`
  const declared = useMemo(() => readActionsList(files?.[logicPath] ?? ""), [files, logicPath])
  const filesPresent = useMemo(() => scanActionFiles(files, phaseId), [files, phaseId])
  // Orphan = an actions/*.py on disk not declared in actions:. Surface it so it
  // isn't invisible (the engine would still load it as an action).
  const orphans = useMemo(
    () => [...filesPresent].filter((name) => !declared.includes(name)).sort((a, b) => a.localeCompare(b)),
    [declared, filesPresent],
  )

  return (
    <Field>
      <YamlFieldLabel>
        actions
        <HelpTooltip label="About actions">
          The deterministic functions this logic node runs, in order. Each action is one
          <span className="font-mono"> def &lt;name&gt;(context)</span> in <span className="font-mono">actions/&lt;name&gt;.py</span>;
          the frontmatter list and body <span className="font-mono">&lt;action&gt;</span> tags are kept in sync for you.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      {declared.length > 0 || orphans.length > 0 ? (
        <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
          {declared.map((name) => (
            <ActionRow
              key={name}
              name={name}
              missingFile={!filesPresent.has(name)}
              onEdit={onOpenFile ? () => onOpenFile({ path: actionFilePath(phaseId, name), skillId, workspaceRoot, language: "python", saveEnabled: true }) : undefined}
              onDelete={onActionDelete ? () => onActionDelete(phaseId, name) : undefined}
            />
          ))}
          {orphans.map((name) => (
            <ActionRow
              key={`orphan:${name}`}
              name={name}
              orphan
              onEdit={onOpenFile ? () => onOpenFile({ path: actionFilePath(phaseId, name), skillId, workspaceRoot, language: "python", saveEnabled: true }) : undefined}
              onDelete={onActionDelete ? () => onActionDelete(phaseId, name) : undefined}
            />
          ))}
        </div>
      ) : (
        <FieldDescription>No actions yet 鈥?add one to scaffold its file.</FieldDescription>
      )}
      {onActionCreate ? (
        <AddActionDialog existing={[...declared, ...orphans]} onAdd={(name) => onActionCreate(phaseId, name)} />
      ) : null}
      {/* n2-properties #19: an action's writeable outputs are bounded by io.outputs,
          edited in the I/O panel 鈥?surfaced here as a non-blocking hint. */}
      <FieldDescription>
        Output fields an action writes are bounded by io.outputs - edit those field boundaries in the I/O panel (toolbar tab 3).
      </FieldDescription>
    </Field>
  )
}

function ActionRow({
  name,
  missingFile = false,
  orphan = false,
  onEdit,
  onDelete,
}: {
  name: string
  missingFile?: boolean
  orphan?: boolean
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-foreground">
      <span className="min-w-0 flex-1 truncate">
        <span aria-hidden className="mr-1.5 text-muted-foreground">&bull;</span>
        {name}
        {orphan ? <span className="ml-1 text-warning">unregistered file</span> : null}
        {missingFile ? <span className="ml-1 text-destructive">missing file</span> : null}
      </span>
      <div className="flex shrink-0 items-center gap-1">
        {onEdit ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className={YAML_ICON_BUTTON_CLASS}
            aria-label={`Edit action ${name}`}
            onClick={onEdit}
          >
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : null}
        {onDelete ? <DeleteActionButton name={name} onConfirm={onDelete} /> : null}
      </div>
    </div>
  )
}

function DeleteActionButton({ name, onConfirm }: { name: string; onConfirm: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className={YAML_ICON_BUTTON_CLASS}
          aria-label={`Delete action ${name}`}
        >
          <Trash2 className="size-3.5" aria-hidden />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete action {name}?</DialogTitle>
          <DialogDescription>
            Removes <span className="font-mono">{name}</span> from this phase and deletes
            <span className="font-mono"> actions/{name}.py</span>. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => {
              setOpen(false)
              onConfirm()
            }}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddActionDialog({ existing, onAdd }: { existing: string[]; onAdd: (name: string) => void }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState("")
  const name = draft.trim()
  const invalid = name.length > 0 && !isValidActionName(name)
  const duplicate = name.length > 0 && existing.includes(name)
  const canAdd = Boolean(name && !invalid && !duplicate)

  useEffect(() => {
    if (open) {
      setDraft("")
    }
  }, [open])

  const submit = () => {
    if (!canAdd) {
      return
    }
    onAdd(name)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" size="sm" variant="secondary" className="mt-1">
          <Plus className="size-3.5" aria-hidden />
          Add action
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add action</DialogTitle>
          <DialogDescription>
            Creates <span className="font-mono">actions/&lt;name&gt;.py</span> with a stub and registers it on this phase.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <form
            className="contents"
            autoComplete="off"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            <FieldLabel htmlFor="action-name-input">Action name</FieldLabel>
            <Input
              id="action-name-input"
              value={draft}
              autoFocus
              spellCheck={false}
              placeholder="strip_noise"
              aria-invalid={invalid || duplicate || undefined}
              onChange={(event) => setDraft(event.currentTarget.value)}
            />
            <FieldDescription>
              A Python identifier 鈥?becomes <span className="font-mono">def &lt;name&gt;(context)</span>.
            </FieldDescription>
            {invalid ? (
              <p className="text-xs text-destructive">Use letters, digits, underscore; not starting with a digit.</p>
            ) : null}
            {duplicate ? <p className="text-xs text-destructive">An action named {name} already exists.</p> : null}
          </form>
        </Field>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={!canAdd} onClick={submit}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AllowSequentialOverwriteField({
  value,
  candidates,
  errors,
  onChange,
}: {
  value: string
  candidates: AllowOverwriteCandidate[]
  errors?: LintError[]
  onChange: (next: string) => void
}) {
  const selectedFields = useMemo(() => overwriteFieldLines(value), [value])
  const setAllowed = (field: string, allowed: boolean) => {
    const next = new Set(selectedFields)
    if (allowed) {
      next.add(field)
    } else {
      next.delete(field)
    }
    onChange([...next].sort((a, b) => a.localeCompare(b)).join("\n"))
  }

  // Rows = union of (a) detected upstream output collisions and (b) fields already
  // written into the YAML array. (b) keeps stale / no-longer-detected entries
  // visible with a Deny button so the author can still clear them. `allowed` means
  // the field is currently in allow_sequential_overwrite.
  const upstreamByField = new Map(candidates.map((candidate) => [candidate.field, candidate.upstreamPhaseIds]))
  const rows = [...new Set([...candidates.map((candidate) => candidate.field), ...selectedFields])]
    .sort((a, b) => a.localeCompare(b))
    .map((field) => ({
      field,
      upstreamPhaseIds: upstreamByField.get(field) ?? [],
      allowed: selectedFields.has(field),
    }))

  return (
    <Field>
      <YamlFieldLabel>
        allow_sequential_overwrite
        <HelpTooltip label="About allow_sequential_overwrite">
          Output fields this phase writes that an upstream phase already wrote to the blackboard. Allow the ones you mean
          to overwrite; any collision left un-allowed is flagged by the engine as an illegal overwrite.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      {rows.length > 0 ? (
        <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
          {rows.map((row) => (
            <div
              key={row.field}
              className="flex items-center justify-between gap-2 text-xs text-foreground"
            >
              <span className="min-w-0 flex-1">
                <span aria-hidden className="mr-1.5 text-muted-foreground">&bull;</span>
                {row.field}
                {row.upstreamPhaseIds.length > 0 ? (
                  <span className="ml-1 text-muted-foreground">
                    from {row.upstreamPhaseIds.join(", ")}
                  </span>
                ) : null}
              </span>
              {row.allowed ? (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="h-6 shrink-0"
                  aria-label={`Deny overwrite for ${row.field}`}
                  onClick={() => setAllowed(row.field, false)}
                >
                  Deny
                </Button>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="default"
                  className="h-6 shrink-0"
                  aria-label={`Allow overwrite for ${row.field}`}
                  onClick={() => setAllowed(row.field, true)}
                >
                  Allow
                </Button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <FieldDescription>
          No upstream phase output collides with this phase&rsquo;s output fields.
        </FieldDescription>
      )}
    </Field>
  )
}

function overwriteFieldLines(value: string): Set<string> {
  return new Set(value.split("\n").map((line) => line.trim()).filter(Boolean))
}

function inferAllowOverwriteCandidates(
  skillDetail: SkillDetail | undefined,
  phaseId: string,
  phaseFilePath: string,
): AllowOverwriteCandidate[] {
  if (!skillDetail) {
    return []
  }
  const currentOutputs = outputFieldsFromPhaseFile(skillDetail, phaseFilePath)
  if (currentOutputs.length === 0) {
    return []
  }

  const topologyById = new Map((skillDetail.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const ancestorIds = transitiveAncestorIds(topologyById, phaseId)
  const candidateMap = new Map<string, Set<string>>()
  for (const ancestorId of ancestorIds) {
    const ancestorPath = phaseFilePathForOutputs(skillDetail, ancestorId)
    if (!ancestorPath) {
      continue
    }
    const ancestorOutputs = new Set(outputFieldsFromPhaseFile(skillDetail, ancestorPath))
    for (const field of currentOutputs) {
      if (!ancestorOutputs.has(field)) {
        continue
      }
      const upstream = candidateMap.get(field) ?? new Set<string>()
      upstream.add(ancestorId)
      candidateMap.set(field, upstream)
    }
  }

  return [...candidateMap.entries()]
    .map(([field, upstreamPhaseIds]) => ({ field, upstreamPhaseIds: [...upstreamPhaseIds].sort((a, b) => a.localeCompare(b)) }))
    .sort((left, right) => left.field.localeCompare(right.field))
}

function phaseFilePathForOutputs(skillDetail: SkillDetail, phaseId: string): string | null {
  const files = skillDetail.files ?? {}
  for (const fileName of ["SKILL.md", "LOGIC.md", "SUBGRAPH.md"]) {
    const candidate = `phases/${phaseId}/${fileName}`
    if (Object.prototype.hasOwnProperty.call(files, candidate)) {
      return candidate
    }
  }
  return null
}

function outputFieldsFromPhaseFile(skillDetail: SkillDetail, path: string): string[] {
  const fileContent = skillDetail.files?.[path]
  if (!fileContent) {
    return []
  }
  const parsed = parsePhaseFrontmatter(fileContent)
  if (!parsed.ok) {
    return []
  }
  const io = recordValue(parsed.frontmatter.io)
  const outputs = recordValue(io?.outputs)
  const properties = recordValue(outputs?.properties)
  return properties ? Object.keys(properties).sort((a, b) => a.localeCompare(b)) : []
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function transitiveAncestorIds(
  topologyById: Map<string, { depends_on?: readonly string[] | null }>,
  phaseId: string,
): Set<string> {
  const ancestors = new Set<string>()
  const queue = [...(topologyById.get(phaseId)?.depends_on ?? [])]
  while (queue.length > 0) {
    const current = queue.shift()
    if (!current || ancestors.has(current)) {
      continue
    }
    ancestors.add(current)
    queue.push(...(topologyById.get(current)?.depends_on ?? []))
  }
  return ancestors
}

function HelpTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
            aria-label={label}
          >
            <CircleHelp className="size-3.5" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-64">
          {/* The base TooltipContent is an inline-flex row; wrap in a single block
              child so prose flows/wraps normally instead of each text run and
              <span> becoming its own flex column. */}
          <div className="space-y-1 text-left text-xs font-normal leading-snug [overflow-wrap:normal]">
            {children}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Generic phase `name` field: read-only display of the phase id with the rename
// action (folder + GRAPH.md refs kept in sync). Shared by LOGIC and SUBGRAPH per
// the skill-spec rule that `name` is changed via a rename action, not a raw textbox.
function PhaseNameField({
  phaseId,
  onPhaseRename,
}: {
  phaseId: string
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
}) {
  return (
    <YamlInputField
      id="phase-name"
      label="name"
      value={phaseId}
      readOnly
      action={onPhaseRename ? (
        <RenamePhaseDialog phaseId={phaseId} onPhaseRename={onPhaseRename} />
      ) : null}
    />
  )
}

function SubgraphPathField({
  value,
  errors,
  skillId,
  workspaceRoot,
  onReconnectFolder,
}: {
  value: string
  errors?: LintError[]
  skillId: string | null
  workspaceRoot: string | null
  onReconnectFolder: () => void
}) {
  const fieldState = subgraphPathFieldState(value, null, workspaceRoot)
  const [diskMissing, setDiskMissing] = useState(false)

  // Confirm the resolved path actually exists on disk via the backend child-graph
  // resolver. A 404 (SUBGRAPH_PATH_NOT_FOUND) means the referenced path does not
  // exist; any non-404/transport error is left un-flagged here (the syntactic
  // state already covers empty/unresolvable paths).
  useEffect(() => {
    if (fieldState.status !== "resolved" || !skillId || !fieldState.path) {
      setDiskMissing(false)
      return
    }
    let cancelled = false
    setDiskMissing(false)
    getChildGraphTopology(skillId, fieldState.path)
      .then(() => {
        if (!cancelled) setDiskMissing(false)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof AxiosError && error.response?.status === 404) {
          setDiskMissing(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [fieldState.status, fieldState.path, skillId])

  const unresolved = fieldState.status !== "resolved" || diskMissing

  return (
    <YamlInputField
      id="phase-path"
      label={(
        <>
          path
          <HelpTooltip label="About path">
            Select the child graph folder that contains GRAPH.md. Studio saves a relative path when it can.
          </HelpTooltip>
          <FieldErrorMarker errors={errors} />
        </>
      )}
      value={value.trim() || "No child graph selected"}
      readOnly
      invalid={unresolved}
      inputClassName="aria-invalid:text-destructive"
      action={(
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className={YAML_ICON_BUTTON_CLASS}
          aria-label="Reconnect path"
          onClick={onReconnectFolder}
        >
          <FolderOpen className="size-3.5" aria-hidden />
        </Button>
      )}
    >
      {unresolved ? (
        <div className="space-y-1.5">
          <p className="text-xs text-destructive">
            {diskMissing
              ? "Path does not resolve to GRAPH.md."
              : "Select a child graph folder."}
          </p>
        </div>
      ) : null}
    </YamlInputField>
  )
}

const ITERATE_OFF_VALUE = "off"
const ITERATE_MODES: Array<{ value: IterateMode | typeof ITERATE_OFF_VALUE; label: string }> = [
  { value: ITERATE_OFF_VALUE, label: "off" },
  { value: "batch", label: "batch" },
  { value: "loop", label: "loop" },
]
const ITERATE_MERGE_MODES: IterateMergeMode[] = ["append", "extend", "merge", "replace"]

function IterateField({
  value,
  errors,
  onChange,
}: {
  value: PhaseIterateFormData
  errors?: LintError[]
  onChange: (next: PhaseIterateFormData) => void
}) {
  const update = (patch: Partial<PhaseIterateFormData>) => onChange({ ...value, ...patch })
  const modeValue = value.mode || ITERATE_OFF_VALUE

  return (
    <Field>
      <YamlFieldLabel htmlFor="phase-iterate-mode">
        iterate
        <HelpTooltip label="About iterate">
          Make this phase run once per item of an array on the blackboard, instead of just once. Leave mode
          <span className="font-mono"> off</span> for a normal single run. I/O fields are edited in the I/O panel.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      <Field>
        <YamlNestedFieldLabel htmlFor="phase-iterate-mode">
          mode
          <HelpTooltip label="About iterate mode">
            <p><span className="font-mono">off</span> 鈥?run once.</p>
            <p><span className="font-mono">batch</span> 鈥?map over the array concurrently, each item independent.</p>
            <p><span className="font-mono">loop</span> 鈥?iterate serially and accumulate results across rounds.</p>
          </HelpTooltip>
        </YamlNestedFieldLabel>
        <Select
          value={modeValue}
          onValueChange={(next) => {
            update({ mode: (next === ITERATE_OFF_VALUE ? "" : next) as IterateMode })
          }}
        >
          <SelectTrigger id="phase-iterate-mode" aria-label="iterate mode" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ITERATE_MODES.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {value.mode ? (
        <div className="space-y-2 pt-1">
          <div className="grid grid-cols-2 gap-2">
            <Field>
              <YamlNestedFieldLabel htmlFor="phase-iterate-over">
                over
                <HelpTooltip label="About over">
                  Path to the array field on the blackboard to iterate, e.g. <span className="font-mono">data.inputs.items</span>.
                  The engine runs this node once per element.
                </HelpTooltip>
              </YamlNestedFieldLabel>
              <Input
                id="phase-iterate-over"
                value={value.over}
                placeholder="data.inputs.items"
                onChange={(event) => update({ over: event.currentTarget.value })}
              />
            </Field>
            <Field>
              <YamlNestedFieldLabel htmlFor="phase-iterate-item-var">
                item_var
                <HelpTooltip label="About item_var">
                  Name under which the current element is injected onto the blackboard each round, so the node can read
                  &ldquo;this item&rdquo;.
                </HelpTooltip>
              </YamlNestedFieldLabel>
              <Input
                id="phase-iterate-item-var"
                value={value.itemVar}
                placeholder="item"
                onChange={(event) => update({ itemVar: event.currentTarget.value })}
              />
            </Field>
          </div>
          <Field>
            <YamlNestedFieldLabel>
              range
              <HelpTooltip label="About range">
                Optional inclusive slice <span className="font-mono">[start, end]</span> (1-based) to iterate only that
                segment of the array. Leave both empty to run the whole array.
              </HelpTooltip>
            </YamlNestedFieldLabel>
            <div className="grid grid-cols-2 gap-2">
              <Input
                aria-label="iterate range start"
                inputMode="numeric"
                value={value.rangeStart}
                placeholder="start"
                onChange={(event) => update({ rangeStart: event.currentTarget.value })}
              />
              <Input
                aria-label="iterate range end"
                inputMode="numeric"
                value={value.rangeEnd}
                placeholder="end"
                onChange={(event) => update({ rangeEnd: event.currentTarget.value })}
              />
            </div>
          </Field>
          {value.mode === "batch" ? (
            <Field>
              <YamlNestedFieldLabel htmlFor="phase-iterate-concurrency">
                concurrency
                <HelpTooltip label="About concurrency">
                  Batch mode only. Max number of items processed at the same time (integer &ge; 1).
                </HelpTooltip>
              </YamlNestedFieldLabel>
              <Input
                id="phase-iterate-concurrency"
                inputMode="numeric"
                value={value.concurrency}
                placeholder="1"
                onChange={(event) => update({ concurrency: event.currentTarget.value })}
              />
            </Field>
          ) : null}
          {value.mode === "loop" ? (
            <div className="space-y-2">
              <YamlNestedFieldLabel>
                accumulate
                <HelpTooltip label="About accumulate">
                  Loop mode only. Declares how each round&rsquo;s output is gathered into a running value that the next
                  round can read.
                </HelpTooltip>
              </YamlNestedFieldLabel>
              {/* Frame accumulate.* sub-properties in the shared Card box (the same
                  bordered card used in Settings > General) so they read as belonging
                  to accumulate. Reuses @/components/ui/card, no new style. */}
              <Card size="sm">
                <CardContent className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <Field>
                      <YamlNestedFieldLabel htmlFor="phase-iterate-accumulate-var">
                        accumulate.var
                        <HelpTooltip label="About accumulate.var">
                          Name of the running accumulator. Each round it is injected onto the blackboard holding everything
                          gathered so far, so the next round can build on it.
                        </HelpTooltip>
                      </YamlNestedFieldLabel>
                      <Input
                        id="phase-iterate-accumulate-var"
                        value={value.accumulateVar}
                        placeholder="collected"
                        onChange={(event) => update({ accumulateVar: event.currentTarget.value })}
                      />
                    </Field>
                    <Field>
                      <YamlNestedFieldLabel htmlFor="phase-iterate-accumulate-from">
                        accumulate.from
                        <HelpTooltip label="About accumulate.from">
                          Which field of this round&rsquo;s output to take as the increment that gets merged into the
                          accumulator.
                        </HelpTooltip>
                      </YamlNestedFieldLabel>
                      <Input
                        id="phase-iterate-accumulate-from"
                        value={value.accumulateFrom}
                        placeholder="piece"
                        onChange={(event) => update({ accumulateFrom: event.currentTarget.value })}
                      />
                    </Field>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Field>
                      <YamlNestedFieldLabel htmlFor="phase-iterate-accumulate-init">
                        accumulate.init
                        <HelpTooltip label="About accumulate.init">
                          Initial value of the accumulator as JSON, e.g. <span className="font-mono">[]</span> or
                          <span className="font-mono"> {"{}"}</span>, before the first round runs.
                        </HelpTooltip>
                      </YamlNestedFieldLabel>
                      <Input
                        id="phase-iterate-accumulate-init"
                        value={value.accumulateInit}
                        placeholder="[]"
                        onChange={(event) => update({ accumulateInit: event.currentTarget.value })}
                      />
                    </Field>
                    <Field>
                      <YamlNestedFieldLabel htmlFor="phase-iterate-accumulate-merge">
                        accumulate.merge
                        <HelpTooltip label="About accumulate.merge">
                          <p>How each increment joins the accumulator:</p>
                          <p><span className="font-mono">append</span> 鈥?add the increment as one item.</p>
                          <p><span className="font-mono">extend</span> 鈥?concatenate a list of items.</p>
                          <p><span className="font-mono">merge</span> 鈥?merge objects key by key.</p>
                          <p><span className="font-mono">replace</span> 鈥?overwrite with the latest value.</p>
                        </HelpTooltip>
                      </YamlNestedFieldLabel>
                      <Select
                        value={value.accumulateMerge}
                        onValueChange={(next) => update({ accumulateMerge: next as IterateMergeMode })}
                      >
                        <SelectTrigger id="phase-iterate-accumulate-merge" aria-label="accumulate merge" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ITERATE_MERGE_MODES.map((mode) => (
                            <SelectItem key={mode} value={mode}>
                              {mode}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </div>
      ) : null}
    </Field>
  )
}

export function RoleTestControl({
  roleName,
  roleTest,
  onRoleTest,
  disabled = false,
}: {
  roleName: string
  roleTest: RoleTestStatusInput
  onRoleTest: (roleName: string) => void
  disabled?: boolean
}) {
  const badge = roleTestStatusBadge(roleTest)
  const showBadge = badge.running || roleTest.status != null || Boolean(roleTest.error)
  const details = roleTestTooltipDetails(roleTest)
  const tooltipLabel = [badge.label, ...details].join("\n")
  const badgeNode = showBadge ? (
    <Badge
      variant={badge.variant}
      className="h-6 max-w-48"
      aria-label={details.length > 0 ? tooltipLabel : undefined}
    >
      {badge.running ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
      <span className="truncate">{badge.label}</span>
    </Badge>
  ) : null
  return (
    <div className="flex shrink-0 items-center gap-2">
      {badgeNode && details.length > 0 ? (
        <span data-role-test-status-tooltip="true">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>{badgeNode}</TooltipTrigger>
              <TooltipContent className="max-w-sm">
                <div className="space-y-1 whitespace-normal">
                  <div className="font-medium">{badge.label}</div>
                  {details.map((detail) => (
                    <div key={detail} className="break-words text-background/90">
                      {detail}
                    </div>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </span>
      ) : (
        badgeNode
      )}
      <Button
        type="button"
        size="icon"
        variant="default"
        data-llm-role-test-trigger="true"
        aria-label={roleName.trim() ? `Test LLM role ${roleName}` : "Test LLM role"}
        disabled={disabled || badge.running || roleName.trim().length === 0}
        onClick={() => onRoleTest(roleName)}
      >
        {badge.running
          ? <Loader2 data-llm-role-test-icon="true" className="size-3 animate-spin" aria-hidden />
          : <FlaskConical data-llm-role-test-icon="true" className="size-3.5" aria-hidden />}
      </Button>
    </div>
  )
}

function roleTestTooltipDetails(roleTest: RoleTestStatusInput): string[] {
  const details = uniqueStrings([
    ...(roleTest.details ?? []),
    roleTest.error ?? null,
  ].filter((detail): detail is string => Boolean(detail?.trim())))
  if (details.length > 0) return details
  if (roleTest.status === "warning") {
    return ["One or more provider routes need attention; rerun the test for provider diagnostics."]
  }
  if (roleTest.status === "blocked" || roleTest.status === "failed") {
    return ["The selected role has no currently usable provider route."]
  }
  return []
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>()
  return values.filter((value) => {
    const normalized = value.trim()
    if (!normalized || seen.has(normalized)) return false
    seen.add(normalized)
    return true
  })
}

// validator gates on whether the sibling validator.py EXISTS. No file 鈫?there is no
// switch, only a "Create validator.py" action (scaffolds a passing stub + flips the
// flag on). File present 鈫?the on/off switch plus an Edit button. Mirrors the user's
// rule that the toggle is only meaningful once the file backing it exists.
function ValidatorField({
  value,
  errors,
  phaseId,
  files,
  skillId,
  workspaceRoot,
  onChange,
  onValidatorCreate,
  onFileOpen,
}: {
  value: boolean
  errors?: LintError[]
  phaseId: string
  files?: Record<string, string>
  skillId: string | null
  workspaceRoot: string | null
  onChange: (next: boolean) => void
  onValidatorCreate?: (phaseId: string) => Promise<void> | void
  onFileOpen?: (fileOrPath: FileOpenInput) => void
}) {
  const filePath = validatorFilePath(phaseId)
  const fileExists = files != null && files[filePath] !== undefined

  return (
    <Field orientation="horizontal" className="items-center justify-between gap-3">
      <YamlFieldLabel
        htmlFor="phase-validator"
        className="min-w-0"
        onClick={(event) => event.preventDefault()}
      >
        validator
        <HelpTooltip label="About validator">
          When on, the engine runs this node&rsquo;s sibling <span className="font-mono">validator.py</span> after the
          node finishes to check its output (return None to pass). Create the file to enable it.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      {fileExists ? (
        <div className="flex shrink-0 items-center gap-2">
          {onFileOpen ? (
            <Button
              type="button"
              size="icon"
              variant="secondary"
              className={YAML_ICON_BUTTON_CLASS}
              aria-label="Edit validator.py"
              onClick={() => onFileOpen({ path: filePath, skillId, workspaceRoot, language: "python", saveEnabled: true })}
            >
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : null}
          <Switch
            id="phase-validator"
            size="sm"
            checked={value}
            onCheckedChange={onChange}
            aria-label="Validator"
          />
        </div>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="shrink-0"
          disabled={!onValidatorCreate}
          onClick={() => onValidatorCreate?.(phaseId)}
        >
          <Plus className="size-3.5" aria-hidden />
          Create validator.py
        </Button>
      )}
    </Field>
  )
}

/**
 * Per-field lint marker (authoring N3 atom #5): an inline warning/error glyph next to a
 * frontmatter field whose engine `field_path` matched a diagnostic. Hover lists the
 * message(s). Mirrors the canvas node badge idiom (SkillNode: AlertTriangle + Tooltip),
 * reusing shadcn Tooltip and severity tokens - never a hand-rolled popover or raw color.
 */
function FieldErrorMarker({ errors }: { errors?: LintError[] | null }) {
  if (!errors || errors.length === 0) {
    return null
  }
  const hasError = errors.some((error) => error.severity === "error")
  const tone = hasError ? "text-destructive" : "text-warning"
  const count = errors.length === 1 ? "1 issue" : `${errors.length} issues`
  const messages = errors.map((error) => error.message)
  // The joined messages live on the trigger's accessible name so the diagnostic
  // is reachable without opening the styled Tooltip (UI-spec §2.7: no native
  // title alongside the Radix tooltip).
  const accessibleSummary = `Field has ${count}: ${messages.join("; ")}`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={accessibleSummary}
          className={`ms-1 inline-flex items-center align-middle ${tone}`}
        >
          <AlertTriangle className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        <ul className="space-y-0.5">
          {messages.map((message, index) => (
            <li key={`${errors[index]?.error_code ?? "err"}-${index}`}>{message}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  )
}

function SubagentsField({
  value,
  onChange,
}: {
  value: PhaseSubagentRef[]
  onChange: (next: PhaseSubagentRef[]) => void
}) {
  const update = (index: number, patch: Partial<PhaseSubagentRef>) => {
    onChange(value.map((entry, idx) => (idx === index ? { ...entry, ...patch } : entry)))
  }
  const remove = (index: number) => {
    onChange(value.filter((_, idx) => idx !== index))
  }
  const add = () => {
    onChange([...value, { name: "", target_skill: "", description: "" }])
  }

  return (
    <Field>
      <YamlFieldLabel>
        subagents
        <HelpTooltip label="About subagents">
          Sub-agents this agent can delegate to at runtime. <span className="font-mono">name</span> is referenced in the
          body with <span className="font-mono">@subagent:&lt;name&gt;</span>; <span className="font-mono">target_skill</span>
          {" "}points at the agent skill being delegated to.
        </HelpTooltip>
      </YamlFieldLabel>
      <div className="space-y-2">
        {value.map((entry, index) => (
          <div key={index} className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
            <Input
              aria-label={`Subagent ${index + 1} name`}
              value={entry.name}
              placeholder="name"
              onChange={(event) => update(index, { name: event.currentTarget.value })}
            />
            <Input
              aria-label={`Subagent ${index + 1} target skill`}
              value={entry.target_skill}
              placeholder="target_skill"
              onChange={(event) => update(index, { target_skill: event.currentTarget.value })}
            />
            <Input
              aria-label={`Subagent ${index + 1} description`}
              value={entry.description}
              placeholder="description"
              onChange={(event) => update(index, { description: event.currentTarget.value })}
            />
            <div className="flex justify-end">
              <Button type="button" size="sm" variant="ghost" onClick={() => remove(index)}>
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Button type="button" size="sm" variant="secondary" className="mt-1" onClick={add}>
        Add subagent
      </Button>
    </Field>
  )
}

// llm_role as a dropdown of CONFIGURED roles (GET /llm/roles). "Use graph
// default" is the PERSISTED use_graph_llm_role frontmatter switch: on = the
// graph-level default role wins at run time and the whole Run role row is
// disabled; the node's own llm_role value stays in the markdown untouched.
function LlmRoleField({
  value,
  useGraphDefault,
  roleNames,
  modelGroups,
  roleTest,
  errors,
  skillId,
  nodeId,
  onChange,
  onUseGraphDefaultChange,
  onRoleTest,
  onOpenSettings,
  onSelectGraph,
  onStartNodeCompare,
}: {
  value: string
  useGraphDefault: boolean
  roleNames: string[]
  modelGroups: ModelGroup[]
  roleTest: RoleTestStatusInput
  errors?: LintError[]
  skillId?: string | null
  nodeId?: string | null
  onChange: (next: string) => void
  onUseGraphDefaultChange: (next: boolean) => void
  onRoleTest: (roleName: string) => void
  onOpenSettings?: (tab?: SettingsTab) => void
  onSelectGraph?: () => void
  onStartNodeCompare?: (nodeId: string) => void
}) {
  const trimmed = value.trim()
  const options = useMemo(
    () => (trimmed && !roleNames.includes(trimmed) ? [trimmed, ...roleNames] : roleNames),
    [roleNames, trimmed],
  )
  const roleComboboxOptions = useMemo<SearchableComboboxOption[]>(
    () => options.map((name) => llmRoleComboboxOption(name, roleNames.includes(name))),
    [options, roleNames],
  )

  return (
    <Field>
      <YamlFieldLabel htmlFor="phase-llm-role">
        llm_role
        <HelpTooltip label="About llm_role">
          The configured LLM role this agent runs as. Turn &ldquo;Use graph default&rdquo; on to run with the
          graph&rsquo;s llm_role (the node&rsquo;s own pick is kept, just inactive). Manage roles in
          Settings &rsaquo; LLM Roles; test the graph default in the graph properties.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      <Field orientation="horizontal" className="items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-1.5">
          <YamlNestedFieldLabel
            htmlFor="phase-llm-role-default"
            className="min-w-0"
            onClick={(event) => event.preventDefault()}
          >
            Use graph default
          </YamlNestedFieldLabel>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
                  aria-label="Open graph properties"
                  data-llm-role-graph-trigger="true"
                  onClick={() => onSelectGraph?.()}
                >
                  <Settings className="size-3.5" aria-hidden />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">Open graph properties</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <Switch
          id="phase-llm-role-default"
          size="sm"
          checked={useGraphDefault}
          aria-label="Use graph default llm_role"
          onCheckedChange={onUseGraphDefaultChange}
        />
      </Field>
      <div className="space-y-2">
        <div
          className="space-y-1"
          {...(useGraphDefault ? { "data-llm-role-row-disabled": "true" } : {})}
        >
          <YamlNestedFieldLabel
            htmlFor="phase-llm-role"
            className={useGraphDefault ? "opacity-50" : undefined}
          >
            Run role
          </YamlNestedFieldLabel>
          <div className="flex items-center gap-2">
            <SearchableOptionCombobox
              id="phase-llm-role"
              value={trimmed}
              options={roleComboboxOptions}
              onChange={onChange}
              ariaLabel="llm_role"
              placeholder="No node role"
              searchPlaceholder="Search roles"
              emptyLabel="No role found."
              triggerClassName="min-w-0 flex-1"
              disabled={useGraphDefault}
            />
            <LlmRoleSettingsButton onOpenSettings={onOpenSettings} disabled={useGraphDefault} />
            <RoleTestControl
              roleName={trimmed}
              roleTest={roleTest}
              onRoleTest={onRoleTest}
              disabled={useGraphDefault}
            />
          </div>
        </div>
      </div>
      <LlmNodeCompareField
        modelGroups={modelGroups}
        skillId={skillId}
        nodeId={nodeId}
        onStartNodeCompare={onStartNodeCompare}
      />
      <LlmNodeParamsField skillId={skillId} nodeId={nodeId} roleName={value} modelGroups={modelGroups} />
    </Field>
  )
}

interface NodeLlmParamsDraft {
  thinking: boolean | null
  maxOutputTokens: string
  temperature: string
}

const EMPTY_NODE_LLM_PARAMS_DRAFT: NodeLlmParamsDraft = {
  thinking: null,
  maxOutputTokens: "",
  temperature: "",
}

export function nodeLlmParamsDraftFromApi(params: NodeLlmParams | undefined): NodeLlmParamsDraft {
  if (!params) return EMPTY_NODE_LLM_PARAMS_DRAFT
  return {
    thinking: params.thinking ?? null,
    maxOutputTokens: params.max_output_tokens != null ? String(params.max_output_tokens) : "",
    temperature: params.temperature != null ? String(params.temperature) : "",
  }
}

export function nodeLlmParamsDraftToApi(draft: NodeLlmParamsDraft): NodeLlmParams {
  return {
    thinking: draft.thinking,
    max_output_tokens: nodeParamOptionalInteger(draft.maxOutputTokens),
    temperature: nodeParamOptionalNumber(draft.temperature),
  }
}

function nodeParamOptionalInteger(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : null
}

function nodeParamOptionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

// PR3: per-node DIRECT overrides of the three simple LLM params. No enable
// switch — each empty field simply inherits the role default. Loads the node's
// stored overrides on mount and persists the full triple on every change,
// mirroring LlmNodeCompareField's load-effect + save-on-change pattern.
function LlmNodeParamsField({
  skillId = null,
  nodeId = null,
  roleName = "",
  modelGroups = [],
}: {
  skillId?: string | null
  nodeId?: string | null
  roleName?: string
  modelGroups?: ModelGroup[]
}) {
  const [draft, setDraft] = useState<NodeLlmParamsDraft>(EMPTY_NODE_LLM_PARAMS_DRAFT)
  const { data: rolesData } = useSWR("llm/roles", getRoles, { shouldRetryOnError: false })

  useEffect(() => {
    if (!skillId || !nodeId) {
      setDraft(EMPTY_NODE_LLM_PARAMS_DRAFT)
      return
    }
    let cancelled = false
    void getNodeLlmParams(skillId)
      .then((map) => {
        if (cancelled) return
        setDraft(nodeLlmParamsDraftFromApi(map.nodes[nodeId]))
      })
      .catch(() => {
        if (!cancelled) setDraft(EMPTY_NODE_LLM_PARAMS_DRAFT)
      })
    return () => {
      cancelled = true
    }
  }, [skillId, nodeId])

  const persist = useCallback(
    (next: NodeLlmParamsDraft) => {
      if (!skillId || !nodeId) return
      void putNodeLlmParams(skillId, nodeId, nodeLlmParamsDraftToApi(next)).catch((error) => {
        toast.error(error instanceof Error ? error.message : "Could not save model params")
      })
    },
    [skillId, nodeId],
  )

  const update = (next: NodeLlmParamsDraft) => {
    setDraft(next)
    persist(next)
  }

  const thinkingId = `node-thinking-${nodeId ?? "none"}`
  const maxOutputId = `node-max-output-${nodeId ?? "none"}`
  const temperatureId = `node-temperature-${nodeId ?? "none"}`

  // Infer the concrete output-token cap this node would use: the effective role's
  // route max (same computation as the Settings role card). Shown as the max
  // output field's placeholder so an empty (inherit) field still reveals the number.
  const providerModelsByRouteId = useMemo(() => {
    const map = new Map<string, ProviderModelOption>()
    for (const group of modelGroups) {
      for (const providerModel of group.provider_models) {
        map.set(providerModel.route_id, providerModel)
      }
    }
    return map
  }, [modelGroups])
  const effectiveRole = roleName.trim() || "graph_agent"
  const roleEntry = rolesData?.roles?.[effectiveRole]
  const inferredOutputMax = roleEntry
    ? roleTokenLimitSummary(roleEntry, providerModelsByRouteId).output.max
    : null
  const maxOutputPlaceholder = inferredOutputMax != null ? formatThousands(String(inferredOutputMax)) : "Inherit"

  return (
    <div className="mt-2 space-y-1.5" data-llm-node-params="true">
      <YamlNestedFieldLabel>
        Model params
        <HelpTooltip label="About model params">
          Per-node overrides of this node&rsquo;s LLM generation params, winning over the role default.
          Leave a field on <span className="font-mono">Inherit</span> / empty to use the role&rsquo;s value.
        </HelpTooltip>
      </YamlNestedFieldLabel>
      {/* Frame the params in the shared Card box, one field per row (each field's
          label sits directly above its own control, so nothing reads as crowded
          or ambiguous about which label belongs to which control). Per-field
          widgets: thinking = Switch, temperature = Slider, max output tokens =
          number Input. Reuses @/components/ui, no new style. */}
      <Card size="sm">
        <CardContent className="space-y-3">
          <Field
            orientation="horizontal"
            className="min-h-9 items-center justify-between gap-3"
          >
            <YamlNestedFieldLabel htmlFor={thinkingId} className="min-w-0">
              thinking
              <HelpTooltip label="About thinking">
                Whether this node asks the model to use reasoning/thinking. Best-effort: only
                applies when the node&rsquo;s model supports it.
              </HelpTooltip>
            </YamlNestedFieldLabel>
            <Switch
              id={thinkingId}
              size="sm"
              data-llm-node-thinking="true"
              checked={draft.thinking === true}
              aria-label="Node thinking override"
              onCheckedChange={(thinking) => update({ ...draft, thinking })}
            />
          </Field>
          <Field className="min-h-14 gap-1">
            <YamlNestedFieldLabel htmlFor={maxOutputId}>
              max output tokens
              <HelpTooltip label="About max output tokens">
                Cap on this node&rsquo;s output tokens. Empty inherits the role default (the placeholder
                shows that inferred max); a value over the route&rsquo;s max is clamped down to it.
              </HelpTooltip>
            </YamlNestedFieldLabel>
            <Input
              id={maxOutputId}
              data-llm-node-max-output="true"
              aria-label="Node max output tokens override"
              value={formatThousands(draft.maxOutputTokens)}
              onChange={(event) => update({ ...draft, maxOutputTokens: stripThousands(event.target.value) })}
              inputMode="numeric"
              placeholder={maxOutputPlaceholder}
            />
          </Field>
          <Field className="min-h-14 gap-1">
            <YamlNestedFieldLabel htmlFor={temperatureId}>
              temperature
              <HelpTooltip label="About temperature">
                Sampling temperature (0&ndash;2) for this node. Drag to override the role default.
              </HelpTooltip>
            </YamlNestedFieldLabel>
            <div className="flex h-9 items-center gap-2">
              <Slider
                id={temperatureId}
                data-llm-node-temperature="true"
                aria-label="Node temperature override"
                min={0}
                max={2}
                step={0.1}
                value={[draft.temperature === "" ? 1 : Number(draft.temperature)]}
                onValueChange={(vals) => setDraft({ ...draft, temperature: String(vals[0]) })}
                onValueCommit={(vals) => persist({ ...draft, temperature: String(vals[0]) })}
                className="flex-1"
              />
              <span className="w-9 shrink-0 text-right text-xs text-foreground">
                {draft.temperature === "" ? "—" : draft.temperature}
              </span>
            </div>
          </Field>
        </CardContent>
      </Card>
    </div>
  )
}

function llmRoleComboboxOption(name: string, configured: boolean): SearchableComboboxOption {
  const option = llmRoleSelectOptionState(name, configured)
  const next: SearchableComboboxOption = {
    value: name,
    label: option.label,
    searchValue: `${name} ${option.label}`,
    unconfigured: option.unconfigured,
  }
  if (option.title) {
    next.detail = option.title
  }
  return next
}

function LlmRoleSettingsButton({
  onOpenSettings,
  disabled = false,
}: {
  onOpenSettings?: (tab?: SettingsTab) => void
  disabled?: boolean
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className={YAML_ICON_BUTTON_CLASS}
          aria-label="Open LLM Roles settings"
          data-llm-role-settings-trigger="true"
          disabled={disabled}
          onClick={() => onOpenSettings?.("llm_roles")}
        >
          <Settings2 className="size-3.5" aria-hidden />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Open LLM Roles settings</TooltipContent>
    </Tooltip>
  )
}

export function llmRoleSelectOptionState(name: string, configured: boolean): {
  label: string
  title?: string
  unconfigured: boolean
} {
  if (configured) {
    return { label: name, unconfigured: false }
  }
  return {
    label: `${name} (not configured)`,
    title: `${name} is not configured in LLM Roles`,
    unconfigured: true,
  }
}

interface LlmCompareCandidateDraft {
  id: string
  modelGroupId: string
  route: string
}

export interface LlmCompareTestResult {
  status: RoleTestStatus
  summary: string
  details: string[]
}

export interface LlmCompareTestState {
  running: boolean
  result?: LlmCompareTestResult
  error?: string
}

const EMPTY_COMPARE_TEST_STATE: LlmCompareTestState = { running: false }

function compareCandidateRouteId(route: string): string | null {
  const trimmed = route.trim()
  return trimmed.startsWith("route:") ? trimmed.replace(/^route:/, "").trim() || null : null
}

async function runCompareCandidateTest(
  modelGroupId: string,
  route: string,
): Promise<LlmCompareTestResult> {
  const routeId = compareCandidateRouteId(route)
  const result = await runRoleTestJobToResult(modelGroupId, {
    startJob: () => startCompareCandidateTestJob({
      canonical_id: modelGroupId,
      route_id: routeId,
    }),
  })
  return compareTestResultFromRoleTest(result)
}

function compareTestResultFromRoleTest(result: RoleTestResponse): LlmCompareTestResult {
  return {
    status: result.status,
    summary: compareTestSummary(result.status),
    details: roleTestDetailsFromResult(result),
  }
}

function compareTestSummary(status: RoleTestStatus): string {
  if (status === "ok") return "Test passed"
  if (status === "warning") return "Needs Attention"
  return "Test failed"
}

function compareStatusToRouteStatus(state: LlmCompareTestState | undefined): RoleRouteStatus | null {
  if (state?.running) return "testing"
  if (state?.error) return "blocked"
  if (state?.result?.status === "ok") return "runnable"
  if (state?.result?.status === "warning") return "limited"
  if (state?.result?.status === "blocked" || state?.result?.status === "failed") return "blocked"
  // Never tested -> no light at all (a "limited" amber here would misread as
  // a degraded test result).
  return null
}

function draftToApiCandidate(draft: LlmCompareCandidateDraft): CompareCandidate {
  return { candidate_id: draft.id, model_group_id: draft.modelGroupId, route: draft.route || "auto" }
}

function apiToDraftCandidate(candidate: CompareCandidate): LlmCompareCandidateDraft {
  return { id: candidate.candidate_id, modelGroupId: candidate.model_group_id, route: candidate.route || "auto" }
}

function LlmNodeCompareField({
  modelGroups,
  skillId = null,
  nodeId = null,
  onStartNodeCompare,
}: {
  modelGroups: ModelGroup[]
  skillId?: string | null
  nodeId?: string | null
  onStartNodeCompare?: (nodeId: string) => void
}) {
  const nextCandidateId = useRef(0)
  const [open, setOpen] = useState(false)
  const [candidates, setCandidates] = useState<LlmCompareCandidateDraft[]>([])

  // Load this node's persisted compare candidates (studio backend, per skill+node).
  useEffect(() => {
    if (!skillId || !nodeId) {
      setCandidates([])
      return
    }
    let cancelled = false
    void getCompareCandidates(skillId)
      .then((map) => {
        if (cancelled) return
        const stored = map.nodes[nodeId] ?? []
        setCandidates(stored.map(apiToDraftCandidate))
        // Seed the id counter past any loaded `compare-N` id so new adds never collide.
        const maxN = stored.reduce((acc, c) => {
          const match = /^compare-(\d+)$/.exec(c.candidate_id)
          return match ? Math.max(acc, Number(match[1])) : acc
        }, 0)
        nextCandidateId.current = maxN
      })
      .catch(() => {
        if (!cancelled) setCandidates([])
      })
    return () => {
      cancelled = true
    }
  }, [skillId, nodeId])

  // Persist the node's full candidate list (an empty list clears the node).
  const persistCandidates = useCallback(
    (next: LlmCompareCandidateDraft[]) => {
      if (!skillId || !nodeId) return
      void putNodeCompareCandidates(skillId, nodeId, next.map(draftToApiCandidate)).catch((error) => {
        toast.error(
          error instanceof Error ? error.message : "Could not save compare candidates",
        )
      })
    },
    [skillId, nodeId],
  )
  const [draftModelGroupId, setDraftModelGroupId] = useState("")
  const [draftRoute, setDraftRoute] = useState("auto")
  const [draftTestState, setDraftTestState] = useState<LlmCompareTestState>(EMPTY_COMPARE_TEST_STATE)
  const [editOpen, setEditOpen] = useState(false)
  const [editingCandidateId, setEditingCandidateId] = useState<string | null>(null)
  const [editModelGroupId, setEditModelGroupId] = useState("")
  const [editRoute, setEditRoute] = useState("auto")
  const [editTestState, setEditTestState] = useState<LlmCompareTestState>(EMPTY_COMPARE_TEST_STATE)
  const [compareTests, setCompareTests] = useState<Record<string, LlmCompareTestState>>({})
  const modelOptions = useMemo<SearchableComboboxOption[]>(
    () => modelGroups.map((group) => {
      const option: SearchableComboboxOption = {
        value: group.canonical_id,
        label: modelGroupPickerLabel(group),
        searchValue: llmCompareModelGroupSearchValue(group),
      }
      option.section = modelGroupSectionLabel(group)
      return option
    }),
    [modelGroups],
  )
  const defaultModelGroupId = modelGroups[0]?.canonical_id ?? ""
  const draftGroup = modelGroups.find((group) => group.canonical_id === draftModelGroupId) ?? null
  const draftEndpointOptions = useMemo<SearchableComboboxOption[]>(
    () => endpointComboboxOptions(modelGroupRouteOptions(draftGroup)),
    [draftGroup],
  )
  const editGroup = modelGroups.find((group) => group.canonical_id === editModelGroupId) ?? null
  const editEndpointOptions = useMemo<SearchableComboboxOption[]>(
    () => endpointComboboxOptions(modelGroupRouteOptions(editGroup)),
    [editGroup],
  )

  useEffect(() => {
    if (!draftModelGroupId || !modelGroups.some((group) => group.canonical_id === draftModelGroupId)) {
      setDraftModelGroupId(defaultModelGroupId)
      setDraftRoute("auto")
    }
  }, [defaultModelGroupId, draftModelGroupId, modelGroups])

  useEffect(() => {
    if (!draftEndpointOptions.some((option) => option.value === draftRoute)) {
      setDraftRoute("auto")
    }
  }, [draftEndpointOptions, draftRoute])

  useEffect(() => {
    if (!editOpen) return
    if (!editModelGroupId || !modelGroups.some((group) => group.canonical_id === editModelGroupId)) {
      setEditModelGroupId(defaultModelGroupId)
      setEditRoute("auto")
    }
  }, [defaultModelGroupId, editModelGroupId, editOpen, modelGroups])

  useEffect(() => {
    if (!editOpen) return
    if (!editEndpointOptions.some((option) => option.value === editRoute)) {
      setEditRoute("auto")
    }
  }, [editEndpointOptions, editOpen, editRoute])

  const addCandidate = () => {
    if (!draftGroup) return
    nextCandidateId.current += 1
    const candidateId = `compare-${nextCandidateId.current}`
    const next = [
      ...candidates,
      {
        id: candidateId,
        modelGroupId: draftGroup.canonical_id,
        route: draftRoute,
      },
    ]
    setCandidates(next)
    persistCandidates(next)
    if (draftTestState.result || draftTestState.error || draftTestState.running) {
      setCompareTests((current) => ({ ...current, [candidateId]: draftTestState }))
    }
    setDraftTestState(EMPTY_COMPARE_TEST_STATE)
    setOpen(false)
  }

  const openEditCandidate = (candidate: LlmCompareCandidateDraft) => {
    setEditingCandidateId(candidate.id)
    setEditModelGroupId(candidate.modelGroupId)
    setEditRoute(candidate.route)
    setEditTestState(compareTests[candidate.id] ?? EMPTY_COMPARE_TEST_STATE)
    setEditOpen(true)
  }

  const saveCandidateEdit = () => {
    if (!editingCandidateId || !editGroup) return
    const next = candidates.map((candidate) => (
      candidate.id === editingCandidateId
        ? { ...candidate, modelGroupId: editGroup.canonical_id, route: editRoute }
        : candidate
    ))
    setCandidates(next)
    persistCandidates(next)
    setCompareTests((current) => {
      if (editTestState.result || editTestState.error || editTestState.running) {
        return { ...current, [editingCandidateId]: editTestState }
      }
      const next = { ...current }
      delete next[editingCandidateId]
      return next
    })
    setEditOpen(false)
    setEditingCandidateId(null)
    setEditTestState(EMPTY_COMPARE_TEST_STATE)
  }

  const removeCandidate = (candidateId: string) => {
    const next = candidates.filter((candidate) => candidate.id !== candidateId)
    setCandidates(next)
    persistCandidates(next)
    setCompareTests((current) => {
      const rest = { ...current }
      delete rest[candidateId]
      return rest
    })
  }

  const runDraftCompareTest = async () => {
    if (!draftGroup) return
    setDraftTestState({ running: true })
    try {
      const result = await runCompareCandidateTest(draftGroup.canonical_id, draftRoute)
      setDraftTestState({ running: false, result })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Compare LLM test failed"
      setDraftTestState({ running: false, error: message })
      toast.error(message)
    }
  }

  const runEditCompareTest = async () => {
    if (!editGroup) return
    setEditTestState({ running: true })
    try {
      const result = await runCompareCandidateTest(editGroup.canonical_id, editRoute)
      setEditTestState({ running: false, result })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Compare LLM test failed"
      setEditTestState({ running: false, error: message })
      toast.error(message)
    }
  }

  const runCandidateCompareTest = async (candidate: LlmCompareCandidateDraft) => {
    setCompareTests((current) => ({ ...current, [candidate.id]: { running: true } }))
    try {
      const result = await runCompareCandidateTest(candidate.modelGroupId, candidate.route)
      setCompareTests((current) => ({ ...current, [candidate.id]: { running: false, result } }))
    } catch (error) {
      const message = error instanceof Error ? error.message : "Compare LLM test failed"
      setCompareTests((current) => ({ ...current, [candidate.id]: { running: false, error: message } }))
      toast.error(message)
    }
  }

  return (
    <div className="mt-2 space-y-1.5">
      <YamlNestedFieldLabel>Compare LLMs</YamlNestedFieldLabel>
      <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2" aria-label="LLM compare candidates">
        {candidates.length > 0
          ? candidates.map((candidate) => (
            <LlmCompareCandidateRow
              key={candidate.id}
              candidate={candidate}
              modelGroups={modelGroups}
              testState={compareTests[candidate.id]}
              onTest={runCandidateCompareTest}
              onEdit={openEditCandidate}
              onRemove={removeCandidate}
            />
          ))
          : <FieldDescription>No compare LLMs yet.</FieldDescription>}
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            data-llm-role-compare-trigger="true"
            aria-label="Add LLM compare candidate"
            className="mt-1 w-full"
          >
            <Plus className="size-3.5" aria-hidden />
            Add compare LLM
          </Button>
        </DialogTrigger>
        <DialogContent className="min-w-0 overflow-hidden sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add compare LLM</DialogTitle>
            <DialogDescription>
              Choose a model candidate for this node. Saved with the node in the workspace, not SKILL.md.
            </DialogDescription>
          </DialogHeader>
          <div className="min-w-0 space-y-3">
            <Field className="min-w-0">
              <FieldLabel>Model</FieldLabel>
              <SearchableOptionCombobox
                value={draftModelGroupId}
                options={modelOptions}
                onChange={(next) => {
                  setDraftModelGroupId(next)
                  setDraftRoute("auto")
                  setDraftTestState(EMPTY_COMPARE_TEST_STATE)
                }}
                ariaLabel="Compare model"
                placeholder={modelOptions.length > 0 ? "Choose model" : "No models"}
                searchPlaceholder="Search models"
                emptyLabel="No model found."
                disabled={modelOptions.length === 0}
                dataSelectAttribute="data-llm-compare-model-group-select"
                dataSearchAttribute="data-llm-compare-model-group-search"
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel>Endpoint</FieldLabel>
              <SearchableOptionCombobox
                value={draftRoute}
                options={draftEndpointOptions}
                onChange={(next) => {
                  setDraftRoute(next)
                  setDraftTestState(EMPTY_COMPARE_TEST_STATE)
                }}
                ariaLabel="Compare model endpoint"
                placeholder="Auto fallback"
                emptyLabel="No endpoint found."
                searchable={false}
                disabled={!draftGroup}
              />
            </Field>
            <LlmCompareTestResultPanel state={draftTestState} />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="default"
              disabled={!draftGroup || draftTestState.running}
              data-llm-compare-dialog-test-trigger="true"
              onClick={runDraftCompareTest}
            >
              {draftTestState.running
                ? <Loader2 data-llm-compare-test-icon="true" className="size-3 animate-spin" aria-hidden />
                : <FlaskConical data-llm-compare-test-icon="true" className="size-3.5" aria-hidden />}
              Test
            </Button>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={!draftGroup} onClick={addCandidate}>
              <Plus className="size-3.5" aria-hidden />
              Add candidate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {candidates.length > 0 && onStartNodeCompare && nodeId ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          data-llm-compare-run-trigger="true"
          aria-label="Run model compare for this node"
          className="w-full"
          onClick={() => onStartNodeCompare(nodeId)}
        >
          <GitCompareArrows className="size-3.5" aria-hidden />
          Run compare
        </Button>
      ) : null}
      <Dialog
        open={editOpen}
        onOpenChange={(next) => {
          setEditOpen(next)
          if (!next) {
            setEditingCandidateId(null)
            setEditTestState(EMPTY_COMPARE_TEST_STATE)
          }
        }}
      >
        <DialogContent className="min-w-0 overflow-hidden sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit compare LLM</DialogTitle>
            <DialogDescription>
              Update this node's model candidate. Saved with the node in the workspace, not SKILL.md.
            </DialogDescription>
          </DialogHeader>
          <div className="min-w-0 space-y-3">
            <Field className="min-w-0">
              <FieldLabel>Model</FieldLabel>
              <SearchableOptionCombobox
                value={editModelGroupId}
                options={modelOptions}
                onChange={(next) => {
                  setEditModelGroupId(next)
                  setEditRoute("auto")
                  setEditTestState(EMPTY_COMPARE_TEST_STATE)
                }}
                ariaLabel="Edit compare model"
                placeholder={modelOptions.length > 0 ? "Choose model" : "No models"}
                searchPlaceholder="Search models"
                emptyLabel="No model found."
                disabled={modelOptions.length === 0}
                dataSelectAttribute="data-llm-compare-model-group-select"
                dataSearchAttribute="data-llm-compare-model-group-search"
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel>Endpoint</FieldLabel>
              <SearchableOptionCombobox
                value={editRoute}
                options={editEndpointOptions}
                onChange={(next) => {
                  setEditRoute(next)
                  setEditTestState(EMPTY_COMPARE_TEST_STATE)
                }}
                ariaLabel="Edit compare model endpoint"
                placeholder="Auto fallback"
                emptyLabel="No endpoint found."
                searchable={false}
                disabled={!editGroup}
              />
            </Field>
            <LlmCompareTestResultPanel state={editTestState} />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="default"
              disabled={!editGroup || editTestState.running}
              data-llm-compare-dialog-test-trigger="true"
              onClick={runEditCompareTest}
            >
              {editTestState.running
                ? <Loader2 data-llm-compare-test-icon="true" className="size-3 animate-spin" aria-hidden />
                : <FlaskConical data-llm-compare-test-icon="true" className="size-3.5" aria-hidden />}
              Test
            </Button>
            <Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={!editGroup} onClick={saveCandidateEdit}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export function LlmCompareTestResultPanel({
  state,
}: {
  state?: LlmCompareTestState
}) {
  if (!state || (!state.running && !state.result && !state.error)) return null
  const badge = state.running
    ? roleTestStatusBadge({ running: true })
    : roleTestStatusBadge({
      running: false,
      status: state.result?.status ?? (state.error ? "failed" : null),
      error: state.error ?? null,
    })
  const summary = state.running ? "Testing compare LLM" : state.result?.summary ?? state.error ?? "Test failed"
  const details = state.result?.details ?? (state.error ? [state.error] : [])
  return (
    <div
      data-llm-compare-test-result="true"
      className="rounded-md border border-border/70 bg-muted/25 px-2 py-2 text-xs text-muted-foreground"
    >
      <div className="flex items-center gap-2">
        <Badge variant={badge.variant} className="h-5">
          {badge.running ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
          {badge.label}
        </Badge>
        <span className="min-w-0 flex-1 truncate font-medium text-foreground">{summary}</span>
      </div>
      {details.length > 0 ? (
        <ul className="mt-1 space-y-0.5">
          {details.map((detail) => (
            <li key={detail} className="break-words">
              {detail}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function LlmCompareCandidateRow({
  candidate,
  modelGroups,
  testState,
  onTest,
  onEdit,
  onRemove,
}: {
  candidate: LlmCompareCandidateDraft
  modelGroups: ModelGroup[]
  testState?: LlmCompareTestState
  onTest: (candidate: LlmCompareCandidateDraft) => void
  onEdit: (candidate: LlmCompareCandidateDraft) => void
  onRemove: (candidateId: string) => void
}) {
  const selectedGroup = modelGroups.find((group) => group.canonical_id === candidate.modelGroupId) ?? null
  const routeOptions = useMemo(
    () => modelGroupRouteOptions(selectedGroup),
    [selectedGroup],
  )
  const modelLabel = selectedGroup ? modelGroupPickerLabel(selectedGroup) : "Missing model"
  const routeLabel = candidate.route === "auto"
    ? "Auto fallback"
    : routeOptions.find((option) => option.value === candidate.route)?.label ?? "Selected endpoint"
  const routeStatus = compareStatusToRouteStatus(testState)
  const statusDetail = compareCandidateStatusDetail(testState)

  return (
    <div className="space-y-1.5" data-llm-compare-row="true">
      <div
        data-llm-compare-model-card="true"
        className={cn(
          "flex min-h-9 items-center gap-2 rounded-md border border-border/70 bg-muted/35 px-2 py-1.5 text-xs text-muted-foreground",
          roleRouteStatusSurfaceClass(routeStatus),
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-foreground">{modelLabel}</div>
          <div className="truncate">{routeLabel}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {routeStatus ? (
            <span data-llm-compare-status-light="true">
              <RoleRouteStatusLight status={routeStatus} detail={statusDetail} showTooltip={false} />
            </span>
          ) : null}
          <Button
            type="button"
            size="icon"
            variant="default"
            data-llm-compare-test-trigger="true"
            aria-label={`Test compare LLM ${modelLabel}`}
            disabled={testState?.running}
            onClick={() => onTest(candidate)}
          >
            {testState?.running
              ? <Loader2 data-llm-compare-test-icon="true" className="size-3 animate-spin" aria-hidden />
              : <FlaskConical data-llm-compare-test-icon="true" className="size-3.5" aria-hidden />}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className={YAML_ICON_BUTTON_CLASS}
            aria-label={`Edit compare LLM ${modelLabel}`}
            onClick={() => onEdit(candidate)}
          >
            <Settings2 className="size-3.5" aria-hidden />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className={YAML_ICON_BUTTON_CLASS}
            aria-label="Remove compare LLM"
            onClick={() => onRemove(candidate.id)}
          >
            <Trash2 className="size-3.5" aria-hidden />
          </Button>
        </div>
      </div>
      <LlmCompareTestResultPanel state={testState} />
    </div>
  )
}

function compareCandidateStatusDetail(state: LlmCompareTestState | undefined): string | null {
  if (state?.running) return "Testing this compare route."
  if (state?.error) return state.error
  if (!state?.result) return "Test has not run yet."
  return [state.result.summary, ...state.result.details].join(" ") || null
}

function SearchableOptionCombobox({
  id,
  value,
  options,
  onChange,
  ariaLabel,
  placeholder,
  searchPlaceholder,
  emptyLabel,
  searchable = true,
  disabled = false,
  dataSelectAttribute,
  dataSearchAttribute,
  triggerClassName,
}: {
  id?: string
  value: string
  options: SearchableComboboxOption[]
  onChange: (value: string) => void
  ariaLabel: string
  placeholder: string
  searchPlaceholder?: string
  emptyLabel: string
  searchable?: boolean
  disabled?: boolean
  dataSelectAttribute?: string
  dataSearchAttribute?: string
  triggerClassName?: string
}) {
  const [open, setOpen] = useState(false)
  // Dialog scroll lock sees this portaled popover as outside the dialog subtree.
  // Stop wheel bubbling at the list so CommandList keeps its native overflow scroll.
  const unlockDialogWheelScroll = useCallback((node: HTMLDivElement | null) => {
    if (!node) return undefined
    const stopWheel = (event: WheelEvent) => event.stopPropagation()
    node.addEventListener("wheel", stopWheel, { passive: true })
    return () => node.removeEventListener("wheel", stopWheel)
  }, [])
  const selected = options.find((option) => option.value === value) ?? null
  const groupedOptions = groupedSearchableOptions(options)
  const triggerDataAttributes = dataSelectAttribute ? { [dataSelectAttribute]: "true" } : {}
  const searchDataAttributes = dataSearchAttribute ? { [dataSearchAttribute]: "true" } : {}

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={selected?.detail ? `${ariaLabel}. ${selected.detail}` : ariaLabel}
          disabled={disabled}
          {...triggerDataAttributes}
          className={cn("w-full min-w-0 justify-between", triggerClassName)}
        >
          {selected?.unconfigured ? <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-hidden /> : null}
          <span className={cn(
            "min-w-0 truncate",
            selected ? null : "text-muted-foreground",
            selected?.unconfigured ? "text-destructive" : null,
          )}>
            {selected ? selected.label : placeholder}
          </span>
          <ChevronsUpDown className="ml-2 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] gap-0 p-0">
        <Command filter={llmCompareModelGroupFilter}>
          {searchable ? <CommandInput placeholder={searchPlaceholder ?? "Search"} {...searchDataAttributes} /> : null}
          <CommandList ref={unlockDialogWheelScroll}>
            <CommandEmpty>{emptyLabel}</CommandEmpty>
            {groupedOptions.map((group) => (
              <CommandGroup key={group.key} heading={group.heading}>
                {group.options.map((option) => (
                  <CommandItem
                    key={option.value}
                    value={option.searchValue ? `${option.value} ${option.searchValue} ${option.section ?? ""}` : `${option.value} ${option.label} ${option.section ?? ""}`}
                    data-checked={option.value === value ? "true" : undefined}
                    data-llm-role-unconfigured={option.unconfigured ? "true" : undefined}
                    aria-label={option.detail ?? option.label}
                    onSelect={() => {
                      onChange(option.value)
                      setOpen(false)
                    }}
                  >
                    {option.unconfigured ? <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-hidden /> : null}
                    <span className={cn("min-w-0 truncate", option.unconfigured ? "text-destructive" : null)}>
                      {option.label}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

function groupedSearchableOptions(options: SearchableComboboxOption[]): Array<{
  key: string
  heading?: string
  options: SearchableComboboxOption[]
}> {
  const groups: Array<{ key: string; heading?: string; options: SearchableComboboxOption[] }> = []
  const indexBySection = new Map<string, number>()
  for (const option of options) {
    const section = option.section?.trim() ?? ""
    let index = indexBySection.get(section)
    if (index === undefined) {
      index = groups.length
      indexBySection.set(section, index)
      const group: { key: string; heading?: string; options: SearchableComboboxOption[] } = {
        key: section || "__default__",
        options: [],
      }
      if (section) {
        group.heading = section
      }
      groups.push(group)
    }
    groups[index]?.options.push(option)
  }
  return groups
}

// Engine built-in tools (loader.py scan_mentions tool set) are always available to an
// agent 鈥?they must NOT be declared in `tools`. Adding them is blocked below.
const RESERVED_TOOL_NAMES = new Set(["finish_task", "read_reference", "read_example", "log_ambiguity"])

// Agent `tools` as a managed name list 鈥?same flat-card idiom as LOGIC actions, minus
// the file scaffolding (a tool name is just a declaration the body references via
// @tool:<name>, no sibling file to create or open). Add/remove edit the form draft.
function ToolsField({
  value,
  errors,
  onChange,
}: {
  value: string
  errors?: LintError[]
  onChange: (next: string) => void
}) {
  const tools = useMemo(
    () => value.split("\n").map((line) => line.trim()).filter(Boolean),
    [value],
  )
  const remove = (name: string) => {
    onChange(tools.filter((tool) => tool !== name).join("\n"))
  }
  const add = (name: string) => {
    onChange([...tools, name].join("\n"))
  }

  return (
    <Field>
      <YamlFieldLabel>
        tools
        <HelpTooltip label="About tools">
          Tools this agent may call at runtime, referenced in the body with
          <span className="font-mono"> @tool:&lt;name&gt;</span>. Each must be declared here first.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      {tools.length > 0 ? (
        <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
          {tools.map((name) => (
            <div key={name} className="flex items-center justify-between gap-2 text-xs text-foreground">
              <span className="min-w-0 flex-1 truncate">
                <span aria-hidden className="mr-1.5 text-muted-foreground">&bull;</span>
                {name}
              </span>
              <Button
                type="button"
                size="icon"
                variant="secondary"
                className={YAML_ICON_BUTTON_CLASS}
                aria-label={`Remove tool ${name}`}
                onClick={() => remove(name)}
              >
                <Trash2 className="size-3.5" aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <FieldDescription>No tools yet 鈥?add one this agent can call.</FieldDescription>
      )}
      <AddToolDialog existing={tools} onAdd={add} />
      <FieldDescription>
        Built-in tools (finish_task, read_reference, read_example, log_ambiguity) are always available 鈥?don&rsquo;t list them here.
      </FieldDescription>
    </Field>
  )
}

function AddToolDialog({ existing, onAdd }: { existing: string[]; onAdd: (name: string) => void }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState("")
  const name = draft.trim()
  const duplicate = name.length > 0 && existing.includes(name)
  const reserved = name.length > 0 && RESERVED_TOOL_NAMES.has(name)
  const canAdd = Boolean(name && !duplicate && !reserved)

  useEffect(() => {
    if (open) {
      setDraft("")
    }
  }, [open])

  const submit = () => {
    if (!canAdd) {
      return
    }
    onAdd(name)
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" size="sm" variant="secondary" className="mt-1">
          <Plus className="size-3.5" aria-hidden />
          Add tool
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add tool</DialogTitle>
          <DialogDescription>
            Declares a tool this agent may call, referenced in the body with
            <span className="font-mono"> @tool:&lt;name&gt;</span>.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <form
            className="contents"
            autoComplete="off"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            <FieldLabel htmlFor="tool-name-input">Tool name</FieldLabel>
            <Input
              id="tool-name-input"
              value={draft}
              autoFocus
              spellCheck={false}
              placeholder="my_tool"
              aria-invalid={duplicate || reserved || undefined}
              onChange={(event) => setDraft(event.currentTarget.value)}
            />
            {duplicate ? <p className="text-xs text-destructive">{name} is already declared.</p> : null}
            {reserved ? <p className="text-xs text-destructive">{name} is a built-in tool 鈥?always available, no need to declare it.</p> : null}
          </form>
        </Field>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={!canAdd} onClick={submit}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MaxIterationsField({
  value,
  errors,
  onChange,
}: {
  value: string
  errors?: LintError[]
  onChange: (next: string) => void
}) {
  return (
    <Field>
      <YamlFieldLabel htmlFor="phase-max-iterations">
        max_iterations
        <HelpTooltip label="About max_iterations">
          The most internal reasoning rounds this agent may take before it must call
          <span className="font-mono"> finish_task</span>. Integer 1&ndash;50; defaults to 10 when left empty.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      <Input
        id="phase-max-iterations"
        inputMode="numeric"
        value={value}
        placeholder="10"
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </Field>
  )
}

// Agent subgraph resources (frontmatter `subgraphs:`). Same flat-card list idiom as
// SubagentsField / ActionsField, but each row's path is a CHILD GRAPH FOLDER picked
// via the OS directory picker (engine requires an absolute path), not free text.
function SubgraphRefsField({
  value,
  errors,
  workspaceRoot,
  onChange,
}: {
  value: PhaseSubgraphRef[]
  errors?: LintError[]
  workspaceRoot: string | null
  onChange: (next: PhaseSubgraphRef[]) => void
}) {
  const update = (index: number, patch: Partial<PhaseSubgraphRef>) => {
    onChange(value.map((entry, idx) => (idx === index ? { ...entry, ...patch } : entry)))
  }
  const remove = (index: number) => {
    onChange(value.filter((_, idx) => idx !== index))
  }
  const add = () => {
    onChange([...value, { name: "", path: "", description: "" }])
  }
  const choosePath = async (index: number) => {
    const selected = await selectSkillDirectory(value[index]?.path || workspaceRoot)
    if (!selected) {
      return
    }
    if (!isPathInsideWorkspaceRoot(selected, workspaceRoot)) {
      toast.error("Select a child graph folder inside the current skill root.")
      return
    }
    update(index, { path: selected })
  }

  return (
    <Field>
      <YamlFieldLabel>
        subgraphs
        <HelpTooltip label="About subgraphs">
          Child graphs this agent can invoke, referenced in the body with
          <span className="font-mono"> @subgraph:&lt;name&gt;</span>. Each binds a <span className="font-mono">name</span> to a
          child graph folder (absolute <span className="font-mono">path</span>). This is a runtime resource, distinct from a
          SUBGRAPH phase node.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      <div className="space-y-2">
        {value.map((entry, index) => (
          <div key={index} className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
            <Input
              aria-label={`Subgraph ${index + 1} name`}
              value={entry.name}
              placeholder="name"
              onChange={(event) => update(index, { name: event.currentTarget.value })}
            />
            <div className="flex items-center gap-2">
              <Input
                aria-label={`Subgraph ${index + 1} path`}
                value={entry.path}
                placeholder="No folder selected"
                readOnly
                className={YAML_READONLY_VALUE_CLASS}
              />
              <Button
                type="button"
                size="icon"
                variant="secondary"
                className={YAML_ICON_BUTTON_CLASS}
                aria-label={`Choose folder for subgraph ${index + 1}`}
                onClick={() => void choosePath(index)}
              >
                <FolderOpen className="size-3.5" aria-hidden />
              </Button>
            </div>
            <Input
              aria-label={`Subgraph ${index + 1} description`}
              value={entry.description}
              placeholder="description"
              onChange={(event) => update(index, { description: event.currentTarget.value })}
            />
            <div className="flex justify-end">
              <Button type="button" size="sm" variant="ghost" onClick={() => remove(index)}>
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Button type="button" size="sm" variant="secondary" className="mt-1" onClick={add}>
        Add subgraph
      </Button>
    </Field>
  )
}

const RESOURCE_FIELD_COPY = {
  references: {
    label: "references",
    addLabel: "Add reference",
    help: (
      <>
        Reference documents this agent can consult, cited in the body with
        <span className="font-mono"> @reference:&lt;id&gt;</span>. Each binds an <span className="font-mono">id</span>
        {" "}(e.g. <span className="font-mono">R1</span>) to a file <span className="font-mono">path</span> with a short summary.
      </>
    ),
  },
  examples: {
    label: "examples",
    addLabel: "Add example",
    help: (
      <>
        Example documents this agent can consult, cited in the body with
        <span className="font-mono"> @example:&lt;id&gt;</span>. Each binds an <span className="font-mono">id</span>
        {" "}(e.g. <span className="font-mono">E1</span>) to a file <span className="font-mono">path</span> with a short summary.
        Distinct from inline <span className="font-mono">&lt;example&gt;</span> tags in the body.
      </>
    ),
  },
} as const

// Agent reference / example resources (frontmatter `references:` / `examples:`).
// Both are id/path/summary shaped, so one component renders either; `path` points
// at a file the author can open in the editor.
function ResourceRefField({
  fieldKey,
  value,
  errors,
  skillId,
  workspaceRoot,
  files,
  onFileOpen,
  onChange,
}: {
  fieldKey: "references" | "examples"
  value: PhaseResourceRef[]
  errors?: LintError[]
  skillId: string | null
  workspaceRoot: string | null
  files?: Record<string, string>
  onFileOpen?: (fileOrPath: FileOpenInput) => void
  onChange: (next: PhaseResourceRef[]) => void
}) {
  const copy = RESOURCE_FIELD_COPY[fieldKey]
  const update = (index: number, patch: Partial<PhaseResourceRef>) => {
    onChange(value.map((entry, idx) => (idx === index ? { ...entry, ...patch } : entry)))
  }
  const remove = (index: number) => {
    onChange(value.filter((_, idx) => idx !== index))
  }
  const add = () => {
    onChange([...value, { id: "", path: "", summary: "" }])
  }

  return (
    <Field>
      <YamlFieldLabel>
        {copy.label}
        <HelpTooltip label={`About ${copy.label}`}>{copy.help}</HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </YamlFieldLabel>
      <div className="space-y-2">
        {value.map((entry, index) => {
          const trimmedPath = entry.path.trim()
          const fileMissing = trimmedPath.length > 0 && files != null && files[trimmedPath] === undefined
          return (
            <div key={index} className="space-y-1.5 rounded-md bg-muted/30 px-2 py-2">
              <Input
                aria-label={`${copy.label} ${index + 1} id`}
                value={entry.id}
                placeholder="id"
                onChange={(event) => update(index, { id: event.currentTarget.value })}
              />
              <div className="flex items-center gap-2">
                <Input
                  aria-label={`${copy.label} ${index + 1} path`}
                  value={entry.path}
                  placeholder="path"
                  className="min-w-0 flex-1"
                  onChange={(event) => update(index, { path: event.currentTarget.value })}
                />
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  className={YAML_ICON_BUTTON_CLASS}
                  aria-label={`Open ${copy.label} ${index + 1} file`}
                  disabled={!onFileOpen || trimmedPath.length === 0}
                  onClick={() => onFileOpen?.({ path: trimmedPath, skillId, workspaceRoot, saveEnabled: true })}
                >
                  <Pencil className="size-3.5" aria-hidden />
                </Button>
              </div>
              {fileMissing ? (
                <p className="text-xs text-warning">File not found in this skill yet.</p>
              ) : null}
              <Input
                aria-label={`${copy.label} ${index + 1} summary`}
                value={entry.summary}
                placeholder="summary"
                onChange={(event) => update(index, { summary: event.currentTarget.value })}
              />
              <div className="flex justify-end">
                <Button type="button" size="sm" variant="ghost" onClick={() => remove(index)}>
                  Remove
                </Button>
              </div>
            </div>
          )
        })}
      </div>
      <Button type="button" size="sm" variant="secondary" className="mt-1" onClick={add}>
        {copy.addLabel}
      </Button>
    </Field>
  )
}

export function formsEqual(left: PhaseFrontmatterFormData, right: PhaseFrontmatterFormData): boolean {
  return (
    left.llmRole === right.llmRole
    && left.useGraphLlmRole === right.useGraphLlmRole
    && left.tools === right.tools
    && left.actions === right.actions
    && left.path === right.path
    && left.validator === right.validator
    && left.allowSequentialOverwrite === right.allowSequentialOverwrite
    && left.maxIterations === right.maxIterations
    && iterateEqual(left.iterate, right.iterate)
    && subagentsEqual(left.subagents, right.subagents)
    && subgraphsEqual(left.subgraphs, right.subgraphs)
    && resourcesEqual(left.references, right.references)
    && resourcesEqual(left.examples, right.examples)
  )
}

function iterateEqual(left: PhaseIterateFormData, right: PhaseIterateFormData): boolean {
  return (
    left.mode === right.mode
    && left.over === right.over
    && left.itemVar === right.itemVar
    && left.rangeStart === right.rangeStart
    && left.rangeEnd === right.rangeEnd
    && left.concurrency === right.concurrency
    && left.accumulateVar === right.accumulateVar
    && left.accumulateInit === right.accumulateInit
    && left.accumulateFrom === right.accumulateFrom
    && left.accumulateMerge === right.accumulateMerge
  )
}

function subagentsEqual(left: PhaseSubagentRef[], right: PhaseSubagentRef[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((entry, index) => {
    const other = right[index]
    return (
      other !== undefined
      && entry.name === other.name
      && entry.target_skill === other.target_skill
      && entry.description === other.description
    )
  })
}

function subgraphsEqual(left: PhaseSubgraphRef[], right: PhaseSubgraphRef[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((entry, index) => {
    const other = right[index]
    return (
      other !== undefined
      && entry.name === other.name
      && entry.path === other.path
      && entry.description === other.description
    )
  })
}

function resourcesEqual(left: PhaseResourceRef[], right: PhaseResourceRef[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((entry, index) => {
    const other = right[index]
    return (
      other !== undefined
      && entry.id === other.id
      && entry.path === other.path
      && entry.summary === other.summary
    )
  })
}
