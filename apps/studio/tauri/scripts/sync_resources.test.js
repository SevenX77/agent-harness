/* eslint-env node */

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  copyRuntimeResources,
  skillsSourceDir,
} = require('./sync_resources')

test('skillsSourceDir prefers the sibling skills directory when present', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const repoSkills = path.join(repoRoot, 'skills')
  const siblingSkills = path.join(tempRoot, 'skills')
  fs.mkdirSync(repoSkills, { recursive: true })
  fs.mkdirSync(siblingSkills, { recursive: true })

  assert.equal(skillsSourceDir({ repoRoot, env: {} }), siblingSkills)
})

test('skillsSourceDir honors an explicit STUDIO_SKILLS_SOURCE_DIR override', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const customSkills = path.join(tempRoot, 'custom-skills')
  fs.mkdirSync(customSkills, { recursive: true })

  assert.equal(
    skillsSourceDir({
      repoRoot,
      env: { STUDIO_SKILLS_SOURCE_DIR: customSkills },
    }),
    customSkills,
  )
})

test('copyRuntimeResources copies external skills without tool metadata directories', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const vendorDir = path.join(tempRoot, 'vendor')
  const externalSkills = path.join(tempRoot, 'skills')
  const skillDir = path.join(externalSkills, 'demo-skill')
  fs.mkdirSync(path.join(repoRoot, 'config'), { recursive: true })
  fs.writeFileSync(path.join(repoRoot, 'config', 'settings.json'), '{}\n', 'utf8')
  fs.mkdirSync(path.join(skillDir, '.git', 'objects'), { recursive: true })
  fs.mkdirSync(path.join(skillDir, '.gemini'), { recursive: true })
  fs.mkdirSync(path.join(skillDir, '.workspace'), { recursive: true })
  fs.mkdirSync(path.join(skillDir, '__pycache__'), { recursive: true })
  fs.writeFileSync(path.join(skillDir, 'GRAPH.md'), '# demo\n', 'utf8')
  fs.writeFileSync(path.join(skillDir, '.git', 'index'), 'git metadata', 'utf8')
  fs.writeFileSync(path.join(skillDir, '.gemini', 'state.json'), '{}\n', 'utf8')
  fs.writeFileSync(path.join(skillDir, '.workspace', 'run.json'), '{}\n', 'utf8')
  fs.writeFileSync(path.join(skillDir, '__pycache__', 'module.pyc'), 'cache', 'utf8')

  copyRuntimeResources({
    repoRoot,
    vendorDir,
    env: { STUDIO_SKILLS_SOURCE_DIR: externalSkills },
  })

  const copiedSkill = path.join(vendorDir, 'resources', 'skills', 'demo-skill')
  assert.equal(fs.existsSync(path.join(copiedSkill, 'GRAPH.md')), true)
  assert.equal(fs.existsSync(path.join(copiedSkill, '.git')), false)
  assert.equal(fs.existsSync(path.join(copiedSkill, '.gemini')), false)
  assert.equal(fs.existsSync(path.join(copiedSkill, '.workspace')), false)
  assert.equal(fs.existsSync(path.join(copiedSkill, '__pycache__')), false)
})
