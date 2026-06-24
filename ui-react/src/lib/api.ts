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
    const detail = body?.detail
    // Mensagem legível: usa `detail` quando string, senão status. Anexa `status`
    // e `detail` (cru) ao erro para o chamador introspectar (ex.: 422 estruturado).
    const msg = typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`
    const err = new Error(msg) as Error & { status?: number; detail?: unknown }
    err.status = res.status
    err.detail = detail
    throw err
  }
  return res.json()
}
