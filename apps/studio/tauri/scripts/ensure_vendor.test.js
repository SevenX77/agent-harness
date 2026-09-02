/* eslint-env node */

const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  ALLOW_STALE_SNAPSHOT_ENV,
  VENDOR_STAMP_FILENAME,
  VENDOR_STAMP_SCHEMA,
  describeSpawnFailure,
  ensureVendor,
  localVenvBin,
  packageSourceDrift,
  pythonExecutable,
  readVendorStamp,
  rebuildVendor,
  sitePackages,
  snapshotDrift,
  sourceAdditions,
  staleSnapshotAllowed,
  vendorStampDrift,
  vendoredImportDrift,
  withLocalVenvOnPath,
} = require('./ensure_vendor')

const PACKAGE_NAME = 'example_pkg'
const SOURCE_ROOT = 'packages/example/src/example_pkg'

// git -z separates paths with a NUL byte.
const NUL = String.fromCharCode(0)

function sha256(content) {
  return crypto.createHash('sha256').update(content).digest('hex')
}

function writeFile(root, relative, content) {
  const file = path.join(root, ...relative.split('/'))
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, content, 'utf8')
}

/**
 * A source tree, a snapshot, the stamp a build would have left behind, and the
 * answer git would give about that source tree.
 *
 * `shipped` is what the wheel carried — the stamp's manifest is built from it,
 * exactly as `build_vendor.py` builds it from the wheel's own entries. The
 * override maps say how reality differs from that record: a string replaces the
 * file's content on that side, `null` deletes it.
 *
 * The last two are the cases a tree-walking gate got wrong, in both
 * directions. `added` files exist in the sources and git lists them, so no
 * wheel has carried them yet. `ignored` files exist in the sources and git does
 * NOT list them (gitignored build artefacts like `_native.pyd`), so demanding
 * them from the snapshot would be a drift no rebuild could clear.
 */
function snapshotFixture({ shipped, sources = {}, snapshot = {}, added = {}, ignored = {} } = {}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-'))
  const repoRoot = path.join(tmp, 'repo')
  const target = path.join(tmp, 'site-packages')
  const sourceRoot = path.join(repoRoot, ...SOURCE_ROOT.split('/'))
  const vendorRoot = path.join(target, PACKAGE_NAME)
  fs.mkdirSync(sourceRoot, { recursive: true })
  fs.mkdirSync(vendorRoot, { recursive: true })

  const files = {}
  for (const [relative, content] of Object.entries(shipped)) {
    files[relative] = sha256(content)
    const inSources = relative in sources ? sources[relative] : content
    const inSnapshot = relative in snapshot ? snapshot[relative] : content
    if (inSources !== null) writeFile(sourceRoot, relative, inSources)
    if (inSnapshot !== null) writeFile(vendorRoot, relative, inSnapshot)
  }
  for (const [relative, content] of Object.entries({ ...added, ...ignored })) {
    writeFile(sourceRoot, relative, content)
  }
  // What `git ls-files --cached --others --exclude-standard` would print for
  // this source root: everything but the ignored artefacts.
  const listed = [...Object.keys(shipped), ...Object.keys(added)].join(NUL)
  const runGit = () => ({ status: 0, stdout: listed })

  const stamp = {
    schema: VENDOR_STAMP_SCHEMA,
    source_digest: 'a'.repeat(64),
    built_at: '2026-09-01T00:00:00+00:00',
    python_version: '3.12.13',
    target_triple: 'x86_64-pc-windows-msvc',
    packages: {
      [PACKAGE_NAME]: { source_root: SOURCE_ROOT, digest: 'b'.repeat(64), files },
    },
  }
  fs.writeFileSync(path.join(target, VENDOR_STAMP_FILENAME), JSON.stringify(stamp), 'utf8')
  // `stampContent` and not `stamp`: fixtures are spread straight into option
  // objects, and a `stamp` key there would inject the record and stop the gate
  // from reading the file the test is about.
  return { repoRoot, target, sourceRoot, vendorRoot, runGit, stampContent: stamp }
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
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '', 'registry/call_methods.json': '{"transform": "new"}\n' },
    snapshot: { 'registry/call_methods.json': '{"transform": "old"}\n' },
  })

  const drift = packageSourceDrift(fixture)

  assert.equal(drift.length, 1)
  assert.match(drift[0], /call_methods\.json/)
})

