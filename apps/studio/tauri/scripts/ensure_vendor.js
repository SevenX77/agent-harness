#!/usr/bin/env node
/* eslint-env node */

const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { spawnSync } = require('node:child_process')

const { hostTargetTriple } = require('./download_runtime')

const TAURI_DIR = path.resolve(__dirname, '..')
const STUDIO_DIR = path.resolve(TAURI_DIR, '..')
const REPO_ROOT = path.resolve(TAURI_DIR, '../../..')
const VENDOR_DIR = path.join(TAURI_DIR, 'vendor')

// Written by `apps/studio/backend/scripts/build_vendor.py` as the last step of
// a build, INSIDE the snapshot it describes. Its lifetime is therefore exactly
// the snapshot's: a build that cleans the target and then fails leaves no stamp,
// which reads as "no provenance" rather than as a description of a snapshot that
// no longer exists.
const VENDOR_STAMP_FILENAME = 'vendor-stamp.json'
// Bumped together with `build_vendor.py`'s STAMP_SCHEMA. A stamp this gate
// cannot read is not a compatibility problem to solve here: it means the
// snapshot predates the current build script, which is the definition of stale.
const VENDOR_STAMP_SCHEMA = 2

// Booting the app on a knowingly stale snapshot is a legitimate thing to want —
// reproducing a defect against the snapshot that still has it. Named after what
// it permits rather than what it disables, because the name is the whole warning
// a reader gets. It never makes the gate silent: the stale files and the fix are
// printed either way.
const ALLOW_STALE_SNAPSHOT_ENV = 'STUDIO_ALLOW_STALE_VENDOR_SNAPSHOT'

// The command AGENTS.md (Workflow Pipeline step 7) tells a developer to run.
const REBUILD_COMMAND = 'uv run python apps/studio/backend/scripts/build_vendor.py'

function pythonExecutable(vendorDir = VENDOR_DIR, target = hostTargetTriple()) {
  const runtimeDir = path.join(vendorDir, 'python', target)
  if (target.includes('windows')) return path.join(runtimeDir, 'python.exe')
  const python312 = path.join(runtimeDir, 'bin', 'python3.12')
  if (fs.existsSync(python312)) return python312
  return path.join(runtimeDir, 'bin', 'python3')
}

function sitePackages(vendorDir = VENDOR_DIR) {
  return path.join(vendorDir, 'site-packages')
}

function pathEnvKey(env = process.env) {
  return Object.keys(env).find((key) => key.toLowerCase() === 'path') ?? 'PATH'
}

