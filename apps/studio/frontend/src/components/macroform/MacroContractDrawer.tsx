import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { serializeSkillGraph } from '@/api/client'
import type { SerializableGraphPhaseRef, SkillDetail } from '@/api/types'
import { sha256Hex } from '@/lib/hash'
import { phaseRefsFromSkillDetail } from '@/components/GraphCanvas/canvas-authoring'
import { errorMessage } from '@/utils/errors'
import { MacroContractForm } from './MacroContractForm'
import {
  applyGraphHeaderForm,
  graphHeaderToForm,
  EMPTY_GRAPH_HEADER,
  type GraphHeaderFormData,
} from './graph-header'

/**
 * Host for the GRAPH.md macro-contract form (n2 atom #22).
 *
 * Owns the form state and the two save paths described by the design:
 *  - scalar header (name / schema_version / llm_role / description): re-render
 *    the GRAPH.md frontmatter via applyGraphHeaderForm and write it back
 *    directly with the current graph hash (writeFile).
 *  - phases (add/remove): map the edited phase ids onto the existing topology
 *    refs and serialize through the preserving serialize endpoint, then write
 *    the returned markdown back with the graph hash — the same chain the canvas
 *    create/connect flows use.
 *
 * FROZEN: the form never offers a `type` entry; node type is decided by file
 * name. The writeFile primitive is injected so this works under both the web
 * and Tauri runtimes without re-implementing doWriteSkillFile here.
 */
interface MacroContractDrawerProps {
  skillId: string
  skillDetail: SkillDetail | undefined
  writeFile: (path: string, content: string, expectedHash?: string | null) => Promise<{ hash: string }>
  onSaved?: () => void
}

const GRAPH_PATH = 'GRAPH.md'

export function MacroContractDrawer({ skillId, skillDetail, writeFile, onSaved }: MacroContractDrawerProps) {
  const graphContent = skillDetail?.files?.[GRAPH_PATH]
  const initialForm = useMemo<GraphHeaderFormData>(
    () => (graphContent === undefined ? EMPTY_GRAPH_HEADER : graphHeaderToForm(graphContent)),
    [graphContent],
  )
  const [form, setForm] = useState<GraphHeaderFormData>(initialForm)
  const [saving, setSaving] = useState(false)

  // Re-seed the form when the underlying GRAPH.md changes (skill switch / external edit).
  useEffect(() => {
    setForm(initialForm)
  }, [initialForm])

  const onChange = <Key extends keyof GraphHeaderFormData>(field: Key, value: GraphHeaderFormData[Key]) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleSaveHeader = async () => {
    if (graphContent === undefined) {
      toast.error('GRAPH.md is not loaded for this skill')
      return
    }
    const applied = applyGraphHeaderForm(graphContent, form)
    if (!applied.ok) {
      toast.error(`Could not update GRAPH.md header: ${applied.message}`)
      return
    }
    setSaving(true)
    try {
      const graphHash = await sha256Hex(graphContent)
      await writeFile(GRAPH_PATH, applied.markdown, graphHash)
      toast.success('Saved macro-contract header')
      onSaved?.()
    } catch (error) {
      toast.error(`Save failed: ${errorMessage(error)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleSavePhases = async () => {
    if (graphContent === undefined) {
      toast.error('GRAPH.md is not loaded for this skill')
      return
    }
    const nextPhases = phasesForSerialize(skillDetail, form.phases)
    setSaving(true)
    try {
      const graphHash = await sha256Hex(graphContent)
      const serialized = await serializeSkillGraph(skillId, nextPhases, graphHash)
      await writeFile(GRAPH_PATH, serialized.markdown_content, graphHash)
      toast.success('Saved macro-contract phases')
      onSaved?.()
    } catch (error) {
      toast.error(`Save failed: ${errorMessage(error)}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <MacroContractForm
      data={form}
      onChange={onChange}
      onSaveHeader={() => void handleSaveHeader()}
      onSavePhases={() => void handleSavePhases()}
      saving={saving}
    />
  )
}

/**
 * Map the edited phase id list onto serializable topology refs. Existing phases
 * keep their src / depends_on / mode; new ids default to a logic phase
 * directory ref so the preserving serializer can place them in the phases block.
 */
export function phasesForSerialize(
  skillDetail: SkillDetail | undefined,
  phaseIds: string[],
): SerializableGraphPhaseRef[] {
  const existing = new Map(phaseRefsFromSkillDetail(skillDetail).map((phase) => [phase.id, phase]))
  return phaseIds.map((id) => {
    const current = existing.get(id)
    if (current) {
      return current
    }
    return {
      id,
      src: `phases/${id}`,
      depends_on: [],
      mode: 'logic',
    }
  })
}
