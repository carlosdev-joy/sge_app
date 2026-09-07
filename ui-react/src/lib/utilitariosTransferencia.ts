// Lógica PURA da transferência de arquivos dos Utilitários (spec
// docs/spec-utilitarios-transferencia.md): o contrato de
// `GET /utilitarios/arquivo/baixar`, o nome que vem no Content-Disposition, o
// estado que a barra de transferência mostra e a tradução dos erros. Sem React,
// sem rede — a bancada de node roda isto byte a byte.
import { erroDaApi, formatarTamanho, type ErroLeitura } from './utilitariosArquivo'

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
