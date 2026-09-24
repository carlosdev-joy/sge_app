// A entrada da tela /agentes: os agentes liberados em cards, para o usuário
// escolher com quem conversar.
//
// Tela de OPERAÇÃO — escolher rápido e sem surpresa, não uma vitrine. Cada card
// diz o que o agente consulta (DataStage, banco, só conversa) ANTES de entrar,
// marca o último usado e a conversa em andamento. Sem coreografia de entrada:
// o movimento é só resposta ao gesto (hover/foco/toque), e some com
// `prefers-reduced-motion`.
//
// A ordem é a do catálogo: nada é reordenado por uso (regra da casa: sem
// pedido claro, os objetos não trocam de lugar). A busca só aparece quando há
// agentes suficientes para precisar dela.
import { useId, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowRight, Bot, Database, MessagesSquare, Search, Workflow } from 'lucide-react'
import type { AgenteCatalogo, Capacidade } from '../../lib/agentes'
import { ROTULO_CAPACIDADE, capacidadesDoAgente, filtrarAgentes } from '../../lib/agentes'

/** A partir de quantos agentes a busca aparece. */
const BUSCA_A_PARTIR_DE = 6

const ICONE: Record<Capacidade, ReactNode> = {
  datastage: <Workflow className="w-[18px] h-[18px]" aria-hidden="true" />,
  banco: <Database className="w-[18px] h-[18px]" aria-hidden="true" />,
  conversa: <MessagesSquare className="w-[18px] h-[18px]" aria-hidden="true" />,
}

// Tom do ícone pelo que o agente CONSULTA — o único lugar com cor no card.
const TOM: Record<Capacidade, string> = {
  datastage: 'bg-[#1A5FA8]/10 text-[#1A5FA8] dark:bg-blue-400/15 dark:text-blue-300',
  banco: 'bg-emerald-600/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300',
  conversa: 'bg-canvas text-dim border border-edge',
}

export interface InfoDoCard {
  /** Mensagens da conversa guardada neste navegador (0 = nenhuma). */
  mensagensEmAndamento: number
  ultimo: boolean
}

