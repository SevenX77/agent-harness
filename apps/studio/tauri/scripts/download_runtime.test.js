/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  REQUIRED_TARGETS,
  artifactFor,
  hostTargetTriple,
  loadLock,
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
