import { useState, type ComponentProps } from "react"
import { FileText, Files, Settings2 } from "lucide-react"
import type { SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { sha256Hex } from "@/lib/hash"
import {
  applyGraphArtifacts,
  applyIoInputChecks,
  blackboardAtNode,
  blackboardAtOutput,
  fileFieldsOf,
  graphArtifactsOf,
  type ArtifactRow,
  type FileFieldDecl,
  type IoInputChecks,
} from "@/lib/io-config"
import { ioSchemaOf, parseFrontmatter, schemaObject } from "@/lib/io-declarations"
import { errorMessage } from "@/utils/errors"
import type { FileOpenInput } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelBody, PanelFieldRow } from "./_shared/PanelSection"
import { InputConfigDialog, OutputConfigDialog } from "./IoConfigDialog"
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
  // Writes for the config-dialog declarations (same optimistic-hash contract
  // PropertiesPanel uses).
  onPhaseFileSave?: SaveIoFile
}

type JsonSchema = Record<string, unknown>

interface IoDocumentView {
  relPath: string
  /** Raw md content of the resolved io document (for edit write-backs). */
  content: string
  inputSchema: JsonSchema | null
  outputSchema: JsonSchema | null
  isGraphLevel: boolean
  label: string
}

const EMPTY_SCHEMA: JsonSchema = {}
const YAML_FIELD_LABEL_CLASS = "!text-sm !font-semibold !leading-5 !text-foreground/70"
const YAML_ICON_BUTTON_CLASS =
  "size-7 rounded-md bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-foreground"
const EXAMPLE_CODE_CLASS =
  "max-h-72 overflow-auto rounded-md bg-muted/30 px-2 py-2 font-mono text-xs leading-relaxed text-foreground"

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
    isGraphLevel: target.isGraphLevel,
    label: target.label,
  }
}

