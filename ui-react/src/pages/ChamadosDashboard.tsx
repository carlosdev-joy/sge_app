// Aba Dashboard dos Chamados — o painel operacional do dia.
//
// A visão é a descrita em `docs/superpowers/specs/2026-08-28-dashboard-chamados.md`
// (quatro visões, fila ativa, alertas de prazo e a lista do bloco escolhido),
// nas formas da casa: `KpiCard` para o número, `Painel` para a seção e
// `BarrasHorizontais` para magnitude — as mesmas da aba Indicadores ao lado.
//
// ⚠️ NÃO recalcula grupo nenhum no cliente. Os blocos chegam prontos de
// `GET /chamados/dashboard`, já recortados no banco pela MESMA regra da fila
// (`_so_trabalhos`). O painel que roda em produção refaz as contas em
// JavaScript a partir de `GET /chamados`, e é dessa duplicação que nasce um
// painel discordando da fila ao lado — com os dois números parecendo certos.
//
// ⚠️ A aba de produção está QUEBRADA hoje: o `DshPanel` foi injetado à mão num
// bundle que um rebuild posterior deixou órfão, e o que sobrou lê `d.backlog`
// como número enquanto a rota devolve objeto.
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { PageSpinner } from '../components/ui/Spinner'
import { KpiCard, type KpiProps } from '../components/ui/KpiCard'
import { BarrasHorizontais, Painel } from '../components/chamados/graficos'
import {
  AlertCircle, CalendarClock, CheckCircle2, Clock, Inbox, PauseCircle,
  PlayCircle, X,
} from 'lucide-react'
import {
  ORDEM_FILA, ORDEM_PRAZO, bloco, contaPorPrazo, contaPorResponsavel,
  mostraPrazo, rotuloDoPrazo,
  type BlocoDoPainel, type ChamadoDoPainel,
} from '../lib/dashboardChamados'

const VISOES = [
  { id: 'geral', rotulo: 'Geral', ajuda: 'toda a fila ativa' },
  { id: 'proprio', rotulo: 'Meu painel', ajuda: 'os chamados atribuídos a você' },
  { id: 'diaadia', rotulo: 'Dia a dia', ajuda: 'marcados como dia a dia nas work notes' },
  { id: 'iniciativa', rotulo: 'Iniciativas', ajuda: 'marcados como iniciativa' },
] as const

// A cor que o backend manda, traduzida para a paleta do KpiCard. Mapa FECHADO:
// cor que o backend invente cai em `slate` em vez de deixar o cartão sem fundo.
const COR: Record<string, KpiProps['color']> = {
  amber: 'yellow', orange: 'yellow', green: 'green',
  indigo: 'blue', red: 'red', neutral: 'slate',
}

const ICONE: Record<string, React.ReactNode> = {
  backlog: <Inbox size={14} />,
  andamento: <PlayCircle size={14} />,
  pendentes: <PauseCircle size={14} />,
  resolvidas: <CheckCircle2 size={14} />,
  vencem_hoje: <Clock size={14} />,
  vencem_semana: <CalendarClock size={14} />,
  vencidas: <AlertCircle size={14} />,
}

const TOM_PRAZO: Record<string, string> = {
  atrasado: 'text-red-600 dark:text-red-400',
  hoje: 'text-orange-600 dark:text-orange-400',
  'no prazo': 'text-emerald-600 dark:text-emerald-400',
}