// Widening the comparison from `.py` to "every file" was still a guess about
// which files a package consists of, and it was wrong in both directions.
// Hatchling ships dotfiles that sit INSIDE the package (verified against a real
// wheel: a package holding `.runtime-data.json`, `CHANGELOG.md`, `_native.pyd`
// and `__pycache__/` produced a wheel containing the first two only), while the
// walk skipped every name starting with `.`. So the file was invisible to the
// gate and could drift for good.
test('packageSourceDrift compares a dotfile the wheel ships', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '', '.runtime-data.json': '{"v": 2}\n' },
    snapshot: { '.runtime-data.json': '{"v": 1}\n' },
  })

  const drift = packageSourceDrift(fixture)

  assert.equal(drift.length, 1, `hatchling ships package dotfiles; got ${JSON.stringify(drift)}`)
  assert.match(drift[0], /\.runtime-data\.json/)
})

// The other direction, and the dangerous one. The root `.gitignore` excludes
// `*.py[cod]`, which covers `.pyd`; hatchling honours VCS ignores, so a native
// extension built in-tree is NEVER in the wheel. A gate that walks the source
// tree therefore demands a file the snapshot can never hold: it reports drift,
// rebuilds, finds the same drift, and refuses to start the app — the shape the
// ledger records as P11/#732, a gate that no rebuild can satisfy.
test('packageSourceDrift ignores a source file the wheel does not ship', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': 'V = 1\n' },
    ignored: { '_native.pyd': 'MZ binary', '__pycache__/__init__.cpython-312.pyc': 'compiled' },
  })

  assert.deepEqual(packageSourceDrift(fixture), [])
})

test('ensureVendor does not rebuild for a build artefact the wheel never ships', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': 'V = 1\n' },
    ignored: { '_native.pyd': 'MZ binary' },
  })
  const commands = []

  const result = ensureVendor({
    ...fixture,
    python: __filename,
    backend: __dirname,
    buildScript: __filename,
    workspaceRoot: __dirname,
    spawn: (command, args) => {
      commands.push(args)
      return { status: 0 }
    },
  })

  assert.deepEqual(result, { rebuilt: false, staleAllowed: false })
  assert.equal(commands.length, 1, 'only the import check may run — no rebuild')
})

test('packageSourceDrift reports a source file that moved on since the build', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '', 'skills/builtin/md-patch/SKILL.md': '# md-patch\n' },
    sources: { 'skills/builtin/md-patch/SKILL.md': '# md-patch, edited\n' },
  })

  const drift = packageSourceDrift(fixture)

  assert.equal(drift.length, 1)
  assert.match(drift[0], /SKILL\.md: the sources have changed/)
})

test('packageSourceDrift reports a package data file absent from the snapshot', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '', 'skills/builtin/md-patch/SKILL.md': '# md-patch\n' },
    snapshot: { 'skills/builtin/md-patch/SKILL.md': null },
  })

  const drift = packageSourceDrift(fixture)

  assert.equal(drift.length, 1)
  assert.match(drift[0], /SKILL\.md: missing from the snapshot/)
})

test('packageSourceDrift reports a shipped file the sources no longer have', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '', 'legacy.py': 'X = 1\n' },
    sources: { 'legacy.py': null },
  })

  const drift = packageSourceDrift(fixture)

  assert.equal(drift.length, 1)
  assert.match(drift[0], /legacy\.py: shipped by the last build, gone from the sources/)
})

