import { useMemo, useState, type DragEvent } from "react"
import yaml from "js-yaml"
import { ArrowRight, Plus, Save, Trash2, TriangleAlert, Upload } from "lucide-react"
import { writeSkillFile } from "@/api/client"
import { Button } from "@/components/ui/button"
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
import type { FieldSupplyEntry, SkillDetail } from "@/api/types"
import {
  addIoField,
  applyImportedFileFieldToGraph,
  applyInputSchemaToGraph,
  applyOutputArtifactPathToGraph,
  inferJsonSchemaFromText,
  IO_FIELD_TYPES,
  listIoFields,
  removeIoField,
  renameIoField,
  setIoFieldType,
  type IoField,
  type IoFieldType,
  type IoSide,
} from "@/lib/schema-infer"
import { sha256Hex } from "@/lib/hash"
import { isTauriRuntime } from "@/config/runtime"
import { errorMessage } from "@/utils/errors"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelBody, PanelSection } from "./_shared/PanelSection"
import { SectionHeading } from "./_shared/SectionHeading"
import { GoldenSection } from "./GoldenSection"
import { fieldSupplyByField, resolveIoEditTarget, type SelectedNode } from "./io-target"
import { inputContractView } from "./panel-files"
import { TestInputsSection } from "./TestInputsSection"

interface InputPanelProps {
  skillId: string
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  // Atom #27 (per-node i/o): when a phase node is selected the panel edits that
  // phase file's frontmatter io; with no node (or the global input/output node)
  // it edits GRAPH.md's graph-level io.
  selectedNode?: SelectedNode
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
}

// Writes back the resolved io-bearing file (`GRAPH.md` for graph-level io, or a
// `phases/<id>/<KIND>.md` phase file for per-node io). `relPath` names which file
// under the skill root; the optimistic-lock hash is over the file's CURRENT
// content so a stale write is rejected by the backend.
async function writeIoFile(
  skillId: string,
  workspaceRoot: string | null | undefined,
  relPath: string,
  current: string,
  next: string,
): Promise<void> {
  // Tauri native writes target the imported workspace root; browser fallback
  // writes still go through the backend skill id.
  const target = isTauriRuntime() ? workspaceRoot ?? skillId : skillId
  await writeSkillFile(target, relPath, next, await sha256Hex(current))
}

interface SchemaInferPanelProps {
  initialJson: string
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
}

function SchemaInferPanel({
  initialJson,
  skillId,
  workspaceRoot = null,
  relPath,
  graphMd,
  onSaved,
}: SchemaInferPanelProps) {
  const [draft, setDraft] = useState(initialJson)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : "Invalid JSON" }
    }
  }, [draft])

  // F2: persist the inferred schema into GRAPH.md's io.inputs (the engine's
  // input contract). The design says inference can be saved; GRAPH.md is git-
  // tracked so this is reversible.
  const handleSave = async () => {
    if (!result.schema || !graphMd) {
      return
    }
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const next = applyInputSchemaToGraph(graphMd, result.schema)
      await writeIoFile(skillId, workspaceRoot, relPath, graphMd, next)
      setSaved(true)
      onSaved?.()
    } catch (error) {
      setSaveError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleDrop = async (event: DragEvent<HTMLTextAreaElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files.item(0)
    if (file) {
      setDraft(await file.text())
      return
    }

    const text = event.dataTransfer.getData("text/plain")
    if (text) {
      setDraft(text)
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Upload className="size-3.5" />
        Infer input schema
      </div>
      <div className="space-y-3 rounded-md border border-border bg-background p-3">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="h-28 resize-none bg-card font-mono text-xs"
          spellCheck={false}
          aria-label="JSON input for schema inference"
        />
        {result.error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {result.error}
          </div>
        ) : (
          <pre className="max-h-52 overflow-auto rounded-md border border-border bg-muted/40 p-2 text-xs text-foreground">
            {JSON.stringify(result.schema, null, 2)}
          </pre>
        )}
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving || !result.schema || !graphMd}
          aria-label="Save inferred schema as input contract"
          className="flex items-center gap-1 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
        >
          <Save className="size-3.5" />
          {saving ? "Saving…" : "Save as input schema"}
        </button>
        {saveError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {saveError}
          </div>
        ) : null}
        {saved && !saveError ? (
          <div className="px-1 text-[11px] text-muted-foreground">
            Saved to {relPath} io.inputs.
          </div>
        ) : null}
      </div>
    </section>
  )
}

