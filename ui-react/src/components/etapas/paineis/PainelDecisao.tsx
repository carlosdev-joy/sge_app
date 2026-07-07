// ── Painel de uma DECISÃO ────────────────────────────────────────────────────
// Fase 4 do redesign: layout LARGO para o dock inferior — 2 colunas no lg+
// (esquerda = fonte da condição; direita = ramos). No modo switch os casos
// viram uma TABELA (uma linha por caso, senão no rodapé), padrão dos routers
// de Informatica/DataStage. Abaixo de lg colapsa para 1 coluna.
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node } from '@xyflow/react'
import { GitBranch, Maximize2, Play, Trash2, Plus, ChevronUp, ChevronDown, X } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Hint } from '../../ui/Hint'
import { Input, Select, Textarea } from '../../ui/Input'
import { toast } from '../../ui/Toast'
import { casoCor, type DecisaoNodeData, type NodeCondition } from '../DecisaoNode'
import type { SqlNodeData } from '../SqlNode'
import { COND_OPERADORES, defaultCondition } from '../condition'
import { defaultSql } from '../fluxoTypes'
import { NomeField, CasoNomeInput, type CasoOps, type SimResult } from './shared'

export interface PainelDecisaoProps extends CasoOps {
  node: Node
  nodes: Node[]
  ramos: Record<string, string[]>
  jobNames: string[]
  sqlNodeNames: string[]
  mssqlConns: { conn_id: string; host: string }[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchCondition: (nodeId: string, patch: Partial<NodeCondition>) => void
  onSimular: (decisaoId: string, ramo: string) => void
  onDelete: (id: string) => void
  // Maximiza o dock (modo focado) — p/ editar SQL longo da condição.
  onMaximizar?: () => void
  // Hover numa linha de caso → o editor destaca a aresta daquele ramo no canvas.
  onHoverRamo?: (nodeId: string, ramo: string | null) => void
}

// Banco da condição (contagem/query): com uma CONEXÃO selecionada, vira select
// com os bancos DAQUELE servidor (credencial nativa — mesma regra do resto do
// Orquestra; cache compartilhado com o storedproc via queryKey 'job-databases').
// Com "Conexão padrão" o servidor não é conhecido aqui → campo livre.
function BancoCondicao({ connId, host, value, onChange }: {
  connId: string
  host: string
  value: string
  onChange: (v: string) => void
}) {
  const { data } = useQuery<{ server: string | null; databases: string[] }>({
    queryKey: ['job-databases', connId, host],
    queryFn: () => apiFetch(
      `/jobs/databases?conn_id=${encodeURIComponent(connId)}&host=${encodeURIComponent(host)}`),
    enabled: !!connId || !!host,
    staleTime: 300_000,
  })
  const dbs = data?.databases ?? []
  if (!connId && !host) {
    return (
      <Input
        label="Banco (opcional)"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="ex: BI_DW"
        className="font-mono text-xs"
      />
    )
  }
  return (
    <Select
      label="Banco (opcional)"
      value={value}
      onChange={e => onChange(e.target.value)}
      className="text-xs"
    >
      <option value="">Banco padrão da conexão</option>
      {dbs.map(d => <option key={d} value={d}>{d}</option>)}
      {value && !dbs.includes(value) && <option value={value}>{value}</option>}
    </Select>
  )
}

export function PainelDecisao({
  node, nodes, ramos, jobNames, sqlNodeNames, mssqlConns, onRename, onPatchCondition, onSimular, onDelete,
  onMaximizar, onHoverRamo,
  onAlternarModo, onAddCaso, onUpdateCaso, onRemoveCaso, onMoveCaso,
}: PainelDecisaoProps) {
  const d = node.data as DecisaoNodeData
  const isNew = !!d.isNew
  const c = d.condition ?? defaultCondition()
  const patch = (p: Partial<NodeCondition>) => onPatchCondition(node.id, p)
  const isSwitch = Array.isArray(c.casos)
  const casos = c.casos ?? []
  const ramosDe = (k: string) => ramos[k] ?? []
  // Jobs disponíveis para a condição "linhas processadas" (exclui a própria decisão).
  const jobsDisponiveis = jobNames.filter(j => j !== node.id)

  // ── Simulação (decisão por valor de SQL) ──────────────────────────────────
  const [simulando, setSimulando] = useState(false)
  const [simResult, setSimResult] = useState<SimResult | null>(null)
  // Limpa o resultado ao trocar de nó/condição (key remonta, mas reforça ao editar).
  useEffect(() => { setSimResult(null) }, [node.id])

  async function simular() {
    // Resolve o nó SQL de origem (source_job) e sua config (sql/conexão/banco).
    const sourceJob = (c.source_job || '').trim()
    if (!sourceJob) { toast.error('Selecione o nó SQL de origem antes de simular.'); return }
    const sqlNode = nodes.find(n => n.id === sourceJob && n.type === 'sql')
    if (!sqlNode) { toast.error(`Nó SQL "${sourceJob}" não encontrado no fluxo — ligue-o a esta decisão.`); return }
    const sqlCfg = (sqlNode.data as SqlNodeData).sql ?? defaultSql()
    if (!(sqlCfg.sql || '').trim()) { toast.error(`O nó SQL "${sourceJob}" não tem consulta — escreva o SELECT.`); return }
    if (!sqlCfg.mssql_conn_id) { toast.error(`O nó SQL "${sourceJob}" não tem conexão MSSQL definida.`); return }
    const host = mssqlConns.find(cn => cn.conn_id === sqlCfg.mssql_conn_id)?.host
    if (!host) { toast.error(`Conexão "${sqlCfg.mssql_conn_id}" não encontrada — verifique a conexão MSSQL.`); return }

    setSimulando(true)
    setSimResult(null)
    try {
      const res = await apiFetch<SimResult>('/jobs/decisao-simular', {
        method: 'POST',
        body: JSON.stringify({
          // mssql_conn_id primeiro (credencial nativa, a mesma do runtime);
          // host segue como fallback para conexões só do Airflow.
          mssql_conn_id: sqlCfg.mssql_conn_id,
          host,
          database: sqlCfg.database,
          sql: sqlCfg.sql,
          comparacao: c.comparacao || 'texto',
          ...(isSwitch
            ? { casos: casos.map(cs => ({ nome: cs.nome, operador: cs.operador, valor: (cs.valor ?? '').toString() })) }
            : { operador: c.operador, valor: (c.valor ?? '').toString() }),
        }),
      })
      setSimResult(res)
      // Destaque animado do ramo/caso escolhido — avisa se ainda não tem aresta.
      const escolhido = isSwitch ? (res.caso || 'senao') : (res.ramo === 'sim' ? 'sim' : 'nao')
      const rotulo = escolhido === 'sim' ? 'SIM' : escolhido === 'nao' ? 'NÃO'
        : escolhido === 'senao' ? 'SENÃO' : `"${escolhido}"`
      if (ramosDe(escolhido).length === 0) {
        toast.info(`Conecte o ramo ${rotulo} para ver o caminho destacado.`)
      } else {
        onSimular(node.id, escolhido)
      }
    } catch (e: any) {
      toast.error(e?.message || 'Falha ao simular a decisão.')
    } finally {
      setSimulando(false)
    }
  }

  // Banco da condição segue a CONEXÃO selecionada (regra de 100% do Orquestra).
  const condHost = mssqlConns.find(cn => cn.conn_id === (c.mssql_conn_id ?? ''))?.host ?? ''

  // Pílula de um alvo de ramo (job ligado por aresta).
  const pill = (m: string) => (
    <span key={m} className="rounded-full border border-edge bg-panel px-1.5 py-0.5 text-[11px] font-medium text-ink">{m}</span>
  )
  const pillSlate = (m: string) => (
    <span key={m} className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">{m}</span>
  )

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho do painel — o Excluir mora no topo direito (mesmo padrão
          nos 4 painéis; o mt-auto da era do aside não funciona no dock largo). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-500 text-white">
          <GitBranch size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">Decisão (roteador)</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir decisão
        </Button>
      </div>

      {/* 2 colunas no lg+: esquerda = fonte da condição; direita = ramos. */}
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(320px,420px)_1fr]">
        {/* ── Coluna esquerda: fonte da condição ─────────────────────────── */}
        <div className="flex min-w-0 flex-col gap-2">
          <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: DECISAO_VOLUME" onRename={onRename} />

