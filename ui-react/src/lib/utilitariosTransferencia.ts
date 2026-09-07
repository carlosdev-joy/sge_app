// Lógica PURA da transferência de arquivos dos Utilitários (spec
// docs/spec-utilitarios-transferencia.md): o contrato de
// `GET /utilitarios/arquivo/baixar` e de `PUT /utilitarios/arquivo/enviar`, o nome
// que vem no Content-Disposition, o estado que a barra de transferência mostra,
// as pré-validações do envio e a tradução dos erros. Sem React, sem rede — a
// bancada de node roda isto byte a byte.
import { EXTENSAO_RE } from './utilitariosAdmin'
import { avisoNome, avisoPasta, erroDaApi, formatarTamanho, type ErroLeitura } from './utilitariosArquivo'
import type { Existente } from './utilitariosGravacao'

export interface PedidoDownload {
  servidor: string
  diretorio: string
  nome: string
}

/** O que a barra de transferência mostra. Um download por vez. */
export type EstadoTransferencia =
  | { fase: 'conectando'; nome: string }
  | { fase: 'baixando'; nome: string; feito: number; total: number | null }
  | { fase: 'pronto'; nome: string; total: number }
  | { fase: 'erro'; nome: string; status: number | null; mensagem: string }

export function emCurso(t: EstadoTransferencia | null): boolean {
  return t !== null && (t.fase === 'conectando' || t.fase === 'baixando')
}

/** Query string do download: `URLSearchParams` percent-encoda espaço, acento e
 *  `+`/`%`/`&` no nome — o servidor recebe o nome como está. */
export function urlBaixar(p: PedidoDownload): string {
  const q = new URLSearchParams({ servidor: p.servidor, diretorio: p.diretorio.trim(), nome: p.nome.trim() })
  return `/utilitarios/arquivo/baixar?${q.toString()}`
}

/** Nome do arquivo salvo, a partir do Content-Disposition da API:
 *  `filename*=UTF-8''…` (o nome de verdade, percent-encoded) vale primeiro;
 *  depois `filename="…"` (o resgate ASCII); sem cabeçalho ou com percent
 *  inválido, o nome pedido. */
export function nomeDoContentDisposition(header: string | null | undefined, fallback: string): string {
  if (!header) return fallback
  const estrela = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header)
  if (estrela) {
    try {
      const n = decodeURIComponent(estrela[1].trim())
      if (n) return n
    } catch {
      // percent inválido: cai no `filename`
    }
  }
  const aspas = /filename\s*=\s*"([^"]*)"/i.exec(header)
  if (aspas && aspas[1].trim()) return aspas[1].trim()
  const cru = /filename\s*=\s*([^;]+)/i.exec(header)
  if (cru && cru[1].trim()) return cru[1].trim()
  return fallback
}

/** "1,5 MB de 40,0 MB" — ou só o feito, quando a API não disse o total. */
export function textoProgresso(feito: number, total: number | null): string {
  return total ? `${formatarTamanho(feito)} de ${formatarTamanho(total)}` : formatarTamanho(feito)
}

/** Largura da barra, 0–100; null sem total (barra indeterminada). */
export function percentual(feito: number, total: number | null): number | null {
  if (!total || total <= 0) return null
  return Math.max(0, Math.min(100, Math.round((feito / total) * 100)))
}

/** O modal de leitura oferece Baixar quando o `ler` recusou por NÃO ser texto
 *  (415) ou pelo teto de leitura (413): são exatamente os arquivos que o
 *  download alcança e a leitura não. */
export function ofereceDownload(status: number | null): boolean {
  return status === 413 || status === 415
}

const POR_STATUS: Record<number, string> = {
  401: 'Sua sessão expirou — entre de novo.',
  403: 'Sem permissão para baixar este caminho.',
  404: 'Arquivo não encontrado.',
  413: 'Arquivo acima do teto de download.',
  422: 'Pedido inválido.',
  // 502/503 da PRÓPRIA API sempre vêm com `detail` (SSH, servidor não
  // configurado, transferências em andamento); sem `detail` é o nginx.
  502: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  503: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  504: 'O servidor não respondeu a tempo.',
}

/** Erro do download → {status, mensagem}. */
export function erroTransferencia(e: unknown): ErroLeitura {
  return erroDaApi(e, POR_STATUS)
}

/** A frase da barra para cada fase. */
export function fraseTransferencia(t: EstadoTransferencia): string {
  switch (t.fase) {
    case 'conectando': return `Conectando ao servidor e lendo ${t.nome}…`
    case 'baixando': return `Baixando ${t.nome}… ${textoProgresso(t.feito, t.total)}`
    case 'pronto': return `Baixado ${t.nome} (${formatarTamanho(t.total)}).`
    case 'erro': return `Não foi possível baixar ${t.nome}: ${t.mensagem}`
  }
}

