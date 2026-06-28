import type { Page } from '@playwright/test'

// ──────────────────────────────────────────────────────────────────────────
// Studio real-machine canvas harness (N2.1 verification)
//
// Why this exists: after PR #162 the Home page lists ONLY the Rust-store Recent
// MRU (empty in a plain browser), so a Playwright session can no longer reach
// the canvas by clicking a `/api/skills` card. And the FE white-screens in
// non-Tauri mode because api/client throws when VITE_STUDIO_API_BASE_URL is
// unset. This harness installs a minimal fake `window.__TAURI_INTERNALS__` so
// the app runs in its real desktop (Tauri) runtime path: isTauriRuntime()=true,
// the sidecar config resolves to same-origin `/api`, and one Recent workspace
// card is seeded so the operator (here: Playwright) can open the skill exactly
// like the shipping desktop app. Skill data / serialize / compile stay on HTTP
// and are mocked with page.route (same shape the shipping sidecar returns).
// ──────────────────────────────────────────────────────────────────────────

export const SKILL_ID = 'n2-canvas-demo'
export const SKILL_NAME = 'N2 Canvas Demo'

/** Install the fake Tauri bridge + seed a single Recent card (non-absolute path
 *  => the app treats it as a registry skill id, so file writes go through the
 *  native write_workspace_file command which this bridge records). */
export async function installStudioBridge(page: Page, opts: { skillId?: string; skillName?: string } = {}) {
  const skillId = opts.skillId ?? SKILL_ID
  const skillName = opts.skillName ?? SKILL_NAME
  await page.addInitScript(
    ([id, name]) => {
      let writeSeq = 0
      const recent = [
        {
          absolute_path: id, // non-absolute => plain skill id selection
          display_name: name,
          identity: `local:${id}`,
          last_opened_at: '2026-06-23T03:00:00Z',
        },
      ]
      const ok = async <T,>(v: T): Promise<T> => v
      const handlers: Record<string, (args: Record<string, unknown>) => unknown> = {
        get_sidecar_config: () => ({
          port: Number(location.port || 80),
          baseURL: `${location.origin}/api`,
          wsURL: `${location.origin.replace('http', 'ws')}/ws`,
          resourceDir: '',
          configDir: '/tmp/studio-config',
          api_token: null,
        }),
        list_recent_workspaces: () => recent,
        add_recent_workspace: () => null,
        remove_recent_workspace: (a) => {
          const i = recent.findIndex((r) => r.identity === a.identity)
          if (i >= 0) recent.splice(i, 1)
          return null
        },
        workspace_path_exists: () => true,
        ensure_workspace_support_dirs: () => null,
        open_skill_workspace: (a) => ({ root: String(a.path ?? id), skill_id: id }),
        select_directory: () => null,
        reveal_in_file_manager: () => null,
        delete_workspace_path: () => null,
        // Native file IO: record + echo a fresh hash so optimistic-lock writes
        // succeed. The canvas reads its data from the HTTP skill-detail mock, so
        // the bridge only needs to ACK writes.
        write_workspace_file: (a) => ({ path: String(a.relativePath ?? ''), hash: `h${++writeSeq}` }),
        read_workspace_file: (a) => ({ path: String(a.path ?? ''), content: '', hash: `h${writeSeq}` }),
        list_workspace_dir: () => [],
        checkpoint_workspace_file: () => ({ checkpoint_id: 'c1', created_at: '2026-06-23T03:00:00Z' }),
        seed_workspace_checkpoint: () => ({ checkpoint_id: 'c1', created_at: '2026-06-23T03:00:00Z' }),
        restore_workspace_file: (a) => ({ path: String(a.path ?? ''), content: '', hash: `h${writeSeq}` }),
        clear_workspace_checkpoint: () => null,
      }
      // @ts-expect-error minimal shim of the Tauri internals contract
      window.__TAURI_INTERNALS__ = {
        invoke: async (cmd: string, args: Record<string, unknown> = {}) => {
          const h = handlers[cmd]
          if (!h) {
            console.warn('[n2bridge] unhandled tauri command:', cmd, args)
            return ok(null)
          }
          return ok(h(args))
        },
        transformCallback: (cb: unknown) => cb,
        unregisterCallback: () => {},
        convertFileSrc: (p: string) => p,
      }
    },
    [skillId, skillName] as const,
  )
}

/** Open the seeded skill from Home → its canvas workspace. */
export async function openSkillWorkspace(page: Page, baseURL: string, skillName = SKILL_NAME) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' })
  await page.getByText(skillName, { exact: true }).first().click()
}
