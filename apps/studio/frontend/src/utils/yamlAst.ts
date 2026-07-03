import yaml from 'js-yaml'
import type { JsonValue, PhaseDef } from '../api/types'
import { isJsonObject } from './errors'

export interface PhaseYamlBlock {
  phaseId: string
  yamlBlock: string
  startLine: number
  endLine: number
}

export interface SkillMdParts {
  frontmatter: string
  body: string
  phases: Map<string, string>
  ranges: Map<string, PhaseYamlBlock>
}

interface FrontmatterRange {
  frontmatter: string
  body: string
  startLine: number
  endLine: number
}

const PHASE_START_RE = /^(\s*)-\s+name:\s*(.+?)\s*(?:#.*)?$/
const PHASES_RE = /^(\s*)phases:\s*(?:#.*)?$/

export function splitSkillMdByPhase(md: string): SkillMdParts {
  const frontmatterRange = readFrontmatter(md)
  const lines = frontmatterRange.frontmatter.split('\n')
  const ranges = new Map<string, PhaseYamlBlock>()
  const phases = new Map<string, string>()
  const phaseStartLines = findPhaseStartLines(lines)

  phaseStartLines.forEach((item, index) => {
    const next = phaseStartLines[index + 1]
    const endLine = next?.lineIndex ?? lines.length
    const yamlBlock = lines.slice(item.lineIndex, endLine).join('\n').replace(/\n+$/, '')
    const absoluteStart = frontmatterRange.startLine + item.lineIndex
    const absoluteEnd = frontmatterRange.startLine + endLine
    const block = {
      phaseId: item.phaseId,
      yamlBlock,
      startLine: absoluteStart,
      endLine: absoluteEnd,
    }
    phases.set(item.phaseId, yamlBlock)
    ranges.set(item.phaseId, block)
  })

  return {
    frontmatter: frontmatterRange.frontmatter,
    body: frontmatterRange.body,
    phases,
    ranges,
  }
}

export function replacePhaseBlock(md: string, phaseId: string, newBlock: string): string {
  const range = splitSkillMdByPhase(md).ranges.get(phaseId)
  if (!range) {
    return md
  }

  const lines = md.split('\n')
  const normalizedBlock = normalizePhaseBlock(newBlock)
  const nextLines = [
    ...lines.slice(0, range.startLine),
    ...normalizedBlock.split('\n'),
    ...lines.slice(range.endLine),
  ]
  return nextLines.join('\n')
}

export function phaseRange(md: string, phaseId: string): PhaseYamlBlock | null {
  return splitSkillMdByPhase(md).ranges.get(phaseId) ?? null
}

export function phaseFromYamlBlock(yamlBlock: string): PhaseDef | null {
  let parsed: unknown
  try {
    parsed = yaml.load(`phases:\n${yamlBlock}`)
  } catch {
    return null
  }
  if (!isJsonObject(parsed) || !Array.isArray(parsed.phases)) {
    return null
  }
  const phase = parsed.phases[0]
  return isJsonObject(phase) ? phase as unknown as PhaseDef : null
}

export function phaseToYamlBlock(phase: PhaseDef): string {
  const dumped = yaml.dump({ phases: [phase] }, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  })
  const lines = dumped.split('\n')
  const phaseLines = lines.slice(1).filter((line) => line.length > 0)
  return phaseLines.join('\n')
}

export function phaseToolsFromManifest(frontmatter: string): string[] {
  let parsed: unknown
  try {
    parsed = yaml.load(frontmatter)
  } catch {
    return []
  }
  if (!isJsonObject(parsed)) {
    return []
  }
  const rootTools = stringList(parsed.agent_tools)
  const phaseTools = Array.isArray(parsed.phases)
    ? parsed.phases.flatMap((phase) => (
      isJsonObject(phase) ? stringList(phase.agent_tools) : []
    ))
    : []
  return Array.from(new Set([...rootTools, ...phaseTools])).sort()
}

function readFrontmatter(md: string): FrontmatterRange {
  const lines = md.split('\n')
  if (lines[0]?.trim() !== '---') {
    return { frontmatter: '', body: md, startLine: 0, endLine: 0 }
  }

  const endLine = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
  if (endLine < 0) {
    return { frontmatter: lines.slice(1).join('\n'), body: '', startLine: 1, endLine: lines.length }
  }

  return {
    frontmatter: lines.slice(1, endLine).join('\n'),
    body: lines.slice(endLine + 1).join('\n'),
    startLine: 1,
    endLine,
  }
}

function findPhaseStartLines(lines: string[]): Array<{ lineIndex: number; phaseId: string }> {
  const phasesLine = lines.findIndex((line) => PHASES_RE.test(line))
  if (phasesLine < 0) {
    return []
  }
  return lines.flatMap((line, index) => {
    if (index <= phasesLine) {
      return []
    }
    const match = PHASE_START_RE.exec(line)
    if (!match) {
      return []
    }
    const phaseId = scalarString(match[2])
    return phaseId ? [{ lineIndex: index, phaseId }] : []
  })
}

function scalarString(value: string): string | null {
  let parsed: JsonValue | undefined
  try {
    parsed = yaml.load(value) as JsonValue | undefined
  } catch {
    return null
  }
  if (typeof parsed === 'string' || typeof parsed === 'number' || typeof parsed === 'boolean') {
    return String(parsed)
  }
  return null
}

function normalizePhaseBlock(block: string): string {
  return block.trimEnd()
}

function stringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string')
}