/** O que a região `aria-live` diz. Só em MARCOS (conectando, 25/50/75/100 % e
 *  o desfecho): a frase visível muda a cada bloco de 256 KB — 200 vezes num
 *  arquivo de 50 MB — e um leitor de tela anunciando cada uma inundaria a fila
 *  "polite" (achado da revisão da F2). */
export function anuncioTransferencia(t: EstadoTransferencia | null): string {
  if (!t) return ''
  if (t.fase !== 'baixando') return fraseTransferencia(t)
  const pct = percentual(t.feito, t.total)
  const marco = pct === null ? 0 : Math.floor(pct / 25) * 25
  return marco ? `Baixando ${t.nome}… ${marco}%` : `Baixando ${t.nome}…`
}

// ── Upload (F4): o contrato de `PUT /utilitarios/arquivo/enviar` ─────────────

export interface PedidoEnvio {
  servidor: string
  diretorio: string
  /** Nome COMPLETO no servidor (com a extensão, na caixa em que está). */
  nome: string
  sobrescrever: boolean
}

export interface ResultadoEnvio {
  caminho: string
  tamanho_bytes: number
  sha256: string
  criado: boolean
  backup: string | null
  duracao_ms: number
}

export interface ErroEnvio extends ErroLeitura {
  /** Só no 409: o arquivo que já está lá. */
  existente?: Existente
}

export type EstadoEnvio = 'enviando' | 'existe' | 'pronto' | 'erro' | 'cancelado'

/** O que a API devolve como padrão (`transferencia_max_kb`); usado se o config
 *  vier de uma API anterior à F1. */
export const TETO_TRANSFERENCIA_KB_PADRAO = 51200
// NAME_MAX (255) menos o que o servidor reserva para o `.tmp` e o `.bak`.
const LIMITE_NOME_ENVIO_BYTES = 215

/** A extensão de um nome COMPLETO: o que vem depois do ÚLTIMO ponto, em
 *  minúsculas — espelho de `extensao_de` do servidor. `README`, `.bashrc` e
 *  `x.` não têm extensão (null). */
export function extensaoDe(nome: string): string | null {
  const s = (nome || '').trim()
  const i = s.lastIndexOf('.')
  if (i <= 0 || i === s.length - 1) return null
  return s.slice(i + 1).toLowerCase()
}

/** O que o campo Nome diz antes de a API ser chamada. null = nada a dizer
 *  (ou nome vazio, que só desliga o botão). */
export function avisoEnvio(nome: string, tamanho: number | null, extensoes: string[], tetoKb: number): string | null {
  const s = (nome || '').trim()
  if (!s) return null
  const base = avisoNome(s)
  if (base) return base
  if ([...s].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127)) return 'Sem caracteres de controle.'
  if (/\p{Cf}/u.test(s)) return 'Sem caracteres invisíveis de formatação.'
  if (new TextEncoder().encode(s).length > LIMITE_NOME_ENVIO_BYTES) {
    return `Nome longo demais para gravar (máximo ${LIMITE_NOME_ENVIO_BYTES} bytes).`
  }
  const ext = extensaoDe(s)
  if (ext === null) return 'Arquivo sem extensão — só entram extensões da lista do admin.'
  if (!EXTENSAO_RE.test(ext) || !extensoes.includes(ext)) return `Extensão ${ext} não está na lista do admin.`
  if (tamanho !== null && tamanho > tetoKb * 1024) {
    return `Arquivo de ${formatarTamanho(tamanho)}, acima do teto de ${formatarTamanho(tetoKb * 1024)} para envio.`
  }
  return null
}

/** Tudo que precisa estar certo para o Enviar ligar. */
export function envioPronto(
  diretorio: string, nome: string, tamanho: number | null, raizes: string[], extensoes: string[],
  tetoKb: number, podeGravar: boolean,
): boolean {
  if (!podeGravar || tamanho === null) return false
  if (!diretorio.trim() || !nome.trim()) return false
  const ap = avisoPasta(diretorio, raizes)
  if (ap && ap.tom === 'erro') return false
  return avisoEnvio(nome, tamanho, extensoes, tetoKb) === null
}

export function urlEnviar(p: PedidoEnvio): string {
  const q = new URLSearchParams({
    servidor: p.servidor, diretorio: p.diretorio.trim(), nome: p.nome.trim(),
    sobrescrever: p.sobrescrever ? 'true' : 'false',
  })
  return `/utilitarios/arquivo/enviar?${q.toString()}`
}

