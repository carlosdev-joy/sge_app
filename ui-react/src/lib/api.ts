import { readLegacyToken } from '../store/auth'

const BASE = '/orquestra'

// Token do React (login próprio) com fallback para a sessão legada (orq_session).
function currentToken(): string | null {
  return localStorage.getItem('orquestra_token') || readLegacyToken()
}

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const token = currentToken()
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts?.headers ?? {}),
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('orquestra_token')
    // Login centralizado na UI legada (raiz). Volta para lá em vez do /login React.
    window.location.href = '/'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}