/** A lista do bloco aberto. */
function ListaDoBloco({ chamados, comPrazo }: {
  chamados: ChamadoDoPainel[]; comPrazo: boolean
}) {
  if (!chamados.length) {
    return <p className="text-xs text-dim">Nenhum chamado nesta categoria.</p>
  }
  return (
    <ul className="flex flex-col gap-1">
      {chamados.map(c => {
        // Chamado finalizado não mostra prazo: "vencido há 40 dias" num
        // resolvido é ruído que ensina a ignorar o aviso.
        const prazo = comPrazo && mostraPrazo(c.estado_kanban)
          ? rotuloDoPrazo(c.prazo) : null
        return (
          <li key={c.sys_id}
            className="flex items-baseline gap-2 text-xs py-1 border-b border-edge last:border-0">
            <a href={c.url || undefined} target="_blank" rel="noopener noreferrer"
              className="font-mono font-semibold text-blue-600 dark:text-blue-400 shrink-0"
              title="Abrir no ServiceNow">
              {c.numero}
            </a>
            <span className="text-ink truncate flex-1 min-w-0" title={c.titulo || ''}>
              {c.titulo || '(sem título)'}
            </span>
            <span className="text-dim shrink-0 w-36 truncate text-right"
              title={c.atribuido_a || 'sem responsável'}>
              {c.atribuido_a || 'sem responsável'}
            </span>
            {/* O prazo em PALAVRAS, não só em cor. */}
            {prazo && (
              <span className={`shrink-0 w-24 text-right tabular-nums ${TOM_PRAZO[prazo.tom]}`}>
                {prazo.texto}
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export default function ChamadosDashboard() {
  const [visao, setVisao] = useState<string>('geral')
  const [aberto, setAberto] = useState<string | null>(null)

  const { data, isLoading, isError, error } = useQuery<Record<string, unknown>>({
    queryKey: ['chamados-dashboard', visao],
    queryFn: () => apiFetch(`/chamados/dashboard?visao=${visao}`),
    staleTime: 0,
  })

  const blocos = useMemo(() => {
    const mapa: Record<string, BlocoDoPainel> = {}
    for (const k of [...ORDEM_FILA, ...ORDEM_PRAZO]) {
      const b = bloco(data, k)
      if (b) mapa[k] = b
    }
    return mapa
  }, [data])

  if (isLoading) return <PageSpinner />

  if (isError) {
    return (
      <div className="border rounded-lg px-4 py-3 text-[12px] bg-red-50 dark:bg-red-900/20
        border-red-200 dark:border-red-800 text-red-800 dark:text-red-200">
        Não foi possível carregar o painel: {(error as Error).message}
      </div>
    )
  }

  // Espelho indisponível é DIFERENTE de fila vazia. Sem dizer qual dos dois,
  // "0 em tudo" parece uma equipe em dia.
  if (data?.migration_ausente) {
    return (
      <div className="border rounded-lg px-4 py-3 text-[12px] bg-amber-50
        dark:bg-yellow-900/20 border-amber-200 dark:border-yellow-800
        text-amber-800 dark:text-yellow-200">
        O espelho de chamados está indisponível — os números não seriam
        confiáveis, então não são mostrados. Verifique em Admin &gt; ServiceNow.
      </div>
    )
  }

  const total = Number(data?.total_fila ?? 0)
  const selecionado = aberto ? blocos[aberto] : null
  const backlog = blocos.backlog?.chamados ?? []
  const andamento = blocos.andamento?.chamados ?? []
  const fluxo = (data?.fluxo_hoje ?? {}) as { entradas?: number; saidas?: number }

  const cartao = (k: string) => {
    const b = blocos[k]
    if (!b) return null
    return (
      <KpiCard key={k} label={b.label} value={b.total} icon={ICONE[k]}
        color={COR[b.cor] ?? 'slate'}
        sub={aberto === k ? 'clique para fechar' : 'clique para ver a lista'}
        onClick={() => setAberto(aberto === k ? null : k)} />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {VISOES.map(v => (
          <button key={v.id} type="button" title={v.ajuda}
            onClick={() => { setVisao(v.id); setAberto(null) }}
            aria-pressed={visao === v.id}
            className={`px-2.5 py-1 rounded-md text-xs border transition
              ${visao === v.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-canvas text-dim border-edge hover:text-ink'}`}>
            {v.rotulo}
          </button>
        ))}
        <span className="ml-auto text-xs text-dim">
          na fila: <strong className="text-ink tabular-nums">{total}</strong>
        </span>
      </div>

      <Painel titulo="Fila ativa"
        descricao="O que está em aberto agora. Clique num cartão para ver a lista.">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {ORDEM_FILA.map(cartao)}
        </div>
      </Painel>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Painel titulo="Backlog por responsável"
          descricao="Quem já tem dono e quanto ainda espera alguém pegar.">
          <BarrasHorizontais total={backlog.length}
            itens={contaPorResponsavel(backlog)} />
        </Painel>

        <Painel titulo="Em andamento por prazo"
          descricao="«Sem prazo» é categoria própria: somado ao que está dentro, faria o gráfico dizer que está tudo sob controle.">
          <BarrasHorizontais total={andamento.length}
            itens={contaPorPrazo(andamento)} />
        </Painel>

        <Painel titulo="Fluxo de hoje"
          descricao="Entradas e saídas do dia — a fila cresce ou diminui.">
          <BarrasHorizontais
            total={(fluxo.entradas ?? 0) + (fluxo.saidas ?? 0)}
            itens={[
              { rotulo: 'entradas', valor: fluxo.entradas ?? 0 },
              { rotulo: 'saídas', valor: fluxo.saidas ?? 0 },
            ]} />
        </Painel>
      </div>

      <Painel titulo="Alertas de prazo"
        descricao="O que vence hoje, esta semana, e o que já passou.">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {ORDEM_PRAZO.map(cartao)}
        </div>
      </Painel>

      {selecionado && (
        <Painel titulo={`${selecionado.label} · ${selecionado.total}`}
          descricao="A lista do cartão selecionado. O número abre no ServiceNow.">
          <div className="flex justify-end -mt-8">
            <button type="button" onClick={() => setAberto(null)}
              className="text-dim hover:text-ink" title="Fechar a lista">
              <X size={14} />
            </button>
          </div>
          <ListaDoBloco chamados={selecionado.chamados}
            comPrazo={(ORDEM_PRAZO as readonly string[]).includes(aberto as string)} />
        </Painel>
      )}
    </div>
  )
}