interface FileImportPanelProps {
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
}

// #28 (any-io-import-file, G2): import a FILE as a declared input field on whatever
// node the i/o panel currently targets (resolveIoEditTarget already scopes relPath +
// graphMd to the selected node, so this entry works on ANY node, not just the start
// input). Unlike SchemaInferPanel (which infers a schema from a pasted JSON SAMPLE),
// importing a file means "inject this file's content into the field when the run
// reaches this node". applyImportedFileFieldToGraph stamps the engine's marker
// (source:'file' + path) onto io.inputs.<field>, which the engine's per-node file
// injection reads to inject the file at run time. Drag a file to prefill its path.
function FileImportPanel({ skillId, workspaceRoot = null, relPath, graphMd, onSaved }: FileImportPanelProps) {
  const [fieldName, setFieldName] = useState("")
  const [type, setType] = useState<IoFieldType>("string")
  const [path, setPath] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const handleImport = async () => {
    if (!graphMd || fieldName.trim() === "" || path.trim() === "") {
      return
    }
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const next = applyImportedFileFieldToGraph(graphMd, fieldName, type, path)
      await writeIoFile(skillId, workspaceRoot, relPath, graphMd, next)
      setSaved(true)
      setFieldName("")
      setPath("")
      onSaved?.()
    } catch (error) {
      setSaveError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files.item(0)
    if (file) {
      // Prefill the path with the dropped file name; the user can adjust it to the
      // workspace-relative path the engine resolves against at run time.
      setPath(file.name)
      if (fieldName.trim() === "") {
        setFieldName(file.name.replace(/\.[^.]+$/, ""))
      }
      setSaved(false)
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Upload className="size-3.5" />
        Import file as input field
      </div>
      <div
        className="space-y-2 rounded-md border border-dashed border-border bg-background p-3"
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        aria-label="Import a file as an input field for this node"
      >
        <div className="flex items-center gap-2">
          <Input
            value={fieldName}
            onChange={(event) => {
              setFieldName(event.target.value)
              setSaved(false)
            }}
            placeholder="field_name"
            className="font-mono"
            spellCheck={false}
            aria-label="Imported file input field name"
            disabled={saving || !graphMd}
          />
          <Select value={type} onValueChange={(value) => setType(value as IoFieldType)} disabled={saving || !graphMd}>
            <SelectTrigger className="w-28 font-mono" aria-label="Imported file input field type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {IO_FIELD_TYPES.map((option) => (
                <SelectItem key={option} value={option} className="font-mono">
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={path}
            onChange={(event) => {
              setPath(event.target.value)
              setSaved(false)
            }}
            placeholder="inputs/brief.md"
            className="font-mono"
            spellCheck={false}
            aria-label="Imported file path"
            disabled={saving || !graphMd}
          />
          <Button
            type="button"
            size="sm"
            onClick={() => void handleImport()}
            disabled={saving || !graphMd || fieldName.trim() === "" || path.trim() === ""}
            aria-label="Import file as input field"
          >
            <Upload className="size-3.5" />
            {saving ? "Importing…" : "Import"}
          </Button>
        </div>
        {saveError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {saveError}
          </div>
        ) : null}
        {saved && !saveError ? (
          <div className="px-1 text-[11px] text-muted-foreground">
            Imported to {relPath} io.inputs (injected from file at run time).
          </div>
        ) : null}
      </div>
    </section>
  )
}

interface OutputArtifactField {
  name: string
  path: string
}

/**
 * Read the declared output fields and their currently-configured artifact paths
 * out of GRAPH.md frontmatter (`io.outputs.properties.<field>.path`). GRAPH.md is
 * the authoritative contract the engine validates, so the editor reads/writes the
 * same source rather than the projected manifest.
 */
function outputArtifactFields(graphMd?: string): OutputArtifactField[] {
  if (!graphMd) {
    return []
  }
  const match = graphMd.match(/^---\n([\s\S]*?)\n---/)
  if (!match) {
    return []
  }
  const data = (yaml.load(match[1]) ?? {}) as { io?: { outputs?: { properties?: Record<string, unknown> } } }
  const properties = data.io?.outputs?.properties
  if (!properties || typeof properties !== "object") {
    return []
  }
  return Object.entries(properties).map(([name, schema]) => {
    const fieldPath =
      schema && typeof schema === "object" && typeof (schema as { path?: unknown }).path === "string"
        ? (schema as { path: string }).path
        : ""
    return { name, path: fieldPath }
  })
}