          <div className="mt-1 flex items-center gap-1.5">
            <GitBranch size={12} className="text-indigo-600 dark:text-indigo-300" />
            <span className="text-xs font-semibold text-ink">Expressão da condição</span>
          </div>

          {/* Modo dos ramos: binário (sim/não) ou switch (N casos). A conversão
              remapeia as arestas (sim→caso_1, não→senão e vice-versa). */}
          <div className="flex items-center justify-between rounded-lg border border-edge bg-canvas px-2.5 py-1.5">
            <span className="text-[11px] font-medium text-ink">Ramos</span>
            <div className="flex overflow-hidden rounded-md border border-edge text-[11px] font-semibold">
              <button
                type="button"
                className={!isSwitch ? 'bg-indigo-500 px-2 py-0.5 text-white' : 'bg-panel px-2 py-0.5 text-dim hover:text-ink'}
                onClick={() => onAlternarModo(node.id, false)}
              >
                Binário
              </button>
              <button
                type="button"
                className={isSwitch ? 'bg-indigo-500 px-2 py-0.5 text-white' : 'bg-panel px-2 py-0.5 text-dim hover:text-ink'}
                onClick={() => onAlternarModo(node.id, true)}
              >
                Switch
              </button>
            </div>
          </div>

          <div className={isSwitch ? 'flex flex-col' : 'grid grid-cols-[1fr_64px] gap-2'}>
            <Select
              label="Tipo"
              hint={'O que a decisão lê:\nContagem = COUNT(*) da tabela informada.\nValor de uma query = 1º valor do SELECT (1ª coluna da 1ª linha).\nLinhas processadas = rows_out do job na MESMA execução do pipeline.\nValor de SQL = valor publicado por um nó SQL a montante.'}
              value={c.tipo}
              onChange={e => patch({ tipo: e.target.value as NodeCondition['tipo'] })}
              className="text-xs"
            >
              <option value="contagem">Contagem de registros</option>
              <option value="query">Valor de uma query</option>
              <option value="linhas_job">Linhas processadas</option>
              <option value="valor_sql">Valor de SQL</option>
            </Select>
            {/* No switch cada caso tem o próprio operador/valor. */}
            {!isSwitch && (
              <Select label="Oper." value={c.operador} onChange={e => patch({ operador: e.target.value })} className="text-center text-xs">
                {COND_OPERADORES.map(op => <option key={op} value={op}>{op}</option>)}
              </Select>
            )}
          </div>

