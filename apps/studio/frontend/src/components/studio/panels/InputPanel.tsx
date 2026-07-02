import { useState, type ComponentProps } from "react"
import { FileInput, FileText } from "lucide-react"
import type { SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { sha256Hex } from "@/lib/hash"
import { ioSchemaOf, parseFrontmatter, schemaObject } from "@/lib/io-declarations"
import { applyImportedFileFieldToGraph, applyOutputArtifactPathToGraph } from "@/lib/schema-infer"
import { errorMessage } from "@/utils/errors"
import type { FileOpenInput } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelBody, PanelFieldRow } from "./_shared/PanelSection"
import { GoldenSection } from "./GoldenSection"
import { resolveIoEditTarget, type SelectedNode } from "./io-target"
import { TestInputsSection } from "./TestInputsSection"

type SaveIoFile = (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void

interface InputPanelProps {
  skillId: string
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode?: SelectedNode
  // F4: which saved test input feeds Predict/Run (wired through Workspace).
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onFileOpen?: (fileOrPath: FileOpenInput) => void
  // Writes for the import-file / artifact-path entries (same optimistic-hash
  // contract PropertiesPanel uses).
  onPhaseFileSave?: SaveIoFile
}

type JsonSchema = Record<string, unknown>

interface IoDocumentView {
  relPath: string
  /** Raw md content of the resolved io document (for edit write-backs). */
  content: string
  inputSchema: JsonSchema | null
  outputSchema: JsonSchema | null
}

const EMPTY_SCHEMA: JsonSchema = {}
const YAML_FIELD_LABEL_CLASS = "!text-sm !font-semibold !leading-5 !text-foreground/70"
const YAML_ICON_BUTTON_CLASS =
  "size-7 rounded-md bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-foreground"
const EXAMPLE_CODE_CLASS =
  "max-h-72 overflow-auto rounded-md bg-muted/30 px-2 py-2 font-mono text-xs leading-relaxed text-foreground"
const ROW_INPUT_CLASS = "w-full rounded-md border border-border bg-card px-2 py-1 text-xs"
const ROW_BUTTON_CLASS =
  "flex items-center gap-1 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
const ROW_ERROR_CLASS =
  "rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive"

function isJsonSerializablePrimitive(value: unknown): value is string | number | boolean | null {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean"
}

function jsonExampleFromSchema(schema: unknown): unknown {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    return null
  }
  const objectSchema = schema as JsonSchema
  const explicitExample = Array.isArray(objectSchema.examples) ? objectSchema.examples[0] : undefined
  if (isJsonSerializablePrimitive(objectSchema.default)) {
    return objectSchema.default
  }
  if (isJsonSerializablePrimitive(objectSchema.const)) {
    return objectSchema.const
  }
  if (isJsonSerializablePrimitive(explicitExample)) {
    return explicitExample
  }
  if (Array.isArray(objectSchema.enum) && isJsonSerializablePrimitive(objectSchema.enum[0])) {
    return objectSchema.enum[0]
  }

  const schemaType = Array.isArray(objectSchema.type)
    ? objectSchema.type.find((candidate) => candidate !== "null")
    : objectSchema.type

  if (schemaType === "object" || schemaObject(objectSchema.properties)) {
    const properties = schemaObject(objectSchema.properties) ?? EMPTY_SCHEMA
    return Object.fromEntries(
      Object.entries(properties).map(([name, propertySchema]) => [name, jsonExampleFromSchema(propertySchema)]),
    )
  }
  if (schemaType === "array") {
    return [jsonExampleFromSchema(objectSchema.items)]
  }
  if (schemaType === "integer" || schemaType === "number") {
    return 0
  }
  if (schemaType === "boolean") {
    return false
  }
  if (schemaType === "string") {
    return ""
  }
  if (Array.isArray(objectSchema.oneOf) && objectSchema.oneOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.oneOf[0])
  }
  if (Array.isArray(objectSchema.anyOf) && objectSchema.anyOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.anyOf[0])
  }
  if (Array.isArray(objectSchema.allOf) && objectSchema.allOf.length > 0) {
    return jsonExampleFromSchema(objectSchema.allOf[0])
  }
  return null
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function buildIoDocumentView(skillDetail: SkillDetail | undefined, selectedNode: SelectedNode = null): IoDocumentView {
  const target = resolveIoEditTarget(selectedNode, skillDetail)
  const content = target.content ?? ""
  const frontmatter = parseFrontmatter(content)
  return {
    relPath: target.relPath,
    content,
    inputSchema: ioSchemaOf(frontmatter, "inputs"),
    outputSchema: ioSchemaOf(frontmatter, "outputs"),
  }
}

