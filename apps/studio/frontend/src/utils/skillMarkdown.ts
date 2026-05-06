import yaml from 'js-yaml'
import type { SkillManifest } from '../api/types'

export function manifestToSkillMarkdown(manifest: SkillManifest): string {
  const frontmatter = yaml.dump(manifest, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
  })
  return `---\n${frontmatter}---\n\n# ${manifest.name}\n\n${manifest.description}\n`
}
