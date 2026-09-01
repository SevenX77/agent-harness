/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  ALLOW_STALE_SNAPSHOT_ENV,
  LOCAL_PACKAGE_SOURCES,
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
} = require('./ensure_vendor')

// A snapshot directory that would satisfy the gate: the stamp build_vendor.py
// writes as its last step. Tests that are about some OTHER branch use this so
// the stamp check is not the thing that decides their outcome.
function stampedSnapshotDir(digest = 'a'.repeat(64)) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-stamped-'))
  fs.writeFileSync(
    path.join(dir, VENDOR_STAMP_FILENAME),
    JSON.stringify({ schema: 1, source_digest: digest, built_at: '2026-09-01T00:00:00+00:00' }),
    'utf8',
  )
  return dir
}

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

// The gate used to compare only files ending in `.py`. Both SDK packages ship
// non-Python files INSIDE the package, installed into the snapshot by the wheel
// and read at runtime: the gateway's provider call-method routing table
// `graph_agent_gateway/registry/call_methods.json` (loaded through
// `importlib.resources` by `registry/call_methods.py`) and the engine's
// `graph_agent/skills/builtin/md-patch/SKILL.md`. Editing either one and
// launching the app printed "Python vendor closure ok" and served the OLD
// table — the whole failure this gate exists to prevent, one file extension
// out of reach.
test('packageSourceDrift detects a changed non-Python package data file', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-data-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg', 'registry')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg', 'registry')
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, '__init__.py'), '', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, '__init__.py'), '', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, 'call_methods.json'), '{"transform": "new"}\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, 'call_methods.json'), '{"transform": "old"}\n', 'utf8')

  const drift = packageSourceDrift({
    packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }],
  })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /call_methods\.json/)
})

test('packageSourceDrift detects a package data file absent from the snapshot', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-data-missing-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  fs.mkdirSync(path.join(sourceRoot, 'skills', 'builtin', 'md-patch'), { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, '__init__.py'), '', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, 'skills', 'builtin', 'md-patch', 'SKILL.md'), '# md-patch\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, '__init__.py'), '', 'utf8')

  const drift = packageSourceDrift({
    packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }],
  })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /SKILL\.md/)
})

test('packageSourceDrift is silent when every file matches byte for byte', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-fresh-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  for (const root of [sourceRoot, vendorRoot]) {
    fs.mkdirSync(path.join(root, 'registry'), { recursive: true })
    fs.writeFileSync(path.join(root, '__init__.py'), 'VERSION = 1\n', 'utf8')
    fs.writeFileSync(path.join(root, 'registry', 'call_methods.json'), '{"a": 1}\n', 'utf8')
    fs.writeFileSync(path.join(root, 'py.typed'), '', 'utf8')
  }

  assert.deepEqual(
    packageSourceDrift({ packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }] }),
    [],
  )
})

// A snapshot with no provenance is a snapshot nobody can place. On a user's
// machine there is no source tree to compare against, so the stamp is the only
// thing that can say which engine the installed app carries — and the gate is
// what makes writing it non-optional.
test('vendorStampDrift reports a snapshot carrying no provenance stamp', () => {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-nostamp-'))

  const drift = vendorStampDrift({ target })

  assert.equal(drift.length, 1)
  assert.match(drift[0], new RegExp(VENDOR_STAMP_FILENAME.replace('.', '\\.')))
})

test('vendorStampDrift reports a stamp that does not parse', () => {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-badstamp-'))
  fs.writeFileSync(path.join(target, VENDOR_STAMP_FILENAME), 'not json', 'utf8')

  assert.equal(vendorStampDrift({ target }).length, 1)
})

test('vendorStampDrift reports a stamp with no source digest', () => {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-emptystamp-'))
  fs.writeFileSync(path.join(target, VENDOR_STAMP_FILENAME), JSON.stringify({ schema: 1 }), 'utf8')

  assert.equal(vendorStampDrift({ target }).length, 1)
})

test('vendorStampDrift accepts a stamp naming a source digest', () => {
  const target = stampedSnapshotDir()

  assert.deepEqual(vendorStampDrift({ target }), [])
  assert.equal(readVendorStamp({ target }).source_digest, 'a'.repeat(64))
})

