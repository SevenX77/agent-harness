import { describe, expect, it, vi } from 'vitest'
import { effectiveDefaultSkillsDirectory, joinDirectoryPath, runtimeDefaultSkillsDirectory } from './skill-paths'

vi.mock('../config/runtime', () => ({
  getRuntimeConfig: vi.fn(() => ({
    resourceDir: '/studio/resources',
    configDir: '/studio/config',
  })),
}))

describe('skill path helpers', () => {
  it('joins POSIX and Windows-style directories without duplicate separators', () => {
    expect(joinDirectoryPath('/Users/sevenx/Skills/', 'new-skill')).toBe('/Users/sevenx/Skills/new-skill')
    expect(joinDirectoryPath('C:\\Users\\sevenx\\Skills\\', 'new-skill')).toBe('C:\\Users\\sevenx\\Skills\\new-skill')
  })

  it('derives the runtime default from configDir', () => {
    expect(runtimeDefaultSkillsDirectory()).toBe('/studio/config/Skills')
  })

  it('prefers the saved app setting over the runtime default', () => {
    expect(effectiveDefaultSkillsDirectory('/Users/sevenx/graph_skills')).toBe('/Users/sevenx/graph_skills')
  })
})
