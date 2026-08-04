// ── Painel de uma ETAPA ──────────────────────────────────────────────────────
// Fase 4 do redesign: layout LARGO para o dock inferior — 2 colunas no lg+
// (esquerda = identidade: nome/tipo/ordem; direita = campos por tipo via
// JobTypeFields SEM compact — em storedproc os params ganham a largura toda).
import { useCallback, useMemo } from 'react'
import type { Node } from '@xyflow/react'
import { Trash2 } from 'lucide-react'
import { Button } from '../../ui/Button'
import { Select } from '../../ui/Input'
import type { EtapaNodeData } from '../EtapaNode'
import { TYPE_META, CREATABLE_TYPES, type EtapaType } from '../types'
import {
  JobTypeFields, jobTypeFieldsErrors,
  type JobTypeFieldsValue, type JobFieldsType, type JobParam,
} from '../JobTypeFields'
import { ConferenciaDsJob } from '../../console/ConferenciaDsJob'
import { conferirNomeDs, sugestoesDs, useDsJobs, usePipelineProject } from '../../../lib/dsJobs'
import { NomeField } from './shared'

export interface PainelEtapaProps {
  node: Node
  // Pipeline do canvas — resolve o PROJETO DataStage para conferir o nome do job.
  pipeline: string
  sshConns: { conn_id: string; host: string }[]
  mssqlConns: { conn_id: string; host: string }[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchData: (nodeId: string, patch: Record<string, unknown>) => void
  onDelete: (id: string) => void
  // Maximiza o dock (modo focado) — o editor de código do nó python usa.
  onMaximizar?: () => void
}

export function PainelEtapa({ node, pipeline, sshConns, mssqlConns, onRename, onPatchData, onDelete, onMaximizar }: PainelEtapaProps) {
  const d = node.data as EtapaNodeData
  const isNew = !!d.isNew
  const meta = TYPE_META[d.type]
  const Icon = meta.icon

  // ── Conferência do nome contra o DataStage (incidente 2026-08-01) ────────
  // Só para etapa 'datastage': nos outros tipos o nome não é um job do DS.
  // A lista vem UMA vez por projeto (cache no servidor e no TanStack) e o
  // veredito é local — nenhuma ida ao servidor por tecla.
  const ehDatastage = d.type === 'datastage'
  const dsProject = usePipelineProject(pipeline)
  const dsJobsQ = useDsJobs(dsProject, ehDatastage)
  const conferencia = useMemo(
    () => ehDatastage
      ? conferirNomeDs(d.name, dsJobsQ.data)
      : { status: 'vazio' as const, sugestao: null, parecidos: [], motivo: null },
    [ehDatastage, d.name, dsJobsQ.data],
  )
  const sugerirJobsDs = useCallback(
    async (q: string) => sugestoesDs(q, dsJobsQ.data),
    [dsJobsQ.data],
  )

  // Valor consumido pela fonte única de campos por tipo (JobTypeFields).
  const typeValue: JobTypeFieldsValue = {
    job_type: d.type as JobFieldsType,
    job_command: d.command ?? '',
    ssh_conn_id: d.ssh_conn_id ?? '',
    verbose_log: !!d.verbose_log,
    mssql_conn_id: d.mssql_conn_id ?? '',
    mssql_database: d.mssql_database ?? '',
    params: (d.params as JobParam[] | undefined) ?? [],
    python: d.python,
  }

  // Patch do JobTypeFields → mapeia job_command de volta p/ `command` (nullável).
  function patchType(patch: Partial<JobTypeFieldsValue>) {
    const out: Record<string, unknown> = { ...patch }
    if ('job_command' in patch) {
      out.command = (patch.job_command ?? '') === '' ? null : patch.job_command
      delete out.job_command
    }
    if ('job_type' in patch) delete out.job_type   // tipo só muda na criação
    onPatchData(node.id, out)
  }

  // Validação AO VIVO (mesma régua do modal da Lista e do guard do salvar) —
  // o usuário vê a pendência no painel em vez de descobrir num toast de 422.
  const typeErrors = jobTypeFieldsErrors(typeValue)

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho do painel — o Excluir mora no topo direito (mesmo padrão
          nos 4 painéis). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${meta.chip}`}>
          <Icon size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">{meta.label}</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir etapa
        </Button>
      </div>

      {/* 2 colunas no lg+: esquerda = identidade; direita = campos por tipo. */}
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
        {/* ── Coluna esquerda: identidade ─────────────────────────────────── */}
        <div className="flex min-w-0 flex-col gap-3">
          <NomeField
            id={node.id}
            name={d.name}
            isNew={isNew}
            placeholder="ex: CARGA_CLIENTES"
            onRename={onRename}
            // Autocompletar com os nomes REAIS do projeto — só no nó NOVO
            // (num nó salvo o nome muda pelo rename transacional) e só quando
            // a lista chegou (DataStage fora = campo normal, sem travar nada).
            fetchSuggestions={ehDatastage && dsJobsQ.data?.disponivel ? sugerirJobsDs : undefined}
            extra={ehDatastage ? (
              <ConferenciaDsJob
                conferencia={conferencia}
                project={dsProject}
                carregando={dsJobsQ.isLoading}
                // Nó novo: preenche. Nó salvo: dispara o rename transacional
                // (a mesma confirmação de qualquer rename no canvas).
                onUsarGrafia={nome => { onRename(node.id, nome) }}
                rotuloAcao={isNew ? 'Usar esta grafia' : 'Renomear para'}
              />
            ) : undefined}
          />

          {/* Tipo (editável só na criação) e Ordem */}
          <div className="grid grid-cols-2 gap-2">
            <Select
              label="Tipo"
              value={d.type}
              disabled={!isNew}
              onChange={e => onPatchData(node.id, { type: e.target.value as EtapaType })}
              className={`text-xs ${!isNew ? 'opacity-60' : ''}`}
            >
              {CREATABLE_TYPES.map(t => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
            </Select>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-dim">Ordem</label>
              <input
                type="number"
                min={1}
                value={d.order ?? ''}
                onChange={e => {
                  const n = parseInt(e.target.value)
                  onPatchData(node.id, { order: Number.isFinite(n) && n >= 1 ? n : 1 })
                }}
                className="rounded-md border border-edge bg-panel px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
          {!isNew && <p className="-mt-1.5 text-[11px] text-dim/70">O tipo de um nó já salvo não é editável.</p>}
        </div>

        {/* ── Coluna direita: campos por TIPO — fonte única (Lista + Fluxo),
            agora no layout confortável (sem `compact`). ───────────────────── */}
        <div className="flex min-w-0 flex-col gap-3 lg:border-l lg:border-edge lg:pl-4">
          {typeErrors.length > 0 && (
            <div className="flex flex-col gap-0.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 dark:border-amber-800 dark:bg-amber-900/20">
              {typeErrors.map(e => (
                <p key={e} className="text-[11px] leading-snug text-amber-800 dark:text-amber-300">{e}</p>
              ))}
            </div>
          )}
          <JobTypeFields
            value={typeValue}
            onChange={patchType}
            sshConns={sshConns}
            mssqlConns={mssqlConns}
            onMaximizar={onMaximizar}
          />
        </div>
      </div>
    </div>
  )
}
