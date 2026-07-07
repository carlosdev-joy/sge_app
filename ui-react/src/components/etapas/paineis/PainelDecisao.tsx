// ── Painel de uma DECISÃO ────────────────────────────────────────────────────
import { useEffect, useState } from 'react'
import type { Node } from '@xyflow/react'
import { GitBranch, Play, Trash2, Plus, ChevronUp, ChevronDown, X } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
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
}

export function PainelDecisao({
  node, nodes, ramos, jobNames, sqlNodeNames, mssqlConns, onRename, onPatchCondition, onSimular, onDelete,
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

  return (
    <div className="flex flex-1 flex-col gap-3 p-3">
      {/* Cabeçalho */}
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-500 text-white">
          <GitBranch size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[10px] text-dim">Decisão (roteador)</p>
        </div>
      </div>

      <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: DECISAO_VOLUME" onRename={onRename} />

      {/* Editor de condição compacto (mesma lógica do DecisaoForm) */}
      <div className="border-t border-edge pt-2.5">
        <div className="mb-2 flex items-center gap-1.5">
          <GitBranch size={12} className="text-indigo-600 dark:text-indigo-300" />
          <span className="text-xs font-semibold text-ink">Expressão da condição</span>
        </div>

        <div className="flex flex-col gap-2">
          {/* Modo dos ramos: binário (sim/não) ou switch (N casos). A conversão
              remapeia as arestas (sim→caso_1, não→senão e vice-versa). */}
          <div className="flex items-center justify-between rounded-lg border border-edge bg-canvas px-2.5 py-1.5">
            <span className="text-[11px] font-medium text-ink">Ramos</span>
            <div className="flex overflow-hidden rounded-md border border-edge text-[10px] font-semibold">
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
            <Select label="Tipo" value={c.tipo} onChange={e => patch({ tipo: e.target.value as NodeCondition['tipo'] })} className="text-xs">
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
                  <p className="text-[10px] text-dim/70">Crie um nó SQL e ligue-o a esta decisão.</p>
                )}
              </div>

              <Select
                label="Comparar como"
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
                    <p className="text-[10px] text-dim/70">Use <code>HOJE</code> ou <code>AAAA-MM-DD</code>.</p>
                  )}
                </div>
              )}

              {/* Simular: roda o SQL de origem e avalia a condição AO VIVO; o ramo
                  escolhido fica destacado (animado) no canvas por alguns segundos. */}
              <div className="flex flex-col gap-2 border-t border-edge pt-2.5">
                <Button
                  variant="secondary"
                  size="sm"
                  className="self-start"
                  onClick={simular}
                  loading={simulando}
                  disabled={!c.source_job || (isSwitch
                    ? casos.length === 0 || casos.some(cs => !(cs.valor ?? '').toString().trim())
                    : !(c.valor ?? '').toString().trim())}
                >
                  <Play size={13} /> Simular
                </Button>
                {simResult && (
                  <div className="rounded-lg border border-edge bg-canvas p-2.5">
                    <p className="text-[11px] text-dim">
                      Valor obtido:{' '}
                      <span className="font-mono text-ink">
                        {simResult.valor_obtido == null ? <span className="text-dim/70">null</span> : simResult.valor_obtido}
                      </span>
                    </p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className="text-[11px] text-dim">{isSwitch ? 'caso:' : 'ramo:'}</span>
                      {isSwitch ? (
                        simResult.caso && simResult.caso !== 'senao' ? (
                          <span
                            className="rounded-full border px-2 py-0.5 text-[10px] font-semibold"
                            style={{ borderColor: casoCor(Math.max(0, casos.findIndex(cs => cs.nome === simResult.caso))), color: casoCor(Math.max(0, casos.findIndex(cs => cs.nome === simResult.caso))) }}
                          >
                            {simResult.caso}
                          </span>
                        ) : (
                          <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                            SENÃO
                          </span>
                        )
                      ) : simResult.ramo === 'sim' ? (
                        <span className="rounded-full border border-green-300 bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                          SIM
                        </span>
                      ) : (
                        <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                          NÃO
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
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
                  <p className="text-[10px] text-dim/70">Crie ao menos uma etapa para escolher o job.</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Input
                  label="Job filho (opcional)"
                  value={c.child_job ?? ''}
                  onChange={e => patch({ child_job: e.target.value })}
                  placeholder="ex: JB_CARGA_DETALHE"
                  className="font-mono text-xs"
                />
                <p className="text-[10px] text-dim/70">Vazio = usa o total do job.</p>
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
              <Input
                label="Banco (opcional)"
                value={c.database ?? ''}
                onChange={e => patch({ database: e.target.value })}
                placeholder="ex: BI_DW"
                className="font-mono text-xs"
              />
            </>
          ) : (
            <>
              <Textarea
                label="SQL (somente SELECT) *"
                value={c.sql ?? ''}
                rows={3}
                onChange={e => patch({ sql: e.target.value })}
                placeholder="ex: SELECT MAX(flag) FROM dbo.Controle WHERE ..."
                className="font-mono text-xs"
              />
              <div className="flex flex-col gap-1">
                <Input
                  label="Banco (opcional)"
                  value={c.database ?? ''}
                  onChange={e => patch({ database: e.target.value })}
                  placeholder="ex: BI_DW"
                  className="font-mono text-xs"
                />
                <p className="text-[10px] text-dim/70">
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
              onChange={e => patch({ mssql_conn_id: e.target.value })}
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

          {/* SWITCH: editor dos casos — a ORDEM é a prioridade de avaliação
              (primeiro que casar vence); os ramos são ligados pelas arestas. */}
          {isSwitch && (
            <div className="flex flex-col gap-1.5 border-t border-edge pt-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-ink">Casos (avaliados em ordem)</span>
                <button
                  type="button"
                  className="flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold text-indigo-600 hover:bg-edge/40 dark:text-indigo-300"
                  onClick={() => onAddCaso(node.id)}
                >
                  <Plus size={11} /> caso
                </button>
              </div>
              {casos.map((cs, i) => (
                <div key={i} className="flex flex-col gap-1 rounded-lg border border-edge bg-canvas p-1.5">
                  <div className="grid grid-cols-[8px_1fr_52px_1fr] items-center gap-1.5">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: casoCor(i) }}
                      title={`cor do handle/aresta do caso ${i + 1}`}
                    />
                    <CasoNomeInput
                      nome={cs.nome}
                      placeholder={`caso_${i + 1}`}
                      onCommit={novo => onUpdateCaso(node.id, i, { nome: novo })}
                    />
                    <Select
                      value={cs.operador}
                      onChange={e => onUpdateCaso(node.id, i, { operador: e.target.value })}
                      className="text-center text-[11px]"
                    >
                      {COND_OPERADORES.map(op => <option key={op} value={op}>{op}</option>)}
                    </Select>
                    <Input
                      value={cs.valor}
                      onChange={e => onUpdateCaso(node.id, i, { valor: e.target.value })}
                      placeholder="valor"
                      className="font-mono text-[11px]"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex min-w-0 flex-wrap items-center gap-1">
                      {ramosDe(cs.nome).length === 0
                        ? <span className="text-[10px] text-dim/70">sem ramo — arraste do handle desta cor</span>
                        : ramosDe(cs.nome).map(m => (
                            <span key={m} className="rounded-full border border-edge bg-panel px-1.5 py-0.5 text-[10px] font-medium text-ink">{m}</span>
                          ))}
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5 text-dim">
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
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Fail-loud: o que fazer se a AVALIAÇÃO da condição der erro. */}
          <div className="flex flex-col gap-1">
            {isSwitch ? (
              <Select
                label="Se a avaliação falhar"
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
                value={c.on_error === 'ramo_falso' ? 'ramo_falso' : 'falhar'}
                onChange={e => patch({ on_error: e.target.value === 'ramo_falso' ? 'ramo_falso' : 'falhar' })}
                className="text-xs"
              >
                <option value="falhar">Falhar a execução (recomendado)</option>
                <option value="ramo_falso">Seguir pelo ramo NÃO (legado)</option>
              </Select>
            )}
            {isSwitch && c.on_error === 'senao' && (
              <p className="text-[10px] text-amber-700 dark:text-amber-400">
                Erro na avaliação roteia o SENÃO em silêncio — o pipeline não acusa a falha.
              </p>
            )}
            {!isSwitch && c.on_error === 'ramo_falso' && (
              <p className="text-[10px] text-amber-700 dark:text-amber-400">
                Erro na avaliação roteia o ramo NÃO em silêncio — o pipeline não acusa a falha.
              </p>
            )}
            {!isSwitch && c.on_error !== 'ramo_falso' && c.on_error_legado && (
              <p className="text-[10px] text-amber-700 dark:text-amber-400">
                Nó legado: a DAG publicada ainda degrada em silêncio — o "falhar"
                passa a valer após salvar o fluxo e republicar.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Ramos atuais (derivados das arestas) — read-only */}
      <div className="rounded-lg border border-edge bg-canvas p-2.5">
        <p className="mb-2 text-[10px] leading-relaxed text-dim">
          {isSwitch ? (
            <>Os ramos são definidos arrastando os handles <b>coloridos</b> (um por caso,
            à direita) e o <b>senão</b> (baixo) da decisão até as etapas, direto no canvas.</>
          ) : (
            <>Os ramos são definidos arrastando os handles <b>sim</b> (direita) e <b>não</b> (baixo)
            da decisão até as etapas, direto no canvas.</>
          )}
        </p>
        <div className="flex flex-col gap-2">
          {isSwitch ? (
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-medium text-slate-600 dark:text-slate-300">Senão (nenhum caso casou) → rodar</span>
              <div className="flex flex-wrap gap-1">
                {ramosDe('senao').length === 0 && <span className="text-[10px] text-dim/70">nenhum (encerra o fluxo)</span>}
                {ramosDe('senao').map(m => (
                  <span key={m} className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-medium text-green-700 dark:text-green-400">Se verdadeiro → rodar</span>
                <div className="flex flex-wrap gap-1">
                  {ramosDe('sim').length === 0 && <span className="text-[10px] text-dim/70">nenhum</span>}
                  {ramosDe('sim').map(m => (
                    <span key={m} className="rounded-full border border-green-300 bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                      {m}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-medium text-slate-600 dark:text-slate-300">Se falso → rodar</span>
                <div className="flex flex-wrap gap-1">
                  {ramosDe('nao').length === 0 && <span className="text-[10px] text-dim/70">nenhum</span>}
                  {ramosDe('nao').map(m => (
                    <span key={m} className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
        {Object.values(ramos).every(lista => lista.length === 0) && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            Ligue ao menos um job em algum ramo (arrastando) antes de salvar.
          </p>
        )}
      </div>

      <div className="mt-auto border-t border-edge pt-3">
        <Button variant="danger" size="sm" className="w-full justify-center" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir decisão
        </Button>
      </div>
    </div>
  )
}
