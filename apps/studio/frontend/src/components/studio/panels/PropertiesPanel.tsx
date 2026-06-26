import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { AxiosError } from "axios"
import { AlertTriangle, CircleHelp, FolderOpen, Loader2, Pencil, ShieldCheck } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { getChildGraphTopology } from "@/api/client"
import { selectSkillDirectory } from "@/lib/tauri"
import { sha256Hex } from "@/lib/hash"
import { errorMessage } from "@/utils/errors"
import { runRoleTestJobToResult } from "../settings/llm-roles/role-test-store"
import type { FileMeta } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { roleTestStatusBadge, type RoleTestStatusInput } from "./role-test-status"
import {
  applyPhaseFrontmatterForm,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
  type IterateMergeMode,
  type IterateMode,
  type PhaseFrontmatterFormData,
  type PhaseFrontmatterKind,
  type PhaseIterateFormData,
  type PhaseSubagentRef,
} from "./phase-frontmatter"

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

function PropertyCard({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-card px-3 py-3">
      {children}
    </div>
  )
}

interface AllowOverwriteCandidate {
  field: string
  upstreamPhaseIds: string[]
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
  onFileOpen?: (fileOrPath: FileMeta | string) => void
  onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
  /** Per-node golden promote (atom #32): write golden for just this node from the active run. */
  onPromoteNode?: (nodeId: string) => Promise<void> | void
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
  onResumeNode,
  onPromoteNode,
}: PropertiesPanelProps) {

  const modeLabel = selectedNode ? phaseKindLabel(selectedNode.data) : null
  const effectiveNodeStatus = selectedNodeStatus ?? selectedNode?.data.status ?? null
  const kind: PhaseFrontmatterKind = phaseFrontmatterKind(modeLabel ?? "LOGIC")
  const filePath = selectedNode?.data.filePath ?? (selectedNode ? `phases/${selectedNode.id}/${phaseKindFile(selectedNode.data)}` : null)
  const fileContent = filePath ? skillDetail?.files?.[filePath] : undefined
  // Field-level near-projection (atom #5): group THIS node's lint errors by the engine's
  // `field_path` so each frontmatter field can show its own marker; no-field errors are
  // dropped here and stay on the node badge (atom #4).
  const fieldErrors = useMemo(
    () => (selectedNode ? fieldErrorsByKey(lintErrors, selectedNode.id) : {}),
    [lintErrors, selectedNode],
  )
  const phaseFormState = useMemo(() => {
    if (!filePath) {
      return { key: "none", ok: false as const, reason: "missing-node" as const, message: "Select a phase node to edit frontmatter." }
    }
    if (fileContent === undefined) {
      return { key: filePath, ok: false as const, reason: "missing-file" as const, message: "Phase file is not available in the loaded skill detail." }
    }
    const parsed = parsePhaseFrontmatter(fileContent)
    if (!parsed.ok) {
      return { key: `${filePath}:${fileContent}`, ok: false as const, reason: parsed.reason, message: parsed.message }
    }
    const form = phaseFrontmatterToForm(parsed.frontmatter)
    return {
      key: `${filePath}:${fileContent}`,
      ok: true as const,
      form,
    }
  }, [fileContent, filePath])
  const [loadedFormKey, setLoadedFormKey] = useState(phaseFormState.key)
  const [draft, setDraft] = useState<PhaseFrontmatterFormData | null>(() => (
    phaseFormState.ok ? phaseFormState.form : null
  ))
  const [saving, setSaving] = useState(false)
  const [roleTest, setRoleTest] = useState<RoleTestStatusInput>({ running: false })

  useEffect(() => {
    setLoadedFormKey(phaseFormState.key)
    setDraft(phaseFormState.ok ? phaseFormState.form : null)
    setSaving(false)
    setRoleTest({ running: false })
  }, [phaseFormState])

  const activeDraft = phaseFormState.ok
    ? loadedFormKey === phaseFormState.key
      ? draft ?? phaseFormState.form
      : phaseFormState.form
    : null
  const effectiveWorkspaceRoot = workspaceRoot ?? selectedNode?.data.workspaceRoot ?? null
  const allowOverwriteCandidates = useMemo(
    () => (selectedNode && filePath
      ? inferAllowOverwriteCandidates(skillDetail, selectedNode.data.phaseId ?? selectedNode.id, filePath)
      : []),
    [filePath, selectedNode, skillDetail],
  )
  const dirty = Boolean(activeDraft && phaseFormState.ok && !formsEqual(activeDraft, phaseFormState.form))
  const canSave = Boolean(onPhaseFileSave && filePath && fileContent !== undefined && activeDraft && phaseFormState.ok && dirty && !saving)

  const setField = <Key extends keyof PhaseFrontmatterFormData>(field: Key, value: PhaseFrontmatterFormData[Key]) => {
    setDraft((current) => current ? { ...current, [field]: value } : current)
  }

  const handleReset = () => {
    if (phaseFormState.ok) {
      setDraft(phaseFormState.form)
    }
  }

  const handleSave = async () => {
    if (!onPhaseFileSave || !filePath || fileContent === undefined || !activeDraft) {
      return
    }
    const next = applyPhaseFrontmatterForm(fileContent, activeDraft, kind)
    if (!next.ok) {
      toast.error(`Frontmatter error: ${next.message}`)
      return
    }
    setSaving(true)
    try {
      await onPhaseFileSave({
        path: filePath,
        content: next.markdown,
        expectedHash: await sha256Hex(fileContent),
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save phase properties")
    } finally {
      setSaving(false)
    }
  }

  // Reuses the settings role-test job runner (runRoleTestJobToResult) verbatim so
  // the node Properties Test button verifies the same backend job + status the
  // Settings page does (settings-ux-spec §2.7). No re-implementation.
  const handleRoleTest = useCallback(async (roleName: string) => {
    const trimmed = roleName.trim()
    if (!trimmed) {
      toast.error("Set an LLM role before testing.")
      return
    }
    setRoleTest({ running: true, status: null, error: null })
    try {
      const result = await runRoleTestJobToResult(trimmed)
      setRoleTest({ running: false, status: result.status, error: null })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Role test failed"
      setRoleTest({ running: false, status: null, error: message })
      toast.error(message)
    }
  }, [])

  // Subgraph "import folder" affordance (n2-properties #20 / F4·R5): when the
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
      <PanelHeader title="Properties" />

      <ScrollArea className="flex-1">
        {selectedNode ? (
          <div className="space-y-3 px-2 py-2">
            <PhaseIdentityHeader
              selectedNode={selectedNode}
              modeLabel={modeLabel}
            />
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
                saving={saving}
                canSave={canSave}
                canReset={dirty && !saving}
                roleTest={roleTest}
                fieldErrors={fieldErrors}
                allowOverwriteCandidates={allowOverwriteCandidates}
                skillId={skillId}
                workspaceRoot={effectiveWorkspaceRoot}
                phaseId={selectedNode.id}
                onPhaseRename={kind === "subgraph" ? onPhaseRename : undefined}
                onReconnectSubgraphFolder={handleReconnectSubgraphFolder}
                onFieldChange={setField}
                onReset={handleReset}
                onSave={() => {
                  void handleSave()
                }}
                onRoleTest={(roleName) => {
                  void handleRoleTest(roleName)
                }}
              />
            ) : (
              <div className="rounded-md border border-border bg-card px-3 py-2">
                <div className="text-xs font-medium text-destructive">Frontmatter error</div>
                <div className="mt-1 text-xs text-muted-foreground">{phaseFormState.message}</div>
                <div className="mt-3 flex gap-2">
                  {filePath ? (
                    <Button type="button" size="sm" variant="secondary" onClick={() => onFileOpen?.(filePath)}>
                      Open file
                    </Button>
                  ) : null}
                  <Button type="button" size="sm" disabled>
                    Save
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="p-4 text-xs text-muted-foreground">Select a node to inspect</div>
        )}
      </ScrollArea>
    </div>
  )
}

function PhaseIdentityHeader({
  selectedNode,
  modeLabel,
}: {
  selectedNode: { id: string; data: SkillGraphNodeData }
  modeLabel: "LOGIC" | "AGENT" | "SUBGRAPH" | null
}) {
  return (
    <div className="flex items-center justify-between gap-2 px-1">
      <span className="min-w-0 truncate text-xs font-medium text-foreground">{selectedNode.data.label}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        {modeLabel ? <Badge variant="secondary">{modeLabel}</Badge> : null}
      </div>
    </div>
  )
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
          size="icon-sm"
          variant="ghost"
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
          <FieldLabel htmlFor="phase-rename-input">New name</FieldLabel>
          <Input
            id="phase-rename-input"
            value={draft}
            autoFocus
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
      <div className="flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400">
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
  saving,
  canSave,
  canReset,
  roleTest,
  fieldErrors,
  allowOverwriteCandidates,
  skillId,
  workspaceRoot,
  phaseId,
  onPhaseRename,
  onReconnectSubgraphFolder,
  onFieldChange,
  onReset,
  onSave,
  onRoleTest,
}: {
  value: PhaseFrontmatterFormData
  kind: PhaseFrontmatterKind
  saving: boolean
  canSave: boolean
  canReset: boolean
  roleTest: RoleTestStatusInput
  fieldErrors: Record<string, LintError[]>
  allowOverwriteCandidates: AllowOverwriteCandidate[]
  skillId: string | null
  workspaceRoot: string | null
  phaseId: string
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
  onReconnectSubgraphFolder: () => void
  onFieldChange: <Key extends keyof PhaseFrontmatterFormData>(field: Key, value: PhaseFrontmatterFormData[Key]) => void
  onReset: () => void
  onSave: () => void
  onRoleTest: (roleName: string) => void
}) {
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <FieldSet>
        <FieldGroup>
          {kind === "agent" ? (
            <>
              <PropertyCard>
                <Field>
                  <FieldLabel htmlFor="phase-llm-role">
                    llm_role
                    <FieldErrorMarker errors={fieldErrors.llm_role} />
                  </FieldLabel>
                  <div className="flex items-center gap-2">
                    <Input
                      id="phase-llm-role"
                      className="flex-1"
                      value={value.llmRole}
                      placeholder="analyst"
                      onChange={(event) => onFieldChange("llmRole", event.currentTarget.value)}
                    />
                    <RoleTestControl
                      roleName={value.llmRole}
                      roleTest={roleTest}
                      onRoleTest={onRoleTest}
                    />
                  </div>
                </Field>
              </PropertyCard>
              <PropertyCard>
                <Field>
                  <FieldLabel htmlFor="phase-tools">
                    tools
                    <FieldErrorMarker errors={fieldErrors.tools} />
                  </FieldLabel>
                  <Textarea
                    id="phase-tools"
                    value={value.tools}
                    onChange={(event) => onFieldChange("tools", event.currentTarget.value)}
                    rows={4}
                  />
                </Field>
              </PropertyCard>
              <PropertyCard>
                <SubagentsField
                  value={value.subagents}
                  onChange={(next) => onFieldChange("subagents", next)}
                />
              </PropertyCard>
            </>
          ) : null}
          {kind === "logic" ? (
            <>
              <PropertyCard>
                <Field>
                  <FieldLabel htmlFor="phase-actions">
                    actions
                    <FieldErrorMarker errors={fieldErrors.actions} />
                  </FieldLabel>
                  <Textarea
                    id="phase-actions"
                    value={value.actions}
                    onChange={(event) => onFieldChange("actions", event.currentTarget.value)}
                    rows={4}
                  />
                </Field>
              </PropertyCard>
              <PropertyCard>
                <ValidatorField
                  value={value.validator}
                  errors={fieldErrors.validator}
                  onChange={(next) => onFieldChange("validator", next)}
                />
              </PropertyCard>
              {/* n2-properties #19 (atom #19): the fields an action may write back
                  are bounded by io.outputs.properties, but that boundary is edited
                  in the I/O panel - not here. Surface a NON-blocking hint so the
                  author doesn't assume a logic node has no io constraint. */}
              <FieldDescription>
                Output fields an action writes are bounded by io.outputs - edit those field
                boundaries in the I/O panel (toolbar tab 3).
              </FieldDescription>
            </>
          ) : null}
          {kind === "subgraph" ? (
            <>
              <PropertyCard>
                <SubgraphNameField
                  phaseId={phaseId}
                  onPhaseRename={onPhaseRename}
                />
              </PropertyCard>
              <PropertyCard>
                <SubgraphPathField
                  value={value.path}
                  errors={fieldErrors.path}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onReconnectFolder={onReconnectSubgraphFolder}
                />
              </PropertyCard>
              <PropertyCard>
                <ValidatorField
                  value={value.validator}
                  errors={fieldErrors.validator}
                  onChange={(next) => onFieldChange("validator", next)}
                />
              </PropertyCard>
            </>
          ) : null}
          <PropertyCard>
            <AllowSequentialOverwriteField
              value={value.allowSequentialOverwrite}
              candidates={allowOverwriteCandidates}
              errors={fieldErrors.allow_sequential_overwrite}
              onChange={(next) => onFieldChange("allowSequentialOverwrite", next)}
            />
          </PropertyCard>
          <PropertyCard>
            <IterateField
              value={value.iterate}
              errors={fieldErrors.iterate}
              onChange={(next) => onFieldChange("iterate", next)}
            />
          </PropertyCard>
        </FieldGroup>
        <div className="flex justify-end gap-2 px-1">
          <Button type="button" size="sm" variant="secondary" disabled={!canReset} onClick={onReset}>
            Reset
          </Button>
          <Button type="submit" size="sm" disabled={!canSave}>
            {saving ? "Saving" : "Save"}
          </Button>
        </div>
      </FieldSet>
    </form>
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
  const toggleCandidate = (field: string, checked: boolean | "indeterminate") => {
    const next = new Set(selectedFields)
    if (checked === true) {
      next.add(field)
    } else {
      next.delete(field)
    }
    onChange([...next].sort((a, b) => a.localeCompare(b)).join("\n"))
  }

  return (
    <Field>
      <FieldLabel htmlFor="phase-allow-sequential-overwrite">
        allow_sequential_overwrite
        <FieldErrorMarker errors={errors} />
      </FieldLabel>
      {candidates.length > 0 ? (
        <div className="space-y-1.5 rounded-md border border-border bg-background px-2 py-2">
          {candidates.map((candidate) => (
            <label
              key={candidate.field}
              className="flex items-start gap-2 text-xs text-foreground"
            >
              <Checkbox
                checked={selectedFields.has(candidate.field)}
                onCheckedChange={(checked) => toggleCandidate(candidate.field, checked)}
                aria-label={`Allow overwrite for ${candidate.field}`}
              />
              <span className="min-w-0 flex-1">
                <span className="font-mono">{candidate.field}</span>
                <span className="ml-1 text-muted-foreground">
                  from {candidate.upstreamPhaseIds.join(", ")}
                </span>
              </span>
            </label>
          ))}
        </div>
      ) : null}
      <Textarea
        id="phase-allow-sequential-overwrite"
        value={value}
        rows={3}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
      <FieldDescription>
        One output field per line that this phase may intentionally overwrite from upstream phases.
      </FieldDescription>
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
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function SubgraphNameField({
  phaseId,
  onPhaseRename,
}: {
  phaseId: string
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => Promise<void> | void
}) {
  return (
    <Field>
      <FieldLabel>name</FieldLabel>
      <div className="flex min-h-8 items-center gap-2">
        <span id="phase-name" className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
          {phaseId}
        </span>
        {onPhaseRename ? (
          <RenamePhaseDialog phaseId={phaseId} onPhaseRename={onPhaseRename} />
        ) : null}
      </div>
    </Field>
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
    <Field>
      <FieldLabel htmlFor="phase-path">
        path
        <HelpTooltip label="About path">
          Select the child graph folder that contains GRAPH.md. Studio saves a relative path when it can.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </FieldLabel>
      <div className="flex min-h-8 items-center gap-2">
        <span
          id="phase-path"
          role="status"
          aria-invalid={unresolved || undefined}
          className="min-w-0 flex-1 truncate font-mono text-xs text-foreground aria-invalid:text-destructive"
        >
          {value.trim() || "No child graph selected"}
        </span>
        <Button type="button" size="icon-sm" variant="secondary" aria-label="Reconnect path" onClick={onReconnectFolder}>
          <FolderOpen className="size-3.5" aria-hidden />
        </Button>
      </div>
      {unresolved ? (
        <div className="space-y-1.5">
          <p className="text-xs text-destructive">
            {diskMissing
              ? "Path does not resolve to GRAPH.md."
              : "Select a child graph folder."}
          </p>
        </div>
      ) : null}
    </Field>
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
      <FieldLabel htmlFor="phase-iterate-mode">
        iterate
        <HelpTooltip label="About iterate">
          Configure phase-level batch or loop execution. I/O fields are edited in the I/O panel.
        </HelpTooltip>
        <FieldErrorMarker errors={errors} />
      </FieldLabel>
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
      {value.mode ? (
        <div className="space-y-2 pt-1">
          <div className="grid grid-cols-2 gap-2">
            <Field>
              <FieldLabel htmlFor="phase-iterate-over">over</FieldLabel>
              <Input
                id="phase-iterate-over"
                value={value.over}
                placeholder="data.inputs.items"
                onChange={(event) => update({ over: event.currentTarget.value })}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="phase-iterate-item-var">item_var</FieldLabel>
              <Input
                id="phase-iterate-item-var"
                value={value.itemVar}
                placeholder="item"
                onChange={(event) => update({ itemVar: event.currentTarget.value })}
              />
            </Field>
          </div>
          <Field>
            <FieldLabel>range</FieldLabel>
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
              <FieldLabel htmlFor="phase-iterate-concurrency">concurrency</FieldLabel>
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
              <FieldLabel>accumulate</FieldLabel>
              <div className="grid grid-cols-2 gap-2">
                <Field>
                  <FieldLabel htmlFor="phase-iterate-accumulate-var">accumulate.var</FieldLabel>
                  <Input
                    id="phase-iterate-accumulate-var"
                    value={value.accumulateVar}
                    placeholder="collected"
                    onChange={(event) => update({ accumulateVar: event.currentTarget.value })}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="phase-iterate-accumulate-from">accumulate.from</FieldLabel>
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
                  <FieldLabel htmlFor="phase-iterate-accumulate-init">accumulate.init</FieldLabel>
                  <Input
                    id="phase-iterate-accumulate-init"
                    value={value.accumulateInit}
                    placeholder="[]"
                    onChange={(event) => update({ accumulateInit: event.currentTarget.value })}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="phase-iterate-accumulate-merge">accumulate.merge</FieldLabel>
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
            </div>
          ) : null}
        </div>
      ) : null}
    </Field>
  )
}

