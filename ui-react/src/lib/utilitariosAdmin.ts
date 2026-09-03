// Lógica PURA da aba Admin › Utilitários (spec docs/spec-utilitarios-arquivos.md, F2):
// tipos do contrato da API, pré-validações que a tela mostra ANTES de chamar o
// servidor, e a leitura dos resultados. Sem React, sem rede — é o que a bancada
// de node prova e o que os componentes só consomem.
//
// ⚠️ O servidor é a AUTORIDADE. Tudo aqui espelha `api/services/ssh_arquivos.py`
// (normalizar_raiz, RAIZES_PROIBIDAS, _EXT_RE) para o usuário ver o erro no campo
// em vez de num toast, não para substituir a validação de lá.

export interface ServidorUtil {
  id: string
  label: string
  configurado: boolean
}

export interface RaizUtil {
  id: number
  servidor: string
  caminho: string
  ativo: boolean
  criado_por: string | null
  criado_em: string | null
}

export interface ExtensaoUtil {
  extensao: string
  criado_por: string | null
  criado_em: string | null
}

export interface TesteRaiz {
  existe: boolean
  eh_pasta: boolean | null
  legivel: boolean
  caminho_real: string | null
  detalhe?: string
  duracao_ms?: number
}

export interface ConfigUtil {
  servidores: ServidorUtil[]
  raizes: { id: number; servidor: string; caminho: string }[]
  extensoes: string[]
  tamanho_max_kb: number
  backup_ao_sobrescrever: boolean
  pode_gravar: boolean
}

// Espelhos do backend.
export const TETO_MAX_KB = 16384
export const LIMITE_RAIZ = 800
export const EXTENSAO_RE = /^[a-z0-9]{1,15}$/
export const RAIZES_PROIBIDAS = [
  '/etc', '/root', '/proc', '/sys', '/dev', '/boot',
  '/bin', '/sbin', '/lib', '/lib64', '/usr', '/run', '/var/run',
]

// normpath LEXICAL, como o `posixpath.normpath` do servidor — com as barras
// iniciais colapsadas ANTES (o POSIX preserva `//`; aqui é sempre uma barra).
export function normalizarCaminhoLexical(bruto: string): string {
  const partes: string[] = []
  for (const p of bruto.split('/')) {
    if (!p || p === '.') continue
    if (p === '..') { partes.pop(); continue }
    partes.push(p)
  }
  return '/' + partes.join('/')
}

// Unidades UTF-16 — o que NVARCHAR(n) conta. `length` de string JS JÁ é isso.
export function utf16Len(s: string): number {
  return s.length
}

/** Aviso a mostrar no campo da raiz enquanto o admin digita; null = nada a dizer. */
export function avisoRaiz(bruto: string): string | null {
  const s = (bruto || '').trim()
  if (!s) return null
  if (!s.startsWith('/')) return 'Precisa ser um caminho absoluto (começar com /).'
  const n = normalizarCaminhoLexical(s)
  if (n === '/') return 'A raiz não pode ser a barra (/): escolha uma pasta.'
  if (utf16Len(n) > LIMITE_RAIZ) return `Raiz longa demais (máximo ${LIMITE_RAIZ} caracteres).`
  for (const p of RAIZES_PROIBIDAS) {
    if (n === p || n.startsWith(p + '/')) return `${p} é pasta do sistema e não pode ser raiz.`
  }
  return null
}

export type ExtensaoNormalizada = { ok: true; valor: string } | { ok: false; erro: string }

/** Minúsculas, sem ponto, só letras e números, até 15 — o mesmo regex do servidor. */
export function normalizarExtensao(bruta: string): ExtensaoNormalizada {
  const s = (bruta || '').trim().toLowerCase().replace(/^\.+/, '')
  if (!s) return { ok: false, erro: 'Informe a extensão.' }
  if (!EXTENSAO_RE.test(s)) {
    return { ok: false, erro: 'Só letras minúsculas e números, sem ponto, até 15 caracteres.' }
  }
  return { ok: true, valor: s }
}

// `sh` é o caso de maior risco da spec (gravar script que roda em pipeline):
// a semente deixa de fora e a tela pede confirmação explícita ao incluir.
export const EXTENSOES_DE_SCRIPT = ['sh', 'bash', 'ksh', 'csh', 'zsh', 'py', 'pl']

export function extensaoPedeConfirmacao(ext: string): boolean {
  return EXTENSOES_DE_SCRIPT.includes(ext)
}

export type TomTeste = 'success' | 'warning' | 'error'

/** Como o botão Testar resume o resultado: tom (badge) + frase. */
export function tomDoTeste(t: TesteRaiz): { tom: TomTeste; texto: string } {
  if (!t.existe) return { tom: 'error', texto: t.detalhe || 'a pasta não existe no servidor' }
  if (t.eh_pasta === false) return { tom: 'error', texto: t.detalhe || 'é um arquivo, não uma pasta' }
  if (!t.legivel) return { tom: 'warning', texto: t.detalhe || 'existe, mas o usuário SSH não consegue listar' }
  return { tom: 'success', texto: t.detalhe || 'existe e é legível pelo usuário SSH' }
}

/** Teto em KB digitado → número válido (1..TETO_MAX_KB) ou null. */
export function tetoValido(texto: string): number | null {
  const s = (texto || '').trim()
  if (!/^\d+$/.test(s)) return null
  const n = Number(s)
  if (n < 1 || n > TETO_MAX_KB) return null
  return n
}

/** Mensagem legível de um erro do `apiFetch` (string, 422 estruturado ou nada). */
export function mensagemErro(e: unknown, padrao: string): string {
  const err = e as { message?: unknown; detail?: unknown; status?: number } | null
  const detail = err?.detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map(d => (d && typeof d === 'object' && 'msg' in d) ? String((d as { msg: unknown }).msg) : '')
      .filter(Boolean)
    if (msgs.length) return msgs.join('; ')
  }
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof err?.message === 'string' && err.message.trim() && !/^\d{3} /.test(err.message)) return err.message
  return padrao
}

/** 503 da API com "migration 105": a aba precisa dizer isso, não "falha ao carregar". */
export function migrationPendente(e: unknown): boolean {
  const err = e as { status?: number; message?: string } | null
  return err?.status === 503 && /migration 105/i.test(err?.message || '')
}
