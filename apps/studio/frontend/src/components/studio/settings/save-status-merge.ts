import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

/**
 * N0 Settings · Shell (atom #4 settings-save-badge).
 *
 * The shell top bar shows ONE global save badge that projects the three
 * per-tab debounced-save statuses (credentials / roles / app settings) into a
 * single shell-level status. Each tab keeps its own badge; this is purely the
 * top-bar summary so the user sees one place whether their edit landed.
 *
 * Priority (highest wins): any `error` → error, else any `saving` → saving,
 * else any `pending` → pending, else any `saved` → saved, else `idle`.
 * `idle` renders nothing (SaveStatusBadge returns null), so when every source
 * is idle the top bar stays clean.
 */
export function mergeSaveStatuses(statuses: readonly SaveStatus[]): SaveStatus {
  if (statuses.includes("error")) return "error"
  if (statuses.includes("saving")) return "saving"
  if (statuses.includes("pending")) return "pending"
  if (statuses.includes("saved")) return "saved"
  return "idle"
}
