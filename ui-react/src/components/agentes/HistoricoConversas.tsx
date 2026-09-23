// O histórico de conversas do agente (F4): lista, busca e retomada.
//
// Painel lateral, não modal: o operador compara o que perguntou antes com o
// que está perguntando agora, e um modal esconderia justamente isso.
//
// A busca é do SERVIDOR (`?q=`), não filtro no que já veio: a lista traz no
// máximo as 100 conversas mais recentes de 30 dias, e filtrar só o que está
// na tela daria "não encontrei" para uma conversa que existe. `%` e `_`
// digitados são escapados no backend (`escapar_like`).
//
// Visual (ajuste de 23/09): agrupado por dia (Hoje, Ontem, Últimos 7 dias,
// Mais antigas) com o cabeçalho do grupo fixo ao rolar; título INTEIRO, sem
// reticências (antes `truncate` cortava na 1ª linha; o título tem no máximo
// 200 caracteres — `TITULO_MAX`); projeto em etiqueta e hora à
// direita; a conversa aberta com barra de destaque. Painel mais largo e, no
// empilhado (tela estreita), teto de meia tela em vez de 224 px — a lista
// cortada no meio do último item era o defeito relatado.
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, MessageSquare, Search, X } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import type { ConversaResumo, GrupoHistorico } from '../../lib/agentes'
import {
  GRUPOS_HISTORICO, RETENCAO_CONVERSAS_DIAS, grupoDaConversa, horaOuDia, mensagemDeErro,
} from '../../lib/agentes'

interface Props {
  agenteId: string
  /** Conversa aberta agora — destacada na lista. */
  conversaAtual: string | null
  onRetomar: (conversaId: string) => void
  onFechar: () => void
}

export function HistoricoConversas({ agenteId, conversaAtual, onRetomar, onFechar }: Props) {
  const [busca, setBusca] = useState('')
  // `busca` entra na queryKey: cada termo é uma consulta própria, e o
  // react-query guarda o resultado de cada uma (voltar para um termo já
  // digitado não bate no servidor de novo).
  const q = useQuery<{ conversas: ConversaResumo[] }>({
    queryKey: ['agentes-conversas', agenteId, busca.trim()],
    queryFn: () => {
      const p = new URLSearchParams({ agente: agenteId })
      if (busca.trim()) p.set('q', busca.trim())
      return apiFetch(`/agentes/conversas?${p}`)
    },
  })

  const conversas = useMemo(() => q.data?.conversas ?? [], [q.data])
  // A API já devolve da mais recente para a mais antiga: agrupar preserva a ordem.
  const grupos = useMemo(() => {
    const mapa = new Map<GrupoHistorico, ConversaResumo[]>()
    for (const c of conversas) {
      const g = grupoDaConversa(c.ultima_msg_em)
      mapa.set(g, [...(mapa.get(g) ?? []), c])
    }
    return GRUPOS_HISTORICO.filter(g => mapa.has(g)).map(g => ({ grupo: g, itens: mapa.get(g)! }))
  }, [conversas])

  return (
    <aside
      // `shrink-0` só a partir de `sm`: abaixo disso o contêiner é
      // flex-COLUNA, e um aside que não encolhe empurra o chat (que é
      // `flex-1` com basis 0) para altura zero — some da tela. No empilhado
      // ele ganha um teto próprio e rola por dentro. Achado da revisão
      // adversarial da F4.
      className="w-full sm:w-80 sm:shrink-0 max-h-[50vh] sm:max-h-none flex flex-col
                 bg-panel border border-edge rounded-xl shadow-sm min-h-0"
      aria-label="Histórico de conversas"
      data-agentes-historico
    >
      <header className="flex flex-col gap-2.5 px-3 pt-3 pb-3 border-b border-edge">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <History className="w-4 h-4 text-dim" aria-hidden="true" />
            Conversas
            {conversas.length > 0 && (
              <span className="text-[11px] font-medium text-dim bg-canvas border border-edge rounded-full px-1.5 py-px">
                {conversas.length}
              </span>
            )}
          </h2>
          <button type="button" onClick={onFechar} aria-label="Fechar histórico"
                  className="rounded-md p-1 text-dim hover:text-ink hover:bg-canvas
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]">
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 text-dim absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            aria-label="Buscar nas conversas"
            placeholder="Buscar pelo título…"
            className="w-full rounded-lg border border-edge bg-canvas text-ink placeholder:text-dim
                       pl-8 pr-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]"
          />
        </div>
      </header>

      {/* `scroll-pt-9`: ao navegar por teclado (Shift+Tab), o item em foco para
          ABAIXO do cabeçalho fixo do grupo — sem isto o cabeçalho cobria o anel
          de foco (nota da revisão). */}
      <div className="flex-1 min-h-0 overflow-y-auto scroll-pt-9 px-2 pb-2" aria-live="polite" aria-busy={q.isFetching}>
        {q.isLoading && (
          <ul className="flex flex-col gap-2 pt-3" aria-hidden="true">
            {[0, 1, 2].map(i => <li key={i} className="h-14 rounded-lg bg-canvas animate-pulse" />)}
          </ul>
        )}

        {q.isError && (
          <p className="text-sm text-dim px-2 py-6 text-center">
            {mensagemDeErro(q.error, 'Não foi possível carregar o histórico.')}
          </p>
        )}

        {!q.isLoading && !q.isError && conversas.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-3 py-8 text-center" data-agentes-historico-vazio>
            <MessageSquare className="w-6 h-6 text-dim" aria-hidden="true" />
            <p className="text-sm text-dim">
              {busca.trim()
                ? 'Nenhuma conversa com esse termo.'
                : `Nenhuma conversa nos últimos ${RETENCAO_CONVERSAS_DIAS} dias.`}
            </p>
          </div>
        )}

        {grupos.map(({ grupo, itens }) => (
          <section key={grupo} aria-label={grupo} data-agentes-historico-grupo={grupo}>
            <h3 className="sticky top-0 z-[1] bg-panel px-2 pt-3 pb-1.5 text-[11px] font-semibold uppercase
                           tracking-wide text-dim">
              {grupo}
            </h3>
            <ul className="flex flex-col gap-1">
              {itens.map(c => {
                const atual = c.conversa_id === conversaAtual
                const titulo = c.titulo?.trim()
                return (
                  <li key={c.conversa_id}>
                    <button
                      type="button"
                      onClick={() => onRetomar(c.conversa_id)}
                      aria-current={atual ? 'true' : undefined}
                      className={`group relative w-full text-left rounded-lg px-3 py-2.5 border transition-colors
                                  focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]
                                  ${atual
                                    ? 'bg-canvas border-edge'
                                    : 'border-transparent hover:bg-canvas hover:border-edge'}`}
                    >
                      {atual && (
                        <span aria-hidden="true"
                              className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-[#1A5FA8]" />
                      )}
                      <span className={`block text-sm leading-snug break-words
                                        ${titulo ? 'text-ink' : 'text-dim italic'}`}
                            data-agentes-historico-titulo>
                        {titulo || 'Conversa sem título'}
                      </span>
                      <span className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-dim">
                        {c.projeto ? (
                          <span className="truncate font-medium rounded-full border border-edge bg-panel px-1.5 py-px">
                            {c.projeto}
                          </span>
                        ) : <span />}
                        <span className="shrink-0 tabular-nums">{horaOuDia(c.ultima_msg_em)}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>

      <p className="text-[11px] text-dim border-t border-edge px-3 py-2.5">
        As conversas ficam guardadas por {RETENCAO_CONVERSAS_DIAS} dias.
      </p>
    </aside>
  )
}