// The branch under test is ensureVendor's own: imports report fine, so no
// rebuild. Running a real interpreter to establish that would tie this to a
// provisioned Python — the vendored runtime is a downloaded artefact absent
// from fresh checkouts, and the workspace venv only exists after `uv sync`.
test('ensureVendor skips rebuild when imports already work', () => {
  const result = ensureVendor({
    python: __filename,
    target: stampedSnapshotDir(),
    backend: __dirname,
    modules: ['sys'],
    packages: [],
    spawn: () => ({ status: 0 }),
  })
  assert.deepEqual(result, { rebuilt: false, staleAllowed: false })
})

test('ensureVendor rebuilds when the vendored interpreter cannot import', () => {
  const calls = []
  const result = ensureVendor({
    python: __filename,
    target: stampedSnapshotDir(),
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
  assert.deepEqual(result, { rebuilt: true, staleAllowed: false })
  assert.equal(calls.length, 3, 'check, rebuild, re-check')
})

test('ensureVendor rebuilds a snapshot whose sources drifted even though imports work', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-drift-rebuild-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, 'table.json'), '{"a": 2}\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, 'table.json'), '{"a": 1}\n', 'utf8')

  const packages = [{ packageName: 'example_pkg', sourceRoot, vendorRoot }]
  let rebuilt = false
  const result = ensureVendor({
    python: __filename,
    target: stampedSnapshotDir(),
    backend: __dirname,
    modules: ['sys'],
    packages,
    buildScript: __filename,
    workspaceRoot: __dirname,
    // The build is what a real rebuild does: it makes the snapshot match.
    spawn: (command, args) => {
      if (args && args[0] === __filename) {
        rebuilt = true
        fs.copyFileSync(path.join(sourceRoot, 'table.json'), path.join(vendorRoot, 'table.json'))
      }
      return { status: 0 }
    },
  })

  assert.equal(rebuilt, true, 'a data-file-only drift must still trigger the rebuild')
  assert.deepEqual(result, { rebuilt: true, staleAllowed: false })
})

// Widening the comparison to every shipped file means editing a package's own
// CHANGELOG.md now costs a full clean rebuild. Booting the app against a
// knowingly stale snapshot is a legitimate thing to want (reproducing a bug
// against the snapshot that has it), so there is one way to say so — named
// after what it permits, and never silent.
test(`${ALLOW_STALE_SNAPSHOT_ENV} boots a stale snapshot without rebuilding, loudly`, () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-escape-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, 'table.json'), '{"a": 2}\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, 'table.json'), '{"a": 1}\n', 'utf8')

  const warnings = []
  const result = ensureVendor({
    python: __filename,
    target: stampedSnapshotDir(),
    backend: __dirname,
    modules: ['sys'],
    packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }],
    buildScript: __filename,
    workspaceRoot: __dirname,
    env: { ...process.env, [ALLOW_STALE_SNAPSHOT_ENV]: '1' },
    warn: (message) => warnings.push(message),
    spawn: () => ({ status: 0 }),
  })

  assert.deepEqual(result, { rebuilt: false, staleAllowed: true })
  const said = warnings.join('\n')
  assert.match(said, /table\.json/, 'the warning must name what is stale')
  assert.match(said, /build_vendor\.py/, 'the warning must name the command that fixes it')
})

test('an unset escape hatch does not let a stale snapshot through', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-noescape-'))
  const sourceRoot = path.join(tmp, 'source', 'example_pkg')
  const vendorRoot = path.join(tmp, 'vendor', 'example_pkg')
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })
  fs.writeFileSync(path.join(sourceRoot, 'table.json'), '{"a": 2}\n', 'utf8')
  fs.writeFileSync(path.join(vendorRoot, 'table.json'), '{"a": 1}\n', 'utf8')

  assert.throws(
    () => ensureVendor({
      python: __filename,
      target: stampedSnapshotDir(),
      backend: __dirname,
      modules: ['sys'],
      packages: [{ packageName: 'example_pkg', sourceRoot, vendorRoot }],
      buildScript: __filename,
      workspaceRoot: __dirname,
      env: { PATH: 'base' },
      // A rebuild that changes nothing: the snapshot stays stale, so the gate
      // must refuse rather than start the app on it.
      spawn: () => ({ status: 0 }),
    }),
    /still stale|table\.json/,
  )
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
