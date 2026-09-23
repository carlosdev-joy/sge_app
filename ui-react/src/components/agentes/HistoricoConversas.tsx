// O histórico de conversas do agente (F4): lista, busca e retomada.
//
// Painel lateral, não modal: o operador compara o que perguntou antes com o
// que está perguntando agora, e um modal esconderia justamente isso.
//
// A busca é do SERVIDOR (`?q=`), não filtro no que já veio: a lista traz no
// máximo as 100 conversas mais recentes de 30 dias, e filtrar só o que está
// na tela daria "não encontrei" para uma conversa que existe. `%` e `_`
// digitados são escapados no backend (`escapar_like`).
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, Search, X } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import type { ConversaResumo } from '../../lib/agentes'
import { RETENCAO_CONVERSAS_DIAS, mensagemDeErro, quando } from '../../lib/agentes'

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

  const conversas = q.data?.conversas ?? []

  return (
    <aside
      // `shrink-0` só a partir de `sm`: abaixo disso o contêiner é
      // flex-COLUNA, e um aside que não encolhe empurra o chat (que é
      // `flex-1` com basis 0) para altura zero — some da tela. No empilhado
      // ele ganha um teto próprio e rola por dentro. Achado da revisão
      // adversarial da F4.
      className="w-full sm:w-72 sm:shrink-0 max-h-56 sm:max-h-none flex flex-col gap-3
                 bg-panel border border-edge rounded-lg p-3 shadow-sm min-h-0"
      aria-label="Histórico de conversas"
      data-agentes-historico
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink flex items-center gap-1.5">
          <History className="w-4 h-4 text-dim" aria-hidden="true" />
          Conversas
        </h2>
        <button type="button" onClick={onFechar} aria-label="Fechar histórico"
                className="text-dim hover:text-ink">
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      </header>

      <div className="relative">
        <Search className="w-4 h-4 text-dim absolute left-2 top-1/2 -translate-y-1/2" aria-hidden="true" />
        <input
          value={busca}
          onChange={e => setBusca(e.target.value)}
          aria-label="Buscar nas conversas"
          placeholder="Buscar…"
          className="w-full rounded border border-edge bg-canvas text-ink placeholder:text-dim
                     pl-8 pr-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]"
        />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1" aria-live="polite">
        {q.isLoading && <p className="text-sm text-dim py-4 text-center">Carregando…</p>}

        {q.isError && (
          <p className="text-sm text-dim py-4">
            {mensagemDeErro(q.error, 'Não foi possível carregar o histórico.')}
          </p>
        )}

        {!q.isLoading && !q.isError && conversas.length === 0 && (
          <p className="text-sm text-dim py-4">
            {busca.trim()
              ? 'Nenhuma conversa com esse termo.'
              : `Nenhuma conversa nos últimos ${RETENCAO_CONVERSAS_DIAS} dias.`}
          </p>
        )}

        <ul className="flex flex-col gap-1">
          {conversas.map(c => {
            const atual = c.conversa_id === conversaAtual
            return (
              <li key={c.conversa_id}>
                <button
                  type="button"
                  onClick={() => onRetomar(c.conversa_id)}
                  aria-current={atual ? 'true' : undefined}
                  className={`w-full text-left rounded px-2 py-1.5 text-sm hover:bg-canvas
                              ${atual ? 'bg-canvas ring-1 ring-[#1A5FA8]' : ''}`}
                >
                  <span className="block text-ink truncate">
                    {c.titulo?.trim() || 'Conversa sem título'}
                  </span>
                  <span className="block text-[11px] text-dim">
                    {quando(c.ultima_msg_em)}
                    {c.projeto ? ` · ${c.projeto}` : ''}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>

      <p className="text-[11px] text-dim border-t border-edge pt-2">
        As conversas ficam guardadas por {RETENCAO_CONVERSAS_DIAS} dias.
      </p>
    </aside>
  )
}
