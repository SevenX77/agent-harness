import type { AssetTreeEntry } from "./use-workspace-directory-tree"

/**
 * The two directories whose children are run attempts (decision 2026-08-09 D13:
 * predict got its own root, and both are read as one history).
 */
const RUN_LISTING_PATHS: ReadonlySet<string> = new Set([
  ".workspace/runs",
  ".workspace/predicts",
])

/** True when this directory's children are runs, not authored skill files. */
export function isRunListing(directoryPath: string): boolean {
  return RUN_LISTING_PATHS.has(directoryPath)
}

/**
 * Newest run first.
 *
 * Everywhere else in the tree, alphabetical order is what a reader wants: they
 * are looking for a file they can name. A run directory is the opposite — it is
 * named after a machine-generated moment, nobody looks one up by name, and the
 * one that matters is almost always the one that just happened. So this listing
 * alone reads newest-first (PM 2026-08-09: "run文件夹默认按照edit时间排序,最新
 * 的在最上面").
 *
 * Modification time decides it, because that is what the PM asked for and it
 * stays right for a run whose directory was written to after it started. The
 * name is the fallback: run ids begin with a sortable local timestamp
 * (`<timestamp>_<uuid8>`), so reverse name order is still chronological when a
 * filesystem reports no mtime.
 */
export function orderRunDirectories(entries: AssetTreeEntry[]): AssetTreeEntry[] {
  return [...entries].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "dir" ? -1 : 1
    const byModified = (right.modifiedMs ?? 0) - (left.modifiedMs ?? 0)
    if (byModified !== 0) return byModified
    return right.name.localeCompare(left.name)
  })
}

/**
 * Which entry of this directory listing carries the `latest` badge, if any.
 *
 * This replaces the deleted `runs/latest/` mirror (D13). That mirror was a full
 * second copy of a run on disk, written to answer a question the ordering
 * already answers — so the answer moved to a badge and the copy went away.
 *
 * Only a run listing has one, and only a directory can be it: a stray file in
 * the runs root is not a run. Expects the entries in the order the listing
 * renders them, which for a run listing is {@link orderRunDirectories}.
 */
export function latestRunDirectory(
  directoryPath: string,
  orderedEntries: readonly AssetTreeEntry[],
): string | null {
  if (!isRunListing(directoryPath)) return null
  return orderedEntries.find((entry) => entry.kind === "dir")?.path ?? null
}