          {c.tipo === 'valor_sql' ? (
            <>
              {/* Nó SQL a montante cujo valor será comparado (deriva da lista de nós). */}
              <div className="flex flex-col gap-1">
                <Select
                  label="Nó SQL *"
                  value={c.source_job ?? ''}
                  onChange={e => patch({ source_job: e.target.value })}
                  className="text-xs"
                >
                  <option value="">Selecione um nó SQL…</option>
                  {sqlNodeNames.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                  {/* Mantém o nó salvo visível mesmo se ele não estiver mais no fluxo */}
                  {c.source_job && !sqlNodeNames.includes(c.source_job) && (
                    <option value={c.source_job}>{c.source_job} (fora do fluxo)</option>
                  )}
                </Select>
                {sqlNodeNames.length === 0 && (
                  <p className="text-[11px] text-dim/70">Crie um nó SQL e ligue-o a esta decisão.</p>
                )}
              </div>

              <Select
                label="Comparar como"
                hint={'Tipo usado na comparação: número, data ou texto.\nData aceita HOJE ou AAAA-MM-DD (nível de dia).'}
                value={c.comparacao ?? 'texto'}
                onChange={e => patch({ comparacao: e.target.value as NonNullable<NodeCondition['comparacao']> })}
                className="text-xs"
              >
                <option value="texto">Texto</option>
                <option value="data">Data</option>
                <option value="numero">Número</option>
              </Select>

              {!isSwitch && (
                <div className="flex flex-col gap-1">
                  <Input
                    label="Valor *"
                    value={c.valor}
                    onChange={e => patch({ valor: e.target.value })}
                    placeholder={c.comparacao === 'numero' ? 'ex: 100' : c.comparacao === 'data' ? 'ex: HOJE' : 'ex: OK'}
                    className="font-mono text-xs"
                  />
                  {c.comparacao === 'data' && (
                    <p className="text-[11px] text-dim/70">Use <code>HOJE</code> ou <code>AAAA-MM-DD</code>.</p>
                  )}
                </div>
              )}
            </>
          ) : (
          <>
          {!isSwitch && (
            <Input
              label="Valor *"
              type={c.tipo === 'linhas_job' ? 'number' : 'text'}
              value={c.valor}
              onChange={e => patch({ valor: e.target.value })}
              placeholder={c.tipo === 'query' ? 'ex: 1' : 'ex: 10000'}
              className="font-mono text-xs"
            />
          )}

          {c.tipo === 'linhas_job' ? (
            <>
              <div className="flex flex-col gap-1">
                <Select
                  label="Job *"
                  value={c.job_name ?? ''}
                  onChange={e => patch({ job_name: e.target.value })}
                  className="text-xs"
                >
                  <option value="">Selecione um job…</option>
                  {jobsDisponiveis.map(j => (
                    <option key={j} value={j}>{j}</option>
                  ))}
                  {/* Mantém o valor salvo visível mesmo se o job não estiver mais no fluxo */}
                  {c.job_name && !jobsDisponiveis.includes(c.job_name) && (
                    <option value={c.job_name}>{c.job_name} (fora do fluxo)</option>
                  )}
                </Select>
                {jobsDisponiveis.length === 0 && (
                  <p className="text-[11px] text-dim/70">Crie ao menos uma etapa para escolher o job.</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Input
                  label="Job filho (opcional)"
                  hint={'Job de runtime DENTRO do SEQUENCE selecionado acima — não é um job do pipeline.\nPreenchido, a decisão usa as linhas desse filho; vazio = total do job.'}
                  value={c.child_job ?? ''}
                  onChange={e => patch({ child_job: e.target.value })}
                  placeholder="ex: JB_CARGA_DETALHE"
                  className="font-mono text-xs"
                />
                <p className="text-[11px] text-dim/70">Vazio = usa o total do job.</p>
              </div>
            </>
          ) : c.tipo === 'contagem' ? (
            <>
              <Input
                label="Tabela * (db.schema.tabela)"
                value={c.tabela ?? ''}
                onChange={e => patch({ tabela: e.target.value })}
                placeholder="db.schema.tabela"
                className="font-mono text-xs"
              />
              <BancoCondicao
                connId={c.mssql_conn_id ?? ''}
                host={condHost}
                value={c.database ?? ''}
                onChange={v => patch({ database: v })}
              />
            </>
          ) : (
            <>
              <div className="flex flex-col gap-1">
                {onMaximizar && (
                  <button
                    type="button"
                    onClick={onMaximizar}
                    title="Ampliar o painel (modo focado) para editar o SELECT"
                    className="flex items-center gap-1 self-end rounded px-1.5 py-0.5 text-[10px] font-semibold text-dim hover:bg-edge/40 hover:text-ink"
                  >
                    <Maximize2 size={11} /> ampliar
                  </button>
                )}
                <Textarea
                  label="SQL (somente SELECT) *"
                  value={c.sql ?? ''}
                  rows={5}
                  onChange={e => patch({ sql: e.target.value })}
                  placeholder="ex: SELECT MAX(flag) FROM dbo.Controle WHERE ..."
                  className="font-mono text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <BancoCondicao
                  connId={c.mssql_conn_id ?? ''}
                  host={condHost}
                  value={c.database ?? ''}
                  onChange={v => patch({ database: v })}
                />
                <p className="text-[11px] text-dim/70">
                  Vazio = banco default da conexão. Preencha se o SELECT usa nomes sem banco.
                </p>
              </div>
            </>
          )}

          {/* Conexão MSSQL não se aplica à decisão por linhas processadas. */}
          {c.tipo !== 'linhas_job' && (
            <Select
              label="Conexão MSSQL (opcional)"
              value={c.mssql_conn_id ?? ''}
              onChange={e => patch({ mssql_conn_id: e.target.value, database: '' })}
              className="text-xs"
            >
              <option value="">Conexão padrão</option>
              {mssqlConns.map(cn => (
                <option key={cn.conn_id} value={cn.conn_id}>{cn.conn_id}{cn.host ? ` (${cn.host})` : ''}</option>
              ))}
            </Select>
          )}
          </>
          )}

          {/* Fail-loud: o que fazer se a AVALIAÇÃO da condição der erro. */}
          <div className="flex flex-col gap-1">
            {isSwitch ? (
              <Select
                label="Se a avaliação falhar"
                hint={'Falhar (recomendado): a execução para e o erro fica visível.\nSeguir pelo SENÃO roteia em silêncio — o pipeline não acusa a falha.'}
                value={c.on_error === 'senao' ? 'senao' : 'falhar'}
                onChange={e => patch({ on_error: e.target.value === 'senao' ? 'senao' : 'falhar' })}
                className="text-xs"
              >
                <option value="falhar">Falhar a execução (recomendado)</option>
                <option value="senao">Seguir pelo ramo SENÃO</option>
              </Select>
            ) : (
              <Select
                label="Se a avaliação falhar"
                hint={'Falhar (recomendado): a execução para e o erro fica visível.\nSeguir pelo ramo NÃO roteia em silêncio — o pipeline não acusa a falha.'}
                value={c.on_error === 'ramo_falso' ? 'ramo_falso' : 'falhar'}
                onChange={e => patch({ on_error: e.target.value === 'ramo_falso' ? 'ramo_falso' : 'falhar' })}
                className="text-xs"
              >
                <option value="falhar">Falhar a execução (recomendado)</option>
                <option value="ramo_falso">Seguir pelo ramo NÃO (legado)</option>
              </Select>
            )}
            {isSwitch && c.on_error === 'senao' && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400">
                Erro na avaliação roteia o SENÃO em silêncio — o pipeline não acusa a falha.
              </p>
            )}
            {!isSwitch && c.on_error === 'ramo_falso' && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400">
                Erro na avaliação roteia o ramo NÃO em silêncio — o pipeline não acusa a falha.
              </p>
            )}
            {!isSwitch && c.on_error !== 'ramo_falso' && c.on_error_legado && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400">
                Nó legado: a DAG publicada ainda degrada em silêncio — o "falhar"
                passa a valer após salvar o fluxo e republicar.
              </p>
            )}
          </div>