/**
 * Shared submit path for config write-backs: run the pure mutation against
 * the CURRENT document content, save with the previous content's hash
 * (optimistic concurrency, same contract PropertiesPanel uses), and return
 * the surfaced error message (null = saved).
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

/** Per-item count hint: the batch numbers recorded on the input side, if any. */
function perItemCountOf(declarations: FileFieldDecl[]): number | null {
  for (const decl of declarations) {
    if (decl.numbers && decl.numbers.length > 0) {
      return decl.numbers.length
    }
  }
  return null
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
  onConfigure,
}: {
  title: string
  schema: JsonSchema | null
  relPath: string
  onEdit?: () => void
  onConfigure?: () => void
}) {
  const example = schema ? jsonExampleFromSchema(schema) : null
  return (
    <PanelFieldRow>
      <Field>
        <div className="flex items-center justify-between gap-2">
          <YamlFieldLabel>{title.toLowerCase()}</YamlFieldLabel>
          {onConfigure ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-6 gap-1 px-2 text-[11px]"
              onClick={onConfigure}
              aria-label={`Configure ${title.toLowerCase()}`}
            >
              <Settings2 className="size-3" aria-hidden />
              Configure
            </Button>
          ) : null}
        </div>
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

/** Panel list row for a declared input file / batch (name + muted path). */
function FileListRow({ decl }: { decl: FileFieldDecl }) {
  const isBatch = Boolean(decl.dir && decl.pattern)
  const hint = isBatch
    ? `${decl.dir} · ×${decl.numbers?.length ?? "?"}`
    : decl.path ?? ""
  return (
    <div className="flex items-baseline gap-2 rounded-md border border-border px-2 py-1">
      {isBatch ? (
        <Files className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      ) : (
        <FileText className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      )}
      <span className="shrink-0 font-mono text-xs text-foreground">{decl.field}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{hint}</span>
        </TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    </div>
  )
}

/** Panel list row for a configured output artifact (stem + mode). */
function ArtifactListRow({ row, perItemCount }: { row: ArtifactRow; perItemCount: number | null }) {
  return (
    <div className="flex items-baseline gap-2 rounded-md border border-border px-2 py-1">
      {row.mode === "per-item" ? (
        <Files className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      ) : (
        <FileText className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />
      )}
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">{row.stem}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {row.mode === "per-item" ? `per-item${perItemCount ? ` ×${perItemCount}` : ""}` : "single"}
      </span>
    </div>
  )
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
  const [inputConfigOpen, setInputConfigOpen] = useState(false)
  const [outputConfigOpen, setOutputConfigOpen] = useState(false)

  // Blackboard context: empty for GRAPH.md (the Input pseudo-node has no
  // blackboard — its checked file fields BECOME the graph entry fields).
  const blackboard = view.isGraphLevel ? [] : blackboardAtNode(skillDetail, selectedNode?.id ?? "")
  const declaredFiles = fileFieldsOf(view.content)
  const artifacts = graphArtifactsOf(skillDetail)
  const graphContent = skillDetail?.files?.["GRAPH.md"] ?? ""
  const perItemCount = perItemCountOf(fileFieldsOf(graphContent))

  const handleInputConfigSave = (checks: IoInputChecks) =>
    submitIoDocumentEdit({
      relPath: view.relPath,
      content: view.content,
      mutate: (content) => applyIoInputChecks(content, checks),
      save: onPhaseFileSave,
    })

  const handleArtifactsSave = (rows: ArtifactRow[]) =>
    submitIoDocumentEdit({
      relPath: "GRAPH.md",
      content: graphContent,
      mutate: (content) => applyGraphArtifacts(content, rows),
      save: onPhaseFileSave,
    })

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input / Output" />
      <ScrollArea className="flex-1">
        <PanelBody>
          <FieldSet>
            <FieldGroup>
              <ExampleField
                title="Input"
                schema={view.inputSchema}
                relPath={view.relPath}
                onEdit={editSource}
                onConfigure={() => setInputConfigOpen(true)}
              />
              {declaredFiles.length > 0 ? (
                <PanelFieldRow>
                  <Field>
                    <YamlFieldLabel>input files</YamlFieldLabel>
                    <div className="space-y-1">
                      {declaredFiles.map((decl) => (
                        <FileListRow key={decl.field} decl={decl} />
                      ))}
                    </div>
                  </Field>
                </PanelFieldRow>
              ) : null}
              <PanelFieldRow>
                <TestInputsSection
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  selectedId={selectedTestInputId}
                  onSelect={onSelectTestInput}
                  onFileOpen={onFileOpen}
                />
              </PanelFieldRow>
              <ExampleField
                title="Output"
                schema={view.outputSchema}
                relPath={view.relPath}
                onEdit={editSource}
                onConfigure={() => setOutputConfigOpen(true)}
              />
              {artifacts.length > 0 ? (
                <PanelFieldRow>
                  <Field>
                    <YamlFieldLabel>output artifacts</YamlFieldLabel>
                    <div className="space-y-1">
                      {artifacts.map((row) => (
                        <ArtifactListRow key={row.stem} row={row} perItemCount={perItemCount} />
                      ))}
                    </div>
                  </Field>
                </PanelFieldRow>
              ) : null}
            </FieldGroup>
          </FieldSet>
        </PanelBody>
      </ScrollArea>
      <InputConfigDialog
        open={inputConfigOpen}
        onOpenChange={setInputConfigOpen}
        skillId={skillId}
        targetLabel={view.isGraphLevel ? "GRAPH.md io.inputs" : view.label}
        blackboard={blackboard}
        declaredFiles={declaredFiles}
        onSave={handleInputConfigSave}
      />
      <OutputConfigDialog
        open={outputConfigOpen}
        onOpenChange={setOutputConfigOpen}
        universe={blackboardAtOutput(skillDetail)}
        artifacts={artifacts}
        perItemCount={perItemCount}
        onSave={handleArtifactsSave}
      />
    </div>
  )
}

export const __test__ = {
  buildIoDocumentView,
  jsonExampleFromSchema,
  parseFrontmatter,
  submitIoDocumentEdit,
  perItemCountOf,
}
