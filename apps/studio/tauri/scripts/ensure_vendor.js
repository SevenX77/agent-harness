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
const LOCAL_PACKAGE_SOURCES = [
  {
    packageName: 'graph_agent',
    sourceRoot: path.join(REPO_ROOT, 'packages', 'graph-agent', 'src', 'graph_agent'),
  },
  {
    packageName: 'graph_agent_gateway',
    sourceRoot: path.join(REPO_ROOT, 'packages', 'graph-agent-gateway', 'src', 'graph_agent_gateway'),
  },
]
// Package roots only, derived from the packages this gate vendors: naming an
// inner module here would be a second, hand-maintained copy of the SDK module
// tree, and `localPackageSourcesAreVendored` below already hash-compares every
// source file against its vendored twin — a stronger check that cannot go
// stale when a package is reorganised internally.
const REQUIRED_VENDOR_IMPORTS = LOCAL_PACKAGE_SOURCES.map((entry) => entry.packageName)

// Written by `apps/studio/backend/scripts/build_vendor.py` as the last step of
// a build, INSIDE the snapshot it describes. Its lifetime is therefore exactly
// the snapshot's: a build that cleans the target and then fails leaves no stamp,
// which reads as "no provenance" rather than as a description of a snapshot that
// no longer exists.
const VENDOR_STAMP_FILENAME = 'vendor-stamp.json'

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

/**
 * Every file the wheel ships for a package, relative to its root.
 *
 * EVERY file, not just `*.py`. Both SDK packages carry non-Python files inside
 * the package that hatchling installs into the snapshot and that the app reads
 * at runtime — the gateway's provider call-method routing table
 * `graph_agent_gateway/registry/call_methods.json` (loaded through
 * `importlib.resources`) and the engine's
 * `graph_agent/skills/builtin/md-patch/SKILL.md`. While this walk filtered on
 * `.py`, editing either one and launching the app printed "Python vendor
 * closure ok" and then served the OLD copy.
 *
 * There is deliberately no ignore list for "files that do not matter at
 * runtime". Deciding that per file is the judgement that already failed once
 * for `call_methods.json`, and an extension-based rule fails immediately:
 * `md-patch/SKILL.md` is load-bearing and `CHANGELOG.md` is not. The invariant
 * is the simple one — the snapshot is byte-identical to the sources it claims
 * to be built from — and its cost is that editing a package's own CHANGELOG
 * does mean the snapshot is stale, because it is.
 *
 * `__pycache__` and dotfiles stay out: bytecode is an output of importing the
 * tree rather than an input to it, and the wheel never carries either.
 * `build_vendor.py`'s `source_tree_digest` excludes the same two things.
 */
function collectPackageFiles(root) {
  if (!fs.existsSync(root)) return null
  const files = []
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '__pycache__' || entry.name.startsWith('.')) continue
      const fullPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        visit(fullPath)
      } else if (entry.isFile()) {
        // Posix-spelled so a drift line reads the same on every platform.
        files.push(path.relative(root, fullPath).split(path.sep).join('/'))
      }
    }
  }
  visit(root)
  return files.sort()
}

