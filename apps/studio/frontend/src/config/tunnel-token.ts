const STORAGE_KEY = 'studio_tunnel_token'
const TOKEN_HASH_RE = /#?tkn=([A-Za-z0-9_-]+)/

export function bootstrapTunnelToken(): string | null {
  const match = window.location.hash.match(TOKEN_HASH_RE)
  if (match) {
    const token = match[1]
    sessionStorage.setItem(STORAGE_KEY, token)
    history.replaceState(null, '', window.location.pathname + window.location.search)
    return token
  }

  return sessionStorage.getItem(STORAGE_KEY)
}
