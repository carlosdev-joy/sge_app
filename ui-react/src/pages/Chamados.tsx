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
import ChamadosIndicadores from './ChamadosIndicadores'
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
}

const ROTULO_COLUNA: Record<string, string> = {
  novo: 'Novo',
  andamento: 'Em andamento',
  aguardando: 'Aguardando',
  resolvido: 'Resolvido',
  outros: 'Outros',
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

// Busca por texto: número, título e responsável. Case-insensitive e por
// prefixo/trecho — "RITM00" precisa achar, e é assim que se procura na prática.
function casaBusca(c: Chamado, termo: string): boolean {
  const t = termo.trim().toLowerCase()
  if (!t) return true
  return [c.numero, c.titulo, c.atribuido_a, c.estado_origem]
    .some(campo => (campo || '').toLowerCase().includes(t))
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

function CardChamado({ c }: { c: Chamado }) {
  return (
    <div className="bg-canvas border border-edge rounded-md p-2.5 flex flex-col gap-1.5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-ink">{c.numero}</span>
        {c.url && (
          <a href={c.url} target="_blank" rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 shrink-0"
            title="Abrir no ServiceNow">
            <ExternalLink size={12} />
          </a>
        )}
      </div>
      <p className="text-xs text-ink leading-snug">{c.titulo || '(sem título)'}</p>
      <div className="flex flex-wrap items-center gap-1">
        <Badge value="neutral">{ROTULO_TIPO[c.tipo] ?? c.tipo}</Badge>
        {c.prioridade && <Badge value="neutral">{c.prioridade}</Badge>}
        {/* estado_origem no title: quando o card cai em "Outros", é ele que
            explica por quê — o valor cru que o ServiceNow devolveu. */}
        {c.estado_origem && (
          <span className="text-[10px] text-dim" title={`Estado na origem: ${c.estado_origem}`}>
            {c.estado_origem}
          </span>
        )}
      </div>
      {/* Derivações: o que o painel da estação lia nas entrelinhas e a tela
          não mostrava. O tipo aparece sempre; categoria e objetos só quando
          existem — chip vazio é ruído que ensina a ignorar a linha inteira. */}
      <div className="flex flex-wrap items-center gap-1 text-[10px]">
        {/* O title NÃO afirma de onde veio o tipo: a dedução usa o título e,
            em segunda mão, o catálogo, e o backend não devolve qual dos dois
            casou. Atribuir a proveniência ao catálogo seria mentir sempre que
            o título tiver vencido — que é o caso comum. */}
        <span className="px-1.5 py-0.5 rounded bg-panel border border-edge text-dim"
          title={`Tipo deduzido do título e do catálogo${c.catalogo ? ` · catálogo na origem: ${c.catalogo}` : ''}`}>
          {c.tipo_demanda}
        </span>
        {c.categoria_diaadia && (
          <span className="px-1.5 py-0.5 rounded bg-panel border border-edge text-dim"
            title="Categoria marcada nas work notes (dia a dia)">
            {c.categoria_diaadia}
          </span>
        )}
        {c.objetos && (
          <span className="font-mono text-dim truncate max-w-full"
            title={`Objetos citados: ${c.objetos}`}>
            {c.objetos}
          </span>
        )}
        {c.sla_vencido === true && (
          <span className="px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300"
            title="O ServiceNow marcou este chamado com SLA vencido">
            SLA vencido
          </span>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px] text-dim">
        <span className="truncate" title={c.demandante
          ? `Responsável: ${c.atribuido_a || 'sem responsável'} · Demandante: ${c.demandante}`
          : (c.atribuido_a || 'sem responsável')}>
          {c.atribuido_a || 'sem responsável'}
        </span>
        {/* Idade: cor E rótulo. A cor sozinha não informa quem não a distingue. */}
        <span title={textoIdade(c.idade_dias)}
          className={`shrink-0 flex items-center gap-1 ${faixaIdade(c.idade_dias).classe}`}>
          {faixaIdade(c.idade_dias).rotulo && (
            <span className="uppercase tracking-wide text-[9px]">
              {faixaIdade(c.idade_dias).rotulo}
            </span>
          )}
          {c.idade_dias !== null ? `${c.idade_dias}d` : '—'}
        </span>
      </div>
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

  const chamados = useMemo(() => data?.chamados ?? [], [data])

  // As opções saem do que ESTÁ na fila, não de uma lista fixa: prioridade e
  // responsável variam por instância, e uma lista fixa mostraria opção que
  // não filtra nada (ou esconderia a que filtra).
  const opcoes = useMemo(() => {
    const unicos = (f: (c: Chamado) => string | null) =>
      [...new Set(chamados.map(f).filter((v): v is string => !!v))].sort()
    return {
      tipos: unicos(c => c.tipo),
      responsaveis: unicos(c => c.atribuido_a),
      prioridades: unicos(c => c.prioridade),
    }
  }, [chamados])

  const filtrados = useMemo(() => chamados.filter(c =>
    (!fTipo || c.tipo === fTipo) &&
    (!fResponsavel || c.atribuido_a === fResponsavel) &&
    (!fPrioridade || c.prioridade === fPrioridade) &&
    casaBusca(c, busca)
  ), [chamados, fTipo, fResponsavel, fPrioridade, busca])

  const temFiltro = !!(busca || fTipo || fResponsavel || fPrioridade)
  const limpar = () => {
    setBusca(''); setFTipo(''); setFResponsavel(''); setFPrioridade('')
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
            {temFiltro ? `${filtrados.length} de ${d.total}` : `${d.total} na fila`}
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
          <Select label="Responsável" value={fResponsavel} className="w-52"
            onChange={e => setFResponsavel(e.target.value)}>
            <option value="">todos</option>
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
          Nenhum chamado casa com os filtros atuais — a fila tem {d.total}{' '}
          chamado(s). Limpe os filtros para vê-la inteira.
        </Aviso>
      )}

      {aba === 'fila' && !d.migration_ausente && d.total > 0 && (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-5">
          {d.colunas.map(coluna => {
            const daColuna = filtrados.filter(c => c.estado_kanban === coluna)
            return (
              <div key={coluna} className="flex flex-col gap-2 min-w-0">
                <div className="flex items-center justify-between px-1">
                  <h2 className="text-xs font-semibold text-dim uppercase tracking-wider">
                    {ROTULO_COLUNA[coluna] ?? coluna}
                  </h2>
                  <span className="text-xs text-dim">{daColuna.length}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {daColuna.length === 0 ? (
                    <p className="text-[11px] text-dim px-1 py-2">nenhum</p>
                  ) : (
                    daColuna.map(c => <CardChamado key={c.sys_id} c={c} />)
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {aba === 'indicadores' && !d.migration_ausente && <ChamadosIndicadores />}
    </div>
  )
}
