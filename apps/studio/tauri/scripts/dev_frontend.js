#!/usr/bin/env node
/* eslint-env node */

const path = require('node:path')
const fs = require('node:fs')
const { spawn } = require('node:child_process')

const TAURI_DIR = path.resolve(__dirname, '..')
const STUDIO_DIR = path.resolve(TAURI_DIR, '..')
const FRONTEND_DIR = path.join(STUDIO_DIR, 'frontend')

function npmExecutable(platform = process.platform) {
  return platform === 'win32' ? 'npm.cmd' : 'npm'
}

function pnpmExecutable(platform = process.platform) {
  return platform === 'win32' ? 'pnpm.cmd' : 'pnpm'
}

function pathEnvKey(env = process.env) {
  return Object.keys(env).find((key) => key.toLowerCase() === 'path') ?? 'PATH'
}

function executableOnPath(executable, env = process.env) {
  const key = pathEnvKey(env)
  const entries = (env[key] ?? '').split(path.delimiter).filter(Boolean)
  for (const entry of entries) {
    const candidate = path.join(entry, executable)
    if (fs.existsSync(candidate)) return candidate
  }
  return null
}

function frontendPackageManagerExecutable(platform = process.platform, env = process.env) {
  return executableOnPath(npmExecutable(platform), env)
    ?? executableOnPath(pnpmExecutable(platform), env)
    ?? npmExecutable(platform)
}

function windowsCmdArg(value) {
  return /[\s&()^|<>"]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

function frontendDevEnv(env = process.env) {
  return {
    ...env,
    VITE_STUDIO_API_BASE_URL: '/api',
  }
}

function frontendDevArgs() {
  return ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort']
}

function frontendDevCommand(platform = process.platform, env = process.env) {
  const packageManager = frontendPackageManagerExecutable(platform, env)
  if (platform === 'win32') {
    return {
      command: env.ComSpec || 'cmd.exe',
      args: ['/d', '/s', '/c', [windowsCmdArg(packageManager), ...frontendDevArgs()].join(' ')],
    }
  }
  return {
    command: packageManager,
    args: frontendDevArgs(),
  }
}

function startFrontendDev({
  cwd = FRONTEND_DIR,
  env = process.env,
  spawnImpl = spawn,
  platform = process.platform,
} = {}) {
  const { command, args } = frontendDevCommand(platform, env)
  const child = spawnImpl(command, args, {
    cwd,
    env: frontendDevEnv(env),
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  })
  child.stdout?.pipe(process.stdout)
  child.stderr?.pipe(process.stderr)
  return child
}

if (require.main === module) {
  const child = startFrontendDev()
  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })
}

module.exports = {
  FRONTEND_DIR,
  frontendDevArgs,
  frontendDevCommand,
  frontendDevEnv,
  frontendPackageManagerExecutable,
  npmExecutable,
  pnpmExecutable,
  startFrontendDev,
}
