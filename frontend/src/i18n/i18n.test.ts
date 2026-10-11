import { describe, expect, it } from 'vitest'
import en from './en.json'
import hi from './hi.json'

function keys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix]
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key))
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{(\w+)\}\}/g)].map((match) => match[1]).sort()
}

function lookup(tree: unknown, path: string): string {
  return path.split('.').reduce<unknown>((node, key) => (node as Record<string, unknown>)[key], tree) as string
}

describe('translations', () => {
  it('have the same keys in English and Hindi', () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort())
  })

  it('use the same placeholders in both languages', () => {
    for (const key of keys(en)) {
      expect(placeholders(lookup(hi, key)), key).toEqual(placeholders(lookup(en, key)))
    }
  })

  it('never use the words the project rules out', () => {
    const banned = /\b(hidden|illegal|caught)\b/i
    for (const key of keys(en)) expect(lookup(en, key), key).not.toMatch(banned)
  })
})
