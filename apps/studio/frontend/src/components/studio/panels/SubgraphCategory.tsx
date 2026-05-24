import yaml from 'js-yaml'
import { AlertTriangle, ChevronDown, ChevronRight, FolderInput, GitBranch, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { getSkillDetail, importStudioSkill } from '@/api/client'
import type { GraphPhaseRef, GraphTopologyItem, SkillDetail } from '@/api/types'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { pickFolder } from '@/lib/tauri'
import { useWorkspaceContext } from '../WorkspaceContext'
import { SectionHeading } from './_shared/SectionHeading'

export interface SubgraphReference {
  targetSkill: string
  phaseIds: string[]
  sourcePaths: string[]
}

type RegistrationStatus =
  | { state: 'loading' }
  | { state: 'registered'; detail: SkillDetail }
  | { state: 'missing'; message: string }

const subgraphPathPattern = /^phases\/([^/]+)\/SUBGRAPH\.md$/

export function extractSubgraphReferences(files: Record<string, string> | undefined): SubgraphReference[] {
  const references = new Map<string, SubgraphReference>()

  for (const [path, content] of Object.entries(files ?? {})) {
    const pathMatch = subgraphPathPattern.exec(path)
    if (!pathMatch) continue

    const targetSkill = readTargetSkill(content)
    if (!targetSkill) continue

    const existing = references.get(targetSkill) ?? {
      targetSkill,
      phaseIds: [],
      sourcePaths: [],
    }
    existing.phaseIds.push(pathMatch[1])
    existing.sourcePaths.push(path)
    references.set(targetSkill, existing)
  }

  return [...references.values()].sort((left, right) => left.targetSkill.localeCompare(right.targetSkill))
}

function readTargetSkill(content: string): string | null {
  const match = /^---\s*\n([\s\S]*?)\n---/.exec(content)
  if (!match) return null

  let parsed: unknown
  try {
    parsed = yaml.load(match[1])
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return null
  }
  const targetSkill = (parsed as { target_skill?: unknown }).target_skill
  return typeof targetSkill === 'string' && targetSkill.trim() ? targetSkill.trim() : null
}

export function SubgraphCategory({ skillDetail }: { skillDetail?: SkillDetail }) {
  const references = useMemo(() => extractSubgraphReferences(skillDetail?.files), [skillDetail?.files])

  if (references.length === 0) {
    return null
  }

  return (
    <div className="space-y-1 pt-2">
      <SectionHeading label="Subgraphs" />
      {references.map((reference) => (
        <SubgraphReferenceRow key={reference.targetSkill} reference={reference} />
      ))}
    </div>
  )
}

function SubgraphReferenceRow({ reference }: { reference: SubgraphReference }) {
  const { pushNavSkill, reloadSkillDetail } = useWorkspaceContext()
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<RegistrationStatus>({ state: 'loading' })
  const [importing, setImporting] = useState(false)

  const refreshRegistration = useCallback(async () => {
    setStatus({ state: 'loading' })
    try {
      const detail = await getSkillDetail(reference.targetSkill)
      setStatus({ state: 'registered', detail })
    } catch (error) {
      setStatus({ state: 'missing', message: error instanceof Error ? error.message : 'Skill is not registered' })
    }
  }, [reference.targetSkill])

  useEffect(() => {
    void refreshRegistration()
  }, [refreshRegistration])

  const handleMissingClick = async () => {
    if (importing) return
    setImporting(true)
    try {
      const directoryPath = await pickFolder(null)
      if (!directoryPath) return
      await importStudioSkill({
        directory_path: directoryPath,
        target_skill_id: reference.targetSkill,
      })
      toast.success(`Imported ${reference.targetSkill}`)
      await reloadSkillDetail()
      await refreshRegistration()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Subgraph import failed'
      toast.error(message)
    } finally {
      setImporting(false)
    }
  }

  if (status.state === 'missing') {
    return (
      <button
        type="button"
        onClick={handleMissingClick}
        className="flex w-full items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-left text-xs text-destructive outline-none transition-colors hover:bg-destructive/15 focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        disabled={importing}
        title={status.message}
      >
        {importing ? <Loader2 className="size-3.5 animate-spin" /> : <AlertTriangle className="size-3.5" />}
        <span className="min-w-0 flex-1 truncate">{reference.targetSkill}</span>
        <FolderInput className="size-3.5" />
      </button>
    )
  }

  const phaseRows = status.state === 'registered' ? collectPhaseRows(status.detail) : []
  const displayName = status.state === 'registered' ? skillDisplayName(status.detail, reference.targetSkill) : reference.targetSkill

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
        >
          {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          {status.state === 'loading' ? <Loader2 className="size-4 animate-spin" /> : <GitBranch className="size-4" />}
          <span className="min-w-0 flex-1 truncate">{displayName}</span>
          <span className="text-[10px] text-muted-foreground">{reference.phaseIds.length}</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-1 pl-7">
          {reference.phaseIds.map((phaseId) => (
            <div key={phaseId} className="truncate rounded-md px-2 py-1 text-[11px] text-muted-foreground">
              {phaseId}
            </div>
          ))}
          {phaseRows.map((phase) => (
            <button
              key={`${reference.targetSkill}-${phase.id}`}
              type="button"
              onClick={() => pushNavSkill(reference.targetSkill)}
              className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[11px] text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-1 focus-visible:ring-ring"
            >
              <span className="min-w-0 truncate">{phase.id}</span>
              <span className="shrink-0 text-[10px] uppercase">{phase.mode}</span>
            </button>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function skillDisplayName(detail: SkillDetail, fallback: string): string {
  return detail.manifest.name || fallback
}

function collectPhaseRows(detail: SkillDetail): GraphTopologyItem[] {
  if (detail.graph_topology?.length) {
    return [...detail.graph_topology].sort((left, right) => left.id.localeCompare(right.id))
  }

  const phases = detail.manifest.phases ?? []
  return phases
    .filter((phase): phase is GraphPhaseRef => 'id' in phase && typeof phase.id === 'string')
    .map((phase) => ({
      id: phase.id,
      src: phase.src,
      depends_on: phase.depends_on,
      mode: 'phase',
    }))
}
