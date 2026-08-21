// Indicadores dos chamados — a aba da gestão.
//
// SVG puro, sem biblioteca (padrão da casa: o Gantt do Dashboard e as
// sparkbars do Admin fazem igual). Quatro leituras, cada uma com a forma que
// o trabalho do dado pede:
//
//   aging por faixa      → barras horizontais, escala sequencial de uma hue
//                          (magnitude ordenada: mais velho = mais escuro)
//   tipo × estado        → heatmap, mesma escala sequencial (grade de magnitude)
//   entradas × saídas    → duas linhas categóricas (identidade importa: são
//                          séries distintas, não magnitudes de uma coisa só)
//   carga por responsável → barras horizontais sequenciais (ranking)
//
// A paleta é a validada: azul #2a78d6 / laranja #eb6834 (claro) e #3987e5 /
// #d95926 (escuro). O par passou os seis testes nos dois modos — banda de
// luminosidade, piso de croma, separação sob daltonismo (ΔE 24.7 protan claro,
// 26.8 escuro), piso de visão normal e contraste com a superfície.
//
// Duas regras que valem em todos os quatro: nenhuma percentagem aparece sem o
// "x de y" ao lado, e nenhuma série é identificada só por cor — há legenda e
// rótulo direto.
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { PageSpinner } from '../components/ui/Spinner'

interface FaixaAging { faixa: string; total: number }
interface Celula { tipo: string; estado: string; total: number }
interface DiaFluxo { dia: string; entradas: number; saidas: number }
interface Carga { responsavel: string; total: number }

interface PorTipoDemanda { tipo: string; total: number }
interface PorCategoria { categoria: string; total: number }

export interface RespostaIndicadores {
  aging: FaixaAging[]
  tipo_estado: { tipos: string[]; estados: string[]; celulas: Celula[] }
  fluxo: DiaFluxo[]
  carga: Carga[]
  total_ativos: number
  responsaveis_ocultos: number
  migration_ausente: boolean
  // Agregações portadas do painel da estação (F3).
  por_tipo_demanda: PorTipoDemanda[]
  por_categoria: PorCategoria[]
  sem_categoria: number
  resolvidos_periodo: number
  dias_historico: number
}

export interface Resolvido {
  numero: string
  tipo: string
  titulo: string | null
  atribuido_a: string
  demandante: string
  tipo_demanda: string
  categoria_diaadia: string
  encerrado_em: string | null
  url: string | null
  dias_ate_resolver: number | null
}

const ROTULO_TIPO: Record<string, string> = {
  incident: 'Incidente', ritm: 'RITM', task: 'Tarefa', change: 'Mudança',
}
const ROTULO_ESTADO: Record<string, string> = {
  novo: 'Novo', andamento: 'Em andamento', aguardando: 'Aguardando',
  resolvido: 'Resolvido', outros: 'Outros',
}

// Rampa sequencial de uma hue (azul), clara → escura. Mais escuro = mais alto.
const RAMPA = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#2a78d6', '#1c5cab']

// Séries categóricas do fluxo. Slots 1 e 2 da paleta validada.
const SERIE_ENTRADAS = '#2a78d6'
const SERIE_SAIDAS = '#eb6834'

function passoRampa(valor: number, maximo: number): string {
  if (maximo <= 0 || valor <= 0) return RAMPA[0]
  const i = Math.min(RAMPA.length - 1,
    Math.max(1, Math.round((valor / maximo) * (RAMPA.length - 1))))
  return RAMPA[i]
}

// "3 de 12 (25%)" — a regra da casa: percentagem nunca sozinha.
function xDeY(parte: number, total: number): string {
  if (!total) return `${parte}`
  return `${parte} de ${total} (${Math.round((parte / total) * 100)}%)`
}

function Painel({ titulo, descricao, children }: {
  titulo: string; descricao: string; children: React.ReactNode
}) {
  return (
    <section className="bg-panel border border-edge rounded-lg p-4 flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
        <p className="text-[11px] text-dim">{descricao}</p>
      </div>
      {children}
    </section>
  )
}

