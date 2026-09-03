// Lógica PURA da tela Utilitários › Ver arquivo (spec docs/spec-utilitarios-arquivos.md,
// F3): o contrato de `POST /utilitarios/arquivo/ler`, a pré-conferência da pasta
// contra as raízes (o mesmo `raiz_de` do servidor, por componente) e a
// tradução dos erros da API em frases para o modal. Sem React, sem rede.
//
// ⚠️ O servidor é a AUTORIDADE (realpath no servidor, auditoria). O que está
// aqui só evita uma ida à API que o usuário já sabe que vai falhar e diz, no
// campo, o que o servidor diria.
import { normalizarCaminhoLexical, utf16Len } from './utilitariosAdmin'

export interface PedidoLeitura {
  servidor: string
  diretorio: string
  nome: string
  ultimas_linhas?: number
  codificacao?: 'utf-8' | 'latin-1'
}

export interface ConteudoArquivo {
  caminho: string
  tamanho_bytes: number
  linhas: number
  codificacao: string
  truncado: boolean
  modificado_em: string | null
  conteudo: string
  duracao_ms: number
}

export interface ErroLeitura {
  status: number | null
  mensagem: string
}

export const ULTIMAS_LINHAS_MAX = 100_000
export const ULTIMAS_LINHAS_PADRAO = 200
// NVARCHAR(1000) do log — o servidor recusa acima disso; o campo avisa antes.
export const LIMITE_CAMINHO = 1000

/** A raiz sob a qual `caminho` está (comparação por componente), ou null. */
export function raizDe(caminho: string, raizes: string[]): string | null {
  for (const bruta of raizes) {
    const r = normalizarCaminhoLexical(bruta)
    if (r === '/') continue
    if (caminho === r || caminho.startsWith(r + '/')) return r
  }
  return null
}

export type AvisoPasta =
  | { tom: 'neutro'; texto: string }
  | { tom: 'erro'; texto: string }
  | null

/** O que o campo Pasta diz enquanto o usuário digita. null = nada a dizer. */
export function avisoPasta(bruto: string, raizes: string[]): AvisoPasta {
  const s = (bruto || '').trim()
  if (!s) return null
  if (!s.startsWith('/')) return { tom: 'erro', texto: 'Precisa ser um caminho absoluto (começar com /).' }
  const n = normalizarCaminhoLexical(s)
  if (utf16Len(n) > LIMITE_CAMINHO) return { tom: 'erro', texto: `Caminho longo demais (máximo ${LIMITE_CAMINHO} caracteres).` }
  if (raizes.length === 0) return { tom: 'erro', texto: 'Nenhum diretório liberado — cadastre uma raiz em Admin › Utilitários.' }
  const raiz = raizDe(n, raizes)
  if (!raiz) return { tom: 'erro', texto: 'Fora dos diretórios liberados.' }
  return { tom: 'neutro', texto: `abaixo de ${raiz}` }
}

/** Nome do arquivo: sem barra, sem `.`/`..`, até 255 bytes UTF-8. */
export function avisoNome(bruto: string): string | null {
  const s = (bruto || '').trim()
  if (!s) return null
  if (s.includes('/') || s === '.' || s === '..') return "Sem barra, e não pode ser '.' nem '..'."
  if (new TextEncoder().encode(s).length > 255) return 'Nome longo demais (máximo 255 bytes).'
  return null
}

/** "Últimas N linhas" digitado → inteiro válido, null = não pedido, ou 'invalido'. */
export function ultimasLinhas(texto: string): number | null | 'invalido' {
  const s = (texto || '').trim()
  if (!s) return null
  if (!/^\d+$/.test(s)) return 'invalido'
  const n = Number(s)
  if (n < 1 || n > ULTIMAS_LINHAS_MAX) return 'invalido'
  return n
}

/** Tudo que precisa estar certo para o Iniciar ligar. */
export function pedidoPronto(diretorio: string, nome: string, ultimas: string, raizes: string[]): boolean {
  const ap = avisoPasta(diretorio, raizes)
  if (!diretorio.trim() || !nome.trim()) return false
  if (ap && ap.tom === 'erro') return false
  if (avisoNome(nome)) return false
  return ultimasLinhas(ultimas) !== 'invalido'
}

export function formatarTamanho(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1).replace('.', ',')} KB`
  return `${(n / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}

const POR_STATUS: Record<number, string> = {
  401: 'Sua sessão expirou — entre de novo.',
  403: 'Sem permissão para abrir este caminho.',
  404: 'Arquivo não encontrado.',
  413: 'Arquivo acima do teto — peça só as últimas N linhas.',
  415: 'O arquivo não é texto (parece binário).',
  422: 'Pedido inválido.',
  // 502/503 da PRÓPRIA API sempre vêm com `detail` (SSH, servidor não
  // configurado); sem `detail` é o nginx respondendo por uma API fora do ar.
  502: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  503: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  504: 'O servidor não respondeu a tempo.',
}

/** Erro do `apiFetch` → {status, mensagem}. O `detail` da API já vem em pt-BR e
 *  nomeia a causa (fora das raízes, binário, teto…); é ele que vale quando existe. */
export function erroLeitura(e: unknown): ErroLeitura {
  const err = e as { status?: number; detail?: unknown; message?: string } | null
  const status = typeof err?.status === 'number' ? err.status : null
  const detail = err?.detail
  if (typeof detail === 'string' && detail.trim()) return { status, mensagem: detail }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map(d => (d && typeof d === 'object' && 'msg' in d) ? String((d as { msg: unknown }).msg) : '')
      .filter(Boolean)
    if (msgs.length) return { status, mensagem: msgs.join('; ') }
  }
  if (status !== null && POR_STATUS[status]) return { status, mensagem: POR_STATUS[status] }
  // Só com status HTTP: sem ele é falha de rede, e o `message` do fetch vem em
  // inglês do navegador ("Failed to fetch") — não é frase para o usuário.
  if (status !== null && typeof err?.message === 'string' && err.message.trim()
      && !/^\d{3} /.test(err.message)) {
    return { status, mensagem: err.message }
  }
  return { status, mensagem: 'Não foi possível falar com a API.' }
}

/** Resumo do rodapé do modal, em frases curtas. */
export function resumoConteudo(c: ConteudoArquivo): string[] {
  const partes = [
    formatarTamanho(c.tamanho_bytes),
    `${c.linhas} ${c.linhas === 1 ? 'linha' : 'linhas'}${c.truncado ? ' (só o fim)' : ''}`,
    `codificação ${c.codificacao}`,
  ]
  if (c.modificado_em) partes.push(`modificado em ${c.modificado_em}`)
  partes.push(`${(c.duracao_ms / 1000).toFixed(1).replace('.', ',')} s`)
  return partes
}