function RoleTestControl({
  roleName,
  roleTest,
  onRoleTest,
}: {
  roleName: string
  roleTest: RoleTestStatusInput
  onRoleTest: (roleName: string) => void
}) {
  const badge = roleTestStatusBadge(roleTest)
  const showBadge = badge.running || roleTest.status != null || Boolean(roleTest.error)
  return (
    <div className="flex shrink-0 items-center gap-2">
      {showBadge ? (
        <Badge variant={badge.variant} className="h-6">
          {badge.running ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
          {badge.label}
        </Badge>
      ) : null}
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={badge.running || roleName.trim().length === 0}
        onClick={() => onRoleTest(roleName)}
      >
        Test
      </Button>
    </div>
  )
}

function ValidatorField({
  value,
  errors,
  onChange,
}: {
  value: boolean
  errors?: LintError[]
  onChange: (next: boolean) => void
}) {
  return (
    <Field orientation="horizontal" className="items-center justify-between gap-3">
      <FieldLabel htmlFor="phase-validator" className="min-w-0">
        validator
        <FieldErrorMarker errors={errors} />
      </FieldLabel>
      <Switch
        id="phase-validator"
        size="sm"
        checked={value}
        onCheckedChange={onChange}
        aria-label="Validator"
      />
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
  const tone = hasError ? "text-destructive" : "text-amber-500"
  const count = errors.length === 1 ? "1 issue" : `${errors.length} issues`
  const messages = errors.map((error) => error.message)
  // The joined messages live on the trigger's accessible name + native title so the
  // diagnostic is reachable without opening the styled Tooltip (and survives SSR).
  const accessibleSummary = `Field has ${count}: ${messages.join("; ")}`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={accessibleSummary}
          title={accessibleSummary}
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
      <FieldLabel>subagents</FieldLabel>
      <div className="space-y-2">
        {value.map((entry, index) => (
          <div key={index} className="space-y-1.5 rounded-md border border-border bg-background px-2 py-2">
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

function formsEqual(left: PhaseFrontmatterFormData, right: PhaseFrontmatterFormData): boolean {
  return (
    left.llmRole === right.llmRole
    && left.tools === right.tools
    && left.actions === right.actions
    && left.path === right.path
    && left.validator === right.validator
    && left.allowSequentialOverwrite === right.allowSequentialOverwrite
    && iterateEqual(left.iterate, right.iterate)
    && subagentsEqual(left.subagents, right.subagents)
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
