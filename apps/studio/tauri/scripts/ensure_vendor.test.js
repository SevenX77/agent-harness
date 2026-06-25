/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  canImportVendoredPackages,
  ensureVendor,
  localPackageSourcesAreVendored,
  pythonExecutable,
  sitePackages,
} = require('./ensure_vendor')

test('pythonExecutable resolves the host runtime path', () => {
  assert.match(pythonExecutable(), /vendor\/python\/.+\/bin\/python3/)
})

test('sitePackages resolves the Tauri vendor target', () => {
  assert.match(sitePackages(), /apps\/studio\/tauri\/vendor\/site-packages$/)
})

test('canImportVendoredPackages returns false when python is missing', () => {
  assert.equal(canImportVendoredPackages({ python: '/missing/python' }), false)
})

test('canImportVendoredPackages requires gateway submodules used by the sidecar', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-import-'))
  for (const packageName of ['graph_agent', 'graph_agent_gateway']) {
    const packageDir = path.join(tmp, packageName)
    fs.mkdirSync(packageDir, { recursive: true })
    fs.writeFileSync(path.join(packageDir, '__init__.py'), '', 'utf8')
  }

  assert.equal(
    canImportVendoredPackages({
      python: pythonExecutable(),
      target: tmp,
      backend: tmp,
    }),
    false,
  )
})

test('localPackageSourcesAreVendored detects source files missing from vendor', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-source-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, '__init__.py'), '', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, 'new_module.py'), 'VALUE = 1\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, '__init__.py'), '', 'utf8')

  assert.equal(
    localPackageSourcesAreVendored({
      packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }],
    }),
    false,
  )
})

test('ensureVendor skips rebuild when imports already work', () => {
  const result = ensureVendor({
    python: pythonExecutable(),
    target: __dirname,
    backend: __dirname,
    modules: ['sys'],
    packages: [],
  })
  assert.deepEqual(result, { rebuilt: false })
})
