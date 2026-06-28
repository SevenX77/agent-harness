import { AxiosError } from 'axios'
import type { ErrorResponse, SkillDetail } from '@/api/types'

// n2-canvas atom #14 (subgraph-drilldown — EDIT-WRITEBACK closure). Pure helpers
// for the drilled-child edit-writeback: which identity a save routes to, whether
// a drilled child is editable (read-only block), and whether a write failed
// because the child is a read-only bundled/public skill. Kept pure (no React) so
// the routing/blocking decisions are unit-testable in isolation.

/** A skill's save identity: where its files + GRAPH.md serialize/compile target. */
export interface SaveTargetIdentity {
  skillId: string
  workspaceRoot: string | null
}

/**
 * The drilled-child save target threaded into the Workspace save handlers when a
 * graph edit happens INSIDE a drilled subgraph. `detail` is the child's own full
 * SkillDetail (its manifest/topology/GRAPH.md text) so the connect/disconnect/
 * reconnect phase-ref transforms + optimistic-lock hash run against the CHILD, and
 * `onSettled` re-fetches the child graph after a write succeeds or fails (instead of
 * revalidating the PARENT via mutateSkillDetail). Absent target ⇒ parent/root edit.
 */
export interface ChildSaveTarget extends SaveTargetIdentity {
  detail: SkillDetail
  onSettled: () => Promise<void> | void
}

/**
 * Pick the save target for a graph edit. When NOT drilled (no drilled-child
 * identity) the edit targets the parent/root skill — byte-identical to the
 * pre-drill behaviour. When drilled into an editable child, the edit targets the
 * CHILD's own identity so serialize/write/compile run against the child skill_id
 * and child workspace root, never the parent's.
 */
export function resolveSaveTarget(
  parent: SaveTargetIdentity,
  drilledChild: SaveTargetIdentity | null,
): SaveTargetIdentity {
  return drilledChild ?? parent
}

/**
 * Decide whether a drilled child subgraph may be edited in place.
 *
 * A subgraph child path resolves into one of three roots (engine skill-syntax
 * §2.1 / backend `_allowed_child_graph_roots`): the parent skill's own tree, the
 * editable workspace skills dir, or the read-only bundled/public skills dir. The
 * child path here is the backend-resolved ABSOLUTE child root.
 *
 * Editable iff the child lives under the parent skill tree OR under the editable
 * workspace skills dir (the parent's workspaceRoot's parent directory). A bundled
 * child shares neither prefix → read-only (PM decision: BLOCK editing, no
 * auto-fork, no silent mutate).
 *
 * The decision is TOTAL and every uncertain case fails SAFE in Tauri (the only
 * runtime whose native writer has no read-only guard, so a wrong "editable"
 * verdict would silently mutate the bundle):
 *   1. child under parentWorkspaceRoot subtree         → editable
 *   2. child under dirname(parentWorkspaceRoot)         → editable
 *   3. parentWorkspaceRoot known but neither matches    → read-only
 *   4. parentWorkspaceRoot unknown (browser-only skill):
 *        - Tauri    → read-only (block; native writer never refuses)
 *        - browser  → editable (rely on the update_skill_file 403 backstop)
 */
export function isDrilledChildEditable(
  childPath: string,
  parentWorkspaceRoot: string | null,
  isTauri: boolean,
): boolean {
  if (parentWorkspaceRoot) {
    if (isPathWithin(childPath, parentWorkspaceRoot)) {
      return true
    }
    const workspaceSkillsDir = parentDirectory(parentWorkspaceRoot)
    if (workspaceSkillsDir && isPathWithin(childPath, workspaceSkillsDir)) {
      return true
    }
    return false
  }
  // Unknown parent root: block under Tauri (no native read-only guard), permit in
  // the browser where the update_skill_file 403 reliably refuses a bundled child.
  return !isTauri
}

/**
 * True when an error is the backend's 403 `SKILL_READ_ONLY` refusal (a write
 * against a bundled/public skill). The browser backstop for the read-only block
 * when the path predicate cannot decide (no parent workspace root).
 */
export function isReadOnlySkillError(error: unknown): boolean {
  if (!(error instanceof AxiosError)) {
    return false
  }
  if (error.response?.status !== 403) {
    return false
  }
  const body = error.response.data as Partial<ErrorResponse> | undefined
  return body?.error_code === 'SKILL_READ_ONLY'
}

/** True when `candidate` equals `root` or is nested under it (separator-aware). */
function isPathWithin(candidate: string, root: string): boolean {
  const normalizedRoot = stripTrailingSeparator(root)
  if (candidate === normalizedRoot) {
    return true
  }
  return candidate.startsWith(`${normalizedRoot}/`) || candidate.startsWith(`${normalizedRoot}\\`)
}

/** The parent directory of an absolute path, or null when at a root. */
function parentDirectory(path: string): string | null {
  const normalized = stripTrailingSeparator(path)
  const lastSeparator = Math.max(normalized.lastIndexOf('/'), normalized.lastIndexOf('\\'))
  if (lastSeparator <= 0) {
    return null
  }
  return normalized.slice(0, lastSeparator)
}

function stripTrailingSeparator(path: string): string {
  return path.replace(/[/\\]+$/, '')
}
