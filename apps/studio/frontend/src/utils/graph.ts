import { MarkerType } from 'reactflow'
import type { Edge, Node } from 'reactflow'
import type { StudioNodeData } from '../CustomNodes'
import type { GraphSkillDef, SkillManifest } from '../api/types'
import type { GraphBuildResult, VisualPhase } from '../types/studio'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'

function normalizeDependency(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value
  }
  return typeof value === 'string' && value.length > 0 ? [value] : []
}

export function subgraphSkillId(path: string | null): string | null {
  if (!path) {
    return null
  }
  const parts = path.split('/').filter(Boolean)
  const last = parts.at(-1)
  if (!last) {
    return null
  }
  return last.endsWith('.md') ? last.slice(0, -3) : last
}

function phasesFromManifest(manifest: SkillManifest): VisualPhase[] {
  if (manifest.schema_version === CURRENT_SCHEMA_VERSION) {
    return manifest.phases.map((phaseId) => ({
      id: phaseId,
      name: phaseId,
      mode: 'logic',
      role: null,
      dependsOn: [],
      subgraph: null,
    }))
  }

  if (manifest.type === 'graph') {
    return manifest.phases.map((phase) => ({
      id: phase.name,
      name: phase.name,
      mode: phase.mode,
      role: phase.mode === 'llm' ? phase.llm_role : null,
      dependsOn: normalizeDependency(phase.depends_on),
      subgraph: phase.subgraph ?? null,
    }))
  }

  if (manifest.type === 'agent') {
    return [{
      id: manifest.name,
      name: manifest.name,
      mode: 'llm',
      role: manifest.agent_profile.llm_role,
      dependsOn: [],
      subgraph: null,
    }]
  }

  return [{
    id: manifest.name,
    name: manifest.name,
    mode: 'persona',
    role: 'Persona',
    dependsOn: [],
    subgraph: null,
  }]
}

function inputLabel(manifest: SkillManifest): string {
  if (manifest.schema_version === CURRENT_SCHEMA_VERSION) {
    return 'Input: schema'
  }
  if (manifest.type !== 'graph') {
    return 'Input: runtime'
  }
  const names = manifest.io.inputs.map((input) => input.name)
  return `Input: ${names.length > 0 ? names.join(', ') : 'None'}`
}

function outputLabel(manifest: SkillManifest): string {
  if (manifest.schema_version === CURRENT_SCHEMA_VERSION) {
    return 'Output: schema'
  }
  if (manifest.type !== 'graph') {
    return 'Output: result'
  }
  const names = manifest.io.outputs.map((output) => output.name)
  return `Output: ${names.length > 0 ? names.join(', ') : 'None'}`
}

export function graphSkill(manifest: SkillManifest): GraphSkillDef | null {
  return manifest.schema_version === '2.0' && manifest.type === 'graph' ? manifest : null
}

export function buildGraph(
  manifest: SkillManifest,
  expandedSubgraphs: Set<string>,
  nestedManifests: Record<string, SkillManifest>,
  onToggleSubgraph: (phase: VisualPhase) => void,
  isDarkMode: boolean,
): GraphBuildResult {
  const nodes: Node<StudioNodeData>[] = [{
    id: 'input',
    type: 'input',
    data: { label: inputLabel(manifest) },
    position: { x: 240, y: 40 },
    style: {
      background: isDarkMode ? '#0f172a' : '#f8fafc',
      border: isDarkMode ? '1px solid #334155' : '1px solid #cbd5e1',
      borderRadius: 8,
      color: isDarkMode ? '#94a3b8' : '#475569',
      fontWeight: 700,
      minWidth: 220,
      padding: 10,
      textAlign: 'center',
    },
  }]
  const edges: Edge[] = []
  const phases = phasesFromManifest(manifest)
  const leafNodes = new Set<string>()
  let y = 150

  phases.forEach((phase, index) => {
    const isSubgraph = Boolean(phase.subgraph)
    const isExpanded = expandedSubgraphs.has(phase.id)
    nodes.push({
      id: phase.id,
      type: isSubgraph ? 'subgraph' : 'agent',
      data: {
        label: phase.name,
        mode: phase.mode,
        role: phase.role,
        subgraphPath: phase.subgraph,
        isExpanded,
        onToggleExpand: isSubgraph ? () => onToggleSubgraph(phase) : undefined,
      },
      position: { x: 240, y },
    })

    const dependencies = phase.dependsOn.length > 0
      ? phase.dependsOn
      : index === 0
        ? ['input']
        : [phases[index - 1].id]

    dependencies.forEach((dependency) => {
      edges.push({
        id: `e-${dependency}-${phase.id}`,
        source: dependency,
        target: phase.id,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#94a3b8', strokeWidth: 2 },
      })
    })

    leafNodes.add(phase.id)
    dependencies.forEach((dependency) => leafNodes.delete(dependency))

    if (isExpanded && phase.subgraph) {
      const nestedId = subgraphSkillId(phase.subgraph)
      const nested = nestedId ? nestedManifests[nestedId] : undefined
      const nestedPhases = nested ? phasesFromManifest(nested) : []
      let childY = y + 105
      let previousChild = phase.id

      nestedPhases.forEach((child) => {
        const childId = `${phase.id}::${child.id}`
        nodes.push({
          id: childId,
          type: 'agent',
          data: {
            label: child.name,
            mode: child.mode,
            role: child.role,
          },
          position: { x: 560, y: childY },
          style: { opacity: 0.9 },
        })
        edges.push({
          id: `e-${previousChild}-${childId}`,
          source: previousChild,
          target: childId,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: '#a78bfa', strokeDasharray: '5 5' },
        })
        previousChild = childId
        childY += 115
      })

      if (nestedPhases.length > 0) {
        leafNodes.delete(phase.id)
        leafNodes.add(previousChild)
      }
    }

    y += isExpanded ? 230 : 140
  })

  nodes.push({
    id: 'output',
    type: 'output',
    data: { label: outputLabel(manifest) },
    position: { x: 240, y },
    style: {
      background: isDarkMode ? '#052e16' : '#f0fdf4',
      border: isDarkMode ? '1px solid #14532d' : '1px solid #bbf7d0',
      borderRadius: 8,
      color: isDarkMode ? '#4ade80' : '#166534',
      fontWeight: 700,
      minWidth: 220,
      padding: 10,
      textAlign: 'center',
    },
  })

  const outputSources = leafNodes.size > 0 ? [...leafNodes] : ['input']
  outputSources.forEach((source) => {
    edges.push({
      id: `e-${source}-output`,
      source,
      target: 'output',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    })
  })

  return { nodes, edges }
}
