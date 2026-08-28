// Chamados da Engenharia — espelho somente-leitura do ServiceNow.
//
// Kanban SEM drag-and-drop de propósito: a v1 não escreve no ServiceNow, e um
// card que se arrasta promete uma ação que não existe. As colunas são <div>
// com lista de cards; nenhuma biblioteca nova.
//
// Duas leituras que a tela precisa deixar acontecer sem esforço:
//   1. "isso está atualizado?" → carimbo de frescor, âmbar quando atrasa;
//   2. "por que está vazio?"   → fila zerada e integração quebrada mostram o
//      mesmo nada, e só o último ciclo separa as duas.
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Input, Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { PageSpinner } from '../components/ui/Spinner'
import { Tabs } from '../components/ui/Tabs'
import { Modal } from '../components/ui/Modal'
import ChamadosIndicadores from './ChamadosIndicadores'
import ChamadosDashboard from './ChamadosDashboard'
import { ChamadoDetalheModal } from '../components/chamados/ChamadoDetalheModal'
import { CabecalhoCard } from '../components/chamados/CabecalhoCard'
import { NumeroChamado } from '../components/chamados/NumeroChamado'
import { RodapeCard } from '../components/chamados/RodapeCard'
import { separarFila } from '../lib/filaChamados'
// Os filtros da fila moram em `filtrosKanban` — é lá que a decisão de quem
// entra e quem some fica alcançável por teste.
import {
  CATEGORIAS, SEM_ATRIBUICAO, SEM_MARCACAO, algumFiltroAtivo, casaFiltros,
  destacaIncidente, ordenarColuna, tiposDisponiveis,
} from '../lib/filtrosKanban'
// A aparência do quadro — superfície do card e tom da raia — mora em
// `estiloKanban`: foi num TOKEN que estava o defeito, e token errado não
// aparece em teste de comportamento.
import {
  CLASSE_RAIA, classeDaGrade, classeDoCard, raiasVisiveis, tomDaColuna,
} from '../lib/estiloKanban'
import { ExternalLink, LifeBuoy, RefreshCw, Search, X } from 'lucide-react'

// Aviso com tom próprio. O InfoBanner da casa é azul e DISPENSÁVEL — certo
// para explicar a tela, errado para "a sincronização falhou": esse não pode
// ser fechado e esquecido, nem se parecer com uma dica.
const TOM_AVISO: Record<string, string> = {
  info:    'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200',
  warning: 'bg-amber-50 dark:bg-yellow-900/20 border-amber-200 dark:border-yellow-800 text-amber-800 dark:text-yellow-200',
  error:   'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200',
}

function Aviso({ tom, children }: { tom: 'info' | 'warning' | 'error'; children: React.ReactNode }) {
  return (
    <div className={`border rounded-lg px-4 py-3 text-[12px] leading-relaxed ${TOM_AVISO[tom]}`}>
      {children}
    </div>
  )
}

interface Chamado {
  sys_id: string
  numero: string
  tipo: string
  titulo: string | null
  estado_origem: string | null
  estado_kanban: string
  prioridade: string | null
  atribuido_a: string | null
  grupo: string | null
  aberto_em: string | null
  atualizado_em: string | null
  encerrado_em: string | null
  ativo: boolean
  url: string | null
  sync_em: string | null
  idade_dias: number | null
  // Derivadas na ingestão (migrations 091/092). `tipo_demanda` nunca chega
  // vazio: o backend devolve rótulo explícito para o que o sync ainda não
  // classificou, senão o card teria de inventar o que escrever.
  tipo_demanda: string
  categoria_diaadia: string
  objetos: string
  demandante: string
  catalogo: string
  prazo: string | null
  // null = ninguém mediu o SLA; false = mediu e está no prazo. Estados
  // diferentes, e o card só fala quando há o que dizer.
  sla_vencido: boolean | null
  // Triagem (migration 093). `veredito: null` = ainda não analisado — que é
  // diferente de qualquer veredito: card não analisado não pode ser pintado
  // como se tivesse sido reprovado.
  veredito: string | null
  suficiencia: string | null
  resumo: string
  lacunas: string[]
  perguntas: string
  // 'ia' | 'heuristica' | ''. A tela DIZ quem julgou: heurística mostrada
  // como análise de IA é veredito em que ninguém pensou.
  triagem_origem: string
  triagem_em: string | null
  triagem_erro: string
  // Parentesco (migration 090). Presente na sc_task, nulo no RITM. É por ele
  // que a tela sabe que a tarefa já está representada pelo card do pedido —
  // e null/ausente mantém a linha como card, que é o certo para a órfã e para
  // o ambiente sem a migration.
  pai_sys_id: string | null
  pai_numero: string | null
}

