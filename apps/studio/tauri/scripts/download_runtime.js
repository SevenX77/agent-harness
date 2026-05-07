#!/usr/bin/env node
/* eslint-env node */

const crypto = require('node:crypto')
const fs = require('node:fs')
const https = require('node:https')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const TAURI_DIR = path.resolve(__dirname, '..')
const DEFAULT_LOCK_PATH = path.join(TAURI_DIR, 'python-runtime.lock.json')
const DEFAULT_VENDOR_DIR = path.join(TAURI_DIR, 'vendor')
const REQUIRED_TARGETS = [
  'x86_64-apple-darwin',
  'aarch64-apple-darwin',
  'x86_64-unknown-linux-gnu',
  'aarch64-unknown-linux-gnu',
  'x86_64-pc-windows-msvc',
]

function hostTargetTriple(platform = process.platform, arch = process.arch) {
  if (platform === 'darwin' && arch === 'x64') return 'x86_64-apple-darwin'
  if (platform === 'darwin' && arch === 'arm64') return 'aarch64-apple-darwin'
  if (platform === 'linux' && arch === 'x64') return 'x86_64-unknown-linux-gnu'
  if (platform === 'linux' && arch === 'arm64') return 'aarch64-unknown-linux-gnu'
  if (platform === 'win32' && arch === 'x64') return 'x86_64-pc-windows-msvc'
  throw new Error(`Unsupported platform/arch: ${platform}/${arch}`)
}

function parseArgs(argv) {
  const args = {
    lockPath: DEFAULT_LOCK_PATH,
    vendorDir: DEFAULT_VENDOR_DIR,
    target: hostTargetTriple(),
    force: false,
  }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--lock') args.lockPath = path.resolve(argv[++index])
    else if (arg === '--vendor') args.vendorDir = path.resolve(argv[++index])
    else if (arg === '--target') args.target = argv[++index]
    else if (arg === '--force') args.force = true
    else throw new Error(`Unknown argument: ${arg}`)
  }
  return args
}

function loadLock(lockPath) {
  const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'))
  validateLock(lock)
  return lock
}

function validateLock(lock) {
  for (const target of REQUIRED_TARGETS) {
    const artifact = lock.artifacts?.[target]
    if (!artifact) throw new Error(`Missing runtime artifact for ${target}`)
    for (const key of ['filename', 'sha256', 'url']) {
      if (typeof artifact[key] !== 'string' || artifact[key].length === 0) {
        throw new Error(`Invalid ${target}.${key} in python-runtime.lock.json`)
      }
    }
    if (!/^[a-f0-9]{64}$/.test(artifact.sha256)) {
      throw new Error(`Invalid sha256 for ${target}: ${artifact.sha256}`)
    }
    if (!artifact.url.includes(encodeURIComponent(lock.tag)) && !artifact.url.includes(lock.tag)) {
      throw new Error(`Artifact URL for ${target} does not include pinned tag ${lock.tag}`)
    }
  }
}

function artifactFor(lock, target) {
  const artifact = lock.artifacts[target]
  if (!artifact) throw new Error(`Unsupported target triple: ${target}`)
  return artifact
}

function sha256File(filePath) {
  const hash = crypto.createHash('sha256')
  hash.update(fs.readFileSync(filePath))
  return hash.digest('hex')
}

function verifySha256(filePath, expectedSha256) {
  const actualSha256 = sha256File(filePath)
  if (actualSha256 !== expectedSha256) {
    throw new Error(
      `SHA256 mismatch for ${filePath}: expected ${expectedSha256}, got ${actualSha256}`,
    )
  }
  return actualSha256
}

function pythonExecutable(runtimeDir, target) {
  return target.includes('windows')
    ? path.join(runtimeDir, 'python.exe')
    : path.join(runtimeDir, 'bin', 'python')
}

function runtimeManifest(runtimeDir) {
  return path.join(runtimeDir, '.python-runtime.json')
}

function isRuntimeInstalled(runtimeDir, target, artifact) {
  const executable = pythonExecutable(runtimeDir, target)
  const manifestPath = runtimeManifest(runtimeDir)
  if (!fs.existsSync(executable) || !fs.existsSync(manifestPath)) return false
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
    return (
      manifest.target === target
      && manifest.filename === artifact.filename
      && manifest.sha256 === artifact.sha256
    )
  } catch {
    return false
  }
}

