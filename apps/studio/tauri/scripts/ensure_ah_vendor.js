#!/usr/bin/env node
/* eslint-env node */

// Vendors the pinned ah release into `vendor/ah/` so Studio ships its own ah
// and can auto-deploy it into WSL at launch (decision:
// docs/design/2026-08-12-ah-vendored-auto-deploy.md). Same lock + sha256 +
// cache pattern as download_runtime.js; the lock file is the single pin.

const fs = require('node:fs')
const path = require('node:path')
const {
  DEFAULT_DOWNLOADS_DIR,
  download,
  extractWithTar,
  verifySha256,
} = require('./download_runtime')

const TAURI_DIR = path.resolve(__dirname, '..')
const DEFAULT_LOCK_PATH = path.join(TAURI_DIR, 'ah-vendor.lock.json')
const DEFAULT_VENDOR_AH_DIR = path.join(TAURI_DIR, 'vendor', 'ah')
// The single release tarball carries both binaries (the official installer
// installs exactly these two from it); a snapshot missing either is incomplete.
const AH_BINARIES = ['ah', 'ahd']

function validateAhLock(lock) {
  if (typeof lock.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(lock.version)) {
    throw new Error(`Invalid version in ah-vendor.lock.json: ${lock.version}`)
  }
  const artifact = lock.artifact
  if (!artifact) throw new Error('ah-vendor.lock.json is missing artifact')
  for (const key of ['filename', 'sha256', 'url']) {
    if (typeof artifact[key] !== 'string' || artifact[key].length === 0) {
      throw new Error(`Invalid artifact.${key} in ah-vendor.lock.json`)
    }
  }
  if (!/^[a-f0-9]{64}$/.test(artifact.sha256)) {
    throw new Error(`Invalid artifact sha256: ${artifact.sha256}`)
  }
  if (!artifact.url.includes(lock.version)) {
    throw new Error(`Artifact URL does not pin version ${lock.version}: ${artifact.url}`)
  }
}

function loadAhLock(lockPath = DEFAULT_LOCK_PATH) {
  const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'))
  validateAhLock(lock)
  return lock
}

// VERSION is written LAST, after a verified extract: its presence certifies
// the binaries next to it. The Rust side reads the same file at runtime.
function vendoredAhVersion(vendorAhDir = DEFAULT_VENDOR_AH_DIR) {
  const versionPath = path.join(vendorAhDir, 'VERSION')
  if (!fs.existsSync(versionPath)) return null
  for (const binary of AH_BINARIES) {
    if (!fs.existsSync(path.join(vendorAhDir, binary))) return null
  }
  return fs.readFileSync(versionPath, 'utf8').trim() || null
}

async function ensureArchive(artifact, downloadsDir, downloadFile) {
  fs.mkdirSync(downloadsDir, { recursive: true })
  const archivePath = path.join(downloadsDir, artifact.filename)
  if (fs.existsSync(archivePath)) {
    verifySha256(archivePath, artifact.sha256)
    console.log(`[ah-vendor] cache verified ${artifact.filename}`)
    return archivePath
  }
  const partialPath = `${archivePath}.partial`
  fs.rmSync(partialPath, { force: true })
  console.log(`[ah-vendor] downloading ${artifact.url}`)
  try {
    await downloadFile(artifact.url, partialPath)
    verifySha256(partialPath, artifact.sha256)
    fs.renameSync(partialPath, archivePath)
    console.log(`[ah-vendor] sha256 ok ${artifact.sha256}`)
    return archivePath
  } catch (error) {
    fs.rmSync(partialPath, { force: true })
    throw error
  }
}

// cargo-dist tarballs nest binaries under `<app>-<target>/`; accept any layout
// by finding the one directory that holds ALL the expected binaries.
function findBinaryDir(rootDir) {
  const queue = [rootDir]
  while (queue.length > 0) {
    const dir = queue.shift()
    if (AH_BINARIES.every((binary) => fs.existsSync(path.join(dir, binary)))) return dir
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) queue.push(path.join(dir, entry.name))
    }
  }
  throw new Error(`Extracted archive does not contain ${AH_BINARIES.join(' + ')}`)
}

async function ensureAhVendor({
  lockPath = DEFAULT_LOCK_PATH,
  vendorAhDir = DEFAULT_VENDOR_AH_DIR,
  downloadsDir = DEFAULT_DOWNLOADS_DIR,
  downloadFile = download,
  extract = extractWithTar,
} = {}) {
  const lock = loadAhLock(lockPath)
  if (vendoredAhVersion(vendorAhDir) === lock.version) {
    console.log(`[ah-vendor] ah ${lock.version} already vendored`)
    return 'up-to-date'
  }
  const archivePath = await ensureArchive(lock.artifact, downloadsDir, downloadFile)
  fs.mkdirSync(path.dirname(vendorAhDir), { recursive: true })
  const tempDir = fs.mkdtempSync(path.join(path.dirname(vendorAhDir), '.ah-vendor-'))
  try {
    extract(archivePath, tempDir)
    const binaryDir = findBinaryDir(tempDir)
    fs.rmSync(vendorAhDir, { recursive: true, force: true })
    fs.mkdirSync(vendorAhDir, { recursive: true })
    for (const binary of AH_BINARIES) {
      fs.copyFileSync(path.join(binaryDir, binary), path.join(vendorAhDir, binary))
      fs.chmodSync(path.join(vendorAhDir, binary), 0o755)
    }
    fs.writeFileSync(path.join(vendorAhDir, 'VERSION'), `${lock.version}\n`)
    console.log(`[ah-vendor] vendored ah ${lock.version}`)
    return 'installed'
  } catch (error) {
    // No half-written snapshot: a failed swap removes the dir outright and the
    // next run rebuilds it from the verified cache.
    fs.rmSync(vendorAhDir, { recursive: true, force: true })
    throw error
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true })
  }
}

// dev chain: a warning, never a blocker (offline machines keep working; the
// launcher just falls back to the ah already installed in WSL). build chain
// passes --strict: a release without the bundled ah defeats the decision.
async function main(argv = process.argv.slice(2), ensure = ensureAhVendor) {
  const strict = argv.includes('--strict')
  try {
    await ensure()
    return 0
  } catch (error) {
    if (strict) {
      console.error(`[ah-vendor] FAILED: ${error.message}`)
      return 1
    }
    console.warn(`[ah-vendor] WARNING: ${error.message}`)
    console.warn('[ah-vendor] continuing without a bundled ah (launcher falls back to the installed one)')
    return 0
  }
}

if (require.main === module) {
  main().then((code) => process.exit(code))
}

module.exports = {
  AH_BINARIES,
  DEFAULT_DOWNLOADS_DIR,
  DEFAULT_LOCK_PATH,
  ensureAhVendor,
  findBinaryDir,
  loadAhLock,
  main,
  validateAhLock,
  vendoredAhVersion,
}
