import { parsePhaseFrontmatter, serializePhaseMarkdown } from "./phase-frontmatter"

// LOGIC action authoring helpers.
//
// Ground truth (docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md §1/§3 + engine
// loader.py `_load_action_dir`): a LOGIC phase's actions live in
// `phases/<phase_id>/actions/`, the action *name is the Python function name*,
// the function's first parameter must be `context`/`ctx`, and the frontmatter
// `actions:` list MUST stay identical to the body `<action>` tags. Studio adopts
// the project convention (copilot.py) of one action per file: each action
// `<name>` is the single `def <name>(context)` in `actions/<name>.py`. That makes
// list / edit / delete / add pure file operations with no Python parsing.

const ACTION_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/

/** `phases/<phaseId>/actions/<name>.py` — the file backing one action. */
export function actionFilePath(phaseId: string, name: string): string {
  return `phases/${phaseId}/actions/${name}.py`
}

/** An action name must be a valid Python identifier (it becomes `def <name>`). */
export function isValidActionName(name: string): boolean {
  return ACTION_NAME_RE.test(name)
}

/**
 * Load-safe stub for a new action file, following the mature-skill convention
 * (`from __future__ import annotations`, a typed `def <name>(context) -> dict`
 * with a docstring, reads via context / returns a dict). There is no engine-
 * enforced fixed header; this is the idiomatic starting point the author fills.
 */
export function actionStubContent(name: string): string {
  return [
    "from __future__ import annotations",
    "",
    "",
    `def ${name}(context) -> dict:`,
    `    """TODO: describe what ${name} does."""`,
    "    # Read inputs from the blackboard with context.get(\"field\").",
    "    # Write this phase's declared io.outputs (or return them as a dict).",
    "    return {}",
    "",
  ].join("\n")
}

/** Action names declared by the frontmatter `actions:` list (the canonical list). */
export function readActionsList(markdown: string): string[] {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return []
  }
  const actions = parsed.frontmatter.actions
  return Array.isArray(actions) ? actions.filter((item): item is string => typeof item === "string") : []
}

/** Action names declared by the body `<action>` tags, in execution order. */
export function parseBodyActions(body: string): string[] {
  return [...body.matchAll(/<action>([^<]*)<\/action>/g)]
    .map((match) => match[1].trim())
    .filter(Boolean)
}

/**
 * Action names that actually have an `actions/<name>.py` file on disk, derived
 * from the skill detail `files` map (which includes phase action `.py` files).
 */
export function scanActionFiles(files: Record<string, string> | undefined, phaseId: string): Set<string> {
  const prefix = `phases/${phaseId}/actions/`
  const names = new Set<string>()
  for (const key of Object.keys(files ?? {})) {
    if (!key.startsWith(prefix) || !key.endsWith(".py")) {
      continue
    }
    const file = key.slice(prefix.length)
    if (file === "__init__.py" || file.includes("/")) {
      continue
    }
    names.add(file.slice(0, -3))
  }
  return names
}

function rewriteBodyActions(body: string, names: string[]): string {
  // LOGIC requires at least one <action> tag; mirror the canvas scaffold's empty
  // `<action></action>` when the list is cleared.
  const block = (names.length > 0 ? names : [""]).map((name) => `<action>${name}</action>`).join("\n")
  const matches = [...body.matchAll(/<action>[^<]*<\/action>/g)]
  if (matches.length === 0) {
    const trimmed = body.replace(/\s+$/, "")
    return `${trimmed ? `${trimmed}\n\n` : ""}${block}\n`
  }
  const first = matches[0].index ?? 0
  const lastMatch = matches[matches.length - 1]
  const last = (lastMatch.index ?? 0) + lastMatch[0].length
  return `${body.slice(0, first)}${block}${body.slice(last)}`
}

export type ApplyActionsResult =
  | { ok: true; markdown: string }
  | { ok: false; message: string }

/**
 * Set the LOGIC phase's action list to `names`, keeping the frontmatter
 * `actions:` array and the body `<action>` tags in sync (engine requires they
 * match exactly). Order is preserved; all other frontmatter / body content is
 * untouched.
 */
export function applyActionsList(markdown: string, names: string[]): ApplyActionsResult {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return { ok: false, message: parsed.message }
  }
  const nextFrontmatter = { ...parsed.frontmatter, actions: names }
  const nextBody = rewriteBodyActions(parsed.body, names)
  return { ok: true, markdown: serializePhaseMarkdown(nextFrontmatter, nextBody) }
}
