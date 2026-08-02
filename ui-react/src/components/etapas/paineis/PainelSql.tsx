// ── Painel de um nó SQL ──────────────────────────────────────────────────────
// Edita a query (SELECT que retorna 1 valor) + conexão/banco e oferece um
// Pré-visualizar (POST /jobs/sql-preview) com grid de amostra (≤100 linhas).
// Fase 4 do redesign: layout LARGO para o dock inferior — 2 colunas no lg+
// (esquerda = SELECT grande + conexão/banco/on_error; direita = preview).
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node } from '@xyflow/react'
// Table2, não Database: mesmo glifo do nó/paleta (Database ficou p/ o DataStage).
import { Table2, Maximize2, Play, Trash2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Select, Textarea } from '../../ui/Input'
import { toast } from '../../ui/Toast'
import type { SqlNodeData } from '../SqlNode'
import { defaultSql, type SqlConfig } from '../fluxoTypes'
import { NomeField } from './shared'

export interface PainelSqlProps {
  node: Node
  mssqlConns: { conn_id: string; host: string }[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchSql: (nodeId: string, patch: Partial<SqlConfig>) => void
  onDelete: (id: string) => void
  // Maximiza o dock (modo focado) — o "tearsheet barato" p/ editar SQL longo.
  onMaximizar?: () => void
}

interface SqlPreview { columns: string[]; rows: unknown[][]; total: number; truncated: boolean }

export function PainelSql({ node, mssqlConns, onRename, onPatchSql, onDelete, onMaximizar }: PainelSqlProps) {
  const d = node.data as SqlNodeData
  const isNew = !!d.isNew
  const cfg = d.sql ?? defaultSql()
  const patch = (p: Partial<SqlConfig>) => onPatchSql(node.id, p)

  // Host derivado da conexão MSSQL escolhida — necessário p/ databases e preview.
  const host = useMemo(
    () => mssqlConns.find(c => c.conn_id === cfg.mssql_conn_id)?.host ?? '',
    [mssqlConns, cfg.mssql_conn_id],
  )

  // Bancos da conexão (enabled com conexão escolhida) — degrada para [].
  // conn_id primeiro: o backend lista com a credencial NATIVA da conexão
  // (dbo.etl_conexao) quando houver; host fica como fallback legado.
  const { data: dbData } = useQuery<{ server: string | null; databases: string[] }>({
    queryKey: ['sql-node-databases', cfg.mssql_conn_id, host],
    queryFn: () => apiFetch(
      `/jobs/databases?conn_id=${encodeURIComponent(cfg.mssql_conn_id ?? '')}&host=${encodeURIComponent(host)}`),
    enabled: !!cfg.mssql_conn_id || !!host,
    staleTime: 300_000,
  })
  const databases = dbData?.databases ?? []

  // Resultado do preview (amostra). Mantido em estado local, na coluna direita.
  const [preview, setPreview] = useState<SqlPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)

