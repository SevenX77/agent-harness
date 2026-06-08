/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const { copyBackend } = require('./sync_resources')

const tauriDir = path.resolve(__dirname, '..')
const vendorBackend = path.join(tauriDir, 'vendor', 'backend')

test('copyBackend syncs only existing backend bundle files', () => {
  copyBackend()

  assert.equal(fs.existsSync(path.join(vendorBackend, 'app')), true)
  assert.equal(fs.existsSync(path.join(vendorBackend, 'pyproject.toml')), true)
  assert.equal(fs.existsSync(path.join(vendorBackend, 'requirements.txt')), false)
})