test('packageSourceDrift is silent when every file matches byte for byte', () => {
  const fixture = snapshotFixture({
    shipped: {
      '__init__.py': 'VERSION = 1\n',
      'registry/call_methods.json': '{"a": 1}\n',
      'py.typed': '',
    },
  })

  assert.deepEqual(packageSourceDrift(fixture), [])
})

// The stamp is read from disk and turned into filesystem paths, so a corrupted
// or hand-edited one must not be able to walk out of the tree it describes
// (same rule #1090 applied to caller-supplied paths).
test('packageSourceDrift refuses a stamp whose paths escape their root', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  const escaped = JSON.parse(JSON.stringify(fixture.stampContent))
  escaped.packages[PACKAGE_NAME].source_root = '../../../etc'

  const drift = packageSourceDrift({ ...fixture, stamp: escaped })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /outside the workspace/)
})

test('packageSourceDrift refuses a manifest entry that escapes the package', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  const escaped = JSON.parse(JSON.stringify(fixture.stampContent))
  escaped.packages[PACKAGE_NAME].files = { '../../secrets.json': 'c'.repeat(64) }

  const drift = packageSourceDrift({ ...fixture, stamp: escaped })

  // The real `__init__.py` also shows up, as an addition the doctored manifest
  // no longer records; the assertion here is about the path guard.
  assert.ok(drift.some((line) => /outside the package/.test(line)), JSON.stringify(drift))
})

// A snapshot with no provenance is a snapshot nobody can place. On a user's
// machine there is no source tree to compare against, so the stamp is the only
// thing that can say which engine the installed app carries — and it is also
// the only record of which files each package consists of, so without it there
// is nothing to compare at all.
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
  fs.writeFileSync(
    path.join(target, VENDOR_STAMP_FILENAME),
    JSON.stringify({ schema: VENDOR_STAMP_SCHEMA }),
    'utf8',
  )

  assert.equal(vendorStampDrift({ target }).length, 1)
})

// A snapshot written by an older build script cannot be checked by this gate:
// it has no per-file manifest to compare against. That is not a compatibility
// problem to paper over, it is the definition of a stale snapshot.
test('vendorStampDrift reports a stamp from an older build script', () => {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-oldstamp-'))
  fs.writeFileSync(
    path.join(target, VENDOR_STAMP_FILENAME),
    JSON.stringify({ schema: 1, source_digest: 'a'.repeat(64) }),
    'utf8',
  )

  const drift = vendorStampDrift({ target })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /predates this launcher/)
})

test('vendorStampDrift reports a package entry that carries no file manifest', () => {
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-nomanifest-'))
  fs.writeFileSync(
    path.join(target, VENDOR_STAMP_FILENAME),
    JSON.stringify({
      schema: VENDOR_STAMP_SCHEMA,
      source_digest: 'a'.repeat(64),
      packages: { example_pkg: { source_root: SOURCE_ROOT } },
    }),
    'utf8',
  )

  const drift = vendorStampDrift({ target })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /file manifest/)
})

test('vendorStampDrift accepts the stamp a build writes', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })

  assert.deepEqual(vendorStampDrift(fixture), [])
  assert.equal(readVendorStamp(fixture).schema, VENDOR_STAMP_SCHEMA)
})

// `result.status` alone cannot tell a failed run from a run that never
// happened: a missing or unexecutable vendored interpreter — the most likely
// state on a fresh checkout — arrives as `status: null` with the reason in
// `result.error`. Reading only the status printed "exit code null", which names
// neither the file nor the problem.
test('vendoredImportDrift names an interpreter that could not be run', () => {
  const drift = vendoredImportDrift({
    python: __filename,
    target: __dirname,
    modules: ['graph_agent'],
    spawn: () => ({
      status: null,
      signal: null,
      error: Object.assign(new Error('spawnSync python.exe ENOENT'), { code: 'ENOENT' }),
    }),
  })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /ENOENT/)
  assert.match(drift[0], new RegExp(path.basename(__filename).replace('.', '\\.')))
})

