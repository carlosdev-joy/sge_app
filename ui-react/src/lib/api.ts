export const BASE = '/orquestra'

/** Apaga do navegador toda conversa de agente guardada (logout / sessão
 *  expirada) — senão o próximo usuário da mesma estação via a última conversa
 *  do anterior (auditoria de segurança da F7). Fica AQUI, sem import: este
 *  arquivo é autocontido (os harnesses o executam sozinho). O prefixo é o
 *  `PREFIXO_CONVERSA_AGENTE` de `lib/agentes.ts` — um teste prende os dois. */
export const PREFIXO_CONVERSA_AGENTE = 'orquestra_agente_conversa_'

export function esquecerConversasDeAgentes(): void {
  try {
    const chaves: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(PREFIXO_CONVERSA_AGENTE)) chaves.push(k)
    }
    for (const k of chaves) localStorage.removeItem(k)
  } catch {
    /* storage bloqueado: nada a limpar */
  }
}

export function currentToken(): string | null {
  return localStorage.getItem('orquestra_token')
}

/** Sessão expirada (401): limpa o token e manda ao login. Um lugar só — o
 *  `apiFetchBruto` e o upload por XHR (`lib/utilitariosEnvio.ts`) usam. */
export function expirarSessao(): void {
  localStorage.removeItem('orquestra_token')
  esquecerConversasDeAgentes()
  window.location.href = '/login'
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
    expirarSessao()
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

/** O login é público: um 401 aqui é credencial recusada, não sessão expirada.
 * Não envia token antigo e não passa pelo interceptador das telas autenticadas. */
export type ErroLogin = ErroApi & { tipo: 'http' | 'transporte' | 'resposta' }
export interface RespostaLogin { token: string; usuario: import('../store/auth').User }
export const LOGIN_TIMEOUT_MS = 30_000

export async function apiLogin(usuario: string, senha: string): Promise<RespostaLogin> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS)
  try {
    let res: Response
    try {
      res = await fetch(`${BASE}/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'omit', signal: controller.signal,
        body: JSON.stringify({ usuario: usuario.trim(), senha }),
      })
    } catch {
      throw Object.assign(new Error('Falha de transporte no login'), { tipo: 'transporte' })
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const detail = body?.detail
      // Mesmo shape HTTP do cliente global; a UI usa mensagens fixas por status.
      throw Object.assign(new Error(typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`), {
        tipo: 'http', status: res.status, detail,
      })
    }
    let body: RespostaLogin
    try {
      body = await res.json()
    } catch (erro) {
      throw Object.assign(new Error('Resposta de login indisponível'), {
        tipo: controller.signal.aborted || erro instanceof TypeError ? 'transporte' : 'resposta',
      })
    }
    if (!body || typeof body.token !== 'string' || !body.token || !body.usuario || typeof body.usuario.matricula !== 'string') {
      throw Object.assign(new Error('Resposta de login inválida'), { tipo: 'resposta' })
    }
    return body
  } finally {
    clearTimeout(timeout)
  }
}

/** Nunca mostra detail do backend, que pode conter dado interno ou distinguir usuários. */
export function mensagemErroLogin(erro: unknown): string {
  const e = erro as Partial<ErroLogin> | null
  if (e?.tipo === 'transporte') return 'Não foi possível conectar ao ORQ. Verifique sua conexão corporativa'
  switch (e?.status) {
    case 401: return 'Matrícula ou senha incorreta. Use a mesma senha da sua rede corporativa'
    case 403: return 'Sua matrícula não tem acesso liberado. Abra um chamado para a Engenharia de Dados'
    case 502:
    case 503:
    case 504: return 'Serviço de autenticação indisponível. Não é a sua senha — tente em alguns minutos'
    case 422: return 'Preencha matrícula e senha.'
    default: return 'Não foi possível abrir sua sessão. O problema é do sistema, não da sua senha'
  }
}
