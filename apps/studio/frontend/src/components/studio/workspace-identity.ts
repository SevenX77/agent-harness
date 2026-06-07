const LOCAL_WORKSPACE_SELECTION_PREFIX = 'local-workspace:'

export function createLocalWorkspaceSelection(skillId: string, workspaceRoot: string): string {
  return `${LOCAL_WORKSPACE_SELECTION_PREFIX}${encodeURIComponent(skillId)}:${encodeURIComponent(workspaceRoot)}`
}

export function resolveWorkspaceIdentity(selection: string | null): { skillId: string | null, workspaceRoot: string | null } {
  if (!selection) {
    return { skillId: null, workspaceRoot: null }
  }

  const explicit = parseLocalWorkspaceSelection(selection)
  if (explicit) {
    return explicit
  }

  const workspaceRoot = selection.startsWith('local:') ? selection.slice('local:'.length) : selection
  if (!isAbsolutePath(workspaceRoot)) {
    return { skillId: selection, workspaceRoot: null }
  }
  return {
    skillId: skillIdFromWorkspaceRoot(workspaceRoot),
    workspaceRoot,
  }
}

export function isAbsolutePath(value: string): boolean {
  return value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value)
}

function parseLocalWorkspaceSelection(selection: string): { skillId: string; workspaceRoot: string } | null {
  if (!selection.startsWith(LOCAL_WORKSPACE_SELECTION_PREFIX)) {
    return null
  }
  const payload = selection.slice(LOCAL_WORKSPACE_SELECTION_PREFIX.length)
  const separator = payload.indexOf(':')
  if (separator <= 0) {
    return null
  }
  try {
    const skillId = decodeURIComponent(payload.slice(0, separator))
    const workspaceRoot = decodeURIComponent(payload.slice(separator + 1))
    return skillId && workspaceRoot ? { skillId, workspaceRoot } : null
  } catch {
    return null
  }
}

function skillIdFromWorkspaceRoot(path: string): string {
  const name = path.split(/[\\/]/).filter(Boolean).pop() ?? 'imported-skill'
  const normalized = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const withLetter = /^[a-z]/.test(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'imported-skill'
}
