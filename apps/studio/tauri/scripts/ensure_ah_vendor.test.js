/* eslint-env node */

const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  AH_BINARIES,
  DEFAULT_LOCK_PATH,
  ensureAhVendor,
  findBinaryDir,
  loadAhLock,
  main,
  validateAhLock,
  vendoredAhVersion,
} = require('./ensure_ah_vendor')

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ah-vendor-test-'))
}

function writeLock(dir, lock) {
  const lockPath = path.join(dir, 'ah-vendor.lock.json')
  fs.writeFileSync(lockPath, JSON.stringify(lock))
  return lockPath
}

function lockFor(content, version = '1.14.3') {
  return {
    version,
    artifact: {
      filename: 'ah-test.tar.xz',
      url: `https://example.invalid/releases/download/v${version}/ah-test.tar.xz`,
      sha256: crypto.createHash('sha256').update(content).digest('hex'),
    },
  }
}

test('the checked-in lock file is valid', () => {
  const lock = loadAhLock(DEFAULT_LOCK_PATH)
  assert.match(lock.version, /^\d+\.\d+\.\d+$/)
})

// The decision doc requires vendored >= AH_VERSION_MIN (kept by hand when the
// lock is bumped); this test is the machine check for that invariant.
test('the pinned version satisfies AH_VERSION_MIN in lib.rs', () => {
  const librs = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'lib.rs'), 'utf8')
  const match = librs.match(/const AH_VERSION_MIN: &str = "(\d+)\.(\d+)\.(\d+)"/)
  assert.ok(match, 'AH_VERSION_MIN not found in lib.rs')
  const toNum = (major, minor, patch) => Number(major) * 1_000_000 + Number(minor) * 1_000 + Number(patch)
  const min = toNum(match[1], match[2], match[3])
  const pinned = toNum(...loadAhLock(DEFAULT_LOCK_PATH).version.split('.'))
  assert.ok(pinned >= min, `pinned ah ${pinned} is below AH_VERSION_MIN ${min}`)
})

test('validateAhLock rejects a malformed sha256 and an unpinned URL', () => {
  const good = lockFor('x')
  assert.throws(
    () => validateAhLock({ ...good, artifact: { ...good.artifact, sha256: 'not-hex' } }),
    /sha256/,
  )
  assert.throws(
    () => validateAhLock({ ...good, artifact: { ...good.artifact, url: 'https://example.invalid/latest.tar.xz' } }),
    /pin version/,
  )
  assert.throws(() => validateAhLock({ ...good, version: 'v1.14.3' }), /Invalid version/)
})

test('vendoredAhVersion requires VERSION plus every binary', () => {
  const dir = tempDir()
  assert.equal(vendoredAhVersion(dir), null)
  fs.writeFileSync(path.join(dir, 'VERSION'), '1.14.3\n')
  assert.equal(vendoredAhVersion(dir), null, 'VERSION alone must not count as vendored')
  for (const binary of AH_BINARIES) fs.writeFileSync(path.join(dir, binary), 'bin')
  assert.equal(vendoredAhVersion(dir), '1.14.3')
})

test('ensureAhVendor skips the network entirely when already vendored', async () => {
  const dir = tempDir()
  const lockPath = writeLock(dir, lockFor('irrelevant'))
  const vendorAhDir = path.join(dir, 'vendor', 'ah')
  fs.mkdirSync(vendorAhDir, { recursive: true })
  for (const binary of AH_BINARIES) fs.writeFileSync(path.join(vendorAhDir, binary), 'bin')
  fs.writeFileSync(path.join(vendorAhDir, 'VERSION'), '1.14.3\n')
  const result = await ensureAhVendor({
    lockPath,
    vendorAhDir,
    downloadsDir: path.join(dir, 'downloads'),
    downloadFile: () => {
      throw new Error('network must not be touched')
    },
  })
  assert.equal(result, 'up-to-date')
})

test('ensureAhVendor downloads, verifies, extracts, and writes VERSION last', async () => {
  const dir = tempDir()
  const archiveContent = 'fake-archive-bytes'
  const lockPath = writeLock(dir, lockFor(archiveContent))
  const vendorAhDir = path.join(dir, 'vendor', 'ah')
  const result = await ensureAhVendor({
    lockPath,
    vendorAhDir,
    downloadsDir: path.join(dir, 'downloads'),
    downloadFile: (url, destination) => fs.writeFileSync(destination, archiveContent),
    extract: (archivePath, intoDir) => {
      // Simulate the cargo-dist layout: binaries nested one directory deep.
      const nested = path.join(intoDir, 'ah-x86_64-unknown-linux-gnu')
      fs.mkdirSync(nested, { recursive: true })
      for (const binary of AH_BINARIES) fs.writeFileSync(path.join(nested, binary), `#!${binary}`)
    },
  })
  assert.equal(result, 'installed')
  assert.equal(vendoredAhVersion(vendorAhDir), '1.14.3')
  for (const binary of AH_BINARIES) {
    assert.equal(fs.readFileSync(path.join(vendorAhDir, binary), 'utf8'), `#!${binary}`)
  }
})

test('a sha256 mismatch rejects the download and leaves no snapshot', async () => {
  const dir = tempDir()
  const lockPath = writeLock(dir, lockFor('expected-bytes'))
  const vendorAhDir = path.join(dir, 'vendor', 'ah')
  await assert.rejects(
    ensureAhVendor({
      lockPath,
      vendorAhDir,
      downloadsDir: path.join(dir, 'downloads'),
      downloadFile: (url, destination) => fs.writeFileSync(destination, 'tampered-bytes'),
      extract: () => {
        throw new Error('must not reach extraction')
      },
    }),
    /SHA256 mismatch/,
  )
  assert.equal(vendoredAhVersion(vendorAhDir), null)
})

test('an archive without both binaries fails and removes the snapshot dir', async () => {
  const dir = tempDir()
  const archiveContent = 'fake-archive-bytes'
  const lockPath = writeLock(dir, lockFor(archiveContent))
  const vendorAhDir = path.join(dir, 'vendor', 'ah')
  await assert.rejects(
    ensureAhVendor({
      lockPath,
      vendorAhDir,
      downloadsDir: path.join(dir, 'downloads'),
      downloadFile: (url, destination) => fs.writeFileSync(destination, archiveContent),
      extract: (archivePath, intoDir) => {
        fs.writeFileSync(path.join(intoDir, 'ah'), 'only-one-binary')
      },
    }),
    /does not contain/,
  )
  assert.equal(fs.existsSync(vendorAhDir), false)
})

test('findBinaryDir locates the one directory holding all binaries', () => {
  const dir = tempDir()
  const nested = path.join(dir, 'a', 'b')
  fs.mkdirSync(nested, { recursive: true })
  for (const binary of AH_BINARIES) fs.writeFileSync(path.join(nested, binary), 'bin')
  assert.equal(findBinaryDir(dir), nested)
})

test('main is lenient by default and strict with --strict', async () => {
  const failing = () => Promise.reject(new Error('boom'))
  assert.equal(await main([], failing), 0)
  assert.equal(await main(['--strict'], failing), 1)
})
