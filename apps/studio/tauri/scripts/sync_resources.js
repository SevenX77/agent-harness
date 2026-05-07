#!/usr/bin/env node
/* eslint-env node */

const fs = require('node:fs')
const path = require('node:path')

const TAURI_DIR = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(TAURI_DIR, '../../..')
const VENDOR_DIR = path.join(TAURI_DIR, 'vendor')

function copyDir(source, destination) {
  if (!fs.existsSync(source)) {
    throw new Error(`Resource source not found: ${source}`)
  }
  fs.rmSync(destination, { recursive: true, force: true })
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (item) => !item.includes(`${path.sep}__pycache__${path.sep}`)
      && !item.endsWith(`${path.sep}__pycache__`)
      && !item.endsWith('.pyc'),
  })
}

function copyBackend() {
  const backendSource = path.join(REPO_ROOT, 'apps', 'studio', 'backend')
  const backendTarget = path.join(VENDOR_DIR, 'backend')
  fs.rmSync(backendTarget, { recursive: true, force: true })
  fs.mkdirSync(backendTarget, { recursive: true })
  copyDir(path.join(backendSource, 'app'), path.join(backendTarget, 'app'))
  for (const file of ['requirements.txt', 'pyproject.toml']) {
    fs.copyFileSync(path.join(backendSource, file), path.join(backendTarget, file))
  }
}

function copyRuntimeResources() {
  const resourcesTarget = path.join(VENDOR_DIR, 'resources')
  fs.mkdirSync(resourcesTarget, { recursive: true })
  copyDir(path.join(REPO_ROOT, 'skills'), path.join(resourcesTarget, 'skills'))
  copyDir(path.join(REPO_ROOT, 'config'), path.join(resourcesTarget, 'config'))
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
  main,
}
