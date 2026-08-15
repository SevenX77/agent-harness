// The gate every tool that DRIVES the shared debugged window passes through.
//
// 9222 has no authentication: whoever connects can click anywhere, and the
// scripts here pick their target as "the first page on :5173" — which is
// whatever window happens to be there, not necessarily this session's. On
// 2026-08-15 two agents drove the same window for hours; each one's clicks
// landed in the other's run and neither could tell. The board already knew who
// was holding the port; nothing asked it. This asks it.
//
// The line drawn here: OBSERVING is free (you must be able to look before you
// claim — that is how you find out someone else is working), DRIVING requires
// the claim. So shot/console/cdp stay open and click/emulate/the launchers
// come through here.
import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const RESOURCE = 'cdp-9222'
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')

/**
 * Exit the process unless this session holds the CDP claim. Failing closed is
 * deliberate: an unanswerable question ("is bash missing?", "is the board
 * gone?") is not permission to type into someone else's window.
 */
export function requireCdpClaim() {
  try {
    execFileSync('bash', [resolve(repoRoot, 'scripts/wt-board.sh'), 'holds', RESOURCE], {
      cwd: repoRoot,
      stdio: ['ignore', 'ignore', 'pipe'],
    })
  } catch (error) {
    const detail = (error.stderr?.toString() || error.message || '').trim()
    console.error(`refusing to drive the window: this session does not hold ${RESOURCE}.`)
    if (detail) console.error(detail.replace(/^/gm, '  '))
    console.error('')
    console.error('  claim it first (and set a session id the board can name you by):')
    console.error('    export WT_BOARD_AGENT=<your session id>')
    console.error(`    scripts/wt-board.sh claim ${RESOURCE} --ttl 3600 --note "点验 PR #NNN"`)
    console.error('  reading is always allowed without a claim: cdp.mjs / shot.mjs / console.mjs')
    process.exit(4)
  }
}
