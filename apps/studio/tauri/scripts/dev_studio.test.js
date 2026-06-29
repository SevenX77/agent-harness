/* eslint-env node */

const assert = require('node:assert/strict')
const test = require('node:test')

const {
  DEFAULT_SIDECAR_PORT,
  TAURI_DIR,
  parsePortArg,
  startStudioDev,
  studioDevArgs,
  studioDevEnv,
} = require('./dev_studio')

test('parsePortArg defaults to the fixed studio dev sidecar port', () => {
  assert.equal(parsePortArg([], {}), DEFAULT_SIDECAR_PORT)
})

test('parsePortArg honors explicit CLI port before inherited env', () => {
  assert.equal(parsePortArg(['--port', '8901'], { STUDIO_SIDECAR_PORT: '7777' }), '8901')
  assert.equal(parsePortArg(['--port=8902'], { STUDIO_SIDECAR_PORT: '7777' }), '8902')
})

test('studioDevEnv pins the sidecar port for both Tauri and Vite', () => {
  const env = studioDevEnv({ env: { PATH: 'base' }, port: '8788' })

  assert.equal(env.PATH, 'base')
  assert.equal(env.STUDIO_SIDECAR_PORT, '8788')
})

test('startStudioDev launches cargo tauri dev from the Tauri directory', () => {
  const calls = []
  const child = { on: () => child }

  const result = startStudioDev({
    env: { PATH: 'base' },
    args: ['--port', '8789'],
    spawnImpl: (command, args, options) => {
      calls.push({ command, args, options })
      return child
    },
  })

  assert.equal(result, child)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].command, 'cargo')
  assert.deepEqual(calls[0].args, studioDevArgs())
  assert.equal(calls[0].options.cwd, TAURI_DIR)
  assert.equal(calls[0].options.env.STUDIO_SIDECAR_PORT, '8789')
  assert.equal(calls[0].options.stdio, 'inherit')
  assert.equal(calls[0].options.shell, false)
})