/** Barras horizontais com rótulo direto — serve aging e carga. */
function BarrasHorizontais({ itens, total }: {
  itens: { rotulo: string; valor: number }[]; total: number
}) {
  const maximo = Math.max(1, ...itens.map(i => i.valor))
  if (itens.length === 0) {
    return <p className="text-xs text-dim">nenhum chamado na fila</p>
  }
  return (
    <div className="flex flex-col gap-1.5">
      {itens.map(i => (
        <div key={i.rotulo} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 text-dim truncate" title={i.rotulo}>
            {i.rotulo}
          </span>
          <div className="flex-1 min-w-0 h-4 flex items-center">
            <svg width="100%" height="16" role="img"
              aria-label={`${i.rotulo}: ${xDeY(i.valor, total)}`}>
              {/* 4px de raio na ponta do dado, ancorada na linha de base */}
              <rect x="0" y="3" rx="4" ry="4" height="10"
                width={`${(i.valor / maximo) * 100}%`}
                fill={passoRampa(i.valor, maximo)} />
            </svg>
          </div>
          {/* Valor em token de texto, nunca na cor da série */}
          <span className="w-28 shrink-0 text-right text-ink tabular-nums">
            {xDeY(i.valor, total)}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Heatmap tipo × estado. Grade de magnitude → uma hue sequencial. */
function MapaTipoEstado({ dados, total }: {
  dados: RespostaIndicadores['tipo_estado']; total: number
}) {
  const valor = (tipo: string, estado: string) =>
    dados.celulas.find(c => c.tipo === tipo && c.estado === estado)?.total ?? 0
  const maximo = Math.max(1, ...dados.celulas.map(c => c.total))
  if (dados.tipos.length === 0) {
    return <p className="text-xs text-dim">nenhum chamado na fila</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-separate" style={{ borderSpacing: '2px' }}>
        <thead>
          <tr>
            <th className="text-left font-normal text-dim px-1" />
            {dados.estados.map(e => (
              <th key={e} className="font-normal text-dim px-1.5 py-1 text-[10px]
                uppercase tracking-wide whitespace-nowrap">
                {ROTULO_ESTADO[e] ?? e}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dados.tipos.map(t => (
            <tr key={t}>
              <td className="text-dim pr-2 whitespace-nowrap">{ROTULO_TIPO[t] ?? t}</td>
              {dados.estados.map(e => {
                const v = valor(t, e)
                return (
                  <td key={e} className="p-0">
                    {/* O número vai DENTRO da célula: cor sozinha não é leitura,
                        e a tabela também é a "table view" de acessibilidade. */}
                    <div className="w-16 h-9 rounded flex items-center justify-center
                      tabular-nums"
                      style={{
                        background: v > 0 ? passoRampa(v, maximo) : 'transparent',
                        color: v > maximo * 0.6 ? '#fff' : undefined,
                        border: v > 0 ? 'none' : '1px dashed var(--color-edge, #ddd)',
                      }}
                      title={`${ROTULO_TIPO[t] ?? t} · ${ROTULO_ESTADO[e] ?? e}: ${xDeY(v, total)}`}>
                      <span className={v > maximo * 0.6 ? '' : 'text-ink'}>{v}</span>
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Entradas × saídas: duas séries distintas → duas linhas categóricas. */
function FluxoDiario({ dias }: { dias: DiaFluxo[] }) {
  if (dias.length === 0) return <p className="text-xs text-dim">sem dados no período</p>
  const L = 28, R = 8, T = 8, B = 20, A = 120, C = 520
  const maximo = Math.max(1, ...dias.flatMap(d => [d.entradas, d.saidas]))
  const x = (i: number) => L + (i / Math.max(1, dias.length - 1)) * (C - L - R)
  const y = (v: number) => T + (1 - v / maximo) * (A - T - B)
  const linha = (campo: 'entradas' | 'saidas') =>
    dias.map((d, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(d[campo]).toFixed(1)}`).join(' ')
  const totalEnt = dias.reduce((s, d) => s + d.entradas, 0)
  const totalSai = dias.reduce((s, d) => s + d.saidas, 0)
  const saldo = totalEnt - totalSai

  return (
    <div className="flex flex-col gap-2">
      {/* Legenda SEMPRE presente com 2 séries — identidade nunca só por cor */}
      <div className="flex items-center gap-4 text-[11px] text-dim">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded" style={{ background: SERIE_ENTRADAS }} />
          Entradas ({totalEnt})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded" style={{ background: SERIE_SAIDAS }} />
          Saídas ({totalSai})
        </span>
        <span className="text-ink">
          saldo {saldo > 0 ? '+' : ''}{saldo}
          {saldo > 0 ? ' — a fila cresceu' : saldo < 0 ? ' — a fila diminuiu' : ' — estável'}
        </span>
      </div>
      <svg viewBox={`0 0 ${C} ${A}`} className="w-full h-auto" role="img"
        aria-label={`Entradas e saídas nos últimos ${dias.length} dias: ${totalEnt} entradas, ${totalSai} saídas`}>
        {/* Grade recessiva */}
        {[0, 0.5, 1].map(f => (
          <line key={f} x1={L} x2={C - R} y1={y(maximo * f)} y2={y(maximo * f)}
            stroke="currentColor" strokeWidth="1" className="text-edge" opacity="0.5" />
        ))}
        <text x="2" y={y(maximo) + 4} className="fill-current text-dim" fontSize="9">{maximo}</text>
        <text x="2" y={y(0) + 4} className="fill-current text-dim" fontSize="9">0</text>
        <path d={linha('entradas')} fill="none" stroke={SERIE_ENTRADAS} strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" />
        <path d={linha('saidas')} fill="none" stroke={SERIE_SAIDAS} strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" />
        {dias.map((d, i) => (
          <g key={d.dia}>
            <circle cx={x(i)} cy={y(d.entradas)} r="3" fill={SERIE_ENTRADAS}>
              <title>{`${d.dia}: ${d.entradas} entrada(s)`}</title>
            </circle>
            <circle cx={x(i)} cy={y(d.saidas)} r="3" fill={SERIE_SAIDAS}>
              <title>{`${d.dia}: ${d.saidas} saída(s)`}</title>
            </circle>
          </g>
        ))}
        {/* Só as pontas rotuladas: rótulo em todo ponto vira ruído */}
        <text x={L} y={A - 6} className="fill-current text-dim" fontSize="9">
          {dias[0].dia.slice(5)}
        </text>
        <text x={C - R} y={A - 6} textAnchor="end" className="fill-current text-dim" fontSize="9">
          {dias[dias.length - 1].dia.slice(5)}
        </text>
      </svg>
    </div>
  )
}

/** Os resolvidos da janela — o trabalho que o kanban deixa de mostrar. */
function HistoricoResolvidos({ dias }: { dias: number }) {
  const { data, isLoading, isError } = useQuery<{ chamados: Resolvido[]; total: number }>({
    queryKey: ['chamados-historico', dias],
    queryFn: () => apiFetch(`/chamados/historico?dias=${dias}`),
  })
  if (isLoading) return <p className="text-[11px] text-dim">Carregando…</p>
  if (isError || !data) return <p className="text-[11px] text-dim">Não foi possível carregar o histórico.</p>
  if (!data.total) {
    // Vazio DITO: sem esta frase, a seção em branco parece falha de carga.
    return <p className="text-[11px] text-dim">Nenhum chamado encerrado no período.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-dim text-left">
            <th className="font-medium py-1 pr-3">Chamado</th>
            <th className="font-medium py-1 pr-3">Tipo de demanda</th>
            <th className="font-medium py-1 pr-3">Responsável</th>
            <th className="font-medium py-1 pr-3 text-right">Dias</th>
            <th className="font-medium py-1">Encerrado</th>
          </tr>
        </thead>
        <tbody>
          {data.chamados.map(c => (
            <tr key={c.numero} className="border-t border-edge">
              <td className="py-1 pr-3 align-top">
                {c.url
                  ? <a href={c.url} target="_blank" rel="noopener noreferrer"
                      className="font-mono text-blue-600 dark:text-blue-400">{c.numero}</a>
                  : <span className="font-mono text-ink">{c.numero}</span>}
                <p className="text-dim leading-snug">{c.titulo || '(sem título)'}</p>
              </td>
              <td className="py-1 pr-3 align-top text-dim">
                {c.tipo_demanda}
                {c.categoria_diaadia && <span className="text-dim"> · {c.categoria_diaadia}</span>}
              </td>
              <td className="py-1 pr-3 align-top text-dim">{c.atribuido_a || '—'}</td>
              {/* Negativo é possível quando as datas da origem discordam: mostrar
                  o absurdo é melhor que escondê-lo com um max(0, …). */}
              <td className="py-1 pr-3 align-top text-right text-ink">
                {c.dias_ate_resolver ?? '—'}
              </td>
              <td className="py-1 align-top text-dim">{c.encerrado_em?.slice(0, 10) ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ChamadosIndicadores() {
  const { data, isLoading, isError, error } = useQuery<RespostaIndicadores>({
    queryKey: ['chamados-indicadores'],
    queryFn: () => apiFetch('/chamados/indicadores'),
  })

  if (isLoading) return <PageSpinner />
  if (isError) {
    return (
      <div className="border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20
        text-red-800 dark:text-red-200 rounded-lg px-4 py-3 text-[12px]">
        Não foi possível carregar os indicadores: {(error as Error).message}
      </div>
    )
  }
  const d = data!
  if (d.migration_ausente) {
    return (
      <div className="border border-amber-200 dark:border-yellow-800 bg-amber-50
        dark:bg-yellow-900/20 text-amber-800 dark:text-yellow-200 rounded-lg px-4 py-3 text-[12px]">
        Sistema em atualização — os indicadores ficam disponíveis assim que a
        migração for aplicada.
      </div>
    )
  }

  return (
    <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
      <Painel titulo="Idade dos chamados na fila"
        descricao={`Quanto tempo os ${d.total_ativos} chamados abertos estão esperando.`}>
        <BarrasHorizontais total={d.total_ativos}
          itens={d.aging.map(a => ({ rotulo: a.faixa, valor: a.total }))} />
      </Painel>

      <Painel titulo="Onde a fila está represada"
        descricao="Chamados abertos por tipo e estado — a célula mais escura é o acúmulo.">
        <MapaTipoEstado dados={d.tipo_estado} total={d.total_ativos} />
      </Painel>

      <Painel titulo="Entradas × saídas"
        descricao={`Chamados abertos e encerrados por dia nos últimos ${d.fluxo.length} dias.`}>
        <FluxoDiario dias={d.fluxo} />
      </Painel>

      <Painel titulo="Carga por responsável"
        descricao={d.responsaveis_ocultos > 0
          ? `Os ${d.carga.length} com mais chamados — outros ${d.responsaveis_ocultos} responsável(is) ficaram fora do gráfico.`
          : 'Chamados abertos por responsável.'}>
        <BarrasHorizontais total={d.total_ativos}
          itens={d.carga.map(c => ({ rotulo: c.responsavel, valor: c.total }))} />
      </Painel>

      <Painel titulo="O que a fila está pedindo"
        descricao="Tipo de demanda deduzido do título e do catálogo de cada chamado aberto.">
        <BarrasHorizontais total={d.total_ativos}
          itens={d.por_tipo_demanda.map(t => ({ rotulo: t.tipo, valor: t.total }))} />
      </Painel>

      <Painel titulo="Categorias do dia a dia"
        descricao={d.sem_categoria > 0
          // O denominador é dito: sem ele, um gráfico com 4 chamados
          // classificados pareceria a fila inteira.
          ? `Marcação feita nas work notes. ${d.sem_categoria} de ${d.total_ativos} chamado(s) da fila ainda não têm marcação.`
          : 'Marcação "dia a dia" feita pela equipe nas work notes.'}>
        {d.por_categoria.length
          ? <BarrasHorizontais total={d.total_ativos}
              itens={d.por_categoria.map(c => ({ rotulo: c.categoria, valor: c.total }))} />
          : <p className="text-[11px] text-dim">
              Nenhum chamado da fila tem marcação de dia a dia nas work notes.
            </p>}
      </Painel>

      <section className="bg-panel border border-edge rounded-lg p-4 flex flex-col gap-3 lg:col-span-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">
            Resolvidos nos últimos {d.dias_historico} dias
          </h2>
          <p className="text-[11px] text-dim">
            {d.resolvidos_periodo} chamado(s) encerrados — o trabalho que sai da fila
            e some do kanban.
          </p>
        </div>
        <HistoricoResolvidos dias={d.dias_historico} />
      </section>
    </div>
  )
}