interface OutputArtifactPathPanelProps {
  fields: OutputArtifactField[]
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
}

interface OutputPathRowProps {
  field: OutputArtifactField
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
}

// F3: configure where each declared output field's artifact is written by setting
// `{target: "artifact", path}` onto `io.outputs.<field>` in GRAPH.md (the engine
// resolves `path` to `runs/<id>/artifacts/<path>`). Mirrors the F2 save path:
// reads GRAPH.md, applies a pure writeback, then writeSkillFile to the resolved
// workspace root. An empty path clears the artifact target.
function OutputPathRow({ field, skillId, workspaceRoot = null, relPath, graphMd, onSaved }: OutputPathRowProps) {
  const [draft, setDraft] = useState(field.path)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    if (!graphMd) {
      return
    }
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const next = applyOutputArtifactPathToGraph(graphMd, field.name, draft)
      await writeIoFile(skillId, workspaceRoot, relPath, graphMd, next)
      setSaved(true)
      onSaved?.()
    } catch (error) {
      setSaveError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-1.5 rounded-md border border-border bg-background p-3">
      <div className="px-0.5 font-mono text-xs text-foreground">{field.name}</div>
      <div className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value)
            setSaved(false)
          }}
          placeholder="artifacts/output.json"
          className="font-mono"
          spellCheck={false}
          aria-label={`Artifact path for output ${field.name}`}
        />
        <Button
          type="button"
          size="sm"
          onClick={() => void handleSave()}
          disabled={saving || !graphMd}
          aria-label={`Save artifact path for output ${field.name}`}
        >
          <Save className="size-3.5" />
          {saving ? "Saving…" : "Save path"}
        </Button>
      </div>
      {saveError ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {saveError}
        </div>
      ) : null}
      {saved && !saveError ? (
        <div className="px-1 text-[11px] text-muted-foreground">
          Saved to {relPath} io.outputs.{field.name}.
        </div>
      ) : null}
    </div>
  )
}

function OutputArtifactPathPanel({
  fields,
  skillId,
  workspaceRoot = null,
  relPath,
  graphMd,
  onSaved,
}: OutputArtifactPathPanelProps) {
  if (fields.length === 0) {
    return null
  }
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Upload className="size-3.5" />
        Output artifact paths
      </div>
      <div className="space-y-2">
        {fields.map((field) => (
          <OutputPathRow
            key={field.name}
            field={field}
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
            onSaved={onSaved}
          />
        ))}
      </div>
    </section>
  )
}

interface IoSchemaFieldsPanelProps {
  side: IoSide
  fields: IoField[]
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
  // n2-canvas#10: per-input-field supply/demand entries keyed by field name. Only
  // the inputs side renders data-gap markers (outputs have no upstream supply).
  supplyByField?: Map<string, FieldSupplyEntry>
}

interface IoFieldRowProps {
  side: IoSide
  field: IoField
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
  // n2-canvas#10: the backend supply/demand entry for THIS input field (keyed by
  // field name out of graph_topology[].field_supply). undefined for output fields
  // and graph-level io (no per-node supply projection there).
  supply?: FieldSupplyEntry
}

// n2-canvas#10 (data-gap-viz): render the input field's supply state from the
// backend `field_supply` entry. A `supplied=false` field is a DATA GAP — nothing
// upstream feeds it — shown as a warning marker; a supplied field shows its
// producer phase (source='phase') or that it comes from the run's external input
// (source='graph_input'). Drives entirely off the real backend projection.
function DataGapMarker({ supply }: { supply: FieldSupplyEntry }) {
  if (!supply.supplied) {
    return (
      <div
        className="flex items-center gap-1.5 rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-[11px] text-destructive"
        role="status"
        aria-label={`Data gap: input field ${supply.field} is not supplied by any upstream phase or graph input`}
      >
        <TriangleAlert className="size-3.5 shrink-0" />
        <span>No upstream supplies this field</span>
      </div>
    )
  }
  const producerLabel =
    supply.source === "graph_input"
      ? "Graph input"
      : supply.producer_phase ?? "upstream phase"
  return (
    <div
      className="flex items-center gap-1.5 px-0.5 text-[11px] text-muted-foreground"
      aria-label={`Input field ${supply.field} supplied by ${producerLabel}`}
    >
      <ArrowRight className="size-3.5 shrink-0" />
      <span>
        from <span className="font-mono text-foreground">{producerLabel}</span>
      </span>
    </div>
  )
}

