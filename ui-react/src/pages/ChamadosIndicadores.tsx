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
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { FiltroResponsaveis } from '../components/chamados/FiltroResponsaveis'
import { NumeroChamado } from '../components/chamados/NumeroChamado'
import { avisoDoFiltro, urlIndicadores } from '../lib/filtroResponsaveis'
import { TabelaChamados } from '../components/chamados/TabelaChamados'
import { apiFetch } from '../lib/api'
import { PageSpinner } from '../components/ui/Spinner'
// A linguagem visual das abas de Chamados mora em components/chamados/graficos
// — a aba Dashboard usa as mesmas formas, e duas cópias divergiriam.
import { BarrasHorizontais, Painel } from '../components/chamados/graficos'
import {
  SERIE_ENTRADAS, SERIE_SAIDAS, passoRampa, xDeY,
} from '../components/chamados/escalas'

interface FaixaAging { faixa: string; total: number }
interface Celula { tipo: string; estado: string; total: number }
interface DiaFluxo { dia: string; entradas: number; saidas: number }
interface Carga { responsavel: string; total: number }

interface PorTipoDemanda { tipo: string; total: number }
interface PorCategoria { categoria: string; total: number }

export interface Responsavel { nome: string; total: number }

export interface RespostaIndicadores {
  // O filtro em vigor e as opções. A tela precisa dos dois: um para desenhar
  // o seletor, outro para DIZER que está filtrando — número filtrado sem
  // aviso é a mesma armadilha do total que não bate com a lista.
  responsavel: string | null
  responsaveis: Responsavel[]
  aging: FaixaAging[]
  /** Ativos que ainda NÃO foram resolvidos — o denominador do aging. */
  total_em_fila: number
  tipo_estado: { tipos: string[]; estados: string[]; celulas: Celula[] }
  fluxo: DiaFluxo[]
  carga: Carga[]
  total_ativos: number
  responsaveis_ocultos: number
  migration_ausente: boolean
  // Agregações portadas do painel da estação (F3).
  por_tipo_demanda: PorTipoDemanda[]
  por_categoria: PorCategoria[]
  categorias_ocultas: number
  triagem: { veredito: string; origem: string; total: number }[]
  // Dois contadores separados: gateway doente e chave nunca configurada
  // produzem o mesmo veredito heurístico, e chamar os dois de "falha da IA"
  // manda o operador investigar rede quando faltava preencher um campo.
  triagem_com_erro: number
  triagem_sem_config: number
  blocos_indisponiveis: boolean
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
  ainda_na_fila: boolean
}

const ROTULO_TIPO: Record<string, string> = {
  incident: 'Incidente', ritm: 'RITM', task: 'Tarefa', change: 'Mudança',
}
const ROTULO_ESTADO: Record<string, string> = {
  novo: 'Novo', andamento: 'Em andamento', aguardando: 'Aguardando',
  resolvido: 'Resolvido', outros: 'Outros',
}