function download(url, destination) {
  return new Promise((resolve, reject) => {
    const request = https.get(url, { headers: { 'User-Agent': 'agent-harness' } }, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode ?? 0)) {
        const location = response.headers.location
        if (!location) {
          reject(new Error(`Redirect without location while downloading ${url}`))
          return
        }
        response.resume()
        download(location, destination).then(resolve, reject)
        return
      }
      if (response.statusCode !== 200) {
        reject(new Error(`Download failed for ${url}: HTTP ${response.statusCode}`))
        response.resume()
        return
      }
      const file = fs.createWriteStream(destination, { flags: 'wx' })
      response.pipe(file)
      file.on('finish', () => file.close(resolve))
      file.on('error', reject)
    })
    request.on('error', reject)
  })
}

async function ensureArchive(artifact, downloadsDir) {
  fs.mkdirSync(downloadsDir, { recursive: true })
  const archivePath = path.join(downloadsDir, artifact.filename)
  if (fs.existsSync(archivePath)) {
    verifySha256(archivePath, artifact.sha256)
    console.log(`[python-runtime] cache verified ${artifact.filename}`)
    return archivePath
  }

  const partialPath = `${archivePath}.partial`
  fs.rmSync(partialPath, { force: true })
  console.log(`[python-runtime] downloading ${artifact.url}`)
  try {
    await download(artifact.url, partialPath)
    verifySha256(partialPath, artifact.sha256)
    fs.renameSync(partialPath, archivePath)
    console.log(`[python-runtime] sha256 ok ${artifact.sha256}`)
    return archivePath
  } catch (error) {
    fs.rmSync(partialPath, { force: true })
    throw error
  }
}

function extractRuntime(archivePath, runtimeDir, target, artifact, lock) {
  fs.mkdirSync(path.dirname(runtimeDir), { recursive: true })
  const tempDir = fs.mkdtempSync(path.join(path.dirname(runtimeDir), '.python-runtime-'))
  try {
    const result = spawnSync('tar', ['-xzf', archivePath, '-C', tempDir], { stdio: 'inherit' })
    if (result.status !== 0) {
      throw new Error(`tar extraction failed with exit code ${result.status}`)
    }

    const extractedPythonDir = path.join(tempDir, 'python')
    const sourceDir = fs.existsSync(extractedPythonDir) ? extractedPythonDir : tempDir
    fs.rmSync(runtimeDir, { recursive: true, force: true })
    fs.renameSync(sourceDir, runtimeDir)
    fs.writeFileSync(
      runtimeManifest(runtimeDir),
      JSON.stringify({
        target,
        filename: artifact.filename,
        sha256: artifact.sha256,
        tag: lock.tag,
        python_version: lock.python_version,
      }, null, 2),
    )
  } catch (error) {
    fs.rmSync(runtimeDir, { recursive: true, force: true })
    throw error
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true })
  }
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv)
  const lock = loadLock(args.lockPath)
  const artifact = artifactFor(lock, args.target)
  const runtimeDir = path.join(args.vendorDir, 'python', args.target)
  const downloadsDir = path.join(args.vendorDir, 'downloads')

  if (!args.force && isRuntimeInstalled(runtimeDir, args.target, artifact)) {
    console.log(`[python-runtime] runtime already installed ${args.target}`)
    console.log(`[python-runtime] executable ${pythonExecutable(runtimeDir, args.target)}`)
    return { runtimeDir, target: args.target, skipped: true }
  }

  const archivePath = await ensureArchive(artifact, downloadsDir)
  extractRuntime(archivePath, runtimeDir, args.target, artifact, lock)
  const executable = pythonExecutable(runtimeDir, args.target)
  if (!fs.existsSync(executable)) {
    fs.rmSync(runtimeDir, { recursive: true, force: true })
    throw new Error(`Runtime extraction missing Python executable: ${executable}`)
  }
  console.log(`[python-runtime] installed ${args.target} -> ${runtimeDir}`)
  console.log(`[python-runtime] executable ${executable}`)
  return { runtimeDir, target: args.target, skipped: false }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`[python-runtime] ${error.message}`)
    process.exit(1)
  })
}

module.exports = {
  REQUIRED_TARGETS,
  artifactFor,
  hostTargetTriple,
  loadLock,
  main,
  pythonExecutable,
  sha256File,
  validateLock,
  verifySha256,
}