export function GaleriaAgentes({ agentes, info, onEscolher, aviso }: {
  agentes: AgenteCatalogo[]
  info: (agenteId: string) => InfoDoCard
  onEscolher: (agenteId: string) => void
  /** Aviso acima dos cards (ex.: gateway sem cadastro) — a escolha continua livre. */
  aviso?: ReactNode
}) {
  const [termo, setTermo] = useState('')
  const idBusca = useId()
  const comBusca = agentes.length >= BUSCA_A_PARTIR_DE
  const visiveis = useMemo(() => (comBusca ? filtrarAgentes(agentes, termo) : agentes), [agentes, termo, comBusca])

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-5 max-w-6xl" data-agentes-galeria>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Bot className="w-5 h-5 text-[#1A5FA8] dark:text-blue-400" aria-hidden="true" />
            Agentes
          </h1>
          <p className="text-sm text-dim mt-0.5 max-w-[65ch]">
            Escolha com quem conversar. Cada agente consulta só o que foi liberado para ele.
          </p>
        </div>
        {comBusca && (
          <div className="relative w-full sm:w-72">
            <label htmlFor={idBusca} className="sr-only">Buscar agente</label>
            <Search className="w-4 h-4 text-dim absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                    aria-hidden="true" />
            <input
              id={idBusca}
              type="search"
              value={termo}
              onChange={e => setTermo(e.target.value)}
              onKeyDown={e => {
                // Um resultado só: Enter já entra nele.
                if (e.key === 'Enter' && visiveis.length === 1) onEscolher(visiveis[0].id)
              }}
              placeholder="Buscar agente…"
              className="w-full h-9 rounded-md border border-edge bg-panel text-ink text-sm pl-8 pr-3
                         placeholder:text-dim focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]"
              data-agentes-busca
            />
          </div>
        )}
      </header>

      {aviso}

      {visiveis.length === 0 ? (
        <p className="text-sm text-dim py-8 text-center" data-agentes-busca-vazia>
          Nenhum agente com “{termo.trim()}”. Tente outra palavra — o nome, o assunto ou o tipo (DataStage, banco, conversa).
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Agentes liberados para você">
          {visiveis.map(ag => (
            <li key={ag.id} className="flex">
              <CardAgente agente={ag} info={info(ag.id)} onEscolher={() => onEscolher(ag.id)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function CardAgente({ agente, info, onEscolher }: {
  agente: AgenteCatalogo
  info: InfoDoCard
  onEscolher: () => void
}) {
  const caps = capacidadesDoAgente(agente)
  const principal = caps[0]
  const andamento = info.mensagensEmAndamento
  return (
    <button
      type="button"
      onClick={onEscolher}
      data-agentes-card={agente.id}
      className="group w-full text-left rounded-xl border border-edge bg-panel p-4 flex flex-col gap-3 min-h-[9.5rem]
                 shadow-[0_1px_2px_rgba(15,23,42,0.06)]
                 transition-[transform,box-shadow,border-color] duration-200 ease-out
                 hover:-translate-y-0.5 hover:border-[#1A5FA8]/50 hover:shadow-[0_10px_24px_-14px_rgba(15,23,42,0.45)]
                 hover:dark:border-blue-400/50
                 active:translate-y-0 active:shadow-[0_1px_2px_rgba(15,23,42,0.06)]
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8] focus-visible:ring-offset-2
                 focus-visible:ring-offset-canvas motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <span className="flex items-start gap-3 w-full">
        <span className={`shrink-0 w-9 h-9 rounded-lg grid place-items-center ${TOM[principal]}`}>
          {ICONE[principal]}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold text-ink leading-snug line-clamp-2 break-words">{agente.nome}</span>
          {info.ultimo && (
            <span className="block text-[11px] text-dim mt-0.5" data-agentes-card-ultimo>usado por último</span>
          )}
        </span>
        <ArrowRight
          className="w-4 h-4 mt-1 shrink-0 text-dim transition-[transform,color,opacity] duration-200 ease-out
                     opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 group-hover:text-[#1A5FA8]
                     group-hover:dark:text-blue-300 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
          aria-hidden="true"
        />
      </span>

      <span className="text-sm text-dim leading-relaxed line-clamp-3">
        {agente.descricao}
      </span>

      <span className="mt-auto flex flex-wrap items-center gap-1.5 w-full">
        {caps.map(c => (
          <span key={c} className="inline-flex items-center h-5 px-1.5 rounded border border-edge text-[11px] text-ink"
                data-agentes-card-capacidade={c}>
            {ROTULO_CAPACIDADE[c]}
          </span>
        ))}
        {agente.curador && (
          <span className="inline-flex items-center h-5 px-1.5 rounded border border-edge text-[11px] text-dim">
            curadoria
          </span>
        )}
        {andamento > 0 && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-dim" data-agentes-card-andamento>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" aria-hidden="true" />
            {andamento === 1 ? 'conversa em andamento' : `conversa em andamento · ${andamento} mensagens`}
          </span>
        )}
      </span>
    </button>
  )
}

/** Três cards "em branco" enquanto o catálogo carrega — mesmo tamanho dos reais. */
export function GaleriaCarregando() {
  return (
    <div className="p-4 sm:p-6 flex flex-col gap-5 max-w-6xl" role="status" aria-busy="true"
         aria-label="Carregando agentes" data-agentes-galeria-carregando>
      <div className="h-7 w-40 rounded bg-edge/60 motion-safe:animate-pulse" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map(i => (
          <div key={i} className="rounded-xl border border-edge bg-panel p-4 min-h-[9.5rem] flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-edge/60 motion-safe:animate-pulse" />
              <div className="h-4 w-1/2 rounded bg-edge/60 motion-safe:animate-pulse" />
            </div>
            <div className="h-3 w-full rounded bg-edge/50 motion-safe:animate-pulse" />
            <div className="h-3 w-4/5 rounded bg-edge/50 motion-safe:animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  )
}
