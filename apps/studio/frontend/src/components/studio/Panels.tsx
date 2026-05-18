import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  Upload,
  type LucideIcon,
} from "lucide-react"
import { useMemo, useState, type DragEvent, type ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import type { SkillDetail } from "@/api/types"
import { HistoryPanel } from "@/components/history/HistoryPanel"
import { inferJsonSchemaFromText } from "@/lib/schema-infer"
import type { SkillGraphNodeData, SubagentRef } from "@/components/GraphCanvas"
import type { PanelKind } from "./Toolbar"
import { useWorkspaceContext } from "./WorkspaceContext"
import type { FileMeta } from "./file-types"

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
}

interface AssetsPanelProps {
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
}

interface InputPanelProps {
  skillDetail?: SkillDetail
  onFileOpen: (file: FileMeta) => void
}

function PanelHeader({ title, extra }: { title: string; extra?: ReactNode }) {
  return (
    <div className="flex h-10 shrink-0 items-center px-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground">{title}</span>
        {extra}
      </div>
    </div>
  )
}

function SectionHeading({ label }: { label: string }) {
  return (
    <div className="px-2 pb-0.5 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
  )
}

function FileRow({
  file,
  icon: Icon = FileText,
  onOpen,
}: {
  file: FileMeta
  icon?: LucideIcon
  onOpen: (file: FileMeta) => void
}) {
  const filename = file.path.split("/").pop() ?? file.path

  return (
    <button
      type="button"
      onClick={() => onOpen(file)}
      className="flex w-full cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
    >
      <Icon className="size-4" strokeWidth={1.5} />
      <span className="truncate">{filename}</span>
    </button>
  )
}

function FolderRow({
  name,
  children,
  defaultExpanded = false,
}: {
  name: string
  children: ReactNode
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md border-0 px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-4" strokeWidth={1.5} />
        <span>{name}</span>
      </button>
      {expanded ? <div className="pl-4">{children}</div> : null}
    </div>
  )
}

function languageForPath(path: string): string {
  if (path.endsWith(".json")) return "json"
  if (path.endsWith(".py")) return "python"
  return "markdown"
}

function fileFromDetail(skillDetail: SkillDetail | undefined, path: string): FileMeta {
  return {
    path,
    language: languageForPath(path),
    content: skillDetail?.files?.[path] ?? "",
  }
}

function phaseIds(skillDetail?: SkillDetail): string[] {
  const fromTopology = skillDetail?.graph_topology?.map((phase) => phase.id) ?? []
  if (fromTopology.length > 0) return fromTopology
  const phases = skillDetail?.manifest.schema_version === "2.1" ? skillDetail.manifest.phases : []
  return phases.map((phase) => phase.id)
}

function actionFiles(skillDetail: SkillDetail | undefined, phaseId: string): FileMeta[] {
  return Object.keys(skillDetail?.files ?? {})
    .filter((path) => path.startsWith(`phases/${phaseId}/actions/`) && path.endsWith(".py"))
    .sort()
    .map((path) => fileFromDetail(skillDetail, path))
}

function manifestFiles(skillDetail?: SkillDetail, selectedNode?: { id: string; data: SkillGraphNodeData } | null): FileMeta[] {
  const manifest = skillDetail?.manifest
  if (skillDetail?.files) {
    return Object.keys(skillDetail.files)
      .sort()
      .map((path) => fileFromDetail(skillDetail, path))
  }
  const files: FileMeta[] = [
    {
      path: "SKILL.md",
      language: "markdown",
      content: manifest
        ? `# ${manifest.name}\n\n${manifest.description ?? "No description."}\n`
        : "# Skill\n\nLoading skill metadata...\n",
    },
    {
      path: "skill-manifest.json",
      language: "json",
      content: JSON.stringify(manifest ?? {}, null, 2),
    },
  ]

  if (selectedNode) {
    files.push({
      path: `nodes/${selectedNode.id}.md`,
      language: "markdown",
      content: `# ${selectedNode.data.label}\n\nMode: ${selectedNode.data.mode}\nStatus: ${selectedNode.data.status}\n`,
    })
  }

  return files
}

function inputFiles(skillDetail?: SkillDetail): FileMeta[] {
  const manifest = skillDetail?.manifest
  const io = manifest?.schema_version === "2.0" && manifest.type === "graph" ? manifest.io : null
  if (skillDetail?.files) {
    return [
      fileFromDetail(skillDetail, "io/inputs.json"),
      fileFromDetail(skillDetail, "io/outputs.json"),
    ]
  }

  return [
    {
      path: "input/schema.json",
      language: "json",
      content: JSON.stringify({ inputs: io?.inputs ?? [], outputs: io?.outputs ?? [] }, null, 2),
    },
    {
      path: "input/sample.json",
      language: "json",
      content: JSON.stringify(Object.fromEntries((io?.inputs ?? []).map((input) => [input.name, ""])), null, 2),
    },
  ]
}