// Writes one mutation back to the targeted io file's frontmatter via the shared
// F2/F3 save path: resolve the workspace root, apply a pure writeback, then
// writeSkillFile to `relPath` (GRAPH.md for graph-level io, or a phase file for
// per-node io). The pure function decides which io side + field changes; the
// other io side, every other frontmatter key, and the body survive.
async function saveGraph(
  skillId: string,
  workspaceRoot: string | null | undefined,
  relPath: string,
  graphMd: string,
  next: (graphMd: string) => string,
): Promise<void> {
  await writeIoFile(skillId, workspaceRoot, relPath, graphMd, next(graphMd))
}

// One declared io field as an editable row: rename (Input, save on blur/Enter),
// change-type (Select), remove (Trash). Each commit goes through saveGraph onto
// `io.<side>.properties.<field>` in GRAPH.md — the authoritative contract the
// engine validates — so there are no fake-file dead paths to lose edits to.
function IoFieldRow({ side, field, skillId, workspaceRoot = null, relPath, graphMd, onSaved, supply }: IoFieldRowProps) {
  const [nameDraft, setNameDraft] = useState(field.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (next: (graphMd: string) => string) => {
    if (!graphMd) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveGraph(skillId, workspaceRoot, relPath, graphMd, next)
      onSaved?.()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  const handleRename = () => {
    const nextName = nameDraft.trim()
    if (nextName === "" || nextName === field.name) {
      setNameDraft(field.name)
      return
    }
    void run((graphMd) => renameIoField(graphMd, side, field.name, nextName))
  }

  return (
    <div className="space-y-1.5 rounded-md border border-border bg-background p-3">
      <div className="flex items-center gap-2">
        <Input
          value={nameDraft}
          onChange={(event) => setNameDraft(event.target.value)}
          onBlur={handleRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.currentTarget.blur()
            }
          }}
          placeholder="field_name"
          className="font-mono"
          spellCheck={false}
          aria-label={`Rename ${side} field ${field.name}`}
          disabled={busy || !graphMd}
        />
        <Select
          value={IO_FIELD_TYPES.includes(field.type as IoFieldType) ? field.type : undefined}
          onValueChange={(value) =>
            void run((graphMd) => setIoFieldType(graphMd, side, field.name, value as IoFieldType))
          }
          disabled={busy || !graphMd}
        >
          <SelectTrigger
            className="w-28 font-mono"
            aria-label={`Type for ${side} field ${field.name}`}
          >
            <SelectValue placeholder={field.type || "type"} />
          </SelectTrigger>
          <SelectContent>
            {IO_FIELD_TYPES.map((type) => (
              <SelectItem key={type} value={type} className="font-mono">
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void run((graphMd) => removeIoField(graphMd, side, field.name))}
          disabled={busy || !graphMd}
          aria-label={`Remove ${side} field ${field.name}`}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {error}
        </div>
      ) : null}
      {supply ? <DataGapMarker supply={supply} /> : null}
    </div>
  )
}