  // Troca de conexão: zera o banco (bancos pertencem ao servidor) e o preview.
  function onConnChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value
    patch({ mssql_conn_id: v || null, database: null })
    setPreview(null)
  }

  async function previewSql() {
    if (!host) { toast.error('Selecione uma conexão MSSQL.'); return }
    if (!cfg.database) { toast.error('Selecione um banco.'); return }
    if (!(cfg.sql || '').trim()) { toast.error('Escreva o SELECT antes de pré-visualizar.'); return }
    setPreviewing(true)
    try {
      const res = await apiFetch<SqlPreview>('/jobs/sql-preview', {
        method: 'POST',
        // mssql_conn_id primeiro (credencial nativa, a mesma do runtime);
        // host segue como fallback para conexões só do Airflow.
        body: JSON.stringify({
          mssql_conn_id: cfg.mssql_conn_id, host, database: cfg.database, sql: cfg.sql,
        }),
      })
      setPreview(res)
    } catch (e: any) {
      toast.error(e?.message || 'Falha ao pré-visualizar a consulta.')
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho do painel — o Excluir mora no topo direito (mesmo padrão
          nos 4 painéis). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-violet-500 text-white">
          <Table2 size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">Consulta SQL</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir nó SQL
        </Button>
      </div>

      {/* 2 colunas no lg+: esquerda = consulta; direita = pré-visualização. */}
      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* ── Coluna esquerda: SELECT + conexão/banco/on_error ────────────── */}
        <div className="flex min-w-0 flex-col gap-2">
          <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: LE_CONTROLE" onRename={onRename} />

          <div className="mt-1 flex items-center gap-1.5">
            <Table2 size={12} className="text-violet-600 dark:text-violet-300" />
            <span className="text-xs font-semibold text-ink">Consulta</span>
            {onMaximizar && (
              <button
                type="button"
                onClick={onMaximizar}
                title="Ampliar o painel (modo focado) para editar o SELECT"
                className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold text-dim hover:bg-edge/40 hover:text-ink"
              >
                <Maximize2 size={11} /> ampliar
              </button>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <Textarea
              label="SELECT *"
              hint={'Somente leitura: comece com SELECT/WITH — sem \';\' nem DML.\nO nó publica 1 valor: a 1ª coluna da 1ª linha do resultado.'}
              value={cfg.sql ?? ''}
              rows={10}
              onChange={e => patch({ sql: e.target.value })}
              placeholder="ex: SELECT MAX(flag) FROM dbo.Controle WHERE ..."
              className="font-mono text-xs"
            />
          </div>

          <Select
            label="Conexão MSSQL *"
            value={cfg.mssql_conn_id ?? ''}
            onChange={onConnChange}
            className="text-xs"
          >
            <option value="">Selecione a conexão…</option>
            {mssqlConns.map(cn => (
              <option key={cn.conn_id} value={cn.conn_id}>{cn.conn_id}{cn.host ? ` (${cn.host})` : ''}</option>
            ))}
            {/* Mantém a conexão salva visível mesmo se não estiver mais na lista */}
            {cfg.mssql_conn_id && !mssqlConns.some(cn => cn.conn_id === cfg.mssql_conn_id) && (
              <option value={cfg.mssql_conn_id}>{cfg.mssql_conn_id} (fora da lista)</option>
            )}
          </Select>

          <div className="flex flex-col gap-1">
            <Select
              label="Banco *"
              hint={'Banco onde o SELECT roda, no servidor da conexão.\nVazio = banco default da conexão — preencha se o SELECT usa nomes sem banco.'}
              value={cfg.database ?? ''}
              onChange={e => { patch({ database: e.target.value || null }); setPreview(null) }}
              disabled={!host}
              className={`text-xs ${!host ? 'opacity-60' : ''}`}
            >
              <option value="">{host ? 'Selecione o banco…' : 'Escolha a conexão primeiro'}</option>
              {databases.map(db => <option key={db} value={db}>{db}</option>)}
              {/* Mantém o banco salvo visível mesmo se não vier na lista atual */}
              {cfg.database && !databases.includes(cfg.database) && (
                <option value={cfg.database}>{cfg.database}</option>
              )}
            </Select>
            {!host && <p className="text-[10px] text-dim/70">Escolha a conexão para listar os bancos.</p>}
          </div>

          {/* Fail-loud: o que fazer se a consulta der erro no runtime. */}
          <div className="flex flex-col gap-1">
            <Select
              label="Se a consulta falhar"
              hint={'Falhar (recomendado): a execução para e o erro fica visível.\nPublicar nulo segue em silêncio — uma decisão a jusante pode rotear o ramo errado.'}
              value={cfg.on_error === 'nulo' ? 'nulo' : 'falhar'}
              onChange={e => patch({ on_error: e.target.value === 'nulo' ? 'nulo' : 'falhar' })}
              className="text-xs"
            >
              <option value="falhar">Falhar a execução (recomendado)</option>
              <option value="nulo">Publicar nulo e seguir (legado)</option>
            </Select>
            {cfg.on_error === 'nulo' && (
              <p className="text-[10px] text-amber-700 dark:text-amber-400">
                Erro no SELECT publica nulo em silêncio — uma decisão a jusante pode rotear o ramo errado.
              </p>
            )}
            {cfg.on_error !== 'nulo' && cfg.on_error_legado && (
              <p className="text-[10px] text-amber-700 dark:text-amber-400">
                Nó legado: a DAG publicada ainda degrada em silêncio — o "falhar"
                passa a valer após salvar o fluxo e republicar.
              </p>
            )}
          </div>
        </div>

        {/* ── Coluna direita: pré-visualização (amostra ≤ 100 linhas) ─────── */}
        <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-edge lg:pl-4">
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            onClick={previewSql}
            loading={previewing}
            disabled={!host || !cfg.database || !(cfg.sql || '').trim()}
          >
            <Play size={13} /> Pré-visualizar
          </Button>

          {preview ? (
            <div className="flex min-h-0 flex-col gap-1">
              <div className="max-h-80 overflow-auto rounded-lg border border-edge bg-panel">
                <table className="w-full border-collapse text-[10px]">
                  <thead className="sticky top-0 bg-canvas">
                    <tr>
                      {preview.columns.map((col, i) => (
                        <th key={i} className="border-b border-edge px-2 py-1 text-left font-semibold text-ink">
                          {col}
                        </th>
                      ))}
                      {preview.columns.length === 0 && (
                        <th className="border-b border-edge px-2 py-1 text-left font-semibold text-dim">—</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, ri) => (
                      <tr key={ri} className="odd:bg-canvas/40">
                        {row.map((cell, ci) => (
                          <td key={ci} className="border-b border-edge px-2 py-1 font-mono text-ink">
                            {cell == null ? <span className="text-dim/60">null</span> : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {preview.rows.length === 0 && (
                      <tr>
                        <td className="px-2 py-2 text-center text-dim" colSpan={Math.max(1, preview.columns.length)}>
                          Sem linhas.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="text-[10px] text-dim">
                {preview.total} linha{preview.total === 1 ? '' : 's'} (máx 100)
                {preview.truncated && (
                  <span className="ml-1 text-amber-700 dark:text-amber-400">· resultado truncado em 100</span>
                )}
              </p>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-edge px-4 py-6">
              <p className="text-center text-[11px] text-dim/80">
                A amostra do resultado (≤100 linhas) aparece aqui após pré-visualizar.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
