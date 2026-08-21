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

// What ships is either named explicitly or lives in the repo. The fallback in
// between used to be `<repo>/../skills` — whatever directory happened to carry
// that name next to the checkout. On the primary dev machine that is
// `D:\coding\skills`, 39 private skill sources, and `bundle.resources` ships
// `vendor/**/*` wholesale, so every installer built there would have carried
// them (ledger D3).
test('skillsSourceDir never reaches outside the repo for a sibling directory', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const repoSkills = path.join(repoRoot, 'skills')
  const siblingSkills = path.join(tempRoot, 'skills')
  fs.mkdirSync(repoSkills, { recursive: true })
  fs.mkdirSync(siblingSkills, { recursive: true })
  fs.writeFileSync(path.join(siblingSkills, 'private.md'), 'not ours\n', 'utf8')

  assert.equal(skillsSourceDir({ repoRoot, env: {} }), repoSkills)
})

test('skillsSourceDir reports nothing to bundle rather than guessing a directory', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const siblingSkills = path.join(tempRoot, 'skills')
  fs.mkdirSync(repoRoot, { recursive: true })
  fs.mkdirSync(siblingSkills, { recursive: true })

  assert.equal(skillsSourceDir({ repoRoot, env: {} }), null)
})

test('copyRuntimeResources ships an empty skills directory when there is nothing to bundle', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const vendorDir = path.join(tempRoot, 'vendor')
  // The sibling exists and must still be ignored — this is the shape the dev
  // machine is actually in.
  fs.mkdirSync(path.join(tempRoot, 'skills', 'someones-private-skill'), { recursive: true })

  copyRuntimeResources({ repoRoot, vendorDir, env: {} })

  const shipped = path.join(vendorDir, 'resources', 'skills')
  assert.equal(fs.existsSync(shipped), true, 'the directory must exist so the app finds a shape it knows')
  assert.deepEqual(fs.readdirSync(shipped), [], 'and it must be empty')
})

// The repo's `config/` used to be shipped TWICE — copied here into
// `vendor/resources/config`, and listed again in tauri.conf.json's
// bundle.resources, from the same source directory. Neither copy was ever read:
// the backend resolves llm_roles.yaml / llm_canonical_rules.yaml under
// `<app settings dir>/llm/`, and even the STUDIO_RESOURCE_DIR fallback looks in
// `<resource>/config/llm/`, one level deeper than the bundle put them. A fresh
// install seeds both files from code (`runtime_truth_init`), never from disk.
// The files stay in the repo because the engine's smoke tests read them from
// the source tree; they just have no business inside an installer (ledger D5).
test('copyRuntimeResources does not ship the repo config directory', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-sync-resources-'))
  const repoRoot = path.join(tempRoot, 'agent-harness')
  const vendorDir = path.join(tempRoot, 'vendor')
  fs.mkdirSync(path.join(repoRoot, 'config'), { recursive: true })
  fs.writeFileSync(path.join(repoRoot, 'config', 'llm_roles.yaml'), 'roles: []\n', 'utf8')

  copyRuntimeResources({ repoRoot, vendorDir, env: {} })

  assert.equal(
    fs.existsSync(path.join(vendorDir, 'resources', 'config')),
    false,
    'a config directory nobody reads is dead weight in the installer',
  )
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
