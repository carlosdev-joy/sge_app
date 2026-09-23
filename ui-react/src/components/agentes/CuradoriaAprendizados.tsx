// Curadoria da base de aprendizados do agente (F6).
//
// Só aparece para quem tem `agente_curador` (o catálogo já devolve
// `curador: true`), e a API responde 403 a quem não tem — a aba escondida é
// conveniência, a regra está no backend (critério 4 da F6).
//
// O curador decide com a EVIDÊNCIA à vista: é ela que diz de onde o
// aprendizado veio. O modelo nunca a recebe — no contexto dele vão só o
// título e o corpo, e só dos VALIDADOS (critério 3).
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import type { AcaoAprendizado, Aprendizado, EstadoAprendizado } from '../../lib/agentes'
import {
  ACOES_APRENDIZADO, ESTADOS_APRENDIZADO, ORIGEM_APRENDIZADO, ROTULO_ACAO, TIPOS_APRENDIZADO,
  codigoDoErro, dataCurta, mensagemDeErro, quando,
} from '../../lib/agentes'
import { toast } from '../ui/Toast'

export function CuradoriaAprendizados({ agenteId, onFechar }: { agenteId: string; onFechar: () => void }) {
  const qc = useQueryClient()
  const [estado, setEstado] = useState<EstadoAprendizado>('rascunho')
  // A fila é POR AGENTE (spec admin B2): a rota antiga só atende o DataStage.
  const base = `/agentes/${encodeURIComponent(agenteId)}/aprendizados`

  const lista = useQuery<{ aprendizados: Aprendizado[] }>({
    queryKey: ['agentes-aprendizados', agenteId, estado],
    queryFn: () => apiFetch(`${base}?estado=${estado}`),
  })

  const decidir = useMutation({
    mutationFn: ({ id, acao }: { id: number; acao: AcaoAprendizado }) =>
      apiFetch<{ aprendizado: Aprendizado }>(`${base}/${id}/decidir`, {
        method: 'POST', body: JSON.stringify({ acao }),
      }),
    onSuccess: (_r, v) => toast.success(`${ROTULO_ACAO[v.acao]}: feito.`),
    onError: (e: unknown) => toast.error(codigoDoErro(e) === 'transicao_invalida'
      ? 'Outro curador já decidiu este item — a lista foi atualizada.'
      : mensagemDeErro(e, 'Não foi possível registrar a decisão.')),
    // O item muda de aba: todas as listas ficam defasadas, e um 409 também
    // pede ressincronizar.
    onSettled: () => qc.invalidateQueries({ queryKey: ['agentes-aprendizados'] }),
  })

  const itens = lista.data?.aprendizados ?? []

  return (
    <section className="flex-1 min-h-0 flex flex-col gap-3 bg-panel border border-edge rounded-lg p-3 sm:p-4"
             aria-label="Curadoria dos aprendizados" data-agentes-curadoria>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Curadoria dos aprendizados</h2>
          <p className="text-xs text-dim mt-0.5">
            Só os validados entram no contexto do agente. Sugestões do agente e a semente inicial chegam
            como “a revisar”.
          </p>
        </div>
        <button type="button" onClick={onFechar}
                className="text-[13px] text-[#1A5FA8] dark:text-blue-400 hover:underline">
          voltar à conversa
        </button>
      </div>

      <div role="tablist" aria-label="Estado" className="flex flex-wrap gap-1 border-b border-edge">
        {ESTADOS_APRENDIZADO.map(e => (
          <button
            key={e.estado}
            type="button"
            role="tab"
            aria-selected={estado === e.estado}
            onClick={() => setEstado(e.estado)}
            className={`px-3 py-1.5 text-[13px] -mb-px border-b-2 ${estado === e.estado
              ? 'border-[#1A5FA8] text-ink font-medium'
              : 'border-transparent text-dim hover:text-ink'}`}
          >
            {e.rotulo}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2" aria-live="polite" aria-busy={lista.isFetching}>
        {lista.isLoading && <p className="text-sm text-dim">Carregando…</p>}
        {lista.isError && (
          <p className="text-sm text-dim">{mensagemDeErro(lista.error, 'Não foi possível carregar os aprendizados.')}</p>
        )}
        {!lista.isLoading && !lista.isError && itens.length === 0 && (
          <p className="text-sm text-dim py-4 text-center">Nada aqui.</p>
        )}
        {itens.map(a => (
          <article key={a.id} className="rounded-lg border border-edge bg-canvas px-3 py-2.5 text-sm"
                   data-agentes-aprendizado={a.estado}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-dim">
                  {TIPOS_APRENDIZADO[a.tipo] ?? a.tipo} · {ORIGEM_APRENDIZADO[a.origem] ?? a.origem}
                  {a.usos > 0 && ` · ${a.usos} ocorrência${a.usos > 1 ? 's' : ''}`}
                </p>
                <h3 className="text-ink font-medium break-words mt-0.5">{a.titulo}</h3>
              </div>
              {ACOES_APRENDIZADO[a.estado].length > 0 && (
                <div className="flex gap-2 shrink-0">
                  {ACOES_APRENDIZADO[a.estado].map(acao => (
                    <button
                      key={acao}
                      type="button"
                      disabled={decidir.isPending}
                      onClick={() => decidir.mutate({ id: a.id, acao })}
                      aria-label={`${ROTULO_ACAO[acao]}: ${a.titulo}`}
                      className={acao === 'validar'
                        ? 'rounded-md px-2.5 py-1 text-[13px] font-medium bg-[#1A5FA8] text-white hover:opacity-90 disabled:opacity-50'
                        : 'rounded-md border border-edge bg-panel px-2.5 py-1 text-[13px] text-ink hover:bg-canvas disabled:opacity-50'}
                    >
                      {ROTULO_ACAO[acao]}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="grid gap-2 mt-2 sm:grid-cols-2">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-dim">O que o agente passa a considerar</p>
                <p className="text-ink whitespace-pre-wrap break-words mt-0.5">{a.corpo}</p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-dim">Evidência</p>
                <blockquote className="mt-0.5 border-l-2 border-edge pl-2 font-mono text-[12px] text-ink whitespace-pre-wrap break-words max-h-40 overflow-y-auto"
                            data-agentes-aprendizado-evidencia>
                  {a.evidencia || '—'}
                </blockquote>
              </div>
            </div>
            <p className="text-[11px] text-dim mt-2">
              Criado {quando(a.criado_em)}
              {a.validado_por && ` · decidido por ${a.validado_por} ${quando(a.validado_em)}`}
              {a.revalidar_em && ` · vale até ${dataCurta(a.revalidar_em)}`}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