test('vendoredImportDrift passes on what the interpreter said', () => {
  const drift = vendoredImportDrift({
    python: __filename,
    target: __dirname,
    modules: ['graph_agent'],
    spawn: () => ({ status: 1, stderr: 'Traceback\nModuleNotFoundError: No module named graph_agent\n' }),
  })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /ModuleNotFoundError/)
})

test('vendoredImportDrift reports a missing interpreter without spawning', () => {
  let spawned = false
  const drift = vendoredImportDrift({
    python: path.join(__dirname, 'no-such-python'),
    target: __dirname,
    modules: ['graph_agent'],
    spawn: () => {
      spawned = true
      return { status: 0 }
    },
  })

  assert.equal(spawned, false)
  assert.match(drift[0], /interpreter is missing/)
})

// The modules to import come from the stamp, i.e. from what the wheels shipped.
// A hand-written list went stale in #706 (the gateway refactor removed the
// module it named) and left a gate no rebuild could satisfy (#732).
test('vendoredImportDrift imports the packages the stamp records', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  const calls = []

  vendoredImportDrift({
    ...fixture,
    python: __filename,
    spawn: (command, args) => {
      calls.push(args)
      return { status: 0 }
    },
  })

  assert.deepEqual(calls, [['-c', `import ${PACKAGE_NAME}`]])
})

test('describeSpawnFailure distinguishes a signal from an exit code', () => {
  assert.match(describeSpawnFailure({ status: null, signal: 'SIGKILL' }, 'python'), /SIGKILL/)
  assert.match(describeSpawnFailure({ status: 2, signal: null }, 'python'), /exit code 2/)
})

// The branch under test is ensureVendor's own: imports report fine, so no
// rebuild. Running a real interpreter to establish that would tie this to a
// provisioned Python — the vendored runtime is a downloaded artefact absent
// from fresh checkouts, and the workspace venv only exists after `uv sync`.
test('ensureVendor skips rebuild when the snapshot is current', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })

  const result = ensureVendor({
    ...fixture,
    python: __filename,
    backend: __dirname,
    spawn: () => ({ status: 0 }),
  })

  assert.deepEqual(result, { rebuilt: false, staleAllowed: false })
})

