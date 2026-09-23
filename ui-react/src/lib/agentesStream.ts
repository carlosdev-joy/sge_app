/**
 * Conversa com o agente pelo endpoint de STREAM (`text/event-stream`), com
 * eventos de progresso — spec docs/spec-agentes-feedback-progresso.md.
 *
 * `fetch` + `ReadableStream`, não `EventSource`: o `EventSource` só faz GET e
 * não manda o `Authorization` — e a pergunta vai no corpo de um POST.
 *
 * Erro ANTES de o stream abrir (403, 404 de conversa alheia, 503 do agente
 * desligado, 422) chega pelo `apiFetchBruto` com o mesmo shape de sempre
 * (`status` + `detail`), e a tela trata como tratava. Erro DEPOIS de aberto
 * vem como evento `{tipo: 'erro', detail}` e é relançado no mesmo shape.
 */
import { apiFetchBruto } from './api'
import type { ErroApi } from './api'
import type { RespostaConversa } from './agentes'
import { lerEventosSSE } from './agentes'

/** A API ainda não tem a rota de stream (a `dist/` subiu antes da API):
 *  quem chama volta ao endpoint JSON. Um 404 de CONVERSA traz `detail` em
 *  objeto (`{code}`) e não é confundido com rota ausente. */
export function rotaStreamAusente(e: unknown): boolean {
  const err = e as ErroApi | null | undefined
  return (err?.status === 404 && err?.detail === 'Not Found') || err?.status === 405
}

function erroDoEvento(detail: unknown): ErroApi {
  const d = detail as { message?: unknown } | null
  const msg = d && typeof d.message === 'string' ? d.message : 'Não foi possível concluir a resposta.'
  const err = new Error(msg) as ErroApi
  err.detail = detail
  return err
}

/**
 * Envia a pergunta e lê o stream até a resposta final.
 *
 * `onStatus` recebe cada frase de progresso. `abandonado()` é consultado a
 * cada pedaço: se a tela trocou de conversa, a leitura para e devolve `null`
 * — o servidor termina a rodada e grava do mesmo jeito (a resposta aparece
 * ao retomar a conversa).
 */
export async function conversarPorStream(
  agenteId: string,
  corpo: string,
  onStatus: (texto: string) => void,
  abandonado: () => boolean,
): Promise<RespostaConversa | null> {
  const res = await apiFetchBruto(`/agentes/${agenteId}/conversar/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: corpo,
  })
  if (!res.body) throw new Error('O navegador não entregou a resposta em partes — tente de novo.')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let acumulado = ''
  try {
    for (;;) {
      if (abandonado()) return null
      const { done, value } = await reader.read()
      if (done) break
      acumulado += decoder.decode(value, { stream: true })
      const { eventos, resto } = lerEventosSSE(acumulado)
      acumulado = resto
      for (const ev of eventos) {
        if (abandonado()) return null
        if (ev.tipo === 'status') onStatus(ev.texto)
        else if (ev.tipo === 'resposta') return ev
        else if (ev.tipo === 'erro') throw erroDoEvento(ev.detail)
      }
    }
  } finally {
    reader.cancel().catch(() => { /* já terminou */ })
  }
  throw new Error('A conexão terminou antes da resposta. A conversa foi gravada — abra o histórico para vê-la.')
}
