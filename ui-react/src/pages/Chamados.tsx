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
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import { ExternalLink, LifeBuoy, RefreshCw } from 'lucide-react'

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
      <div className="flex items-center justify-between gap-2 text-[11px] text-dim">
        <span className="truncate" title={c.atribuido_a || 'sem responsável'}>
          {c.atribuido_a || 'sem responsável'}
        </span>
        <span title={textoIdade(c.idade_dias)} className="shrink-0">
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
          <Badge value="neutral">{d.total} na fila</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Badge value={f.tom}>{f.texto}</Badge>
          <button onClick={() => refetch()} disabled={isFetching}
            className="text-dim hover:text-ink disabled:opacity-50" title="Recarregar">
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

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

      {d.alerta_fila_vazia && (
        <Aviso tom={d.ultimo_sync?.status === 'OK' ? 'info' : 'warning'}>
          {d.alerta_fila_vazia}
        </Aviso>
      )}

      {!d.migration_ausente && d.total > 0 && (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-5">
          {d.colunas.map(coluna => {
            const daColuna = d.chamados.filter(c => c.estado_kanban === coluna)
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
    </div>
  )
}