// Rampa sequencial de uma hue (azul), clara → escura. Mais escuro = mais alto.
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
  const { data, isLoading, isError } = useQuery<{
    chamados: Resolvido[]; total: number; ainda_na_fila: number; migration_ausente: boolean
  }>({
    queryKey: ['chamados-historico', dias],
    queryFn: () => apiFetch(`/chamados/historico?dias=${dias}`),
  })
  if (isLoading) return <p className="text-[11px] text-dim">Carregando…</p>
  if (isError || !data) return <p className="text-[11px] text-dim">Não foi possível carregar o histórico.</p>
  // O endpoint devolve 200 com lista vazia quando o banco falha, então
  // `isError` não pega esse caso: sem esta checagem a seção afirmaria "nada
  // foi encerrado" — uma frase FALSA — enquanto o cabeçalho acima, vindo de
  // outra consulta, diz que houve encerramentos.
  if (data.migration_ausente) {
    return (
      <p className="text-[11px] text-amber-700 dark:text-amber-400">
        Não foi possível ler o histórico agora — isto não quer dizer que nada
        foi encerrado no período.
      </p>
    )
  }
  if (!data.total) {
    // Vazio DITO: sem esta frase, a seção em branco parece falha de carga.
    return <p className="text-[11px] text-dim">Nenhum chamado encerrado no período.</p>
  }
  return (
    <TabelaChamados id="indicadores-resolvidos" itens={data.chamados}
      chaveDe={c => c.numero} vazio="Nenhum chamado encerrado no período."
      colunas={[
        {
          chave: 'numero', rotulo: 'Chamado', largura: 180, minima: 120,
          titulo: c => c.numero,
          conteudo: c => (
            <span className="flex items-center gap-1.5 min-w-0">
              <NumeroChamado numero={c.numero} />
              {c.url && (
                <a href={c.url} target="_blank" rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 shrink-0"
                  title="Abrir no ServiceNow (nova aba)">
                  <ExternalLink size={11} />
                </a>
              )}
              {/* No espelho, "Resolvido" continua ativo=1: só 'encerrado' tira
                  da fila. Sem esta marca, o mesmo chamado apareceria aqui e na
                  coluna Resolvido do kanban, e a seção estaria afirmando que
                  ele saiu. */}
              {c.ainda_na_fila && (
                <span className="text-[10px] text-dim shrink-0"
                  title="Encerrado na origem, mas ainda aparece na coluna Resolvido do kanban">
                  (ainda na fila)
                </span>
              )}
            </span>
          ),
        },
        {
          chave: 'titulo', rotulo: 'Título', largura: 300, minima: 120,
          titulo: c => c.titulo || '(sem título)',
          conteudo: c => <span className="text-dim">{c.titulo || '(sem título)'}</span>,
        },
        {
          // ⚠️ Era "Tipo de demanda". Ele é DERIVADO do título e chegava
          // repetindo o que a coluna Título já mostra ("BI e Dados - Inclusão
          // de coluna" → "Inclusão de coluna"). No lugar dele, o SOLICITANTE,
          // que não aparecia em lugar nenhum desta tabela.
          // A categoria fica: ela não vem do título, vem das work notes.
          chave: 'solicitante', rotulo: 'Solicitante', largura: 190, minima: 100,
          titulo: c => c.demandante || 'sem solicitante',
          conteudo: c => (
            <span className={c.demandante ? 'text-dim' : 'text-dim italic'}>
              {c.demandante || 'sem solicitante'}
            </span>
          ),
        },
        {
          chave: 'categoria', rotulo: 'Categoria', largura: 130, minima: 90,
          titulo: c => c.categoria_diaadia || 'sem marcação',
          conteudo: c => (
            <span className={c.categoria_diaadia ? 'text-dim' : 'text-dim italic'}>
              {c.categoria_diaadia || 'sem marcação'}
            </span>
          ),
        },
        {
          chave: 'responsavel', rotulo: 'Responsável', largura: 180, minima: 100,
          titulo: c => c.atribuido_a || 'sem responsável',
          conteudo: c => (
            <span className={c.atribuido_a ? 'text-dim' : 'text-dim italic'}>
              {c.atribuido_a || 'sem responsável'}
            </span>
          ),
        },
        {
          chave: 'dias', rotulo: 'Dias', largura: 70, minima: 48, direita: true,
          // Negativo é possível quando as datas da origem discordam: mostrar o
          // absurdo é melhor que escondê-lo com um max(0, …).
          conteudo: c => <span className="text-ink tabular-nums">{c.dias_ate_resolver ?? '—'}</span>,
        },
        {
          chave: 'encerrado', rotulo: 'Encerrado', largura: 110, minima: 90,
          titulo: c => c.encerrado_em || '',
          conteudo: c => (
            <span className="text-dim tabular-nums">{c.encerrado_em?.slice(0, 10) ?? '—'}</span>
          ),
        },
      ]} />
  )
}

