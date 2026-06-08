import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { Textarea } from "@/components/ui/textarea"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData, SubagentRef } from "@/components/GraphCanvas"
import { sha256Hex } from "@/lib/hash"
import type { FileMeta } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { useOptionalWorkspaceContext } from "../WorkspaceContext"
import {
  applyPhaseFrontmatterForm,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
  type PhaseFrontmatterFormData,
} from "./phase-frontmatter"

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

function DetailRow({ label, value }: { label: string; value?: string | string[] | null }) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2">
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-xs text-foreground">
        {values.length > 0 ? values.join(", ") : <span className="text-muted-foreground">None</span>}
      </dd>
    </div>
  )
}

export function subagentSkillFilePath(skillId: string, subagent: SubagentRef): string {
  return `${skillId}/${subagent.path}/SKILL.md`
}

function SubagentsSection({
  skillId,
  subagents,
  onFileOpen,
}: {
  skillId: string | null
  subagents: SubagentRef[]
  onFileOpen?: (fileOrPath: FileMeta | string) => void
}) {
  if (subagents.length === 0) {
    return null
  }

  return (
    <div className="rounded-md border border-border bg-card px-3 py-2">
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Subagents</dt>
      <dd className="mt-2 space-y-1">
        {subagents.map((subagent) => (
          <button
            key={`${subagent.name}:${subagent.path}`}
            type="button"
            onClick={() => {
              if (skillId) {
                onFileOpen?.(subagentSkillFilePath(skillId, subagent))
              }
            }}
            className="flex w-full items-start gap-2 rounded-md border-0 px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-foreground">{subagent.name}</span>
              <span className="block truncate">{subagent.description}</span>
            </span>
          </button>
        ))}
      </dd>
    </div>
  )
}

interface PropertiesPanelProps {
  skillId?: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  onFileOpen?: (fileOrPath: FileMeta | string) => void
  onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
}