export function AssetsPanel({ skillDetail, selectedNode }: AssetsPanelProps) {
  const { onFileOpen } = useWorkspaceContext()
  const files = manifestFiles(skillDetail, selectedNode)
  const phases = phaseIds(skillDetail)
  const filesByPath = new Map(files.map((file) => [file.path, file]))
  const openFile = (file: FileMeta) => onFileOpen(file)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Assets" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Skill Files" />
          <FileRow file={filesByPath.get("GRAPH.md") ?? fileFromDetail(skillDetail, "GRAPH.md")} onOpen={openFile} />
          <FolderRow name="phases" defaultExpanded>
            {phases.map((phaseId) => (
              <FolderRow key={phaseId} name={phaseId} defaultExpanded>
                {(["SKILL.md", "LOGIC.md", "SUBGRAPH.md"] as const).map((filename) => {
                  const path = `phases/${phaseId}/${filename}`
                  const file = filesByPath.get(path)
                  return file ? <FileRow key={path} file={file} onOpen={openFile} /> : null
                })}
                {actionFiles(skillDetail, phaseId).length > 0 ? (
                  <FolderRow name="actions" defaultExpanded>
                    {actionFiles(skillDetail, phaseId).map((file) => (
                      <FileRow key={file.path} file={file} onOpen={openFile} />
                    ))}
                  </FolderRow>
                ) : null}
              </FolderRow>
            ))}
          </FolderRow>
          <FolderRow name="io" defaultExpanded>
            {(["io/inputs.json", "io/outputs.json"] as const).map((path) => {
              const file = filesByPath.get(path)
              return file ? <FileRow key={path} file={file} onOpen={openFile} /> : null
            })}
          </FolderRow>
          {filesByPath.size === 0 && files[2] ? (
            <FolderRow name="nodes" defaultExpanded>
              <FileRow file={files[2]} onOpen={openFile} />
            </FolderRow>
          ) : null}
        </div>
      </ScrollArea>
    </div>
  )
}

function SchemaInferPanel({ initialJson }: { initialJson: string }) {
  const [draft, setDraft] = useState(initialJson)
  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : "Invalid JSON" }
    }
  }, [draft])

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
      </div>
    </section>
  )
}

export function InputPanel({ skillDetail, onFileOpen }: InputPanelProps) {
  const files = inputFiles(skillDetail)
  const sample = files.find((file) => file.path === "input/sample.json")?.content ?? "{}"

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input" />

      <ScrollArea className="flex-1">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Input Files" />
          <FileRow file={files[1]} onOpen={onFileOpen} />

          <SectionHeading label="Schema" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <SchemaInferPanel initialJson={sample} />
        </div>
      </ScrollArea>
    </div>
  )
}

export function TimelinePanel() {
  const traces = [
    { id: 1, name: "Latest run", status: "success", duration: "2.3s", time: "2m ago" },
    { id: 2, name: "Previous run", status: "error", duration: "0.8s", time: "5m ago" },
  ]

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Timeline" />

      <ScrollArea className="flex-1">
        <div className="px-2 py-2">
          {traces.map((trace) => (
            <div
              key={trace.id}
              className="group cursor-pointer rounded-md px-2 py-2 transition-colors hover:bg-accent"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {trace.status === "success" ? (
                    <CheckCircle2 className="size-4 text-foreground" />
                  ) : (
                    <AlertCircle className="size-4 text-destructive" />
                  )}
                  <span className="text-xs text-muted-foreground group-hover:text-foreground">{trace.name}</span>
                </div>
                <span className="text-xs text-muted-foreground">{trace.time}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 pl-6 text-xs text-muted-foreground">
                <span>{trace.duration}</span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

function phaseKindLabel(data: Pick<SkillGraphNodeData, "mode" | "subgraphPath">): "LOGIC" | "AGENT" | "SUBGRAPH" {
  if (data.subgraphPath || data.mode === "subgraph") return "SUBGRAPH"
  if (data.mode === "skill" || data.mode === "llm") return "AGENT"
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
}

export function PropertiesPanel({
  skillId = null,
  selectedNode,
  onFileOpen,
}: PropertiesPanelProps) {
  const modeLabel = selectedNode ? phaseKindLabel(selectedNode.data) : null
  const filePath = selectedNode?.data.filePath ?? (selectedNode ? `phases/${selectedNode.id}/${phaseKindFile(selectedNode.data)}` : null)
  const subagents = selectedNode?.data.subagents ?? []

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Properties" />

      <ScrollArea className="flex-1">
        {selectedNode ? (
          <dl className="space-y-3 px-2 py-2">
            <div className="flex items-center justify-between px-1">
              <span className="truncate text-xs font-medium text-foreground">{selectedNode.data.label}</span>
              {modeLabel ? <Badge variant="secondary">{modeLabel}</Badge> : null}
            </div>
            <DetailRow label="Phase ID" value={selectedNode.id} />
            <DetailRow label="Mode" value={modeLabel} />
            <DetailRow label="Depends On" value={selectedNode.data.dependsOn} />
            <DetailRow label="Role" value={selectedNode.data.role} />
            <DetailRow label="Tools" value={selectedNode.data.tools} />
            <SubagentsSection skillId={skillId} subagents={subagents} onFileOpen={onFileOpen} />
            <DetailRow label="File" value={filePath} />
          </dl>
        ) : (
          <div className="p-4 text-xs text-muted-foreground">Select a node to inspect</div>
        )}
      </ScrollArea>
    </div>
  )
}

export function Panels({ activePanel, skillId, skillDetail, selectedNode }: PanelsProps) {
  const { onFileOpen } = useWorkspaceContext()
  if (!skillId) {
    return (
      <div className="flex h-full w-full flex-col bg-sidebar">
        <PanelHeader title="Workspace" />
        <div className="p-4 text-xs text-muted-foreground">Open a skill to populate this panel.</div>
      </div>
    )
  }

  if (activePanel === "assets") {
    return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} />
  }
  if (activePanel === "input") {
    return <InputPanel skillDetail={skillDetail} onFileOpen={onFileOpen} />
  }
  if (activePanel === "timeline") {
    return <TimelinePanel />
  }
  if (activePanel === "local-history") {
    return <HistoryPanel skillId={skillId} />
  }
  if (activePanel === "properties") {
    return <PropertiesPanel skillId={skillId} skillDetail={skillDetail} selectedNode={selectedNode} onFileOpen={onFileOpen} />
  }
  return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} />
}