/**
 * Shared submit path for the io-document edit entries (import-file field /
 * artifact path): run the pure mutation against the CURRENT document content,
 * save with the previous content's hash (optimistic concurrency, same contract
 * PropertiesPanel uses), and return the surfaced error message (null = saved).
 */
async function submitIoDocumentEdit({
  relPath,
  content,
  mutate,
  save,
}: {
  relPath: string
  content: string
  mutate: (content: string) => string
  save?: SaveIoFile
}): Promise<string | null> {
  let next: string
  try {
    next = mutate(content)
  } catch (err) {
    return errorMessage(err)
  }
  if (!save) {
    return "Saving is unavailable in this context"
  }
  try {
    await save({ path: relPath, content: next, expectedHash: await sha256Hex(content) })
    return null
  } catch (err) {
    return errorMessage(err)
  }
}

function YamlFieldLabel({ className, ...props }: ComponentProps<typeof FieldLabel>) {
  return (
    <FieldLabel
      className={`${YAML_FIELD_LABEL_CLASS}${className ? ` ${className}` : ""}`}
      {...props}
    />
  )
}

function ExampleField({
  title,
  schema,
  relPath,
  onEdit,
}: {
  title: string
  schema: JsonSchema | null
  relPath: string
  onEdit?: () => void
}) {
  const example = schema ? jsonExampleFromSchema(schema) : null
  return (
    <PanelFieldRow>
      <Field>
        <YamlFieldLabel>{title.toLowerCase()}</YamlFieldLabel>
        <div className="flex items-center justify-between gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <FieldDescription className="min-w-0 flex-1 truncate font-mono">
                {relPath}
              </FieldDescription>
            </TooltipTrigger>
            <TooltipContent>{relPath}</TooltipContent>
          </Tooltip>
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className={YAML_ICON_BUTTON_CLASS}
            onClick={onEdit}
            disabled={!onEdit}
            aria-label={`Edit ${title.toLowerCase()} schema in ${relPath}`}
          >
            <FileText className="size-3.5" aria-hidden />
          </Button>
        </div>
        {schema ? (
          <pre className={EXAMPLE_CODE_CLASS}>{prettyJson(example)}</pre>
        ) : (
          <FieldDescription>No {title.toLowerCase()} example can be generated from this md file.</FieldDescription>
        )}
      </Field>
    </PanelFieldRow>
  )
}

/**
 * #28 any-io-import-file: declare `{source:'file', path}` on an input field of
 * the resolved io document — the engine lazily injects the file's content into
 * the blackboard when the phase runs.
 */
function ImportFileFieldRow({ view, onSave }: { view: IoDocumentView; onSave?: SaveIoFile }) {
  const [fieldName, setFieldName] = useState("")
  const [filePath, setFilePath] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleImport = async () => {
    setBusy(true)
    const failure = await submitIoDocumentEdit({
      relPath: view.relPath,
      content: view.content,
      mutate: (content) => applyImportedFileFieldToGraph(content, fieldName, "string", filePath),
      save: onSave,
    })
    setError(failure)
    if (!failure) {
      setFieldName("")
      setFilePath("")
    }
    setBusy(false)
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-2">
      <p className="text-[11px] text-muted-foreground">
        Import a file as an input field — the engine injects its content when this node runs.
      </p>
      <input
        value={fieldName}
        onChange={(event) => setFieldName(event.target.value)}
        placeholder="Field name"
        aria-label="Import file field name"
        className={ROW_INPUT_CLASS}
      />
      <input
        value={filePath}
        onChange={(event) => setFilePath(event.target.value)}
        placeholder="Workspace-relative file path (e.g. references/ch1.md)"
        aria-label="Import file path"
        className={ROW_INPUT_CLASS}
      />
      {error ? <div className={ROW_ERROR_CLASS}>{error}</div> : null}
      <button
        type="button"
        onClick={() => void handleImport()}
        disabled={busy}
        aria-label="Import file as input field"
        className={ROW_BUTTON_CLASS}
      >
        <FileInput className="size-3.5" aria-hidden />
        Import file as input field
      </button>
    </div>
  )
}