test('ensureVendor rebuilds when the vendored interpreter cannot import', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  const calls = []

  const result = ensureVendor({
    ...fixture,
    python: __filename,
    backend: __dirname,
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

test('ensureVendor rebuilds a snapshot whose data files drifted even though imports work', () => {
  const fixture = snapshotFixture({
    shipped: { 'table.json': '{"a": 2}\n' },
    snapshot: { 'table.json': '{"a": 1}\n' },
  })
  let rebuilt = false

  const result = ensureVendor({
    ...fixture,
    python: __filename,
    backend: __dirname,
    buildScript: __filename,
    workspaceRoot: __dirname,
    // The build is what a real rebuild does: it makes the snapshot match.
    spawn: (command, args) => {
      if (args && args[0] === __filename) {
        rebuilt = true
        fs.copyFileSync(
          path.join(fixture.sourceRoot, 'table.json'),
          path.join(fixture.vendorRoot, 'table.json'),
        )
      }
      return { status: 0 }
    },
  })

  assert.equal(rebuilt, true, 'a data-file-only drift must still trigger the rebuild')
  assert.deepEqual(result, { rebuilt: true, staleAllowed: false })
})

test('ensureVendor rebuilds a snapshot that carries no stamp at all', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  fs.rmSync(path.join(fixture.target, VENDOR_STAMP_FILENAME))
  const seen = []

  assert.throws(
    () => ensureVendor({
      ...fixture,
      python: __filename,
      backend: __dirname,
      buildScript: __filename,
      workspaceRoot: __dirname,
      env: { PATH: 'base' },
      // A rebuild that writes no stamp leaves the snapshot unplaceable, so the
      // gate must refuse rather than start the app on it.
      spawn: (command, args) => {
        seen.push(args)
        return { status: 0 }
      },
    }),
    /still stale|provenance/,
  )
  assert.ok(seen.length > 0)
})

// Comparing every file the wheel ships means editing a package's own
// CHANGELOG.md now costs a full clean rebuild. Booting the app against a
// knowingly stale snapshot is a legitimate thing to want (reproducing a bug
// against the snapshot that has it), so there is one way to say so — named
// after what it permits, and never silent.
test(`${ALLOW_STALE_SNAPSHOT_ENV} boots a stale snapshot without rebuilding, loudly`, () => {
  const fixture = snapshotFixture({
    shipped: { 'table.json': '{"a": 2}\n' },
    snapshot: { 'table.json': '{"a": 1}\n' },
  })
  const warnings = []

  const result = ensureVendor({
    ...fixture,
    python: __filename,
    backend: __dirname,
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

// Bare presence would read `...=0` as "allow", the opposite of what anyone
// typing that intends. A dangerous flag has to fail closed.
test('the escape hatch only opens for an affirmative value', () => {
  for (const value of ['1', 'true', 'TRUE', 'yes', ' 1 ']) {
    assert.equal(staleSnapshotAllowed({ [ALLOW_STALE_SNAPSHOT_ENV]: value }), true, value)
  }
  for (const value of ['0', 'false', 'no', '', 'please']) {
    assert.equal(staleSnapshotAllowed({ [ALLOW_STALE_SNAPSHOT_ENV]: value }), false, value)
  }
  assert.equal(staleSnapshotAllowed({}), false)
})

test('an unset escape hatch does not let a stale snapshot through', () => {
  const fixture = snapshotFixture({
    shipped: { 'table.json': '{"a": 2}\n' },
    snapshot: { 'table.json': '{"a": 1}\n' },
  })

  assert.throws(
    () => ensureVendor({
      ...fixture,
      python: __filename,
      backend: __dirname,
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

test('snapshotDrift stops at a missing stamp instead of guessing a file set', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })
  fs.rmSync(path.join(fixture.target, VENDOR_STAMP_FILENAME))

  const drift = snapshotDrift({ ...fixture, python: __filename, spawn: () => ({ status: 0 }) })

  assert.equal(drift.length, 1)
  assert.match(drift[0], /provenance/)
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

test('rebuildVendor names why the interpreter could not be run', () => {
  assert.throws(
    () => rebuildVendor({
      python: '/missing/python',
      buildScript: __filename,
      workspaceRoot: __dirname,
      env: { PATH: 'base' },
      spawn: () => ({
        status: null,
        signal: null,
        error: Object.assign(new Error('spawnSync /missing/python ENOENT'), { code: 'ENOENT' }),
      }),
    }),
    /ENOENT.*\/missing\/python/s,
  )
})

// ── RED (new finding: pure additions are invisible) ─────────────────────────
function gitStub(files) {
  return () => ({ status: 0, stdout: files.join(NUL) })
}

test('RED A: a newly added module that no wheel has shipped yet is drift', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': 'V = 1\n' },
    added: { 'probe.py': 'X = 1\n' },
  })

  const drift = packageSourceDrift({ ...fixture, runGit: gitStub(['__init__.py', 'probe.py']) })

  assert.equal(drift.length, 1, `got ${JSON.stringify(drift)}`)
  assert.match(drift[0], /probe\.py: in the sources, not in the snapshot/)
})

test('RED B: a newly added builtin skill directory is drift', () => {
  const fixture = snapshotFixture({
    shipped: { '__init__.py': '' },
    added: { 'skills/builtin/new-skill/SKILL.md': '# new\n' },
  })

  const drift = packageSourceDrift({
    ...fixture,
    runGit: gitStub(['__init__.py', 'skills/builtin/new-skill/SKILL.md']),
  })

  assert.equal(drift.length, 1, `got ${JSON.stringify(drift)}`)
  assert.match(drift[0], /new-skill\/SKILL\.md: in the sources, not in the snapshot/)
})

test('RED C: a snapshot cannot be vouched for when git will not answer', () => {
  const fixture = snapshotFixture({ shipped: { '__init__.py': '' } })

  const drift = packageSourceDrift({
    ...fixture,
    runGit: () => ({ status: 128, stderr: 'fatal: not a git repository\n' }),
  })

  assert.equal(drift.length, 1, `got ${JSON.stringify(drift)}`)
  assert.match(drift[0], /not a git repository/)
})

// An empty manifest turns `sourceAdditions` into "print everything git lists",
// which is what these two tests need: the real command, the real ignore rules.
const REPO = path.resolve(__dirname, '../../../..')

test('sourceAdditions asks git, so the repo ignore files are the rules that apply', () => {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-vendor-gitrepo-'))
  const sourceRoot = path.join(repo, 'src', 'example_pkg')
  fs.mkdirSync(path.join(sourceRoot, '__pycache__'), { recursive: true })
  fs.writeFileSync(path.join(repo, '.gitignore'), '*.py[cod]\n__pycache__/\n', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, '__init__.py'), 'V = 1\n', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, '.runtime-data.json'), '{}\n', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, '_native.pyd'), 'MZ', 'utf8')
  fs.writeFileSync(path.join(sourceRoot, '__pycache__', 'x.cpython-312.pyc'), 'x', 'utf8')
  require('node:child_process').spawnSync('git', ['init', '-q', repo], { encoding: 'utf8' })

  const listed = sourceAdditions('example_pkg', sourceRoot, {}).join('\n')

  // Shipped by hatchling and listed by git — including the dotfile.
  assert.match(listed, /example_pkg\/__init__\.py/)
  assert.match(listed, /example_pkg\/\.runtime-data\.json/)
  // Ignored by the repo, therefore never in a wheel: demanding them would be a
  // drift no rebuild could clear.
  assert.doesNotMatch(listed, /_native\.pyd/)
  assert.doesNotMatch(listed, /__pycache__/)
})

// The precondition of the check above, asserted on THIS repo rather than on a
// fixture: hatchling ships the git-listed set minus `__pycache__`/`*.py[cod]`,
// so the git set may only be a SUBSET of what the wheel carries. It stops being
// one the moment a package's sources hold a git-listed file hatchling drops —
// which is what this fails on, in CI, at the change that introduces it.
test('git lists nothing inside the SDK packages that a wheel would drop', () => {
  for (const [packageName, root] of [
    ['graph_agent', path.join(REPO, 'packages', 'graph-agent', 'src', 'graph_agent')],
    ['graph_agent_gateway', path.join(REPO, 'packages', 'graph-agent-gateway', 'src', 'graph_agent_gateway')],
  ]) {
    const listed = sourceAdditions(packageName, root, {})
    assert.ok(listed.length > 50, `${packageName}: git listed ${listed.length} files`)
    const dropped = listed.filter((line) => /__pycache__|\.py[cod]: /.test(line))
    assert.deepEqual(dropped, [], `${packageName}: git lists files hatchling would not ship`)
  }
})

// The two non-Python files this whole gate exists for have to be in that set,
// or the addition check would not notice a sibling arriving next to them.
test('the package data files the app reads at runtime are git-listed', () => {
  const engine = sourceAdditions('graph_agent', path.join(REPO, 'packages', 'graph-agent', 'src', 'graph_agent'), {})
  const gateway = sourceAdditions('graph_agent_gateway', path.join(REPO, 'packages', 'graph-agent-gateway', 'src', 'graph_agent_gateway'), {})

  assert.ok(engine.some((line) => line.startsWith('graph_agent/skills/builtin/md-patch/SKILL.md:')), 'md-patch SKILL.md')
  assert.ok(gateway.some((line) => line.startsWith('graph_agent_gateway/registry/call_methods.json:')), 'call_methods.json')
})
