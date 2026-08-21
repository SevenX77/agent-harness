/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  DEFAULT_DOWNLOADS_DIR,
  DEFAULT_VENDOR_DIR,
  REQUIRED_TARGETS,
  artifactFor,
  extractWithTar,
  hostTargetTriple,
  loadLock,
  tarExtractCommand,
  validateLock,
  verifySha256,
} = require('./download_runtime')

const lockPath = path.resolve(__dirname, '..', 'python-runtime.lock.json')

test('hostTargetTriple maps the five supported desktop targets', () => {
  assert.equal(hostTargetTriple('darwin', 'x64'), 'x86_64-apple-darwin')
  assert.equal(hostTargetTriple('darwin', 'arm64'), 'aarch64-apple-darwin')
  assert.equal(hostTargetTriple('linux', 'x64'), 'x86_64-unknown-linux-gnu')
  assert.equal(hostTargetTriple('linux', 'arm64'), 'aarch64-unknown-linux-gnu')
  assert.equal(hostTargetTriple('win32', 'x64'), 'x86_64-pc-windows-msvc')
})

test('lock file pins all required artifacts with fixed hashes', () => {
  const lock = loadLock(lockPath)
  validateLock(lock)
  assert.equal(lock.tag, '20260414')
  assert.equal(lock.python_version, '3.12.13')
  assert.deepEqual(Object.keys(lock.artifacts).sort(), REQUIRED_TARGETS.toSorted())
  assert.equal(artifactFor(lock, 'x86_64-pc-windows-msvc').variant, 'install_only')
  assert.equal(artifactFor(lock, 'x86_64-unknown-linux-gnu').variant, 'install_only_stripped')
})

test('verifySha256 fails closed on mismatched digest', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-sha-'))
  const file = path.join(dir, 'payload.txt')
  fs.writeFileSync(file, 'payload')
  assert.throws(
    () => verifySha256(file, '0'.repeat(64)),
    /SHA256 mismatch/,
  )
  fs.rmSync(dir, { recursive: true, force: true })
})

// `tar` is not one program. On Windows it is whichever of two comes first on
// PATH — System32's bsdtar or Git's GNU tar — and they disagree about what a
// colon means: GNU tar reads `D:\vendor\downloads\cpython.tar.gz` as the
// rsh-style `host:path` and tries to reach a machine named `D`, failing with
// "Cannot connect to D: resolve failed". Measured on the Windows 11 dev box,
// GNU tar 1.35 vs bsdtar 3.8.4: every RELATIVE form (`sub`, `../dest`,
// `..\dest`) is accepted by both, and only the drive-letter absolute form
// splits them. So the invariant worth pinning is that no absolute path ever
// reaches tar — not "which tar do we have".
test('tar is never handed an absolute path, so both tars read it the same way', () => {
  const { cwd, args } = tarExtractCommand(
    path.join('vendor', 'downloads', 'cpython-3.12.13.tar.gz'),
    path.join('vendor', 'downloads', '.python-runtime-abc'),
  )

  assert.equal(cwd, path.join('vendor', 'downloads'),
    'tar must run from the archive\'s own directory — that is what lets both ends be relative')

  for (const arg of args) {
    assert.ok(!path.isAbsolute(arg),
      `tar argument "${arg}" is absolute; on Windows that carries a drive letter and GNU tar reads it as a hostname`)
    assert.ok(!/^[A-Za-z]:/.test(arg),
      `tar argument "${arg}" starts with a drive letter, which GNU tar resolves as a remote host`)
    assert.ok(!arg.includes('\\'),
      `tar argument "${arg}" contains a backslash, which GNU tar reads as an escape character`)
  }
})

// A single `..\` survives GNU tar; a deeper one does not, so the shallow case
// cannot stand in for this. Measured when the download cache moved out of
// `vendor/`: `-C ..\..\vendor\python\.python-runtime-XXX` failed with "Cannot
// open: No such file or directory" against a directory that existed.
test('a destination several levels away is still spelled the way tar reads it', () => {
  const { args } = tarExtractCommand(
    path.join('a', 'b', 'cache', 'downloads', 'cpython.tar.gz'),
    path.join('a', 'b', 'vendor', 'python', '.python-runtime-XXX'),
  )

  assert.deepEqual(
    args,
    ['-xf', 'cpython.tar.gz', '-C', '../../vendor/python/.python-runtime-XXX'],
  )
})

// `tauri.conf.json` ships `vendor/**/*`, so `vendor/` IS the payload: whatever
// is in it goes to every user. The download cache used to live at
// `vendor/downloads/`, which put the .tar.gz the runtime was extracted FROM
// next to the runtime itself — 48.9 MB of it in a 154.7 MB installer, a third
// of the download, for files nothing reads after the build (ledger D4).
//
// Keeping the cache outside `vendor/` is what makes the simple glob correct.
// The alternative — listing vendor's subdirectories one by one in
// `bundle.resources` — leaves the trap in place and fails the other way round:
// a new payload directory nobody adds to the list silently does NOT ship, and
// a missing payload is worse than a fat one.
test('the download cache is not inside the directory that gets bundled', () => {
  const vendor = path.resolve(DEFAULT_VENDOR_DIR)
  const downloads = path.resolve(DEFAULT_DOWNLOADS_DIR)

  assert.ok(
    !downloads.startsWith(vendor + path.sep) && downloads !== vendor,
    `the download cache (${downloads}) is inside the bundled payload (${vendor}), so every ` +
      'archive it caches ships to users inside the installer',
  )
})

test('both vendoring scripts cache into the same place', () => {
  // One cache, one definition. ensure_ah_vendor.js already takes `download`
  // and `verifySha256` from this module; taking the cache location from
  // anywhere else is how the two drifted apart in the first place.
  const ahVendor = require('./ensure_ah_vendor')
  assert.equal(
    path.resolve(ahVendor.DEFAULT_DOWNLOADS_DIR),
    path.resolve(DEFAULT_DOWNLOADS_DIR),
  )
})

test('extractWithTar unpacks an archive whichever tar is on PATH', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-extract-'))
  const downloads = path.join(dir, 'downloads')
  const source = path.join(dir, 'source')
  fs.mkdirSync(downloads)
  fs.mkdirSync(source)
  fs.writeFileSync(path.join(source, 'payload.txt'), 'vendored\n')

  // Build the fixture the same colon-free way, so making the archive cannot
  // itself trip the bug the test is about.
  const build = require('node:child_process').spawnSync(
    'tar', ['-czf', path.join('..', 'downloads', 'fixture.tar.gz'), 'payload.txt'],
    { cwd: source },
  )
  assert.equal(build.status, 0, `could not build the fixture archive: ${build.stderr}`)

  const into = path.join(downloads, 'unpacked')
  fs.mkdirSync(into)
  extractWithTar(path.join(downloads, 'fixture.tar.gz'), into)

  assert.equal(fs.readFileSync(path.join(into, 'payload.txt'), 'utf8'), 'vendored\n')
  fs.rmSync(dir, { recursive: true, force: true })
})
