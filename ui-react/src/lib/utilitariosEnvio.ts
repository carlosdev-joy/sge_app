// Upload de um arquivo do computador do usuário para o servidor (spec
// docs/spec-utilitarios-transferencia.md, F4).
//
// ⚠️ Por que `XMLHttpRequest` e não `fetch`: o `fetch` não expõe progresso de
// ENVIO, e 50 MB sem barra é "travou?". O XHR manda o `File` como corpo cru
// (`application/octet-stream`, o contrato da F3 — sem multipart), com o
// `Authorization` do token, e devolve o gesto de cancelar (`abort`).
//
// A resposta segue o shape de erro do `apiFetch` (`status` + `detail`), para a
// mesma tradução de erros. Corpo que não é JSON (o 502/413 em HTML do nginx)
// vira `detail` ausente — a frase sai pelo status. O 401 expira a sessão como
// no `apiFetchBruto`.
//
// O ambiente (`criarXhr`, `token`, `aoExpirar`) é injetável como em
// `lib/copiar.ts`: a bancada de node não tem XHR nem localStorage.
import { BASE, currentToken, expirarSessao, type ErroApi } from './api'
import { urlEnviar, type PedidoEnvio, type ResultadoEnvio } from './utilitariosTransferencia'

/** O pedaço de XMLHttpRequest que o envio usa (a bancada injeta um fake). */
export interface XhrEnvio {
  open(metodo: string, url: string): void
  setRequestHeader(nome: string, valor: string): void
  send(corpo: Blob): void
  abort(): void
  upload: { onprogress: ((ev: { loaded: number; total: number; lengthComputable: boolean }) => void) | null }
  onload: (() => void) | null
  onerror: (() => void) | null
  onabort: (() => void) | null
  readonly status: number
  readonly responseText: string
}

export interface AmbienteEnvio {
  criarXhr?: () => XhrEnvio
  token?: () => string | null
  aoExpirar?: () => void
}

export interface EnvioEmCurso {
  promessa: Promise<ResultadoEnvio>
  /** Aborta o XHR; a promessa rejeita com `cancelado: true`. */
  cancelar: () => void
}

export type ErroEnvioTransporte = ErroApi & { cancelado?: boolean }
export type ProgressoEnvio = (enviado: number, total: number) => void

function erroDe(status: number, corpo: unknown, mensagemPadrao?: string): ErroEnvioTransporte {
  const detail = corpo && typeof corpo === 'object' && 'detail' in corpo ? (corpo as { detail: unknown }).detail : undefined
  const err = new Error(typeof detail === 'string' ? detail : (mensagemPadrao ?? `${status}`)) as ErroEnvioTransporte
  err.status = status
  err.detail = detail
  return err
}

function corpoJson(texto: string): unknown {
  if (!texto) return null
  try {
    return JSON.parse(texto)
  } catch {
    return null   // HTML do nginx, texto solto: sem `detail`
  }
}

/** Dispara o envio e devolve a promessa do resultado mais o gesto de cancelar. */
export function enviarArquivo(
  pedido: PedidoEnvio, arquivo: Blob, onProgresso: ProgressoEnvio, amb: AmbienteEnvio = {},
): EnvioEmCurso {
  // O XHR real é maior que `XhrEnvio` (e o `onprogress` dele é contravariante
  // no evento): o cast diz que só o pedaço da interface é usado.
  const xhr: XhrEnvio = (amb.criarXhr ?? (() => new XMLHttpRequest() as unknown as XhrEnvio))()
  const promessa = new Promise<ResultadoEnvio>((resolve, reject) => {
    xhr.open('PUT', `${BASE}${urlEnviar(pedido)}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    const token = (amb.token ?? currentToken)()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = ev => {
      onProgresso(ev.loaded, ev.lengthComputable ? ev.total : arquivo.size)
    }
    xhr.onload = () => {
      const status = xhr.status
      const corpo = corpoJson(xhr.responseText)
      if (status === 401) {
        ;(amb.aoExpirar ?? expirarSessao)()
        reject(erroDe(status, corpo, 'Unauthorized'))
        return
      }
      if (status >= 200 && status < 300) {
        resolve(corpo as ResultadoEnvio)
        return
      }
      reject(erroDe(status, corpo))
    }
    xhr.onerror = () => {
      // Sem status: falha de rede (a frase vem da tradução, não do navegador).
      reject(new Error('Falha de rede no envio') as ErroEnvioTransporte)
    }
    xhr.onabort = () => {
      const err = new Error('Envio cancelado') as ErroEnvioTransporte
      err.cancelado = true
      reject(err)
    }
    xhr.send(arquivo)
  })
  return { promessa, cancelar: () => xhr.abort() }
}