function fileHash(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

/**
 * What is stale about the vendored copies of the local workspace packages, one
 * human-readable line per finding, empty when the snapshot is current.
 *
 * The comparison is against the bytes actually on disk in both trees, not
 * against the digest recorded in the stamp. A stamp says what a build INTENDED
 * to install; the bytes say what is there — which is the question the sidecar
 * will answer when it imports them. It also needs no hashing algorithm shared
 * between this file and `build_vendor.py`: two implementations of one algorithm
 * drift, and the ledger already records that shape of defect (P11, #732 — a
 * hand-copied SDK module tree in JS that the Python side outgrew).
 */
function packageSourceDrift({
  packages = LOCAL_PACKAGE_SOURCES,
  target = sitePackages(),
} = {}) {
  const drift = []
  for (const packageInfo of packages) {
    const vendorRoot = packageInfo.vendorRoot ?? path.join(target, packageInfo.packageName)
    const sourceFiles = collectPackageFiles(packageInfo.sourceRoot)
    const vendorFiles = collectPackageFiles(vendorRoot)
    if (sourceFiles === null) {
      drift.push(`${packageInfo.packageName}: no sources at ${packageInfo.sourceRoot}`)
      continue
    }
    if (vendorFiles === null) {
      drift.push(`${packageInfo.packageName}: not vendored at ${vendorRoot}`)
      continue
    }
    const vendored = new Set(vendorFiles)
    const sourced = new Set(sourceFiles)
    for (const file of sourceFiles) {
      if (!vendored.has(file)) {
        drift.push(`${packageInfo.packageName}/${file}: in the sources, missing from the snapshot`)
        continue
      }
      const sourceFile = path.join(packageInfo.sourceRoot, ...file.split('/'))
      const vendorFile = path.join(vendorRoot, ...file.split('/'))
      if (fileHash(sourceFile) !== fileHash(vendorFile)) {
        drift.push(`${packageInfo.packageName}/${file}: the snapshot holds a different version`)
      }
    }
    for (const file of vendorFiles) {
      if (!sourced.has(file)) {
        drift.push(`${packageInfo.packageName}/${file}: in the snapshot, gone from the sources`)
      }
    }
  }
  return drift
}

function localPackageSourcesAreVendored(options = {}) {
  return packageSourceDrift(options).length === 0
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

/**
 * Why the snapshot cannot say where it came from, empty when it can.
 *
 * A snapshot with no stamp is treated as stale even when its bytes match,
 * because a build that produced no provenance is a build this gate cannot
 * vouch for on the machine where it matters most: the installed app, which has
 * no source tree to compare against and nothing else to name.
 */
function vendorStampDrift(options = {}) {
  const file = vendorStampPath(options)
  const stamp = readVendorStamp(options)
  if (stamp === null) {
    return [`${file}: the snapshot carries no readable ${VENDOR_STAMP_FILENAME} provenance stamp`]
  }
  if (typeof stamp.source_digest !== 'string' || stamp.source_digest.length === 0) {
    return [`${file}: the provenance stamp names no source_digest`]
  }
  return []
}

function describeSnapshot(options = {}) {
  const stamp = readVendorStamp(options)
  if (stamp === null) return 'no provenance stamp'
  return `sources ${stamp.source_digest.slice(0, 12)}, built ${stamp.built_at ?? 'at an unrecorded time'}`
}

function canImportVendoredPackages({
  python = pythonExecutable(),
  target = sitePackages(),
  backend = path.join(VENDOR_DIR, 'backend'),
  modules = REQUIRED_VENDOR_IMPORTS,
  // Injectable for the same reason rebuildVendor's is: whether ensureVendor
  // rebuilds is a decision about its own branches, and a test of that decision
  // should not depend on a Python runtime being provisioned on the machine.
  spawn = spawnSync,
} = {}) {
  if (!fs.existsSync(python) || !fs.existsSync(target)) return false
  const result = spawn(
    python,
    ['-c', `import ${modules.join(', ')}`],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [target, backend].join(path.delimiter),
      },
      encoding: 'utf8',
    },
  )
  return result.status === 0
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
    throw new Error(`build_vendor.py failed with exit code ${result.status}`)
  }
}

function snapshotDrift(options = {}) {
  const drift = []
  if (!canImportVendoredPackages(options)) {
    drift.push('the vendored interpreter cannot import the SDK packages')
  }
  drift.push(...packageSourceDrift(options))
  drift.push(...vendorStampDrift(options))
  return drift
}

// Only the first few, so a package-wide rename does not bury the fix under a
// hundred identical lines.
function summariseDrift(drift, limit = 8) {
  const shown = drift.slice(0, limit).map((line) => `  - ${line}`)
  if (drift.length > limit) shown.push(`  - ... and ${drift.length - limit} more`)
  return shown.join('\n')
}

function ensureVendor(options = {}) {
  const { env = process.env, warn = console.warn } = options
  const drift = snapshotDrift(options)
  if (drift.length === 0) {
    console.log(`[vendor] Python vendor closure ok (${describeSnapshot(options)})`)
    return { rebuilt: false, staleAllowed: false }
  }

  if (env[ALLOW_STALE_SNAPSHOT_ENV]) {
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
  LOCAL_PACKAGE_SOURCES,
  REBUILD_COMMAND,
  REQUIRED_VENDOR_IMPORTS,
  VENDOR_STAMP_FILENAME,
  canImportVendoredPackages,
  ensureVendor,
  localVenvBin,
  localPackageSourcesAreVendored,
  packageSourceDrift,
  pythonExecutable,
  readVendorStamp,
  rebuildVendor,
  sitePackages,
  vendorStampDrift,
  withLocalVenvOnPath,
}
