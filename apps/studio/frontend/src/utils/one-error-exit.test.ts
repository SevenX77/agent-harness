import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SOURCE_ROOT = join(import.meta.dirname, '..')

/**
 * `errors.ts` is where the pattern legitimately lives — it IS the exit, and its
 * own last-resort branches read an unknown rejection's `.message`.
 */
const ALLOWED = new Set(['utils/errors.ts'])

function sourceFiles(directory: string, prefix = ''): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const full = join(directory, entry)
    const relative = prefix ? `${prefix}/${entry}` : entry
    if (statSync(full).isDirectory()) {
      return sourceFiles(full, relative)
    }
    if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) {
      return []
    }
    return [relative]
  })
}

describe('what a failure reads as has one exit', () => {
  it('nowhere else turns an error into a message by hand', () => {
    // A caller that writes `error instanceof Error ? error.message : '…'` opts
    // out of `errorMessage`, and with it out of translating the backend's
    // `error_code`. That is not hypothetical: the Save-to-Team path did exactly
    // this, so a correctly-typed APP_SETTINGS_INCOMPLETE reached the user as
    // "Request failed with status code 400" (ledger K4a, overturned on the real
    // app 2026-08-21). Route it through `errorMessage(error, fallback)` instead.
    const offenders = sourceFiles(SOURCE_ROOT)
      .filter((relative) => !ALLOWED.has(relative))
      .flatMap((relative) => {
        const lines = readFileSync(join(SOURCE_ROOT, relative), 'utf8').split('\n')
        return lines.flatMap((line, index) => (
          / instanceof Error \?/.test(line) ? [`${relative}:${index + 1}: ${line.trim()}`] : []
        ))
      })

    expect(offenders).toEqual([])
  })
})
