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
const REQUIRED_VENDOR_IMPORTS = [
  'graph_agent',
  'graph_agent_gateway',
  'graph_agent_gateway.probe_catalog',
]
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

function collectPythonFiles(root) {
  if (!fs.existsSync(root)) return null
  const files = []
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === '__pycache__' || entry.name.startsWith('.')) continue
      const fullPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        visit(fullPath)
      } else if (entry.isFile() && entry.name.endsWith('.py')) {
        files.push(path.relative(root, fullPath))
      }
    }
  }
  visit(root)
  return files.sort()
}

function fileHash(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

function localPackageSourcesAreVendored({
  packages = LOCAL_PACKAGE_SOURCES,
  target = sitePackages(),
} = {}) {
  for (const packageInfo of packages) {
    const vendorRoot = packageInfo.vendorRoot ?? path.join(target, packageInfo.packageName)
    const sourceFiles = collectPythonFiles(packageInfo.sourceRoot)
    const vendorFiles = collectPythonFiles(vendorRoot)
    if (sourceFiles === null || vendorFiles === null) return false
    if (sourceFiles.length !== vendorFiles.length) return false
    for (let index = 0; index < sourceFiles.length; index += 1) {
      if (sourceFiles[index] !== vendorFiles[index]) return false
      const sourceFile = path.join(packageInfo.sourceRoot, sourceFiles[index])
      const vendorFile = path.join(vendorRoot, vendorFiles[index])
      if (fileHash(sourceFile) !== fileHash(vendorFile)) return false
    }
  }
  return true
}

function canImportVendoredPackages({
  python = pythonExecutable(),
  target = sitePackages(),
  backend = path.join(VENDOR_DIR, 'backend'),
  modules = REQUIRED_VENDOR_IMPORTS,
} = {}) {
  if (!fs.existsSync(python) || !fs.existsSync(target)) return false
  const result = spawnSync(
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
} = {}) {
  console.log('[vendor] Python vendor closure stale or incomplete; rebuilding')
  const result = spawnSync('python3', [buildScript, '--python', python], {
    cwd: REPO_ROOT,
    stdio: 'inherit',
  })
  if (result.status !== 0) {
    throw new Error(`build_vendor.py failed with exit code ${result.status}`)
  }
}

function ensureVendor(options = {}) {
  const importsOk = canImportVendoredPackages(options)
  const sourcesOk = localPackageSourcesAreVendored(options)
  if (importsOk && sourcesOk) {
    console.log('[vendor] Python vendor closure ok')
    return { rebuilt: false }
  }
  rebuildVendor(options)
  if (!canImportVendoredPackages(options)) {
    throw new Error('Python vendor closure rebuilt, but required imports still fail')
  }
  if (!localPackageSourcesAreVendored(options)) {
    throw new Error('Python vendor closure rebuilt, but local package sources are still stale')
  }
  console.log('[vendor] Python vendor closure rebuilt and verified')
  return { rebuilt: true }
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
  canImportVendoredPackages,
  ensureVendor,
  localPackageSourcesAreVendored,
  pythonExecutable,
  rebuildVendor,
  sitePackages,
}