export function PropertiesPanel({
  skillId = null,
  skillDetail,
  selectedNode,
  onFileOpen,
  onPhaseFileSave,
}: PropertiesPanelProps) {
  const workspace = useOptionalWorkspaceContext()
  const selectedEdge = workspace?.selectedEdge

  const modeLabel = selectedNode ? phaseKindLabel(selectedNode.data) : null
  const filePath = selectedNode?.data.filePath ?? (selectedNode ? `phases/${selectedNode.id}/${phaseKindFile(selectedNode.data)}` : null)
  const fileContent = filePath ? skillDetail?.files?.[filePath] : undefined
  const subagents = selectedNode?.data.subagents ?? []
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
    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    if (typeof parsed.frontmatter.mode !== "string") {
      form.mode = modeLabel === "SUBGRAPH" ? "subgraph" : modeLabel === "AGENT" ? "agent" : "logic"
    }
    return { key: `${filePath}:${fileContent}`, ok: true as const, form }
  }, [fileContent, filePath, modeLabel])
  const [loadedFormKey, setLoadedFormKey] = useState(phaseFormState.key)
  const [draft, setDraft] = useState<PhaseFrontmatterFormData | null>(() => (
    phaseFormState.ok ? phaseFormState.form : null
  ))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoadedFormKey(phaseFormState.key)
    setDraft(phaseFormState.ok ? phaseFormState.form : null)
    setSaving(false)
  }, [phaseFormState])

  const activeDraft = phaseFormState.ok
    ? loadedFormKey === phaseFormState.key
      ? draft ?? phaseFormState.form
      : phaseFormState.form
    : null
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
    const next = applyPhaseFrontmatterForm(fileContent, activeDraft)
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

  if (selectedEdge) {
    return (
      <div className="flex h-full flex-col bg-background">
        <PanelHeader title="Connection Trace" />
        <ScrollArea className="flex-1">
          <div className="space-y-4 px-3 py-3 animate-in fade-in duration-200">
            <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-3 shadow-md">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Path Route
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="font-mono text-xs text-indigo-400 bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-900/50">
                  {selectedEdge.source}
                </span>
                <span className="text-muted-foreground text-xs">→</span>
                <span className="font-mono text-xs text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-900/50">
                  {selectedEdge.target}
                </span>
              </div>
              <div className="mt-2 text-xs text-muted-foreground leading-relaxed">
                Transferred context package captured during run execution.
              </div>
            </div>

            {/* Rich formatted subsections */}
            <div className="space-y-3">
              {/* Inputs Segment */}
              {selectedEdge.contextJson?.inputs != null && (
                <div className="rounded-md border border-border bg-zinc-900/40 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center justify-between">
                    <span>Input Arguments</span>
                    <Badge variant="outline" className="text-[9px] px-1 py-0 border-zinc-700 text-zinc-400">Inputs</Badge>
                  </div>
                  <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950 p-2.5 rounded border border-zinc-800/80 overflow-x-auto whitespace-pre-wrap break-all leading-normal">
                    {JSON.stringify(selectedEdge.contextJson.inputs, null, 2)}
                  </pre>
                </div>
              )}

              {/* Phase Outputs Segment */}
              {selectedEdge.contextJson?.phase_outputs && Object.keys(selectedEdge.contextJson.phase_outputs).length > 0 && (
                <div className="rounded-md border border-border bg-zinc-900/40 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center justify-between">
                    <span>Phase Outputs</span>
                    <Badge variant="outline" className="text-[9px] px-1 py-0 border-zinc-700 text-zinc-400">Outputs</Badge>
                  </div>
                  <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950 p-2.5 rounded border border-zinc-800/80 overflow-x-auto whitespace-pre-wrap break-all leading-normal">
                    {JSON.stringify(selectedEdge.contextJson.phase_outputs, null, 2)}
                  </pre>
                </div>
              )}

              {/* Full Trace JSON */}
              <div className="rounded-md border border-border bg-zinc-900/40 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center justify-between">
                  <span>Full Frame Trace</span>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(selectedEdge.contextJson, null, 2))
                      toast.success("Trace JSON copied to clipboard!")
                    }}
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 cursor-pointer bg-transparent border-none p-0 outline-none"
                  >
                    Copy JSON
                  </button>
                </div>
                <pre className="max-h-72 text-[11px] font-mono text-zinc-400 bg-zinc-950 p-2.5 rounded border border-zinc-800/80 overflow-auto whitespace-pre leading-normal">
                  {JSON.stringify(selectedEdge.contextJson, null, 2)}
                </pre>
              </div>
            </div>

            <Button
              type="button"
              variant="secondary"
              className="w-full text-xs"
              onClick={() => workspace?.setSelectedEdge?.(null)}
            >
              Clear Inspector Selection
            </Button>
          </div>
        </ScrollArea>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Properties" />

      <ScrollArea className="flex-1">
        {selectedNode ? (
          <div className="space-y-3 px-2 py-2">
            <div className="flex items-center justify-between px-1">
              <span className="truncate text-xs font-medium text-foreground">{selectedNode.data.label}</span>
              {modeLabel ? <Badge variant="secondary">{modeLabel}</Badge> : null}
            </div>
            {phaseFormState.ok && activeDraft ? (
              <PhaseFrontmatterForm
                value={activeDraft}
                modeLabel={modeLabel}
                saving={saving}
                canSave={canSave}
                canReset={dirty && !saving}
                onFieldChange={setField}
                onReset={handleReset}
                onSave={() => {
                  void handleSave()
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
            <dl className="space-y-3">
              <DetailRow label="Phase ID" value={selectedNode.id} />
              <DetailRow label="Mode" value={modeLabel} />
              <DetailRow label="Depends On" value={selectedNode.data.dependsOn} />
              <DetailRow label="Role" value={selectedNode.data.role} />
              <DetailRow label="Tools" value={selectedNode.data.tools} />
              <SubagentsSection skillId={skillId} subagents={subagents} onFileOpen={onFileOpen} />
              <DetailRow label="File" value={filePath} />
            </dl>
          </div>
        ) : (
          <div className="p-4 text-xs text-muted-foreground">Select a node to inspect</div>
        )}
      </ScrollArea>
    </div>
  )
}

function PhaseFrontmatterForm({
  value,
  modeLabel,
  saving,
  canSave,
  canReset,
  onFieldChange,
  onReset,
  onSave,
}: {
  value: PhaseFrontmatterFormData
  modeLabel: "LOGIC" | "AGENT" | "SUBGRAPH" | null
  saving: boolean
  canSave: boolean
  canReset: boolean
  onFieldChange: <Key extends keyof PhaseFrontmatterFormData>(field: Key, value: PhaseFrontmatterFormData[Key]) => void
  onReset: () => void
  onSave: () => void
}) {
  const kind = value.mode === "subgraph" ? "subgraph" : value.mode === "skill" || value.mode === "llm" || value.mode === "agent" ? "agent" : modeLabel === "SUBGRAPH" ? "subgraph" : modeLabel === "AGENT" ? "agent" : "logic"

  return (
    <form
      className="rounded-md border border-border bg-card px-3 py-3"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <FieldSet>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="phase-name">Name</FieldLabel>
            <Input
              id="phase-name"
              value={value.name}
              onChange={(event) => onFieldChange("name", event.currentTarget.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Mode</FieldLabel>
            <Select value={value.mode || kind} onValueChange={(next) => onFieldChange("mode", next)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="logic">Logic</SelectItem>
                <SelectItem value="agent">Agent</SelectItem>
                <SelectItem value="subgraph">Subgraph</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          {kind === "agent" ? (
            <Field>
              <FieldLabel htmlFor="phase-tools">Tools</FieldLabel>
              <Textarea
                id="phase-tools"
                value={value.tools}
                onChange={(event) => onFieldChange("tools", event.currentTarget.value)}
                rows={4}
              />
              <FieldDescription>One tool name per line.</FieldDescription>
            </Field>
          ) : null}
          {kind === "subgraph" ? (
            <Field>
              <FieldLabel htmlFor="phase-path">Path</FieldLabel>
              <Input
                id="phase-path"
                value={value.targetSkill}
                onChange={(event) => onFieldChange("targetSkill", event.currentTarget.value)}
              />
            </Field>
          ) : null}
        </FieldGroup>
        <div className="flex justify-end gap-2">
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

function formsEqual(left: PhaseFrontmatterFormData, right: PhaseFrontmatterFormData): boolean {
  return Object.keys(left).every((key) => (
    left[key as keyof PhaseFrontmatterFormData] === right[key as keyof PhaseFrontmatterFormData]
  ))
}