// Add-a-field control: a name Input + type Select + Add Button that appends a
// new `{type}` field to `io.<side>.properties` in GRAPH.md.
function IoFieldAddRow({
  side,
  skillId,
  workspaceRoot = null,
  relPath,
  graphMd,
  onSaved,
}: {
  side: IoSide
  skillId: string
  workspaceRoot?: string | null
  relPath: string
  graphMd?: string
  onSaved?: () => void
}) {
  const [name, setName] = useState("")
  const [type, setType] = useState<IoFieldType>("string")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAdd = async () => {
    if (!graphMd || name.trim() === "") {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveGraph(skillId, workspaceRoot, relPath, graphMd, (graphMd) => addIoField(graphMd, side, name, type))
      setName("")
      onSaved?.()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1.5 rounded-md border border-dashed border-border bg-background p-3">
      <div className="flex items-center gap-2">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              void handleAdd()
            }
          }}
          placeholder="new_field"
          className="font-mono"
          spellCheck={false}
          aria-label={`New ${side} field name`}
          disabled={busy || !graphMd}
        />
        <Select
          value={type}
          onValueChange={(value) => setType(value as IoFieldType)}
          disabled={busy || !graphMd}
        >
          <SelectTrigger className="w-28 font-mono" aria-label={`New ${side} field type`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {IO_FIELD_TYPES.map((option) => (
              <SelectItem key={option} value={option} className="font-mono">
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          size="sm"
          onClick={() => void handleAdd()}
          disabled={busy || !graphMd || name.trim() === ""}
          aria-label={`Add ${side} field`}
        >
          <Plus className="size-3.5" />
          Add
        </Button>
      </div>
      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  )
}

// Field-level editor for one io side (inputs/outputs): lists each declared field
// with rename / change-type / remove, plus an add row. Writes back to GRAPH.md
// `io.<side>.properties` frontmatter — the engine's authoritative contract —
// complementing the F2 schema-infer and F3 artifact-path tools (which stay).
function IoSchemaFieldsPanel({
  side,
  fields,
  skillId,
  workspaceRoot = null,
  relPath,
  graphMd,
  onSaved,
  supplyByField,
}: IoSchemaFieldsPanelProps) {
  const label = side === "inputs" ? "Input fields" : "Output fields"
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <Upload className="size-3.5" />
        {label}
      </div>
      <div className="space-y-2">
        {fields.map((field) => (
          <IoFieldRow
            key={field.name}
            side={side}
            field={field}
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
            onSaved={onSaved}
            supply={side === "inputs" ? supplyByField?.get(field.name) : undefined}
          />
        ))}
        <IoFieldAddRow
          side={side}
          skillId={skillId}
          workspaceRoot={workspaceRoot}
          relPath={relPath}
          graphMd={graphMd}
          onSaved={onSaved}
        />
      </div>
    </section>
  )
}

export function InputPanel({
  skillId,
  workspaceRoot = null,
  skillDetail,
  selectedNode = null,
  selectedTestInputId = null,
  onSelectTestInput,
}: InputPanelProps) {
  const contract = inputContractView(skillDetail)
  // Atom #27: resolve which io-bearing file this panel edits — GRAPH.md for the
  // graph-level io (no node / global input-output node) or the selected phase's
  // own file for per-node io. The field readers + writebacks below all operate
  // on this one target so a phase node edits ITS frontmatter io, not the graph's.
  const target = useMemo(() => resolveIoEditTarget(selectedNode, skillDetail), [selectedNode, skillDetail])
  const { relPath } = target
  const graphMd = target.content
  const outputFields = useMemo(() => outputArtifactFields(graphMd), [graphMd])
  const inputIoFields = useMemo(() => (graphMd ? listIoFields(graphMd, "inputs") : []), [graphMd])
  const outputIoFields = useMemo(() => (graphMd ? listIoFields(graphMd, "outputs") : []), [graphMd])
  // n2-canvas#10: per-input-field supply/demand projection for THIS selected node,
  // read from the backend graph_topology[].field_supply (see fieldSupplyByField).
  // Empty for graph-level io — the data-gap view is a per-node concern.
  const supplyByField = useMemo(
    () => fieldSupplyByField(selectedNode, skillDetail),
    [selectedNode, skillDetail],
  )
  const scopeLabel = target.isGraphLevel ? "Graph-level i/o" : `Node i/o · ${target.label}`

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="I/O" />

      <ScrollArea className="flex-1">
        <PanelBody>
          <PanelSection>
            <div className="text-[11px] text-muted-foreground" aria-label="I/O edit scope">
              {scopeLabel}
            </div>
          </PanelSection>

          <TestInputsSection
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            selectedId={selectedTestInputId}
            onSelect={onSelectTestInput}
          />

          <GoldenSection skillId={skillId} />

          <SectionHeading label="Input Schema" />
          <IoSchemaFieldsPanel
            side="inputs"
            fields={inputIoFields}
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
            supplyByField={supplyByField}
          />
          <SchemaInferPanel
            initialJson={contract.inputSampleJson}
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
          />
          <FileImportPanel
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
          />

          <SectionHeading label="Output Schema" />
          <IoSchemaFieldsPanel
            side="outputs"
            fields={outputIoFields}
            skillId={skillId}
            workspaceRoot={workspaceRoot}
            relPath={relPath}
            graphMd={graphMd}
          />

          {outputFields.length > 0 ? (
            <>
              <SectionHeading label="Output Artifacts" />
              <OutputArtifactPathPanel
                fields={outputFields}
                skillId={skillId}
                workspaceRoot={workspaceRoot}
                relPath={relPath}
                graphMd={graphMd}
              />
            </>
          ) : null}
        </PanelBody>
      </ScrollArea>
    </div>
  )
}
