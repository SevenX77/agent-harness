#!/usr/bin/env node
/* eslint-env node */

const fs = require('node:fs')
const path = require('node:path')

const TAURI_DIR = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(TAURI_DIR, '../../..')
const VENDOR_DIR = path.join(TAURI_DIR, 'vendor')
const RESOURCE_METADATA_DIRS = new Set(['.git', '.gemini', '.workspace', '__pycache__'])

function shouldCopyResourcePath(item, sourceRoot) {
  const relative = path.relative(sourceRoot, item)
  if (!relative) {
    return true
  }
  const parts = relative.split(path.sep)
  if (parts.some((part) => RESOURCE_METADATA_DIRS.has(part))) {
    return false
  }
  return !item.endsWith('.pyc')
}

function copyDir(source, destination) {
  if (!fs.existsSync(source)) {
    throw new Error(`Resource source not found: ${source}`)
  }
  fs.rmSync(destination, { recursive: true, force: true })
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (item) => shouldCopyResourcePath(item, source),
  })
}

/**
 * Where the skills that ship inside the installer come from, or `null` when
 * there are none.
 *
 * Two sources, both of them things someone chose: the environment variable a
 * packager sets, and the repo's own `skills/`. There used to be a third between
 * them — `<repo>/../skills`, whatever directory happens to carry that name next
 * to the checkout. On the primary dev machine that is `D:\coding\skills` with 39
 * private skill sources, and `bundle.resources` ships `vendor/**` wholesale, so
 * an installer built there would have carried every one of them (ledger D3).
 * A path nobody named is not a decision, and shipping is not the place to guess.
 *
 * Nothing to bundle is a legitimate answer — Home does not auto-scan a bundled
 * registry anyway (backend `test_api.py`, 01_init.md D11) — so it returns null
 * instead of throwing, and the caller ships an empty directory.
 */
function skillsSourceDir({ repoRoot = REPO_ROOT, env = process.env } = {}) {
  const explicitSource = env.STUDIO_SKILLS_SOURCE_DIR?.trim()
  if (explicitSource) {
    return path.resolve(explicitSource)
  }

  const repoSkills = path.join(repoRoot, 'skills')
  return fs.existsSync(repoSkills) ? repoSkills : null
}

function copyBackend({ repoRoot = REPO_ROOT, vendorDir = VENDOR_DIR } = {}) {
  const backendSource = path.join(repoRoot, 'apps', 'studio', 'backend')
  const backendTarget = path.join(vendorDir, 'backend')
  fs.rmSync(backendTarget, { recursive: true, force: true })
  fs.mkdirSync(backendTarget, { recursive: true })
  copyDir(path.join(backendSource, 'app'), path.join(backendTarget, 'app'))
  for (const file of ['requirements.txt', 'pyproject.toml']) {
    fs.copyFileSync(path.join(backendSource, file), path.join(backendTarget, file))
  }
}

function copyRuntimeResources({
  repoRoot = REPO_ROOT,
  vendorDir = VENDOR_DIR,
  env = process.env,
} = {}) {
  const resourcesTarget = path.join(vendorDir, 'resources')
  fs.rmSync(resourcesTarget, { recursive: true, force: true })
  fs.mkdirSync(resourcesTarget, { recursive: true })
  const skillsSource = skillsSourceDir({ repoRoot, env })
  const skillsTarget = path.join(resourcesTarget, 'skills')
  if (skillsSource) {
    copyDir(skillsSource, skillsTarget)
  } else {
    fs.mkdirSync(skillsTarget, { recursive: true })
    console.log('[resources] no skills to bundle: set STUDIO_SKILLS_SOURCE_DIR to ship some')
  }
  copyDir(path.join(repoRoot, 'config'), path.join(resourcesTarget, 'config'))
  fs.mkdirSync(path.join(resourcesTarget, 'workspaces'), { recursive: true })
}

function main() {
  copyBackend()
  copyRuntimeResources()
  console.log(`[resources] synced backend and runtime resources under ${VENDOR_DIR}`)
}

if (require.main === module) {
  try {
    main()
  } catch (error) {
    console.error(`[resources] ${error.message}`)
    process.exit(1)
  }
}

module.exports = {
  copyBackend,
  copyRuntimeResources,
  skillsSourceDir,
  shouldCopyResourcePath,
  main,
}