const POR_STATUS_ENVIO: Record<number, string> = {
  400: 'O envio chegou incompleto ao servidor — tente de novo.',
  500: 'Falha na API do Orquestra — tente de novo em instantes.',
  401: 'Sua sessão expirou — entre de novo.',
  403: 'Sem permissão para enviar para este caminho.',
  404: 'Pasta não encontrada.',
  408: 'O envio parou no meio — tente de novo.',
  409: 'O arquivo já existe.',
  411: 'O navegador não informou o tamanho do arquivo — tente de novo.',
  413: 'Arquivo acima do teto de envio.',
  422: 'Pedido inválido.',
  // 502/503 da PRÓPRIA API vêm com `detail`; sem ele é o nginx (inclusive o
  // 413/502 em HTML acima de 64 MB, que o transporte reduz a status + nada).
  502: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  503: 'A API do Orquestra não respondeu — tente de novo em instantes.',
  504: 'O servidor não respondeu a tempo.',
}

/** Erro do envio → {status, mensagem, existente?}. O 409 vem com
 *  `detail = {mensagem, existente}`; o 504 ganha o aviso de conferir a pasta —
 *  o servidor pode ter concluído a gravação depois da resposta (spec §8.18). */
export function erroEnvio(e: unknown): ErroEnvio {
  const err = e as { status?: number; detail?: unknown } | null
  const detail = err?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'mensagem' in detail) {
    const d = detail as { mensagem: unknown; existente?: unknown }
    const base: ErroEnvio = { status: typeof err?.status === 'number' ? err.status : null, mensagem: String(d.mensagem) }
    const ex = d.existente as Partial<Existente> | undefined
    if (ex && typeof ex === 'object') {
      base.existente = {
        tamanho_bytes: typeof ex.tamanho_bytes === 'number' ? ex.tamanho_bytes : 0,
        modificado_em: typeof ex.modificado_em === 'string' ? ex.modificado_em : null,
      }
    }
    return base
  }
  const base = erroDaApi(e, POR_STATUS_ENVIO)
  if (base.status === 504) {
    return { ...base, mensagem: `${base.mensagem} Confira na pasta antes de reenviar: o servidor pode ter concluído a gravação.` }
  }
  return base
}

/** Resumo do resultado, em frases curtas. */
export function resumoEnvio(r: ResultadoEnvio): string[] {
  const partes = [
    r.criado ? 'arquivo criado' : 'arquivo sobrescrito',
    formatarTamanho(r.tamanho_bytes),
    `sha256 ${r.sha256.slice(0, 12)}…`,
  ]
  if (r.backup) partes.push(`cópia de segurança em ${r.backup}`)
  partes.push(`${(r.duracao_ms / 1000).toFixed(1).replace('.', ',')} s`)
  return partes
}

/** O corpo já tinha chegado inteiro quando o usuário cancelou? Aí o servidor
 *  (ou o nginx, que bufferiza) pode gravar mesmo assim (spec §8.15). */
export function envioChegouInteiro(p: { enviado: number; total: number } | null): boolean {
  return p !== null && p.enviado >= p.total
}

export function fraseCancelamento(chegouInteiro: boolean): string {
  return chegouInteiro
    ? 'O envio foi cancelado, mas o arquivo já tinha chegado inteiro ao servidor: confira na pasta — ele pode ter sido gravado.'
    : 'Envio cancelado antes de terminar: nada foi gravado no servidor.'
}

/** O que a região `aria-live` do modal de envio diz. Só em MARCOS enquanto o
 *  corpo sobe (25/50/75/100 %), a virada para "gravando", e o desfecho —
 *  mesma regra da faixa de download (revisão da F4). */
export function anuncioEnvio(
  estado: EstadoEnvio, progresso: { enviado: number; total: number } | null,
  erro: ErroEnvio | null, chegouInteiro: boolean,
): string {
  switch (estado) {
    case 'enviando': {
      if (envioChegouInteiro(progresso)) return 'Enviado ao servidor; gravando… aguarde.'
      const pct = progresso ? percentual(progresso.enviado, progresso.total) : null
      const marco = pct === null ? 0 : Math.floor(pct / 25) * 25
      return marco ? `Enviando… ${marco}%` : 'Enviando…'
    }
    case 'existe': return erro?.mensagem ?? 'O arquivo já existe.'
    case 'pronto': return 'Arquivo enviado.'
    case 'cancelado': return fraseCancelamento(chegouInteiro)
    case 'erro': return erro?.mensagem ?? 'Não foi possível enviar o arquivo.'
  }
}
