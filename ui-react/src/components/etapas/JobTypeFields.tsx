import { Plus } from 'lucide-react'
import { Button } from '../ui/Button'

// ─────────────────────────────────────────────────────────────────────────────
// FONTE ÚNICA de campos por TIPO de etapa (datastage | shell | python | storedproc).
//
// Este componente concentra TODA a regra de "quais campos cada tipo de etapa
// tem" e como validá-los. É reusado pela Lista (JobFormModal em Jobs.tsx) e,
// futuramente, pelo painel lateral do Fluxo (FluxoEditor). Qualquer campo novo
// adicionado num tipo aqui vale automaticamente nas duas telas.
//
// NÃO renderiza job_name / ordem / tipo / "depende de" — isso fica no consumidor.
// A decisão (job_type='decisao') também NÃO entra aqui: é tratada no Fluxo.
// ─────────────────────────────────────────────────────────────────────────────

// Tipos de dado de parâmetro de stored procedure — mesma lista do wizard.
export const PARAM_TYPES = ['VARCHAR', 'INT', 'DATE', 'DATETIME', 'DECIMAL', 'BIT'] as const

export interface JobParam {
  id?: string
  param_name: string
  param_type: string
  param_value: string
}

export type JobFieldsType = 'datastage' | 'shell' | 'python' | 'storedproc'

export interface JobTypeFieldsValue {
  job_type: JobFieldsType
  job_command: string
  ssh_conn_id: string
  verbose_log: boolean
  mssql_conn_id: string
  mssql_database: string
  params: JobParam[]
}

export interface ConnOpt { conn_id: string; host?: string }

export interface JobTypeFieldsProps {
  value: JobTypeFieldsValue
  onChange: (patch: Partial<JobTypeFieldsValue>) => void
  sshConns: ConnOpt[]
  mssqlConns: ConnOpt[]
  dbServer: string | null
  dbDatabases: string[]
  compact?: boolean   // layout denso p/ o painel lateral do Fluxo (fontes/spacing menores)
}

// ── Label / placeholder do campo de comando, por tipo ────────────────────────

export function jobCommandLabel(t: JobFieldsType): string {
  return t === 'datastage' ? 'Nome do job DataStage'
    : t === 'storedproc' ? 'Procedure (ex: dbo.sp_nome)'
    : t === 'python' ? 'Módulo / Path'
    : 'Comando / Path'
}

export function jobCommandPlaceholder(t: JobFieldsType): string {
  return t === 'datastage' ? 'ex: BiCvp.job_name'
    : t === 'shell' ? 'ex: /opt/scripts/run.sh'
    : t === 'python' ? 'ex: scripts.modulo.run'
    : 'ex: dbo.sp_procedure'
}

// ── Validação unificada (espelha as regras do wizard) ────────────────────────
// Retorna a lista de mensagens de erro (vazia = válido). Não valida nome/ordem,
// que pertencem ao consumidor.
export function jobTypeFieldsErrors(v: JobTypeFieldsValue): string[] {
  const errs: string[] = []
  if (v.job_type === 'shell' && !v.ssh_conn_id) {
    errs.push('Servidor SSH é obrigatório para etapas shell')
  }
  if (v.job_type === 'storedproc') {
    if (!v.mssql_conn_id) errs.push('Conexão MSSQL é obrigatória para etapas storedproc')
    const vistos = new Set<string>()
    v.params.forEach((p, i) => {
      const nome = p.param_name.trim()
      if (!nome) errs.push(`Parâmetro #${i + 1} sem nome definido`)
      if (!p.param_type || !(PARAM_TYPES as readonly string[]).includes(p.param_type)) {
        errs.push(`Parâmetro #${i + 1} sem tipo de dado válido`)
      }
      const key = nome.replace(/^@/, '').toLowerCase()
      if (nome && vistos.has(key)) errs.push(`Parâmetro "${nome}" duplicado`)
      vistos.add(key)
    })
  }
  return errs
}

// ── Sub-editor de parâmetros de stored procedure ─────────────────────────────
// Reusável; controlado pelo valor `params` e por `onChange` do pai.

export interface JobParamsEditorProps {
  params: JobParam[]
  onChange: (params: JobParam[]) => void
  compact?: boolean
}

