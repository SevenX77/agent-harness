/**
 * Agent-phase body L3 step parsing + edits (phase-editing F5).
 *
 * An agent SKILL.md body is XML with `<role>`, `<goal>`, `<step id name>`,
 * `<example>`, `<protocol>` blocks. The L3 "steps" are the `<step>` elements;
 * the canvas expands them inline as draggable sub-nodes (add / remove / reorder /
 * edit), then writes the body back via the normal phase-file save path.
 *
 * These transforms are PURE string→string and PRESERVE the source text: only the
 * `<step>` region is rewritten; `<role>`/`<goal>`/`<example>`/`<protocol>` and the
 * surrounding whitespace are kept verbatim. They mirror the engine loader's step
 * grammar (`<step\b([^>]*)>(.*?)</step>`, id + name required) so a serialized body
 * round-trips through compile unchanged.
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

function renderStep(step: { id: string; name: string; content: string }): string {
  return `<step id="${step.id}" name="${step.name}">\n${step.content}\n</step>`
}

/**
 * Rewrite the body so its `<step>` blocks appear in `orderedIds` order, keeping
 * every non-step character (role/goal/example/protocol + inter-step whitespace)
 * in place. `orderedIds` must be a permutation of the body's step ids.
 */
export function reorderAgentSteps(body: string, orderedIds: readonly string[]): string {
  const steps = parseAgentSteps(body)
  if (steps.length === 0) return body
  const byId = new Map(steps.map((step) => [step.id, step]))
  const reordered = orderedIds.map((id) => byId.get(id)).filter((step): step is AgentStep => step != null)
  if (reordered.length !== steps.length) {
    // Not a clean permutation (unknown/missing id) — leave the body untouched
    // rather than silently dropping a step.
    return body
  }
  let result = ""
  let cursor = 0
  steps.forEach((slot, index) => {
    result += body.slice(cursor, slot.start) + reordered[index].raw
    cursor = slot.end
  })
  result += body.slice(cursor)
  return result
}

/** Remove a step block (and a single trailing blank line) by id. */
export function removeAgentStep(body: string, stepId: string): string {
  const step = parseAgentSteps(body).find((candidate) => candidate.id === stepId)
  if (!step) return body
  let end = step.end
  // Swallow one trailing newline run so we don't leave a widening gap.
  const trailing = /^[ \t]*\n/.exec(body.slice(end))
  if (trailing) end += trailing[0].length
  return body.slice(0, step.start) + body.slice(end)
}

/** Allocate the next `S<n>` id not already used by the body's steps. */
export function nextStepId(existingIds: readonly string[]): string {
  let max = 0
  for (const id of existingIds) {
    const match = /^S(\d+)$/.exec(id)
    if (match) max = Math.max(max, Number(match[1]))
  }
  return `S${max + 1}`
}

/**
 * Append a new step after the last existing step (or after `<goal>`/`<role>` when
 * there are none yet), preserving everything else.
 */
export function addAgentStep(body: string, step: { id: string; name: string; content: string }): string {
  const block = renderStep(step)
  const steps = parseAgentSteps(body)
  if (steps.length > 0) {
    const last = steps[steps.length - 1]
    return body.slice(0, last.end) + "\n\n" + block + body.slice(last.end)
  }
  // No steps yet: insert after the last of <goal>/<role>, else prepend.
  const anchor = lastTagEnd(body, "goal") ?? lastTagEnd(body, "role")
  if (anchor != null) {
    return body.slice(0, anchor) + "\n\n" + block + body.slice(anchor)
  }
  return block + "\n\n" + body
}

/** Replace a step's name and/or content in place, keeping its id and position. */
export function updateAgentStep(
  body: string,
  stepId: string,
  patch: { name?: string; content?: string },
): string {
  const step = parseAgentSteps(body).find((candidate) => candidate.id === stepId)
  if (!step) return body
  const next = renderStep({
    id: step.id,
    name: patch.name ?? step.name,
    content: patch.content ?? step.content,
  })
  return body.slice(0, step.start) + next + body.slice(step.end)
}

function lastTagEnd(body: string, tag: string): number | null {
  const re = new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, "gi")
  let end: number | null = null
  let match: RegExpExecArray | null
  while ((match = re.exec(body)) !== null) {
    end = match.index + match[0].length
  }
  return end
}
