const BASE = '/orquestra'

function currentToken(): string | null {
  return localStorage.getItem('orquestra_token')
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
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}
