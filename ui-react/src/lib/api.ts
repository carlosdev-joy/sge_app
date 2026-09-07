const BASE = '/orquestra'

function currentToken(): string | null {
  return localStorage.getItem('orquestra_token')
}

/** Erro que `apiFetch`/`apiFetchBruto` lançam: `status` e `detail` crus para o
 *  chamador introspectar (ex.: 422 estruturado, 409 com `existente`). */
export type ErroApi = Error & { status?: number; detail?: unknown }

/** Chamada CRUA à API: injeta o `Authorization`, trata o 401 (limpa o token e
 *  manda ao login) e dá ao erro o mesmo shape do `apiFetch` — mas NÃO injeta
 *  `Content-Type` nem lê o corpo. Quem chama decide o que fazer com a
 *  `Response` (blob, stream, json). É o caminho do download de arquivo
 *  (spec docs/spec-utilitarios-transferencia.md): o `apiFetch` só fala JSON. */
export async function apiFetchBruto(path: string, opts?: RequestInit): Promise<Response> {
  const token = currentToken()
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
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
    const err = new Error(msg) as ErroApi
    err.status = res.status
    err.detail = detail
    throw err
  }
  return res
}

/** Chamada JSON à API (o padrão do app): `Content-Type: application/json` por
 *  padrão e a resposta já decodificada. Comportamento idêntico ao de sempre —
 *  só o miolo (token, 401, shape do erro) mudou para `apiFetchBruto`. */
export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await apiFetchBruto(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts?.headers ?? {}),
    },
  })
  return res.json()
}
