import { getRuntimeConfig } from '../config/runtime'

export function joinDirectoryPath(parentDirectory: string, folderName: string) {
  const separator = parentDirectory.includes('\\') && !parentDirectory.includes('/') ? '\\' : '/'
  return `${parentDirectory.replace(/[\\/]+$/, '')}${separator}${folderName}`
}

export function runtimeDefaultSkillsDirectory(): string | null {
  const config = getRuntimeConfig()
  const configDir = config?.configDir?.trim()
  if (configDir) {
    return joinDirectoryPath(configDir, 'Skills')
  }
  const resourceDir = config?.resourceDir?.trim()
  return resourceDir ? joinDirectoryPath(joinDirectoryPath(resourceDir, 'config'), 'Skills') : null
}

export function effectiveDefaultSkillsDirectory(customDirectory?: string | null): string | null {
  const trimmed = customDirectory?.trim()
  return trimmed || runtimeDefaultSkillsDirectory()
}
