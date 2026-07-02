import type { ComponentProps } from "react"
import yaml from "js-yaml"
import { FileText } from "lucide-react"
import type { SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { FileOpenInput } from "../file-types"
import { PanelHeader } from "./_shared/PanelHeader"
import { PanelBody, PanelFieldRow } from "./_shared/PanelSection"
import { resolveIoEditTarget, type SelectedNode } from "./io-target"

interface InputPanelProps {
  skillId: string
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode?: SelectedNode
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onFileOpen?: (fileOrPath: FileOpenInput) => void
}

type JsonSchema = Record<string, unknown>
type IoSide = "inputs" | "outputs"

interface IoDocumentView {
  relPath: string
  inputSchema: JsonSchema | null
  outputSchema: JsonSchema | null
}

const EMPTY_SCHEMA: JsonSchema = {}
const YAML_FIELD_LABEL_CLASS = "!text-sm !font-semibold !leading-5 !text-foreground/70"
const YAML_ICON_BUTTON_CLASS =
  "size-7 rounded-md bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-foreground"
const EXAMPLE_CODE_CLASS =
  "max-h-72 overflow-auto rounded-md bg-muted/30 px-2 py-2 font-mono text-xs leading-relaxed text-foreground"

function parseFrontmatter(content: string | undefined): Record<string, unknown> {
  if (!content) {
    return {}
  }
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content)
  if (!match) {
    return {}
  }
  const parsed = yaml.load(match[1])
  return parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? parsed as Record<string, unknown>
    : {}
}

function schemaObject(value: unknown): JsonSchema | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonSchema
    : null
}

function ioSchema(frontmatter: Record<string, unknown>, side: IoSide): JsonSchema | null {
  const io = schemaObject(frontmatter.io)
  return io ? schemaObject(io[side]) : null
}

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
  const frontmatter = parseFrontmatter(target.content)
  return {
    relPath: target.relPath,
    inputSchema: ioSchema(frontmatter, "inputs"),
    outputSchema: ioSchema(frontmatter, "outputs"),
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

export function InputPanel({
  skillDetail,
  selectedNode = null,
  onFileOpen,
}: InputPanelProps) {
  const view = buildIoDocumentView(skillDetail, selectedNode)
  const openSource = () => onFileOpen?.(view.relPath)
  const editSource = onFileOpen ? openSource : undefined

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input / Output" />
      <ScrollArea className="flex-1">
        <PanelBody>
          <FieldSet>
            <FieldGroup>
              <ExampleField title="Input" schema={view.inputSchema} relPath={view.relPath} onEdit={editSource} />
              <ExampleField title="Output" schema={view.outputSchema} relPath={view.relPath} onEdit={editSource} />
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
}
