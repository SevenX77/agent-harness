import { afterEach, describe, expect, it, vi } from 'vitest'
import { bootstrapTunnelToken } from './tunnel-token'

function stubBrowserLocation(hash: string): Map<string, string> {
  const storage = new Map<string, string>()
  const location = {
    hash,
    pathname: '/studio',
    search: '?mode=dev',
  }

  vi.stubGlobal('window', { location })
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  })
  vi.stubGlobal('history', {
    replaceState: vi.fn((_state: unknown, _title: string, url: string) => {
      expect(url).toBe('/studio?mode=dev')
      location.hash = ''
    }),
  })
  return storage
}

describe('bootstrapTunnelToken', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads token from URL hash, stores it, and clears the hash', () => {
    const storage = stubBrowserLocation('#tkn=abc123')

    expect(bootstrapTunnelToken()).toBe('abc123')
    expect(storage.get('studio_tunnel_token')).toBe('abc123')
    expect(window.location.hash).toBe('')
    expect(history.replaceState).toHaveBeenCalledOnce()
  })

  it('falls back to sessionStorage when hash is empty', () => {
    const storage = stubBrowserLocation('')
    storage.set('studio_tunnel_token', 'stored-token')

    expect(bootstrapTunnelToken()).toBe('stored-token')
    expect(history.replaceState).not.toHaveBeenCalled()
  })

  it('returns null when hash and sessionStorage are empty', () => {
    stubBrowserLocation('')

    expect(bootstrapTunnelToken()).toBeNull()
    expect(history.replaceState).not.toHaveBeenCalled()
  })
})