interface UltimoSync {
  id: number
  iniciado_em: string | null
  terminado_em: string | null
  status: string
  quantidades: Record<string, number | null>
  desativados: number | null
  erro: string | null
  idade_minutos: number | null
  em_andamento: boolean
  atrasado: boolean
}

interface RespostaChamados {
  chamados: Chamado[]
  colunas: string[]
  ultimo_sync: UltimoSync | null
  migration_ausente: boolean
  total: number
  por_coluna: Record<string, number>
  alerta_fila_vazia: string | null
  // true = o espelho responde, mas as colunas novas ainda não existem. Sem
  // dizer isso, a tela mostraria "não classificado" em 100% dos cards e
  // ninguém saberia se faltou dado ou faltou classificação.
  derivacoes_pendentes: boolean
}

const ROTULO_COLUNA: Record<string, string> = {
  novo: 'Novo',
  andamento: 'Em andamento',
  aguardando: 'Aguardando',
  resolvido: 'Resolvido',
  outros: 'Outros',
}

// O badge da categoria. Cor E palavra: cor sozinha não informa quem não a
// distingue, nem sobrevive a uma impressão em preto e branco.
const TOM_CATEGORIA: Record<string, string> = {
  'dia a dia': 'bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300 '
    + 'border-sky-200 dark:border-sky-900',
  iniciativa: 'bg-violet-100 text-violet-800 dark:bg-violet-950/60 '
    + 'dark:text-violet-300 border-violet-200 dark:border-violet-900',
}

const ROTULO_TIPO: Record<string, string> = {
  incident: 'Incidente',
  ritm: 'RITM',
  task: 'Tarefa',
  change: 'Mudança',
}

// Idade em texto: o card mostra "8d", mas o title traz a frase inteira —
// número sozinho não diz se é bom ou ruim para quem chega na tela agora.
function textoIdade(dias: number | null): string {
  if (dias === null) return 'sem data de abertura'
  if (dias <= 0) return 'aberto hoje'
  if (dias === 1) return 'aberto há 1 dia'
  return `parado há ${dias} dias`
}

// Destaque progressivo da idade. NUNCA só cor: cada faixa tem rótulo textual
// no card, senão a informação não existe para quem não distingue as cores
// (e some por completo se a tela for impressa ou lida em preto e branco).
const FAIXAS_IDADE = [
  { min: 7, classe: 'text-red-600 dark:text-red-400 font-semibold', rotulo: 'parado' },
  { min: 3, classe: 'text-amber-600 dark:text-yellow-400 font-medium', rotulo: 'atenção' },
] as const

function faixaIdade(dias: number | null) {
  if (dias === null) return { classe: 'text-dim', rotulo: '' }
  for (const f of FAIXAS_IDADE) {
    if (dias > f.min) return { classe: f.classe, rotulo: f.rotulo }
  }
  return { classe: 'text-dim', rotulo: '' }
}

function frescor(sync: UltimoSync | null): { texto: string; tom: string } {
  if (!sync) return { texto: 'nunca sincronizado', tom: 'warning' }
  if (sync.em_andamento) return { texto: 'sincronização em andamento', tom: 'info' }
  const min = sync.idade_minutos ?? 0
  const texto = min < 60
    ? `sincronizado há ${min} min`
    : `sincronizado há ${Math.floor(min / 60)}h`
  if (sync.status !== 'OK') return { texto: `${texto} — com erro`, tom: 'error' }
  return { texto, tom: sync.atrasado ? 'warning' : 'success' }
}

