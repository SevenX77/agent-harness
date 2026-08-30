/**
 * Agent-phase body L3 step parsing (phase-editing F5).
 *
 * An agent SKILL.md body is XML with `<role>`, `<goal>`, `<step id name>`,
 * `<example>`, `<protocol>` blocks. The L3 "steps" are the `<step>` elements;
 * the canvas projects them inline as READ-ONLY sub-nodes (R3-8, 批示轮三
 * 2026-08-29: canvas-inline step editing withdrawn — the body is edited in
 * the editor, so the string→string edit transforms that used to live here
 * were deleted with it). The parser mirrors the engine loader's step grammar
 * (`<step\b([^>]*)>(.*?)</step>`, id + name required).
 */

export interface AgentStep {
  id: string
  name: string
  content: string
  /** Full matched `<step ...>...</step>` source, verbatim. */
  raw: string
  start: number
  end: number
}

const STEP_RE = /<step\b([^>]*)>([\s\S]*?)<\/step>/gi

function readAttr(attrs: string, key: string): string {
  const match = new RegExp(`${key}\\s*=\\s*"([^"]*)"`, "i").exec(attrs)
  if (match) return match[1]
  const single = new RegExp(`${key}\\s*=\\s*'([^']*)'`, "i").exec(attrs)
  return single ? single[1] : ""
}

/** Parse the `<step>` blocks of an agent body in document order. */
export function parseAgentSteps(body: string): AgentStep[] {
  const steps: AgentStep[] = []
  STEP_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = STEP_RE.exec(body)) !== null) {
    const attrs = match[1]
    steps.push({
      id: readAttr(attrs, "id"),
      name: readAttr(attrs, "name"),
      content: match[2].trim(),
      raw: match[0],
      start: match.index,
      end: match.index + match[0].length,
    })
  }
  return steps
}
