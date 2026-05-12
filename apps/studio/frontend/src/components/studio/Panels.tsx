import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, FileText, Folder, Upload } from 'lucide-react'
import { useMemo, useState, type DragEvent } from 'react'
import type { SkillDetail } from '../../api/types'
import { inferJsonSchemaFromText } from '../../lib/schema-infer'
import type { SkillGraphNodeData } from '../GraphCanvas'
import type { PanelKind } from './Toolbar'

export interface FileMeta {
  path: string
  language: string
  content: string
}

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string, data: SkillGraphNodeData } | null
  onFileOpen: (file: FileMeta) => void
}

function PanelHeader({ title }: { title: string }) {
  return (
    <div className="flex h-10 shrink-0 items-center px-3">
      <span className="text-xs font-medium text-foreground">{title}</span>
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

function FileRow({ file, onOpen, indent = false }: { file: FileMeta, onOpen: (file: FileMeta) => void, indent?: boolean }) {
  const filename = file.path.split('/').pop() ?? file.path

  return (
    <button
      type="button"
      onClick={() => onOpen(file)}
      className={[
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
        indent ? 'ml-4 border-l border-border pl-3' : '',
      ].join(' ')}
    >
      <FileText className="size-4" strokeWidth={1.5} />
      <span className="truncate">{filename}</span>
    </button>
  )
}

function FolderRow({ name, children, defaultExpanded = false }: { name: string, children: React.ReactNode, defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Folder className="size-4" strokeWidth={1.5} />
        <span>{name}</span>
      </button>
      {expanded ? <div>{children}</div> : null}
    </div>
  )
}

function manifestFiles(skillDetail?: SkillDetail, selectedNode?: { id: string, data: SkillGraphNodeData } | null): FileMeta[] {
  const manifest = skillDetail?.manifest
  const files: FileMeta[] = [
    {
      path: 'SKILL.md',
      language: 'markdown',
      content: manifest
        ? `# ${manifest.name}\n\n${manifest.description ?? 'No description.'}\n\nType: ${manifest.type}\n`
        : '# Skill\n\nLoading skill metadata...\n',
    },
    {
      path: 'skill-manifest.json',
      language: 'json',
      content: JSON.stringify(manifest ?? {}, null, 2),
    },
  ]

  if (selectedNode) {
    files.push({
      path: `nodes/${selectedNode.id}.md`,
      language: 'markdown',
      content: `# ${selectedNode.data.label}\n\nMode: ${selectedNode.data.mode}\nStatus: ${selectedNode.data.status}\n`,
    })
  }

  return files
}

function inputFiles(skillDetail?: SkillDetail): FileMeta[] {
  const manifest = skillDetail?.manifest
  const io = manifest?.type === 'graph' ? manifest.io : null

  return [
    {
      path: 'input/schema.json',
      language: 'json',
      content: JSON.stringify({ inputs: io?.inputs ?? [], outputs: io?.outputs ?? [] }, null, 2),
    },
    {
      path: 'input/sample.json',
      language: 'json',
      content: JSON.stringify(Object.fromEntries((io?.inputs ?? []).map((input) => [input.name, ''])), null, 2),
    },
  ]
}

function AssetsPanel({ skillDetail, selectedNode, onFileOpen }: Pick<PanelsProps, 'skillDetail' | 'selectedNode' | 'onFileOpen'>) {
  const files = manifestFiles(skillDetail, selectedNode)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Assets" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Skill Files" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <FileRow file={files[1]} onOpen={onFileOpen} />
          {files[2] ? (
            <FolderRow name="nodes" defaultExpanded>
              <FileRow file={files[2]} onOpen={onFileOpen} indent />
            </FolderRow>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function SchemaInferPanel({ initialJson }: { initialJson: string }) {
  const [draft, setDraft] = useState(initialJson)
  const result = useMemo(() => {
    try {
      return { schema: inferJsonSchemaFromText(draft), error: null as string | null }
    } catch (error) {
      return { schema: null, error: error instanceof Error ? error.message : 'Invalid JSON' }
    }
  }, [draft])

  const handleDrop = async (event: DragEvent<HTMLTextAreaElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files.item(0)
    if (file) {
      setDraft(await file.text())
      return
    }

    const text = event.dataTransfer.getData('text/plain')
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
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="h-28 w-full resize-none rounded-md border border-input bg-card p-2 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
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

function InputPanel({ skillDetail, onFileOpen }: Pick<PanelsProps, 'skillDetail' | 'onFileOpen'>) {
  const files = inputFiles(skillDetail)
  const sample = files.find((file) => file.path === 'input/sample.json')?.content ?? '{}'

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Input" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-3 px-2 py-2 text-xs">
          <SectionHeading label="Input Files" />
          <FileRow file={files[1]} onOpen={onFileOpen} />
          <SectionHeading label="Schema" />
          <FileRow file={files[0]} onOpen={onFileOpen} />
          <SchemaInferPanel initialJson={sample} />
        </div>
      </div>
    </div>
  )
}

function TimelinePanel() {
  const traces = [
    { id: 1, name: 'Latest run', status: 'success', duration: '2.3s', time: '2m ago' },
    { id: 2, name: 'Previous run', status: 'error', duration: '0.8s', time: '5m ago' },
  ]

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Timeline" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="px-2 py-2">
          {traces.map((trace) => (
            <div key={trace.id} className="group rounded-md px-2 py-2 transition-colors hover:bg-accent">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {trace.status === 'success' ? (
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
      </div>
    </div>
  )
}

function PropertiesPanel({ skillDetail, selectedNode }: Pick<PanelsProps, 'skillDetail' | 'selectedNode'>) {
  const manifest = skillDetail?.manifest
  const selectedType = selectedNode?.data.mode ?? manifest?.type ?? 'Skill'

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader title="Properties" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-5 p-4">
          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Node ID</label>
            <input
              readOnly
              value={selectedNode?.id ?? manifest?.name ?? 'No node selected'}
              className="h-7 w-full rounded-md border border-border bg-muted px-2 text-xs text-foreground"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Type</label>
            <div className="flex items-center gap-2">
              <span className="inline-flex h-5 items-center rounded-full bg-secondary px-2 text-[0.625rem] font-medium text-secondary-foreground">
                {selectedType}
              </span>
            </div>
          </div>

          <div className="border-t border-border" />

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Model</label>
            <button
              type="button"
              className="flex h-7 w-full items-center justify-between rounded-md border border-border bg-background px-2 text-xs font-normal text-foreground"
            >
              <span>{selectedNode?.data.role ?? 'Default model'}</span>
              <ChevronDown className="size-3.5 text-muted-foreground" />
            </button>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs text-muted-foreground">Temperature</label>
              <span className="text-xs text-muted-foreground">0.7</span>
            </div>
            <input className="w-full accent-primary" type="range" min="0" max="2" step="0.1" defaultValue="0.7" />
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">System Prompt</label>
            <textarea
              readOnly
              value={selectedNode ? `${selectedNode.data.label}\n\nDepends on: ${selectedNode.data.dependsOn.join(', ') || 'None'}` : 'Select a node on the canvas.'}
              className="min-h-24 w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export function Panels({ activePanel, skillId, skillDetail, selectedNode, onFileOpen }: PanelsProps) {
  if (!skillId) {
    return (
      <div className="flex h-full w-full flex-col bg-sidebar">
        <PanelHeader title="Workspace" />
        <div className="p-4 text-xs text-muted-foreground">Open a skill to populate this panel.</div>
      </div>
    )
  }

  if (activePanel === 'assets') {
    return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} onFileOpen={onFileOpen} />
  }
  if (activePanel === 'input') {
    return <InputPanel skillDetail={skillDetail} onFileOpen={onFileOpen} />
  }
  if (activePanel === 'timeline') {
    return <TimelinePanel />
  }
  return <PropertiesPanel skillDetail={skillDetail} selectedNode={selectedNode} />
}