// O veredito colore o card, então o mapa é fechado: valor fora dele não
// ganha cor nem significado — por isso o backend recusa veredito que a IA
// invente, e aqui o desconhecido cai no neutro em vez de sumir.
const ESTILO_VEREDITO: Record<string, { classe: string; curto: string }> = {
  'PODE INICIAR': {
    classe: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    curto: 'pode iniciar',
  },
  'RETORNAR AO SOLICITANTE': {
    classe: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    curto: 'retornar',
  },
}

interface Sugestao { tipo_demanda: string; responsavel: string; resolvidos: number }

/** O laudo inteiro, para ler e copiar. */
function ModalTriagem({ c, aoFechar }: { c: Chamado; aoFechar: () => void }) {
  const heuristica = c.triagem_origem === 'heuristica'
  // Quem costuma atender este tipo — histórico de 90 dias, não IA. Carregado
  // só quando o modal abre: é informação de apoio à decisão de quem lê o
  // laudo, não algo que a fila inteira precise pagar para renderizar.
  const { data: sugestoes } = useQuery<{ sugestoes: Sugestao[]; dias: number }>({
    queryKey: ['chamados-sugestoes'],
    queryFn: () => apiFetch('/chamados/sugestoes'),
    staleTime: 5 * 60 * 1000,
  })
  const sugestao = sugestoes?.sugestoes.find(s => s.tipo_demanda === c.tipo_demanda)
  return (
    <Modal open onClose={aoFechar} title={`Triagem · ${c.numero}`} size="lg">
      <div className="flex flex-col gap-3 text-[12px]">
        {/* A PRIMEIRA coisa do modal é quem julgou. Um laudo heurístico lido
            como análise de IA leva o operador a confiar num julgamento que
            ninguém fez — e a heurística só mediu sinais do texto. */}
        <div className={`rounded-md px-3 py-2 ${heuristica
          ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200'
          : 'bg-panel text-ink'}`}>
          {heuristica ? (
            <>
              <strong>Análise automática por regra de texto</strong> — a IA não
              respondeu, então este veredito vem de heurística: ela mede sinais
              da descrição, não lê o pedido.
              {c.triagem_erro && <span className="block text-[11px] mt-1">Motivo: {c.triagem_erro}</span>}
            </>
          ) : (
            <><strong>Análise por IA</strong>{c.triagem_em ? ` · ${c.triagem_em}` : ''}</>
          )}
        </div>

        {c.resumo && <p className="text-ink">{c.resumo}</p>}

        {c.lacunas.length > 0 && (
          <div>
            <h4 className="text-[11px] font-semibold text-dim uppercase tracking-wide">
              Lacunas identificadas
            </h4>
            <ul className="list-disc pl-4 text-ink">
              {c.lacunas.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        )}

        {c.perguntas && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[11px] font-semibold text-dim uppercase tracking-wide">
                Perguntas sugeridas
              </h4>
              {/* Copiar, e não enviar: devolver chamado pela automação é
                  decisão de outra spec. Quem fala com o solicitante é uma
                  pessoa. */}
              <Button variant="secondary" size="sm"
                onClick={() => navigator.clipboard?.writeText(c.perguntas)}>
                Copiar
              </Button>
            </div>
            <pre className="whitespace-pre-wrap text-ink font-sans">{c.perguntas}</pre>
          </div>
        )}

        {!c.resumo && !c.lacunas.length && !c.perguntas && (
          <p className="text-dim">Este chamado ainda não tem laudo de triagem.</p>
        )}

        {/* SUGESTÃO, e o texto diz isso. Distribuir chamado é decisão de
            gestão: a contagem não sabe de férias, carga atual nem de quem
            está aprendendo o quê. */}
        {sugestao && sugestao.responsavel !== c.atribuido_a && (
          <p className="text-[11px] text-dim border-t border-edge pt-2">
            Quem mais resolveu “{c.tipo_demanda}” nos últimos {sugestoes?.dias ?? 90} dias:{' '}
            <strong className="text-ink">{sugestao.responsavel}</strong> ({sugestao.resolvidos}).
            É histórico, não atribuição.
          </p>
        )}
      </div>
    </Modal>
  )
}