export default function ChamadosIndicadores() {
  // Um filtro só, para TODA a análise da aba. Ele vai para o servidor porque
  // é lá que as contas são feitas: filtrar a lista no cliente deixaria os
  // totais falando da fila inteira enquanto os gráficos falam de uma pessoa.
  //
  // Vários nomes de uma vez: a gestão compara duas ou três pessoas, e com um
  // seletor único isso vira olhar uma, guardar o número de cabeça, olhar a
  // outra — apagando justamente o número que se queria comparar.
  const [responsaveis, setResponsaveis] = useState<string[]>([])

  const { data, isLoading, isError, error } = useQuery<RespostaIndicadores>({
    // A chave leva a lista JÁ SERIALIZADA: um array novo a cada render tem
    // identidade nova, e o react-query refaria a consulta sem parar.
    queryKey: ['chamados-indicadores', responsaveis.join('|')],
    queryFn: () => apiFetch(urlIndicadores(responsaveis)),
    // Mantém o gráfico anterior na tela enquanto o novo carrega: sem isso, a
    // aba pisca em branco a cada troca de responsável e perde-se a comparação
    // que a pessoa estava fazendo.
    placeholderData: anterior => anterior,
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

  // As três fatias da categoria, na mesma barra. "Sem marcação" entra como
  // grupo próprio — ele não é uma categoria que alguém escolheu, é a ausência
  // de escolha; mas é o maior balde da fila e o único que pede ação, e deixá-lo
  // fora do gráfico fazia o denominador mentir.
  const categorias = [
    ...d.por_categoria,
    ...(d.sem_categoria > 0
      ? [{ categoria: 'sem marcação', total: d.sem_categoria }]
      : []),
  ].sort((a, b) => b.total - a.total)

  return (
    <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
      {/* O filtro que vale para a aba inteira. Fica no topo, e não dentro de
          um painel, porque ele não pertence a nenhum deles: pertence a todos. */}
      <div className="lg:col-span-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-dim">Responsável</span>
        <FiltroResponsaveis opcoes={d.responsaveis ?? []}
          escolhidos={responsaveis} aoMudar={setResponsaveis}
          totalGeral={d.total_ativos} />
        {/* O aviso existe porque TODO número da aba muda com o filtro. Sem
            ele, um print desta tela vira "a fila tem 16 chamados".
            ⚠️ Vem do estado LOCAL, não da resposta: com `placeholderData` a
            tela ainda mostra os dados anteriores enquanto a consulta nova
            corre, e ler o filtro da resposta faria o aviso ficar um passo
            atrás — dizendo "apenas de Ana" sobre números que já são de Ana e
            Bruno. */}
        {responsaveis.length > 0 && (
          <span className="text-[11px] text-amber-700 dark:text-yellow-400">
            {avisoDoFiltro(responsaveis)}
          </span>
        )}
        {responsaveis.length > 0 && (
          <button type="button" onClick={() => setResponsaveis([])}
            className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline">
            limpar
          </button>
        )}
      </div>

      {/* O painel base (aging, tipo × estado, fluxo, carga) continua servido
          mesmo sem as colunas novas — mas o que falta precisa ser DITO, senão
          os painéis ausentes parecem dados zerados. */}
      {d.blocos_indisponiveis && (
        <div className="lg:col-span-2 border border-amber-200 dark:border-yellow-800
          bg-amber-50 dark:bg-yellow-900/20 text-amber-800 dark:text-yellow-200
          rounded-lg px-4 py-3 text-[12px]">
          Os indicadores de triagem e classificação não estão disponíveis: as
          migrations desta versão ainda não foram aplicadas. Os demais painéis
          seguem com os dados de sempre.
        </div>
      )}
      {/* O denominador aqui é `total_em_fila`, e NÃO `total_ativos`: o aging
          exclui quem já foi resolvido, porque a pergunta é "tem coisa velha
          PARADA?" e ela existe para priorizar. Com o total geral, o "x de y"
          diria "27 de 56" — vinte e sete velhos sobre uma fila que inclui o
          trabalho já feito. */}
      <Painel titulo="Idade dos chamados na fila"
        descricao={`Há quanto tempo os ${d.total_em_fila} chamados ainda não `
          + `resolvidos estão esperando. Resolvidos ficam de fora: eles não `
          + `estão parados, estão prontos.`}>
        <BarrasHorizontais total={d.total_em_fila}
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

      <Painel titulo="Triagem da fila"
        // O estado é dito no cabeçalho, não escondido num campo por chamado:
        // "18 podem iniciar" soa como análise feita, quando pode ser a
        // heurística respondendo por todos.
        descricao={[
          'Veredito por chamado aberto, com a origem de cada análise.',
          d.triagem_com_erro > 0
            ? `⚠ ${d.triagem_com_erro} laudo(s) falharam ao consultar a IA — esses vereditos vieram da regra de texto.`
            : '',
          d.triagem_sem_config > 0
            ? `${d.triagem_sem_config} laudo(s) saíram por regra de texto porque a triagem por IA não está configurada — não é falha do gateway.`
            : '',
        ].filter(Boolean).join(' ')}>
        {d.triagem.length
          ? <BarrasHorizontais total={d.total_ativos}
              itens={d.triagem.map(t => ({
                // Veredito e origem no MESMO rótulo: separá-los deixaria o
                // leitor supor que todo veredito veio de IA.
                rotulo: t.origem === 'heuristica'
                  ? `${t.veredito} (por regra)`
                  : t.origem === 'ia' ? `${t.veredito} (IA)` : t.veredito,
                valor: t.total,
              }))} />
          : <p className="text-[11px] text-dim">
              Nenhum chamado triado ainda. Ligue a triagem em Admin &gt; ServiceNow.
            </p>}
      </Painel>

      <Painel titulo="O que a fila está pedindo"
        descricao="Tipo de demanda deduzido do título e do catálogo de cada chamado aberto.">
        <BarrasHorizontais total={d.total_ativos}
          itens={d.por_tipo_demanda.map(t => ({ rotulo: t.tipo, valor: t.total }))} />
      </Painel>

      {/* ⚠️ O painel se chamava "Categorias do dia a dia" e mostrava só as
          categorias MARCADAS. O nome estava errado por dois motivos: a
          classificação é "categoria" (dia a dia É uma delas, ao lado de
          iniciativa), e o gráfico escondia o terceiro grupo — o dos chamados
          sem marcação —, que é justamente o maior e o único acionável.
          Com ele de fora, um gráfico com 18 classificados parecia a fila
          inteira, e a única pista era uma frase na descrição. */}
      <Painel titulo="Categoria"
        descricao={[
          'Marcação feita pela equipe nas work notes.',
          d.categorias_ocultas > 0
            ? `Outras ${d.categorias_ocultas} categoria(s) ficaram fora do gráfico.`
            : '',
        ].filter(Boolean).join(' ')}>
        {categorias.length
          ? <BarrasHorizontais total={d.total_ativos}
              itens={categorias.map(c => ({ rotulo: c.categoria, valor: c.total }))} />
          : <p className="text-[11px] text-dim">
              Nenhum chamado na fila.
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