          {/* Simular: roda o SQL de origem e avalia a condição AO VIVO; o ramo
              escolhido fica destacado (animado) no canvas por alguns segundos.
              O resultado aparece AO LADO do botão (layout largo do dock). */}
          {c.tipo === 'valor_sql' && (
            <div className="flex flex-wrap items-center gap-2 border-t border-edge pt-2.5">
              <Button
                variant="secondary"
                size="sm"
                onClick={simular}
                loading={simulando}
                disabled={!c.source_job || (isSwitch
                  ? casos.length === 0 || casos.some(cs => !(cs.valor ?? '').toString().trim())
                  : !(c.valor ?? '').toString().trim())}
              >
                <Play size={13} /> Simular
              </Button>
              {simResult && (
                <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-edge bg-canvas px-2.5 py-1.5">
                  <p className="text-[11px] text-dim">
                    Valor obtido:{' '}
                    <span className="font-mono text-ink">
                      {simResult.valor_obtido == null ? <span className="text-dim/70">null</span> : simResult.valor_obtido}
                    </span>
                  </p>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] text-dim">{isSwitch ? 'caso:' : 'ramo:'}</span>
                    {isSwitch ? (
                      simResult.caso && simResult.caso !== 'senao' ? (
                        <span
                          className="rounded-full border px-2 py-0.5 text-[11px] font-semibold"
                          style={{ borderColor: casoCor(Math.max(0, casos.findIndex(cs => cs.nome === simResult.caso))), color: casoCor(Math.max(0, casos.findIndex(cs => cs.nome === simResult.caso))) }}
                        >
                          {simResult.caso}
                        </span>
                      ) : (
                        <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                          SENÃO
                        </span>
                      )
                    ) : simResult.ramo === 'sim' ? (
                      <span className="rounded-full border border-green-300 bg-green-100 px-2 py-0.5 text-[11px] font-semibold text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                        SIM
                      </span>
                    ) : (
                      <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                        NÃO
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Coluna direita: ramos ───────────────────────────────────────── */}
        <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-edge lg:pl-4">
          {isSwitch ? (
            <>
              {/* SWITCH: tabela dos casos — a ORDEM é a prioridade de avaliação
                  (primeiro que casar vence); os ramos são ligados pelas arestas. */}
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-xs font-semibold text-ink">
                  Casos (avaliados em ordem)
                  <Hint texto={'Avaliados de cima para baixo: o PRIMEIRO caso que casar vence.\nNenhum casou → segue pelo senão. Use ▲▼ para mudar a prioridade.'} />
                </span>
                <button
                  type="button"
                  className="flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] font-semibold text-indigo-600 hover:bg-edge/40 dark:text-indigo-300"
                  onClick={() => onAddCaso(node.id)}
                >
                  <Plus size={11} /> caso
                </button>
              </div>
              <div className="overflow-x-auto rounded-lg border border-edge bg-canvas">
                <table className="w-full min-w-[560px] border-collapse">
                  <thead>
                    <tr className="border-b border-edge text-left text-[11px] font-medium text-dim">
                      <th className="w-7 px-2 py-1.5 font-medium" aria-label="cor do handle" />
                      <th className="w-8 px-1 py-1.5 font-medium">nº</th>
                      <th className="px-1 py-1.5 font-medium">Nome</th>
                      <th className="w-[76px] px-1 py-1.5 font-medium">Operador</th>
                      <th className="px-1 py-1.5 font-medium">Valor</th>
                      <th className="px-2 py-1.5 font-medium">Ramo →</th>
                      <th className="w-[76px] px-2 py-1.5 font-medium" aria-label="ações" />
                    </tr>
                  </thead>
                  <tbody>
                    {casos.map((cs, i) => (
                      <tr
                        key={i}
                        className="border-b border-edge align-middle hover:bg-edge/20"
                        onMouseEnter={() => onHoverRamo?.(node.id, cs.nome)}
                        onMouseLeave={() => onHoverRamo?.(node.id, null)}
                      >
                        <td className="px-2 py-1.5">
                          <span
                            className="block h-2.5 w-2.5 rounded-full"
                            style={{ background: casoCor(i) }}
                            title={`cor do handle/aresta do caso ${i + 1}`}
                          />
                        </td>
                        <td className="px-1 py-1.5 font-mono text-[11px] text-dim">{i + 1}</td>
                        <td className="min-w-[140px] px-1 py-1.5">
                          <CasoNomeInput
                            nome={cs.nome}
                            placeholder={`caso_${i + 1}`}
                            onCommit={novo => onUpdateCaso(node.id, i, { nome: novo })}
                          />
                        </td>
                        <td className="px-1 py-1.5">
                          <Select
                            value={cs.operador}
                            onChange={e => onUpdateCaso(node.id, i, { operador: e.target.value })}
                            className="w-full px-1.5 text-center text-xs"
                          >
                            {COND_OPERADORES.map(op => <option key={op} value={op}>{op}</option>)}
                          </Select>
                        </td>
                        <td className="min-w-[110px] px-1 py-1.5">
                          <Input
                            value={cs.valor}
                            onChange={e => onUpdateCaso(node.id, i, { valor: e.target.value })}
                            placeholder="valor"
                            className="w-full font-mono text-xs"
                          />
                        </td>
                        <td className="min-w-[150px] px-2 py-1.5">
                          <div className="flex flex-wrap items-center gap-1">
                            {ramosDe(cs.nome).length === 0
                              ? <span className="text-[11px] text-dim/70">arraste do handle desta cor</span>
                              : ramosDe(cs.nome).map(pill)}
                          </div>
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="flex items-center justify-end gap-0.5 text-dim">
                            <button type="button" title="Subir (avalia antes)" className="rounded p-0.5 hover:bg-edge/40 hover:text-ink disabled:opacity-30" disabled={i === 0} onClick={() => onMoveCaso(node.id, i, -1)}>
                              <ChevronUp size={12} />
                            </button>
                            <button type="button" title="Descer (avalia depois)" className="rounded p-0.5 hover:bg-edge/40 hover:text-ink disabled:opacity-30" disabled={i === casos.length - 1} onClick={() => onMoveCaso(node.id, i, 1)}>
                              <ChevronDown size={12} />
                            </button>
                            <button type="button" title="Remover caso" className="rounded p-0.5 hover:bg-edge/40 hover:text-red-500" onClick={() => onRemoveCaso(node.id, i)}>
                              <X size={12} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {casos.length === 0 && (
                      <tr className="border-b border-edge">
                        <td colSpan={7} className="px-3 py-3 text-center text-[11px] text-dim">
                          Nenhum caso — adicione com “+ caso”.
                        </td>
                      </tr>
                    )}
                  </tbody>
                  <tfoot>
                    {/* Senão (nenhum caso casou) — rodapé fixo da tabela. */}
                    <tr
                      className="bg-panel/60 hover:bg-edge/20"
                      onMouseEnter={() => onHoverRamo?.(node.id, 'senao')}
                      onMouseLeave={() => onHoverRamo?.(node.id, null)}
                    >
                      <td className="px-2 py-2">
                        <span className="block h-2.5 w-2.5 rounded-full bg-slate-400 dark:bg-slate-500" title="cor do handle/aresta do senão" />
                      </td>
                      <td className="px-1 py-2" />
                      <td className="px-1 py-2 text-xs font-medium text-slate-600 dark:text-slate-300">senão</td>
                      <td colSpan={2} className="px-1 py-2 text-[11px] text-dim">nenhum caso casou</td>
                      <td className="px-2 py-2">
                        <div className="flex flex-wrap items-center gap-1">
                          {ramosDe('senao').length === 0
                            ? <span className="text-[11px] text-dim/70">nenhum (encerra o fluxo)</span>
                            : ramosDe('senao').map(pillSlate)}
                        </div>
                      </td>
                      <td className="px-2 py-2" />
                    </tr>
                  </tfoot>
                </table>
              </div>
              <p className="text-[11px] leading-relaxed text-dim">
                Os ramos são definidos arrastando os handles <b>coloridos</b> (um por caso,
                à direita) e o <b>senão</b> (baixo) da decisão até as etapas, direto no canvas.
              </p>
            </>
          ) : (
            <>
              {/* BINÁRIO: os dois blocos de pílulas (derivados das arestas) — read-only. */}
              <span className="text-xs font-semibold text-ink">Ramos</span>
              <p className="text-[11px] leading-relaxed text-dim">
                Os ramos são definidos arrastando os handles <b>sim</b> (direita) e <b>não</b> (baixo)
                da decisão até as etapas, direto no canvas.
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-edge bg-canvas p-3">
                  <span className="text-[11px] font-medium text-green-700 dark:text-green-400">Se verdadeiro → rodar</span>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {ramosDe('sim').length === 0 && <span className="text-[11px] text-dim/70">nenhum</span>}
                    {ramosDe('sim').map(m => (
                      <span key={m} className="rounded-full border border-green-300 bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                        {m}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg border border-edge bg-canvas p-3">
                  <span className="text-[11px] font-medium text-slate-600 dark:text-slate-300">Se falso → rodar</span>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {ramosDe('nao').length === 0 && <span className="text-[11px] text-dim/70">nenhum</span>}
                    {ramosDe('nao').map(pillSlate)}
                  </div>
                </div>
              </div>
            </>
          )}

          {Object.values(ramos).every(lista => lista.length === 0) && (
            <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Ligue ao menos um job em algum ramo (arrastando) antes de salvar.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
