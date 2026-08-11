/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  LOCAL_PACKAGE_SOURCES,
  REQUIRED_VENDOR_IMPORTS,
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

// The gate names modules it will `import` inside the vendored interpreter. A
// name that no longer exists makes the gate unsatisfiable: ensureVendor keeps
// rebuilding and then throws, so the desktop app cannot start at all. That is
// what happened when the gateway's six-domain refactor (#706) folded
// `graph_agent_gateway.probe_catalog` into the registry domain and this list
// kept naming the dead module.
test('every required vendor import exists in the workspace package sources', () => {
  for (const moduleName of REQUIRED_VENDOR_IMPORTS) {
    const [packageName, ...submodules] = moduleName.split('.')
    const source = LOCAL_PACKAGE_SOURCES.find((entry) => entry.packageName === packageName)
    assert.ok(source, `${moduleName} names a package the vendor gate does not vendor`)

    const modulePath = path.join(source.sourceRoot, ...submodules)
    assert.ok(
      fs.existsSync(`${modulePath}.py`) || fs.existsSync(path.join(modulePath, '__init__.py')),
      `${moduleName} does not exist under ${source.sourceRoot}`,
    )
  }
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

// The branch under test is ensureVendor's own: imports report fine, so no
// rebuild. Running a real interpreter to establish that would tie this to a
// provisioned Python — the vendored runtime is a downloaded artefact absent
// from fresh checkouts, and the workspace venv only exists after `uv sync`.
test('ensureVendor skips rebuild when imports already work', () => {
  const result = ensureVendor({
    python: __filename,
    target: __dirname,
    backend: __dirname,
    modules: ['sys'],
    packages: [],
    spawn: () => ({ status: 0 }),
  })
  assert.deepEqual(result, { rebuilt: false })
})

test('ensureVendor rebuilds when the vendored interpreter cannot import', () => {
  const calls = []
  const result = ensureVendor({
    python: __filename,
    target: __dirname,
    backend: __dirname,
    modules: ['sys'],
    packages: [],
    buildScript: __filename,
    workspaceRoot: __dirname,
    // Only the first check fails, so the rebuild between them is what changed
    // the answer — not a check that was going to pass anyway.
    spawn: (...args) => {
      calls.push(args)
      return { status: calls.length === 1 ? 1 : 0 }
    },
  })
  assert.deepEqual(result, { rebuilt: true })
  assert.equal(calls.length, 3, 'check, rebuild, re-check')
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