function CardChamado({ c, filhas = [] }: { c: Chamado; filhas?: Chamado[] }) {
  // Incidente é INTERRUPÇÃO: alguma coisa que funcionava parou. No meio de
  // pedidos de trabalho planejado ele some — e some justamente quando é o que
  // deveria ser lido primeiro. O destaque acaba no resolvido: alarme sobre
  // trabalho FEITO não pede ação e ensina a ignorar os outros.
  const urgente = destacaIncidente(c)
  const [verLaudo, setVerLaudo] = useState(false)
  // O conteúdo do chamado — descrição, notas e anexos. O gesto que abre isto,
  // e o porquê de ele ser anunciado, moram em `CabecalhoCard`.
  const [verDetalhe, setVerDetalhe] = useState(false)
  const estilo = c.veredito ? ESTILO_VEREDITO[c.veredito] : undefined
  return (
    <div data-urgente={urgente || undefined} className={classeDoCard(urgente)}>
      {/* A marca do incidente como BARRA sobreposta, não como borda grossa:
          borda muda o tamanho da caixa e desalinha o card dos vizinhos. */}
      {urgente && (
        <span aria-hidden
          className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg
            bg-red-500 dark:bg-red-500" />
      )}
      <CabecalhoCard numero={c.numero} titulo={c.titulo} url={c.url}
        aoAbrirDetalhe={() => setVerDetalhe(true)} />
      {verDetalhe && (
        <ChamadoDetalheModal sysId={c.sys_id} numero={c.numero}
          aoFechar={() => setVerDetalhe(false)} />
      )}
      {/* UMA fileira de marcas, não duas. Antes eram duas linhas de chips
          empilhadas — o que dava ao card a silhueta de formulário e fazia a
          coluna parecer uma pilha de retângulos. O conteúdo é o MESMO: nada
          saiu, tudo passou a fluir na mesma linha, quebrando quando precisa.
          Todos com a mesma altura e o mesmo raio, para o olho ler "marcas" em
          vez de "elementos diferentes". */}
      <div className="flex flex-wrap items-center gap-1 text-[10px]">
        {/* O rótulo do tipo carrega o tom. Cor sozinha não informa quem não a
            distingue: aqui a palavra "Incidente" continua sendo o que diz o
            que é, e o vermelho só reforça. */}
        <span className={`px-2 py-0.5 rounded-full border font-medium ${urgente
          ? 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/50 '
            + 'dark:text-red-300 dark:border-red-800'
          : 'bg-canvas text-dim border-edge'}`}>
          {ROTULO_TIPO[c.tipo] ?? c.tipo}
        </span>
        {c.prioridade && (
          <span className="px-2 py-0.5 rounded-full bg-canvas border border-edge text-dim">
            {c.prioridade}
          </span>
        )}
        {/* O title NÃO afirma de onde veio o tipo: a dedução usa o título e,
            em segunda mão, o catálogo, e o backend não devolve qual dos dois
            casou. Atribuir a proveniência ao catálogo seria mentir sempre que
            o título tiver vencido — que é o caso comum. */}
        <span className="px-2 py-0.5 rounded-full bg-canvas border border-edge text-dim"
          title={`Tipo deduzido do título e do catálogo${c.catalogo ? ` · catálogo na origem: ${c.catalogo}` : ''}`}>
          {c.tipo_demanda}
        </span>
        {/* A CATEGORIA em destaque, e não como mais um chip cinza ao lado do
            tipo. Ela é o recorte pelo qual a gestão lê a fila — dia a dia é
            operação, iniciativa é projeto —, e no meio dos chips neutros ela
            desaparecia. Cor E palavra: cor sozinha não informa quem não a
            distingue, nem sobrevive a uma impressão em preto e branco.
            Sem marcação NÃO ganha badge: chip "sem marcação" em metade da fila
            é ruído que ensina a ignorar a linha inteira — quem procura o que
            falta classificar tem o filtro "Sem marcação" acima. */}
        {c.categoria_diaadia && (
          <span className={`px-2 py-0.5 rounded-full border font-medium
            ${TOM_CATEGORIA[c.categoria_diaadia]
              ?? 'bg-canvas border-edge text-dim'}`}
            title={`Categoria marcada pela equipe nas work notes: ${c.categoria_diaadia}`}>
            {c.categoria_diaadia}
          </span>
        )}
        {c.objetos && (
          <span className="font-mono text-dim truncate max-w-full"
            title={`Objetos citados: ${c.objetos}`}>
            {c.objetos}
          </span>
        )}
        {/* estado_origem sem moldura: ele é CONTEXTO, não classificação —
            quando o card cai em "Outros", é ele que explica por quê. Com
            moldura, competiria com as marcas que pedem leitura. */}
        {c.estado_origem && (
          <span className="text-dim" title={`Estado na origem: ${c.estado_origem}`}>
            {c.estado_origem}
          </span>
        )}
        {c.sla_vencido === true && (
          <span className="px-2 py-0.5 rounded-full border border-red-300
            dark:border-red-800 bg-red-100 dark:bg-red-950/60
            text-red-700 dark:text-red-300 font-medium"
            title="O ServiceNow marcou este chamado com SLA vencido">
            SLA vencido
          </span>
        )}
        {/* Veredito: só aparece quando existe. Card não analisado fica SEM
            selo — pintá-lo de âmbar diria que ele foi reprovado. */}
        {estilo && (
          <button type="button" onClick={() => setVerLaudo(true)}
            className={`px-2 py-0.5 rounded-full border ${estilo.classe}`}
            title={c.triagem_origem === 'heuristica'
              ? 'Veredito por regra de texto (a IA não respondeu) — clique para ver'
              : 'Veredito da análise por IA — clique para ver o laudo'}>
            {estilo.curto}
            {/* O til marca o que veio da heurística. Sem esta marca, os dois
                vereditos têm exatamente a mesma cara no card. */}
            {c.triagem_origem === 'heuristica' && <span aria-hidden> ~</span>}
          </button>
        )}
      </div>
      {verLaudo && <ModalTriagem c={c} aoFechar={() => setVerLaudo(false)} />}
      <RodapeCard c={c} textoIdade={textoIdade} faixaIdade={faixaIdade} />

      {/* As tarefas do pedido. Elas saíram da contagem de cards, mas NÃO da
          vista: some da fila é diferente de sumir do sistema, e o estado da
          task é o que responde "o pedido está aberto, mas alguém já pegou?".
          O responsável só aparece quando DIFERE do pai — é assim que a
          premissa "mesmo responsável" mostra que quebrou, antes de virar
          dúvida no gráfico de carga. */}
      {filhas.length > 0 && (
        <div className="flex flex-col gap-0.5 -mx-1 px-1 pt-2 border-t border-edge">
          {filhas.map(f => (
            <div key={f.sys_id}
              className="flex items-center gap-1.5 text-[10px] text-dim
                rounded px-1 py-0.5 hover:bg-canvas">
              <span aria-hidden className="shrink-0">↳</span>
              {/* O número da TASK também se copia: é ele que se cita ao
                  perguntar de uma tarefa a quem a executa. */}
              <NumeroChamado numero={f.numero} className="shrink-0" />
              <span className="px-1.5 py-px rounded-full bg-canvas border
                border-edge shrink-0">
                {ROTULO_COLUNA[f.estado_kanban] ?? f.estado_kanban}
              </span>
              {f.atribuido_a && f.atribuido_a !== c.atribuido_a && (
                <span className="truncate" title={`Responsável da tarefa: ${f.atribuido_a}`}>
                  {f.atribuido_a}
                </span>
              )}
              {f.url && (
                <a href={f.url} target="_blank" rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 shrink-0 ml-auto"
                  title="Abrir a tarefa no ServiceNow">
                  <ExternalLink size={10} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Chamados() {
  const { data, isLoading, isError, error, refetch, isFetching } =
    useQuery<RespostaChamados>({
      queryKey: ['chamados'],
      queryFn: () => apiFetch('/chamados'),
    })

  // Filtro client-side: a fila é de ordem de dezenas (a spec dimensionou ~50)
  // e a resposta já traz tudo — ida-e-volta ao servidor a cada tecla seria
  // latência sem ganho nenhum.
  const [aba, setAba] = useState('fila')
  const [busca, setBusca] = useState('')
  const [fTipo, setFTipo] = useState('')
  const [fResponsavel, setFResponsavel] = useState('')
  const [fPrioridade, setFPrioridade] = useState('')
  const [fCategoria, setFCategoria] = useState('')

  const todos = useMemo(() => data?.chamados ?? [], [data])

  // O card é o TRABALHO: a tarefa vira linha dentro do card do pedido. A regra
  // (e a recusa que ela protege — órfã continua card) mora em `lib/filaChamados`.
  // As filhas saem da lista que já chegou: uma requisição por card seriam
  // dezenas a cada abertura da tela.
  const { cards: chamados, filhasPorPai } = useMemo(
    () => separarFila(todos), [todos])

  // As opções saem do que ESTÁ na fila, não de uma lista fixa: prioridade e
  // responsável variam por instância, e uma lista fixa mostraria opção que
  // não filtra nada (ou esconderia a que filtra).
  //
  // Olham o card E as filhas (`todos`, não `chamados`): a tarefa continua
  // visível na tela, então "Tarefa" precisa continuar na lista de tipos, e o
  // responsável que só aparece numa task precisa ser filtrável.
  const opcoes = useMemo(() => {
    const unicos = (f: (c: Chamado) => string | null) =>
      [...new Set(todos.map(f).filter((v): v is string => !!v))].sort()
    return {
      // Os tipos saem dos CARDS e sem 'task' — ver `tiposDisponiveis`.
      tipos: tiposDisponiveis(chamados),
      responsaveis: unicos(c => c.atribuido_a),
      prioridades: unicos(c => c.prioridade),
    }
  }, [todos, chamados])

  // O filtro casa contra o card e suas filhas. Sem isso, o número da SCTASK
  // estaria na tela e a busca por ele não acharia nada — e filtrar por
  // "Tarefa" esvaziaria a fila inteira, porque nenhum CARD é uma task.
  const filtros = useMemo(
    () => ({ busca, tipo: fTipo, responsavel: fResponsavel,
             prioridade: fPrioridade, categoria: fCategoria }),
    [busca, fTipo, fResponsavel, fPrioridade, fCategoria])

  const filtrados = useMemo(
    () => chamados.filter(c =>
      casaFiltros(c, filhasPorPai.get(c.sys_id) ?? [], filtros)),
    [chamados, filhasPorPai, filtros])

  // Quantos cards em cada coluna, DEPOIS do filtro. É esta conta que decide se
  // a raia "Outros" aparece, e é a mesma que o cabeçalho de cada raia mostra.
  const porColuna = useMemo(() => {
    const mapa = new Map<string, Chamado[]>()
    for (const c of filtrados) {
      const lista = mapa.get(c.estado_kanban)
      if (lista) lista.push(c)
      else mapa.set(c.estado_kanban, [c])
    }
    return mapa
  }, [filtrados])

  // `data`, e não `d`: os hooks correm ANTES das guardas de carregamento, e
  // `d` só existe depois delas.
  const raias = useMemo(
    () => raiasVisiveis(data?.colunas ?? [],
                        col => (porColuna.get(col) ?? []).length),
    [data?.colunas, porColuna])

  const temFiltro = algumFiltroAtivo(filtros)
  const limpar = () => {
    setBusca(''); setFTipo(''); setFResponsavel(''); setFPrioridade('')
    setFCategoria('')
  }

  if (isLoading) return <PageSpinner />

  if (isError) {
    return (
      <div className="p-4">
        <Aviso tom="error">
          Não foi possível carregar os chamados: {(error as Error).message}
        </Aviso>
      </div>
    )
  }

  const d = data!
  const f = frescor(d.ultimo_sync)

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <LifeBuoy size={18} className="text-dim" />
          <h1 className="text-lg font-semibold text-ink">Chamados da Engenharia</h1>
          {/* Com filtro ativo, "x de y" — nunca só o número filtrado, que
              faria a fila parecer menor do que é. */}
          <Badge value="neutral">
            {/* Conta TRABALHOS, não registros: `d.total` vem da API e inclui
                as tarefas que já estão representadas no card do pai. Dizer 95
                com 59 cards na tela é a mesma incoerência que esta fase veio
                fechar, só que no rodapé. */}
            {temFiltro
              ? `${filtrados.length} de ${chamados.length}`
              : `${chamados.length} na fila`}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Badge value={f.tom}>{f.texto}</Badge>
          <button onClick={() => refetch()} disabled={isFetching}
            className="text-dim hover:text-ink disabled:opacity-50" title="Recarregar">
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <Tabs active={aba} onChange={setAba} tabs={[
        { id: 'fila', label: 'Fila' },
        { id: 'indicadores', label: 'Indicadores' },
        { id: 'dashboard', label: 'Dashboard' },
      ]} />

      {/* Os avisos de estado do espelho valem para as DUAS abas — um
          indicador calculado sobre espelho quebrado engana igual. */}
      {d.migration_ausente && (
        <Aviso tom="warning">
          Sistema em atualização — o espelho de chamados ainda não está
          disponível neste ambiente. Assim que a migração for aplicada, a fila
          aparece aqui.
        </Aviso>
      )}

      {/* Um sync com erro não esconde o espelho: os dados anteriores continuam
          servindo, com o aviso por cima. */}
      {d.ultimo_sync?.erro && (
        <Aviso tom="warning">
          A última sincronização reportou erro: {d.ultimo_sync.erro} — a fila
          abaixo pode estar desatualizada.
        </Aviso>
      )}

      {aba === 'fila' && d.alerta_fila_vazia && (
        <Aviso tom={d.ultimo_sync?.status === 'OK' ? 'info' : 'warning'}>
          {d.alerta_fila_vazia}
        </Aviso>
      )}

      {/* Sem este aviso, os cards apareceriam com "não classificado" em todos
          os campos novos e ninguém saberia se faltou dado ou classificação —
          o mesmo "vazio × quebrado" que o resto da tela evita. */}
      {d.derivacoes_pendentes && (
        <Aviso tom="warning">
          A fila está sendo servida, mas os campos de triagem e classificação
          ainda não existem no banco — as migrations desta versão não foram
          aplicadas. Os cards aparecem sem tipo, categoria e veredito.
        </Aviso>
      )}

      {aba === 'fila' && !d.migration_ausente && d.total > 0 && (
        <div className="bg-panel border border-edge rounded-lg p-3 flex flex-wrap items-end gap-3">
          <div className="relative">
            <Input label="Buscar" value={busca} className="w-64 pl-7"
              placeholder="número, título ou responsável"
              onChange={e => setBusca(e.target.value)} />
            <Search size={13} className="absolute left-2 bottom-2 text-dim pointer-events-none" />
          </div>
          <Select label="Tipo" value={fTipo} className="w-40"
            onChange={e => setFTipo(e.target.value)}>
            <option value="">todos</option>
            {opcoes.tipos.map(t => (
              <option key={t} value={t}>{ROTULO_TIPO[t] ?? t}</option>
            ))}
          </Select>
          <Select label="Categoria" value={fCategoria} className="w-44"
            onChange={e => setFCategoria(e.target.value)}>
            <option value="">todas</option>
            {CATEGORIAS.map(c => (
              <option key={c.valor} value={c.valor}>{c.rotulo}</option>
            ))}
            {/* "Sem marcação" é o recorte mais acionável dos três: é a lista
                do que ainda precisa ser classificado pela equipe. */}
            <option value={SEM_MARCACAO}>Sem marcação</option>
          </Select>
          <Select label="Responsável" value={fResponsavel} className="w-52"
            onChange={e => setFResponsavel(e.target.value)}>
            <option value="">todos</option>
            {/* Sem dono é o que pede ação: chamado que ninguém pegou não
                aparece na carga de ninguém e some da conversa. */}
            <option value={SEM_ATRIBUICAO}>sem atribuição</option>
            {opcoes.responsaveis.map(r => <option key={r} value={r}>{r}</option>)}
          </Select>
          <Select label="Prioridade" value={fPrioridade} className="w-44"
            onChange={e => setFPrioridade(e.target.value)}>
            <option value="">todas</option>
            {opcoes.prioridades.map(p => <option key={p} value={p}>{p}</option>)}
          </Select>
          {temFiltro && (
            <Button size="sm" variant="ghost" onClick={limpar}>
              <X size={13} /> Limpar
            </Button>
          )}
        </div>
      )}

      {/* Filtro que zera a fila precisa dizer que foi o FILTRO — senão parece
          espelho vazio, e o operador vai procurar defeito na integração. */}
      {aba === 'fila' && temFiltro && filtrados.length === 0 && d.total > 0 && (
        <Aviso tom="info">
          Nenhum chamado casa com os filtros atuais — a fila tem {chamados.length}{' '}
          chamado(s). Limpe os filtros para vê-la inteira.
        </Aviso>
      )}

      {aba === 'fila' && !d.migration_ausente && d.total > 0 && (
        // "Outros" só aparece quando tem card, e a grade se ajusta ao número
        // de raias — ver `raiasVisiveis`. Sem ajustar a grade, esconder uma
        // coluna deixaria um vão do tamanho dela no fim do quadro.
        <div className={classeDaGrade(raias.length)}>
          {raias.map(coluna => {
            // Incidentes em curso no TOPO. Quem abre o kanban lê de cima para
            // baixo e para quando acha o que procura — um incidente na décima
            // posição de uma coluna que rola é um incidente que ninguém viu.
            const daColuna = ordenarColuna(porColuna.get(coluna) ?? [])
            return (
              // ⚠️ A RAIA. Antes a coluna não tinha superfície nenhuma: os
              // cards flutuavam direto sobre o fundo da página, sem nada que
              // dissesse onde uma coluna termina e a outra começa. Somado ao
              // card pintado com a cor do próprio fundo, era a leitura de
              // "quadrados jogados". Ver `estiloKanban`.
              <div key={coluna} className={CLASSE_RAIA}>
                <div className="flex items-center justify-between gap-2 px-3 py-2
                  border-b border-edge">
                  <div className="flex items-center gap-2 min-w-0">
                    {/* O ponto NÃO carrega informação sozinho — o nome está do
                        lado. Ele serve de marco para achar a raia certa sem
                        reler os cinco títulos. */}
                    <span aria-hidden
                      className={`w-2 h-2 rounded-full shrink-0 ${tomDaColuna(coluna)}`} />
                    <h2 className="text-[11px] font-semibold text-ink uppercase
                      tracking-wider truncate">
                      {ROTULO_COLUNA[coluna] ?? coluna}
                    </h2>
                  </div>
                  {/* A contagem numa pílula: solta, ela se confundia com o
                      texto do título ao lado. */}
                  <span className="shrink-0 text-[11px] text-dim tabular-nums
                    px-2 py-0.5 rounded-full bg-panel border border-edge">
                    {daColuna.length}
                  </span>
                </div>
                <div className="flex flex-col gap-2 p-2">
                  {daColuna.length === 0 ? (
                    <p className="text-[11px] text-dim px-1 py-3 text-center">
                      nenhum
                    </p>
                  ) : (
                    daColuna.map(c => (
                      <CardChamado key={c.sys_id} c={c}
                        filhas={filhasPorPai.get(c.sys_id)} />
                    ))
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {aba === 'indicadores' && !d.migration_ausente && <ChamadosIndicadores />}

      {/* O painel busca a própria resposta (`/chamados/dashboard`), com os
          blocos já recortados no banco pela MESMA regra da fila. Ele tem o
          próprio aviso de espelho indisponível, então não depende do `d`
          desta tela — se dependesse, uma fila vazia esconderia o painel. */}
      {aba === 'dashboard' && <ChamadosDashboard />}
    </div>
  )
}