function genParamId() {
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

export function JobParamsEditor({ params, onChange, compact }: JobParamsEditorProps) {
  const txt = compact ? 'text-xs' : 'text-sm'
  const inputCls = `bg-panel border text-ink rounded-md ${compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500`

  function addParam() {
    onChange([...params, { id: genParamId(), param_name: '', param_type: 'VARCHAR', param_value: '' }])
  }
  function removeParam(idx: number) {
    onChange(params.filter((_, i) => i !== idx))
  }
  function updateParam(idx: number, patch: Partial<JobParam>) {
    onChange(params.map((p, i) => i === idx ? { ...p, ...patch } : p))
  }

  return (
    <div className="flex flex-col gap-1.5">
      {params.map((p, idx) => (
        <div key={p.id ?? idx} className={`grid ${compact ? 'grid-cols-[1fr_90px_1fr_24px]' : 'grid-cols-[1fr_110px_1fr_28px]'} gap-1.5 items-start`}>
          <input
            type="text"
            value={p.param_name}
            onChange={e => updateParam(idx, { param_name: e.target.value })}
            placeholder="@nome_param"
            className={`${inputCls} ${!p.param_name.trim() ? 'border-red-500/60' : 'border-edge'}`}
          />
          <select
            value={p.param_type}
            onChange={e => updateParam(idx, { param_type: e.target.value })}
            className={`bg-panel border border-edge text-ink rounded-md ${compact ? 'px-1.5 py-1 text-xs' : 'px-2 py-1.5 text-sm'} focus:outline-none focus:ring-1 focus:ring-blue-500`}
          >
            {PARAM_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
          <input
            type="text"
            value={p.param_value}
            onChange={e => updateParam(idx, { param_value: e.target.value })}
            placeholder="valor fixo"
            className={`${inputCls} border-edge`}
          />
          <button
            type="button"
            onClick={() => removeParam(idx)}
            className={`text-dim hover:text-red-500 ${txt} justify-self-center pt-1`}
            title="Remover parâmetro"
          >✕</button>
        </div>
      ))}
      <Button size="sm" variant="ghost" onClick={addParam} className="self-start">
        <Plus size={compact ? 10 : 12} /> Adicionar parâmetro
      </Button>
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────

export function JobTypeFields({
  value, onChange, sshConns, mssqlConns, dbServer, dbDatabases, compact,
}: JobTypeFieldsProps) {
  const { job_type } = value

  // Densidade: o painel do Fluxo é estreito → fontes/paddings menores.
  const labelCls = `${compact ? 'text-[10px]' : 'text-xs'} text-dim font-medium`
  const fieldCls = `bg-panel border border-edge text-ink rounded-md ${compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500`
  const noteCls = `${compact ? 'text-[10px]' : 'text-[11px]'} text-dim/70`
  const gap = compact ? 'gap-2' : 'gap-4'

  return (
    <div className={`flex flex-col ${gap}`}>
      {/* Comando / nome / procedure — label e placeholder por tipo */}
      <div className="flex flex-col gap-1">
        <label className={labelCls}>{jobCommandLabel(job_type)}</label>
        <input
          type="text"
          value={value.job_command}
          onChange={e => onChange({ job_command: e.target.value })}
          placeholder={jobCommandPlaceholder(job_type)}
          className={`${fieldCls} font-mono`}
        />
        {job_type === 'storedproc' && (
          <p className={noteCls}>
            Apenas o <strong>nome</strong> da procedure (ex.: <code>dbo.sp_nome</code>). O sistema
            adiciona o <code>EXEC</code> e os parâmetros automaticamente — <strong>não</strong> escreva
            “EXEC”. Sem parâmetros cadastrados, a proc é chamada sem nenhum parâmetro.
          </p>
        )}
      </div>

      {/* shell → conexão SSH (obrigatória) */}
      {job_type === 'shell' && (
        <div className="flex flex-col gap-1">
          <label className={labelCls}>Servidor SSH (conexão Airflow) *</label>
          <select
            value={value.ssh_conn_id}
            onChange={e => onChange({ ssh_conn_id: e.target.value })}
            className={fieldCls}
          >
            <option value="">Selecione a conexão SSH...</option>
            {sshConns.map(c => (
              <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>
            ))}
          </select>
        </div>
      )}

      {/* datastage → log detalhado (caixa âmbar) */}
      {job_type === 'datastage' && (
        <div className={`bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/40 rounded-lg ${compact ? 'px-2.5 py-2' : 'px-3 py-3'}`}>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={value.verbose_log}
              onChange={e => onChange({ verbose_log: e.target.checked })}
              className="mt-0.5 accent-amber-400"
            />
            <div>
              <span className={`${compact ? 'text-xs' : 'text-sm'} text-ink font-medium`}>Log detalhado durante execução</span>
              <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-dim mt-0.5`}>
                Registra o progresso dos jobs filhos a cada 5 min (jobs SEQUENCE).
                Útil para diagnosticar lentidão — desative após a investigação.
              </p>
            </div>
          </label>
        </div>
      )}

      {/* storedproc → conexão MSSQL (obrigatória) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1">
          <label className={labelCls}>Conexão MSSQL *</label>
          <select
            value={value.mssql_conn_id}
            onChange={e => onChange({ mssql_conn_id: e.target.value })}
            className={fieldCls}
          >
            <option value="">Selecione a conexão...</option>
            {mssqlConns.map(c => (
              <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>
            ))}
          </select>
        </div>
      )}

      {/* storedproc → servidor / banco-alvo (opcional, mesmo servidor) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1">
          <label className={labelCls}>
            Servidor / Banco {dbServer && <span className="text-dim/60 font-mono normal-case">({dbServer})</span>}
          </label>
          <select
            value={value.mssql_database}
            onChange={e => onChange({ mssql_database: e.target.value })}
            className={fieldCls}
          >
            <option value="">Banco padrão da conexão</option>
            {dbDatabases.map(d => <option key={d} value={d}>{d}</option>)}
            {value.mssql_database && !dbDatabases.includes(value.mssql_database) && (
              <option value={value.mssql_database}>{value.mssql_database}</option>
            )}
          </select>
          <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-dim/60`}>
            A proc roda no banco escolhido, no mesmo servidor (<code>EXEC [banco].schema.proc</code>). Vazio = banco padrão.
          </p>
        </div>
      )}

      {/* storedproc → parâmetros (lista editável nome/tipo/valor) */}
      {job_type === 'storedproc' && (
        <div className="flex flex-col gap-1.5">
          <label className={`${labelCls} flex items-center gap-1.5`}>
            Parâmetros (opcional)
            {value.params.length > 0 && (
              <span className="bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800/40 rounded-full px-1.5 py-0 text-[9px] font-bold">
                {value.params.length}
              </span>
            )}
          </label>
          <JobParamsEditor
            params={value.params}
            onChange={params => onChange({ params })}
            compact={compact}
          />
        </div>
      )}
    </div>
  )
}
