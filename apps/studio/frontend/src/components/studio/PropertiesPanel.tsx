import { Braces, Info, Workflow } from 'lucide-react'
import type { SkillDetail } from '../../api/types'
import type { SkillGraphNodeData } from '../GraphCanvas'

interface PropertiesPanelProps {
  skillDetail?: SkillDetail
  selectedNode: { id: string, data: SkillGraphNodeData } | null
}

function metadataEntries(skillDetail?: SkillDetail) {
  const manifest = skillDetail?.manifest
  if (!manifest) {
    return []
  }

  return [
    ['Name', manifest.name],
    ['Type', manifest.type],
    ['Version', manifest.version ?? 'Unversioned'],
    ['Author', manifest.author ?? 'Unknown'],
    ['License', manifest.license ?? 'Unspecified'],
  ]
}

export function PropertiesPanel({ skillDetail, selectedNode }: PropertiesPanelProps) {
  const manifest = skillDetail?.manifest
  const graphIo = manifest?.type === 'graph' ? manifest.io : null

  return (
    <aside className="flex h-full min-h-0 flex-col border-l border-border bg-card text-card-foreground">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">Properties</h2>
        <p className="mt-1 text-xs text-muted-foreground">Metadata, schema, and selected node details.</p>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <section>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Info className="size-3.5" />
            Skill metadata
          </div>
          <dl className="space-y-2 rounded-md border border-border bg-background p-3 text-sm">
            {metadataEntries(skillDetail).map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="truncate font-medium text-foreground">{value}</dd>
              </div>
            ))}
            {!manifest ? <div className="text-sm text-muted-foreground">Loading metadata...</div> : null}
          </dl>
        </section>

        <section>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Braces className="size-3.5" />
            Input / output schema
          </div>
          <div className="space-y-2 rounded-md border border-border bg-background p-3 text-sm">
            <div>
              <div className="text-xs font-medium text-muted-foreground">Inputs</div>
              <div className="mt-1 text-foreground">
                {graphIo?.inputs.length ? graphIo.inputs.map((input) => input.name).join(', ') : 'Runtime input'}
              </div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Outputs</div>
              <div className="mt-1 text-foreground">
                {graphIo?.outputs.length ? graphIo.outputs.map((output) => output.name).join(', ') : 'Result artifact'}
              </div>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Workflow className="size-3.5" />
            Node
          </div>
          {selectedNode ? (
            <dl className="space-y-2 rounded-md border border-border bg-background p-3 text-sm">
              <div>
                <dt className="text-xs font-medium text-muted-foreground">ID</dt>
                <dd className="mt-1 font-medium text-foreground">{selectedNode.id}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Mode</dt>
                <dd className="mt-1 text-foreground">{selectedNode.data.mode}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Status</dt>
                <dd className="mt-1 text-foreground">{selectedNode.data.status}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Depends on</dt>
                <dd className="mt-1 text-foreground">{selectedNode.data.dependsOn.join(', ') || 'None'}</dd>
              </div>
              {selectedNode.data.subgraphPath ? (
                <div>
                  <dt className="text-xs font-medium text-muted-foreground">Subgraph</dt>
                  <dd className="mt-1 break-all font-mono text-xs text-foreground">{selectedNode.data.subgraphPath}</dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <div className="rounded-md border border-dashed border-border bg-background p-3 text-sm text-muted-foreground">
              Select a node on the canvas.
            </div>
          )}
        </section>
      </div>
    </aside>
  )
}
