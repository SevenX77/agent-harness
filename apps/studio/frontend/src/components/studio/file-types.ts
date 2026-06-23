export interface FileMeta {
  path: string
  language: string
  content: string
  hash?: string | null
  skillId?: string | null
  workspaceRoot?: string | null
  title?: string
  saveEnabled?: boolean
}
