// Download de um arquivo do servidor para o computador do usuário (spec
// docs/spec-utilitarios-transferencia.md, F2).
//
// ⚠️ Por que `fetch` + Blob e não `<a href>`: o token do Orquestra vive no
// `localStorage`, não em cookie — um link direto chegaria à API sem
// `Authorization` (é o defeito do precedente de anexos de chamados). Então o
// arquivo desce pela `apiFetchBruto`, o corpo é lido em blocos (contando
// bytes contra o Content-Length, para a barra de progresso e para recusar um
// download que chegou pela metade), vira um Blob e um `<a download>` criado
// na hora dispara o "salvar como" do navegador com o nome que a API mandou.
//
// O ambiente (`buscar`, `entregar`) é injetável como em `lib/copiar.ts`: a
// bancada de node não tem `fetch` autenticado nem `URL.createObjectURL`.
import { apiFetchBruto } from './api'
import { nomeDoContentDisposition, urlBaixar, type PedidoDownload } from './utilitariosTransferencia'

export interface AmbienteDownload {
  /** `apiFetchBruto` por padrão. */
  buscar?: (url: string) => Promise<Response>
  /** Entrega o Blob ao usuário (`<a download>`); a bancada guarda em vez de clicar. */
  entregar?: (blob: Blob, nome: string) => void
}

export interface ResultadoDownload {
  nome: string
  total: number
  sha256: string | null
}

export type ProgressoDownload = (feito: number, total: number | null) => void

function entregarPadrao(blob: Blob, nome: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nome
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revogar na hora cancela o download em alguns navegadores: um instante depois.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function totalDeclarado(res: Response): number | null {
  const bruto = res.headers.get('content-length')
  if (bruto === null) return null
  const n = Number(bruto)
  return Number.isFinite(n) && n >= 0 ? n : null
}

/** Baixa o arquivo do pedido. Lança o erro do `apiFetchBruto` (com `status` e
 *  `detail`) ou um erro sem status quando o corpo chegou incompleto. */
export async function baixarArquivo(
  pedido: PedidoDownload, onProgresso: ProgressoDownload, amb: AmbienteDownload = {},
): Promise<ResultadoDownload> {
  const buscar = amb.buscar ?? (u => apiFetchBruto(u))
  const res = await buscar(urlBaixar(pedido))
  const nome = nomeDoContentDisposition(res.headers.get('content-disposition'), pedido.nome.trim())
  const total = totalDeclarado(res)

  const partes: BlobPart[] = []
  let feito = 0
  const leitor = res.body?.getReader()
  if (leitor) {
    for (;;) {
      const { done, value } = await leitor.read()
      if (done) break
      if (value && value.byteLength) {
        partes.push(value)
        feito += value.byteLength
        onProgresso(feito, total)
      }
    }
  } else {
    // Sem stream (navegador antigo): tudo de uma vez, progresso só no fim.
    const blob = await res.blob()
    partes.push(blob)
    feito = blob.size
    onProgresso(feito, total)
  }

  if (total !== null && feito !== total) {
    const err = new Error('Download incompleto') as Error & { status?: number; detail?: unknown }
    err.detail = `O arquivo chegou incompleto (${feito} de ${total} bytes) — tente de novo.`
    throw err
  }
  const blob = new Blob(partes, { type: 'application/octet-stream' })
  ;(amb.entregar ?? entregarPadrao)(blob, nome)
  return { nome, total: feito, sha256: res.headers.get('x-orquestra-sha256') }
}
