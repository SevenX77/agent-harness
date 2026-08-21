import { describe, expect, it } from 'vitest'
import { resources, supportedLngs } from '../i18n'

/**
 * A namespace that exists in one language and not the other is a screen that
 * silently reverts to English — i18next falls back rather than failing, so a
 * missing key never shows up as an error, only as the wrong words.
 *
 * This is the gate the canvas batch (#958) proved was needed: its own sweep
 * over all 24 problem codes × 2 languages is what caught the entries that had
 * been forgotten. Generalised here so every namespace gets the same guard
 * instead of each one re-inventing it.
 */

/**
 * i18next appends a plural category to the key (`_one`, `_other`, …) and which
 * categories exist depends on the language: English needs two, Chinese has
 * exactly one. So the comparison is between BASE keys — `count_one` and
 * `count_other` are the same entry, and a language is complete when it carries
 * at least one form of it.
 */
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/

function baseKeys(node: unknown, prefix = ''): Set<string> {
  const keys = new Set<string>()
  if (typeof node !== 'object' || node === null) {
    return keys
  }
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'object' && value !== null) {
      for (const nested of baseKeys(value, path)) keys.add(nested)
    } else {
      keys.add(path.replace(PLURAL_SUFFIX, ''))
    }
  }
  return keys
}

function emptyValues(node: unknown, prefix = ''): string[] {
  if (typeof node !== 'object' || node === null) {
    return []
  }
  return Object.entries(node as Record<string, unknown>).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'object' && value !== null) {
      return emptyValues(value, path)
    }
    return typeof value === 'string' && value.trim() !== '' ? [] : [path]
  })
}

const [reference, ...others] = supportedLngs

describe('every namespace says the same things in every language', () => {
  it('registers the same namespaces in every language', () => {
    const expected = Object.keys(resources[reference]).sort()
    for (const language of others) {
      expect(Object.keys(resources[language]).sort(), language).toEqual(expected)
    }
  })

  it.each(Object.keys(resources[reference]))('%s carries every key in every language', (namespace) => {
    const expected = [...baseKeys(resources[reference][namespace as keyof (typeof resources)[typeof reference]])].sort()
    for (const language of others) {
      const bundle = resources[language][namespace as keyof (typeof resources)[typeof language]]
      expect([...baseKeys(bundle)].sort(), `${language}/${namespace}`).toEqual(expected)
    }
  })

  it.each(supportedLngs.flatMap((language) =>
    Object.keys(resources[reference]).map((namespace) => [language, namespace] as const),
  ))('%s/%s has no blank entries', (language, namespace) => {
    const bundle = resources[language][namespace as keyof (typeof resources)[typeof language]]
    expect(emptyValues(bundle)).toEqual([])
  })
})