function localVenvBin(workspaceRoot = REPO_ROOT) {
  return path.join(workspaceRoot, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin')
}

function withLocalVenvOnPath(env = process.env, workspaceRoot = REPO_ROOT) {
  const next = { ...env }
  const key = pathEnvKey(next)
  const current = next[key] ?? ''
  const venvBin = localVenvBin(workspaceRoot)
  if (!fs.existsSync(venvBin)) return next
  const pathEntries = current.split(path.delimiter).filter(Boolean)
  const alreadyPresent = pathEntries.some((entry) => {
    if (process.platform === 'win32') return entry.toLowerCase() === venvBin.toLowerCase()
    return entry === venvBin
  })
  if (!alreadyPresent) {
    next[key] = current ? `${venvBin}${path.delimiter}${current}` : venvBin
  }
  return next
}

function vendorStampPath({ target = sitePackages(), stampPath } = {}) {
  return stampPath ?? path.join(target, VENDOR_STAMP_FILENAME)
}

/**
 * The snapshot's own account of what it was built from, or null when it has
 * none. `build_vendor.py` is the only writer; this side never synthesises one,
 * so "which sources is this snapshot" keeps a single owner.
 */
function readVendorStamp(options = {}) {
  const file = vendorStampPath(options)
  if (!fs.existsSync(file)) return null
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

function isFileManifest(value) {
  return (
    value !== null
    && typeof value === 'object'
    && !Array.isArray(value)
    && Object.values(value).every((digest) => typeof digest === 'string' && digest.length > 0)
  )
}

/**
 * Why the snapshot cannot say where it came from, empty when it can.
 *
 * A snapshot with no readable stamp is stale by definition here, for two
 * reasons at once. It cannot be placed: on a user's machine there IS no source
 * tree, so the stamp is the only thing that can name the engine the installed
 * app carries. And it cannot be checked: the stamp carries the per-file
 * manifest the freshness comparison is made of, so without it there is nothing
 * to compare against except a guess about which files a package consists of —
 * which is exactly the guess this gate must not make.
 */
function vendorStampDrift(options = {}) {
  const file = vendorStampPath(options)
  const stamp = options.stamp ?? readVendorStamp(options)
  if (stamp === null || typeof stamp !== 'object') {
    return [`${file}: the snapshot carries no readable ${VENDOR_STAMP_FILENAME} provenance stamp`]
  }
  if (stamp.schema !== VENDOR_STAMP_SCHEMA) {
    return [`${file}: provenance stamp schema ${stamp.schema} predates this launcher (expected ${VENDOR_STAMP_SCHEMA})`]
  }
  if (typeof stamp.source_digest !== 'string' || stamp.source_digest.length === 0) {
    return [`${file}: the provenance stamp names no source_digest`]
  }
  const packages = stamp.packages
  if (packages === null || typeof packages !== 'object' || Object.keys(packages).length === 0) {
    return [`${file}: the provenance stamp lists no vendored packages`]
  }
  for (const [name, info] of Object.entries(packages)) {
    if (info === null || typeof info !== 'object' || typeof info.source_root !== 'string' || !isFileManifest(info.files)) {
      return [`${file}: the provenance stamp's entry for ${name} is not a source root plus a file manifest`]
    }
  }
  return []
}

function stampedPackages(stamp) {
  return stamp === null || typeof stamp !== 'object' || typeof stamp.packages !== 'object' || stamp.packages === null
    ? {}
    : stamp.packages
}

function fileHash(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

/**
 * Resolve a stamp-supplied relative path, or null when it escapes its root.
 *
 * The stamp is a file this gate reads and turns into filesystem paths; a
 * corrupted or hand-edited one must not be able to send the walk outside the
 * tree it claims to describe (same rule as #1090 for caller-supplied paths).
 */
function resolveWithin(root, relative) {
  if (typeof relative !== 'string' || relative.length === 0 || path.isAbsolute(relative)) return null
  const resolved = path.resolve(root, relative)
  const inside = path.relative(root, resolved)
  if (inside.startsWith('..') || path.isAbsolute(inside)) return null
  return resolved
}

/**
 * What is stale about the vendored copies of the local workspace packages, one
 * human-readable line per finding, empty when the snapshot is current.
 *
 * The set of files to check comes from the stamp, which records exactly what
 * the wheels shipped (see `wheel_package_files` in `build_vendor.py`). Nothing
 * here walks either tree, and that is the point: any walk needs a rule for
 * which files "count", and this gate had one that disagreed with the build
 * backend in BOTH directions — it skipped dotfiles hatchling ships, and it
 * demanded gitignored build artefacts (`*.py[cod]` covers `.pyd`) that
 * hatchling will never ship, a drift no rebuild could ever clear (P11/#732).
 * The build backend decides what a package consists of; this gate only checks
 * the answer it recorded.
 *
 * Both directions are checked against the recorded hash — the sources (did the
 * working tree move on since the build?) and the snapshot (is the snapshot
 * still what that build installed?) — so the comparison needs no hashing
 * algorithm shared between this file and `build_vendor.py`, only the digests
 * the build already wrote down.
 *
 * What it deliberately does NOT report: files in the source tree that the
 * stamp does not mention. Telling "added since the build" apart from "the
 * wheel never ships this" requires re-deriving hatchling's selection rules
 * here, and that is the defect above. Adding a file to an SDK package is
 * caught in practice through the edit that starts using it; a rebuild remains
 * the only thing that can be sure.
 */
function packageSourceDrift({
  target = sitePackages(),
  repoRoot = REPO_ROOT,
  stamp = null,
  stampPath,
} = {}) {
  const resolvedStamp = stamp ?? readVendorStamp({ target, stampPath })
  const drift = []
  for (const [packageName, info] of Object.entries(stampedPackages(resolvedStamp))) {
    const sourceRoot = resolveWithin(repoRoot, info.source_root)
    if (sourceRoot === null) {
      drift.push(`${packageName}: the stamp names a source root outside the workspace: ${info.source_root}`)
      continue
    }
    drift.push(...packageDrift(packageName, sourceRoot, path.join(target, packageName), info.files))
  }
  return drift
}

// Code-unit order rather than `localeCompare`: the same snapshot has to produce
// the same lines in the same order on every machine, and locale collation is
// the one thing here that would not.
function byCodeUnit(left, right) {
  if (left === right) return 0
  return left < right ? -1 : 1
}

// One package's recorded files, checked on both sides.
function packageDrift(packageName, sourceRoot, vendorRoot, files) {
  const drift = []
  for (const relative of Object.keys(files).sort(byCodeUnit)) {
    // Validated once, against one root: what makes a path safe is the relative
    // half (no `..`, not absolute), and both roots take the same one.
    if (resolveWithin(sourceRoot, relative) === null) {
      drift.push(`${packageName}: the stamp names a file outside the package: ${relative}`)
      continue
    }
    const named = `${packageName}/${relative}`
    drift.push(
      ...fileDrift(path.join(sourceRoot, relative), files[relative],
        `${named}: shipped by the last build, gone from the sources`,
        `${named}: the sources have changed since the snapshot was built`),
      ...fileDrift(path.join(vendorRoot, relative), files[relative],
        `${named}: missing from the snapshot`,
        `${named}: the snapshot holds a different version`),
    )
  }
  return drift
}

// How one file fails the digest the build recorded for it, on one side.
function fileDrift(file, digest, missing, differs) {
  if (!fs.existsSync(file)) return [missing]
  if (fileHash(file) !== digest) return [differs]
  return []
}

/**
 * Why a spawn produced no successful exit, in words a reader can act on.
 *
 * `result.status` alone cannot say: when the process never started — a missing
 * or unexecutable vendored interpreter, the single most likely failure on a
 * fresh checkout — Node reports `status: null` and puts the reason in
 * `result.error`. Reading only the status turned that into "exit code null",
 * which names neither the file nor the problem.
 */
function describeSpawnFailure(result, executable) {
  if (result.error) {
    const code = result.error.code ? `${result.error.code}: ` : ''
    return `${code}could not run ${executable} (${result.error.message})`
  }
  if (result.signal) return `killed by signal ${result.signal}`
  return `exit code ${result.status}`
}

function lastLines(text, limit = 3) {
  if (typeof text !== 'string') return ''
  const lines = text.trim().split(/\r?\n/).filter(Boolean)
  return lines.slice(-limit).join(' | ')
}

/**
 * Whether the vendored interpreter can actually import the vendored packages.
 *
 * The module names come from the stamp, i.e. from what the wheels shipped, so
 * this list cannot go stale the way a hand-written one did in #706 — where the
 * gate kept naming a module the gateway's refactor had removed and the app
 * could not start at all (#732).
 */
function vendoredImportDrift({
  python = pythonExecutable(),
  target = sitePackages(),
  backend = path.join(VENDOR_DIR, 'backend'),
  modules,
  stamp = null,
  stampPath,
  // Injectable for the same reason rebuildVendor's is: whether ensureVendor
  // rebuilds is a decision about its own branches, and a test of that decision
  // should not depend on a Python runtime being provisioned on the machine.
  spawn = spawnSync,
} = {}) {
  const names = modules ?? Object.keys(stampedPackages(stamp ?? readVendorStamp({ target, stampPath })))
  if (names.length === 0) return []
  if (!fs.existsSync(python)) return [`the vendored interpreter is missing at ${python}`]
  if (!fs.existsSync(target)) return [`there is no vendored site-packages at ${target}`]
  const result = spawn(
    python,
    ['-c', `import ${names.join(', ')}`],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [target, backend].join(path.delimiter),
      },
      encoding: 'utf8',
    },
  )
  if (result.status === 0) return []
  const said = lastLines(result.stderr)
  const detail = said ? ` — ${said}` : ''
  return [
    `the vendored interpreter cannot import ${names.join(', ')}: `
    + `${describeSpawnFailure(result, python)}${detail}`,
  ]
}

function rebuildVendor({
  python = pythonExecutable(),
  buildScript = path.join(STUDIO_DIR, 'backend', 'scripts', 'build_vendor.py'),
  env = process.env,
  spawn = spawnSync,
  workspaceRoot = REPO_ROOT,
} = {}) {
  // What is stale is printed by the caller, which is the only one that knows.
  console.log('[vendor] rebuilding the Python vendor snapshot')
  const result = spawn(python, [buildScript, '--python', python], {
    cwd: workspaceRoot,
    env: withLocalVenvOnPath(env, workspaceRoot),
    stdio: 'inherit',
  })
  if (result.status !== 0) {
    throw new Error(`build_vendor.py did not finish: ${describeSpawnFailure(result, python)}`)
  }
}

function snapshotDrift(options = {}) {
  const { target = sitePackages(), stampPath } = options
  const stamp = options.stamp ?? readVendorStamp({ target, stampPath })
  // Without a readable stamp there is no manifest to compare against, so the
  // missing provenance IS the whole finding: rebuilding is what produces one.
  const stampProblems = vendorStampDrift({ ...options, stamp })
  if (stampProblems.length > 0) return stampProblems
  return [
    ...vendoredImportDrift({ ...options, stamp }),
    ...packageSourceDrift({ ...options, stamp }),
  ]
}

// Only the first few, so a package-wide rename does not bury the fix under a
// hundred identical lines.
function summariseDrift(drift, limit = 8) {
  const shown = drift.slice(0, limit).map((line) => `  - ${line}`)
  if (drift.length > limit) shown.push(`  - ... and ${drift.length - limit} more`)
  return shown.join('\n')
}

/**
 * Whether the caller explicitly asked to run on a stale snapshot.
 *
 * Only an affirmative value counts, so anything unclear fails CLOSED — the
 * direction a dangerous flag has to fail. Bare presence would make
 * `STUDIO_ALLOW_STALE_VENDOR_SNAPSHOT=0` mean "allow", which is the opposite of
 * what anyone typing it intends.
 */
function staleSnapshotAllowed(env = process.env) {
  const value = env[ALLOW_STALE_SNAPSHOT_ENV]
  if (typeof value !== 'string') return false
  return ['1', 'true', 'yes'].includes(value.trim().toLowerCase())
}

function describeSnapshot(options = {}) {
  const stamp = options.stamp ?? readVendorStamp(options)
  if (stamp === null) return 'no provenance stamp'
  return `sources ${String(stamp.source_digest).slice(0, 12)}, built ${stamp.built_at ?? 'at an unrecorded time'}`
}

function ensureVendor(options = {}) {
  const { env = process.env, warn = console.warn } = options
  const drift = snapshotDrift(options)
  if (drift.length === 0) {
    console.log(`[vendor] Python vendor closure ok (${describeSnapshot(options)})`)
    return { rebuilt: false, staleAllowed: false }
  }

  if (staleSnapshotAllowed(env)) {
    warn(
      [
        `[vendor] ${ALLOW_STALE_SNAPSHOT_ENV} is set: starting on a STALE vendor snapshot.`,
        '[vendor] The desktop app will run the engine/gateway code in the snapshot, NOT your working tree:',
        summariseDrift(drift),
        `[vendor] Rebuild with: ${REBUILD_COMMAND}`,
      ].join('\n'),
    )
    return { rebuilt: false, staleAllowed: true }
  }

  console.log(`[vendor] Python vendor snapshot is stale or incomplete:\n${summariseDrift(drift)}`)
  rebuildVendor(options)
  const remaining = snapshotDrift(options)
  if (remaining.length > 0) {
    throw new Error(
      [
        'the Python vendor snapshot is still stale after a rebuild, so the desktop app would run',
        'engine/gateway code that is not in your working tree. Still wrong:',
        summariseDrift(remaining),
        `Rebuild by hand to see the failure: ${REBUILD_COMMAND}`,
      ].join('\n'),
    )
  }
  console.log(`[vendor] Python vendor closure rebuilt and verified (${describeSnapshot(options)})`)
  return { rebuilt: true, staleAllowed: false }
}

if (require.main === module) {
  try {
    ensureVendor()
  } catch (error) {
    console.error(`[vendor] ${error.message}`)
    process.exit(1)
  }
}

module.exports = {
  ALLOW_STALE_SNAPSHOT_ENV,
  REBUILD_COMMAND,
  VENDOR_STAMP_FILENAME,
  VENDOR_STAMP_SCHEMA,
  describeSpawnFailure,
  ensureVendor,
  localVenvBin,
  packageSourceDrift,
  pythonExecutable,
  readVendorStamp,
  rebuildVendor,
  sitePackages,
  snapshotDrift,
  staleSnapshotAllowed,
  vendorStampDrift,
  vendoredImportDrift,
  withLocalVenvOnPath,
}
