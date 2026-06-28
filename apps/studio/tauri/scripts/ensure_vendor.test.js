/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  canImportVendoredPackages,
  ensureVendor,
  localVenvBin,
  localPackageSourcesAreVendored,
  pythonExecutable,
  rebuildVendor,
  sitePackages,
  withLocalVenvOnPath,
} = require('./ensure_vendor')

test('pythonExecutable resolves the host runtime path', () => {
  const executable = pythonExecutable()
  if (process.platform === 'win32') {
    assert.match(executable, /vendor\\python\\.+\\python\.exe/)
  } else {
    assert.match(executable, /vendor\/python\/.+\/bin\/python3/)
  }
})

test('sitePackages resolves the Tauri vendor target', () => {
  assert.match(sitePackages().split(path.sep).join('/'), /apps\/studio\/tauri\/vendor\/site-packages$/)
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

test('withLocalVenvOnPath prepends the workspace venv scripts directory', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-venv-'))
  const scriptsDir = localVenvBin(tmp)
  fs.mkdirSync(scriptsDir, { recursive: true })

  const result = withLocalVenvOnPath({ PATH: 'base' }, tmp)

  assert.equal(result.PATH, `${scriptsDir}${path.delimiter}base`)
})

test('rebuildVendor runs the build script with the vendored python', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-rebuild-'))
  const scriptsDir = localVenvBin(tmp)
  fs.mkdirSync(scriptsDir, { recursive: true })
  const calls = []

  rebuildVendor({
    python: path.join(tmp, 'vendor-python'),
    buildScript: path.join(tmp, 'build_vendor.py'),
    env: { PATH: 'base' },
    workspaceRoot: tmp,
    spawn: (command, args, options) => {
      calls.push({ command, args, options })
      return { status: 0 }
    },
  })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].command, path.join(tmp, 'vendor-python'))
  assert.deepEqual(calls[0].args, [
    path.join(tmp, 'build_vendor.py'),
    '--python',
    path.join(tmp, 'vendor-python'),
  ])
  assert.equal(calls[0].options.cwd, tmp)
  assert.equal(calls[0].options.env.PATH, `${scriptsDir}${path.delimiter}base`)
})