/**
 * #29 output-artifact-path: per output field, set/clear `{target:'artifact',
 * path}` so the run persists that field under `.workspace/runs/<id>/artifacts`.
 */
function OutputArtifactRow({
  view,
  field,
  currentPath,
  onSave,
}: {
  view: IoDocumentView
  field: string
  currentPath: string
  onSave?: SaveIoFile
}) {
  const [path, setPath] = useState(currentPath)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleApply = async () => {
    setBusy(true)
    const failure = await submitIoDocumentEdit({
      relPath: view.relPath,
      content: view.content,
      mutate: (content) => applyOutputArtifactPathToGraph(content, field, path),
      save: onSave,
    })
    setError(failure)
    setBusy(false)
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="min-w-0 shrink-0 font-mono text-xs text-foreground">{field}</span>
        <input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="artifact path (empty = no artifact)"
          aria-label={`Artifact path for ${field}`}
          className={ROW_INPUT_CLASS}
        />
        <button
          type="button"
          onClick={() => void handleApply()}
          disabled={busy || path === currentPath}
          aria-label={`Apply artifact path for ${field}`}
          className={ROW_BUTTON_CLASS}
        >
          Apply
        </button>
      </div>
      {error ? <div className={ROW_ERROR_CLASS}>{error}</div> : null}
    </div>
  )
}

function outputArtifactEntries(outputSchema: JsonSchema | null): Array<{ field: string; path: string }> {
  const properties = outputSchema ? schemaObject(outputSchema.properties) : null
  if (!properties) {
    return []
  }
  return Object.entries(properties).map(([field, schema]) => {
    const fieldSchema = schemaObject(schema)
    const path = fieldSchema && fieldSchema.target === "artifact" && typeof fieldSchema.path === "string"
      ? fieldSchema.path
      : ""
    return { field, path }
  })
}

export function InputPanel({
  skillId,
  workspaceRoot = null,
  skillDetail,
  selectedNode = null,
  selectedTestInputId = null,
  onSelectTestInput,
  onFileOpen,
  onPhaseFileSave,
}: InputPanelProps) {
  const view = buildIoDocumentView(skillDetail, selectedNode)
  const openSource = () => onFileOpen?.(view.relPath)
  const editSource = onFileOpen ? openSource : undefined
  const artifactEntries = outputArtifactEntries(view.outputSchema)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input / Output" />
      <ScrollArea className="flex-1">
        <PanelBody>
          <FieldSet>
            <FieldGroup>
              <ExampleField title="Input" schema={view.inputSchema} relPath={view.relPath} onEdit={editSource} />
              <PanelFieldRow>
                <div className="space-y-2">
                  <TestInputsSection
                    skillId={skillId}
                    workspaceRoot={workspaceRoot}
                    selectedId={selectedTestInputId}
                    onSelect={onSelectTestInput}
                  />
                  <ImportFileFieldRow view={view} onSave={onPhaseFileSave} />
                </div>
              </PanelFieldRow>
              <ExampleField title="Output" schema={view.outputSchema} relPath={view.relPath} onEdit={editSource} />
              {artifactEntries.length > 0 ? (
                <PanelFieldRow>
                  <Field>
                    <YamlFieldLabel>output artifacts</YamlFieldLabel>
                    <div className="space-y-2">
                      {artifactEntries.map((entry) => (
                        <OutputArtifactRow
                          key={entry.field}
                          view={view}
                          field={entry.field}
                          currentPath={entry.path}
                          onSave={onPhaseFileSave}
                        />
                      ))}
                    </div>
                  </Field>
                </PanelFieldRow>
              ) : null}
              <PanelFieldRow>
                <GoldenSection skillId={skillId} />
              </PanelFieldRow>
            </FieldGroup>
          </FieldSet>
        </PanelBody>
      </ScrollArea>
    </div>
  )
}

export const __test__ = {
  buildIoDocumentView,
  jsonExampleFromSchema,
  parseFrontmatter,
  submitIoDocumentEdit,
  outputArtifactEntries,
}
