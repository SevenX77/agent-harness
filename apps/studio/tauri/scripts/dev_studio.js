#!/usr/bin/env node
/* eslint-env node */

const path = require('node:path')
const { spawn } = require('node:child_process')

const TAURI_DIR = path.resolve(__dirname, '..')
const DEFAULT_SIDECAR_PORT = '8787'

function parsePortArg(args = process.argv.slice(2), env = process.env) {
  const explicit = args.find((arg) => arg.startsWith('--port='))
  if (explicit) return explicit.slice('--port='.length)
  const index = args.indexOf('--port')
  if (index >= 0 && args[index + 1]) return args[index + 1]
  return env.STUDIO_SIDECAR_PORT || DEFAULT_SIDECAR_PORT
}

function studioDevEnv({ env = process.env, port = parsePortArg([], env) } = {}) {
  return {
    ...env,
    STUDIO_SIDECAR_PORT: String(port),
  }
}

function studioDevArgs() {
  return ['tauri', 'dev']
}

function startStudioDev({
  cwd = TAURI_DIR,
  env = process.env,
  args = process.argv.slice(2),
  spawnImpl = spawn,
} = {}) {
  const port = parsePortArg(args, env)
  const child = spawnImpl('cargo', studioDevArgs(), {
    cwd,
    env: studioDevEnv({ env, port }),
    stdio: 'inherit',
    shell: false,
  })
  return child
}

if (require.main === module) {
  const child = startStudioDev()
  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })
}

module.exports = {
  DEFAULT_SIDECAR_PORT,
  TAURI_DIR,
  parsePortArg,
  startStudioDev,
  studioDevArgs,
  studioDevEnv,
}
