/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  FRONTEND_DIR,
  frontendDevArgs,
  frontendDevCommand,
  frontendDevEnv,
  frontendPackageManagerExecutable,
  npmExecutable,
  startFrontendDev,
} = require('./dev_frontend')

test('frontendDevEnv keeps /api as a literal browser path', () => {
  const env = frontendDevEnv({ PATH: 'base', VITE_STUDIO_API_BASE_URL: 'stale' })

  assert.equal(env.PATH, 'base')
  assert.equal(env.VITE_STUDIO_API_BASE_URL, '/api')
})

test('npmExecutable uses npm.cmd on Windows', () => {
  assert.equal(npmExecutable('win32'), 'npm.cmd')
  assert.equal(npmExecutable('linux'), 'npm')
})

test('frontendPackageManagerExecutable falls back to pnpm when npm is unavailable', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-dev-frontend-'))
  const pnpmPath = path.join(tempDir, 'pnpm.cmd')
  fs.writeFileSync(pnpmPath, '@echo off\n')

  assert.equal(frontendPackageManagerExecutable('win32', { PATH: tempDir }), pnpmPath)
})

test('startFrontendDev launches vite from the frontend directory', () => {
  const calls = []
  const child = { on: () => child }
  const env = { PATH: 'base', ComSpec: 'cmd.exe' }

  const result = startFrontendDev({
    env,
    spawnImpl: (command, args, options) => {
      calls.push({ command, args, options })
      return child
    },
    platform: 'win32',
  })

  assert.equal(result, child)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].command, 'cmd.exe')
  assert.deepEqual(calls[0].args, ['/d', '/s', '/c', `npm.cmd ${frontendDevArgs().join(' ')}`])
  assert.equal(calls[0].options.cwd, FRONTEND_DIR)
  assert.equal(calls[0].options.env.VITE_STUDIO_API_BASE_URL, '/api')
  assert.deepEqual(calls[0].options.stdio, ['ignore', 'pipe', 'pipe'])
  assert.equal(calls[0].options.shell, false)
})

test('frontendDevCommand keeps non-Windows launches direct', () => {
  assert.deepEqual(frontendDevCommand('linux', { PATH: '' }), {
    command: 'npm',
    args: frontendDevArgs(),
  })
})
