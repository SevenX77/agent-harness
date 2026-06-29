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

export function topLevelSkillIdFromWorkspaceRoot(workspaceRoot: string | null | undefined): string | null {
  if (!workspaceRoot || !isAbsolutePath(workspaceRoot)) return null
  const parts = workspaceRoot.split(/[\\/]+/).filter(Boolean)
  const skillsIndex = parts.lastIndexOf('skills')
  if (skillsIndex < 0 || skillsIndex + 1 >= parts.length) return null
  return normalizeSkillIdSegment(parts[skillsIndex + 1]) || null
}

export function isAbsolutePath(value: string): boolean {
  return value.startsWith('/') || isWindowsAbsolutePath(value)
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
  const name = lastPathSegment(path) ?? 'imported-skill'
  const normalized = normalizeSkillIdSegment(name)
  const withLetter = startsWithAsciiLetter(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'imported-skill'
}

function isWindowsAbsolutePath(value: string): boolean {
  return value.length >= 3 && isAsciiLetter(value[0]) && value[1] === ':' && isPathSeparator(value[2])
}

function lastPathSegment(path: string): string | null {
  let segment = ''
  let lastSegment: string | null = null
  for (const char of path) {
    if (isPathSeparator(char)) {
      if (segment) {
        lastSegment = segment
        segment = ''
      }
      continue
    }
    segment += char
  }
  return segment || lastSegment
}

function normalizeSkillIdSegment(name: string): string {
  let normalized = ''
  for (const char of name.toLowerCase()) {
    if (isAsciiAlphaNumeric(char)) {
      normalized += char
    } else if (normalized && !normalized.endsWith('-')) {
      normalized += '-'
    }
  }
  return normalized.endsWith('-') ? normalized.slice(0, -1) : normalized
}

function isPathSeparator(char: string): boolean {
  return char === '/' || char === '\\'
}

function startsWithAsciiLetter(value: string): boolean {
  return value.length > 0 && isAsciiLetter(value[0])
}

function isAsciiAlphaNumeric(char: string): boolean {
  return isAsciiLetter(char) || (char >= '0' && char <= '9')
}

function isAsciiLetter(char: string): boolean {
  return (char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z')
}
