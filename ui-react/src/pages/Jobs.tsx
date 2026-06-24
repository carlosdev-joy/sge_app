import { useState, useMemo, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { copyToClipboard } from '../lib/clipboard'
import {
  Edit, Plus, ClipboardList, Play, Save, X, Trash2,
  ChevronUp, ChevronDown, Copy, Network, ArrowUpDown,
  List, Workflow,
} from 'lucide-react'
import { useAirflowUrl } from '../lib/config'
import { FluxoEditor } from '../components/etapas/FluxoEditor'

// ── constants ──────────────────────────────────────────────────────────────

const JOB_TYPES = ['datastage', 'shell', 'python', 'storedproc', 'decisao'] as const
type JobType = typeof JOB_TYPES[number]

// ── types ──────────────────────────────────────────────────────────────────

interface Job {
  pipeline_name: string
  project_name?: string
  job_name: string
  execution_order: number
  job_type: JobType
  job_command: string | null
  active: number
  ssh_conn_id: string | null
  verbose_log: boolean
  created_at?: string
  updated_at?: string
}

interface SshConn { conn_id: string; host: string; description: string }

// ── helpers ────────────────────────────────────────────────────────────────

function pipelineToDagId(name: string) {
  return name
}

function copyText(t: string) {
  copyToClipboard(t).then(ok => ok ? toast.info('Copiado!') : toast.error('Erro ao copiar'))
}

function typeBadgeColor(t: JobType | string) {
  const m: Record<string, string> = {
    datastage: 'bg-blue-500/15 text-blue-400 border border-blue-800/40',
    shell: 'bg-amber-500/15 text-amber-400 border border-amber-800/40',
    python: 'bg-green-500/15 text-green-400 border border-green-800/40',
    storedproc: 'bg-purple-500/15 text-purple-400 border border-purple-800/40',
  }
  return m[t] ?? 'bg-slate-500/15 text-slate-400 border border-slate-700'
}

// ── JobFormModal ───────────────────────────────────────────────────────────

interface JobFormData {
  job_name: string
  execution_order: number
  job_type: JobType
  job_command: string
  ssh_conn_id: string
  verbose_log: boolean
  depends_on_jobs: string[]
  mssql_database: string
}

function JobFormModal({
  job, pipeline, onClose,
}: { job?: Job; pipeline: string; onClose: () => void }) {
  const qc = useQueryClient()
  const isEdit = !!job

  const [form, setForm] = useState<JobFormData>({
    job_name: job?.job_name ?? '',
    execution_order: job?.execution_order ?? 1,
    job_type: job?.job_type ?? 'datastage',
    job_command: job?.job_command ?? '',
    ssh_conn_id: job?.ssh_conn_id ?? '',
    verbose_log: job?.verbose_log ?? false,
    depends_on_jobs: [],
    mssql_database: '',
  })
  const [err, setErr] = useState<string[]>([])

  const { data: sshData } = useQuery<{ connections: SshConn[] }>({
    queryKey: ['ssh-connections'],
    queryFn: () => apiFetch('/airflow/connections/ssh'),
    staleTime: 60_000,
  })
  const sshConns = sshData?.connections ?? []

  // Bancos do mesmo servidor da conexão do ORQUESTRA (seletor de banco-alvo storedproc).
  const { data: dbData } = useQuery<{ server: string | null; databases: string[] }>({
    queryKey: ['job-databases'],
    queryFn: () => apiFetch('/jobs/databases'),
    staleTime: 300_000,
  })
  const dbServer    = dbData?.server ?? null
  const dbDatabases = dbData?.databases ?? []

  // Jobs irmãos do mesmo pipeline — candidatos a predecessores ("Depende de").
  const { data: pipeJobs } = useQuery<{ data: { job_name: string }[] }>({
    queryKey: ['jobs-of-pipeline', pipeline],
    queryFn: () => apiFetch(`/jobs?limit=200&filter_pipeline=${encodeURIComponent(pipeline)}`),
    staleTime: 30_000,
  })
  const siblings = (pipeJobs?.data ?? [])
    .map(j => j.job_name)
    .filter(n => n && n !== form.job_name.trim())

  // Carrega as dependências atuais do job em edição.
  useEffect(() => {
    if (!isEdit || !job) return
    apiFetch<{ depends_on_jobs?: string | null; mssql_database?: string | null }>(
      `/pipelines/jobs/${encodeURIComponent(pipeline)}/${encodeURIComponent(job.job_name)}`)
      .then(d => setForm(prev => ({
        ...prev,
        depends_on_jobs: (d.depends_on_jobs || '').split(',').map(s => s.trim()).filter(Boolean),
        mssql_database: d.mssql_database ?? '',
      })))
      .catch(() => {})
  }, [isEdit, pipeline, job])

  const saveMut = useMutation({
    mutationFn: () => apiFetch('/pipelines/jobs/register', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name: pipeline,
        job_name: form.job_name.trim(),
        execution_order: form.execution_order,
        job_type: form.job_type,
        job_command: form.job_command.trim() || null,
        ssh_conn_id: form.job_type === 'shell' ? (form.ssh_conn_id || null) : null,
        verbose_log: form.job_type === 'datastage' ? form.verbose_log : false,
        depends_on_jobs: form.depends_on_jobs,
        mssql_database: form.job_type === 'storedproc' ? (form.mssql_database || null) : null,
        require_lineage: false,
        operacao: 'upsert',
      }),
    }),
    onSuccess: () => {
      toast.success(isEdit ? 'Etapa atualizada' : 'Etapa criada')
      qc.invalidateQueries({ queryKey: ['jobs'] })
      onClose()
    },
    onError: (e: any) => {
      const detail = e.message
      try {
        const parsed = JSON.parse(detail)
        setErr(parsed.errors ?? [detail])
      } catch { setErr([detail]) }
    },
  })

  function validate() {
    const errs: string[] = []
    if (!form.job_name.trim()) errs.push('Nome da etapa é obrigatório')
    if (!form.execution_order || form.execution_order < 1) errs.push('Ordem deve ser >= 1')
    if (form.job_type === 'shell' && !form.ssh_conn_id) errs.push('Servidor SSH é obrigatório para jobs shell')
    setErr(errs)
    return errs.length === 0
  }

  function f<K extends keyof JobFormData>(k: K, v: JobFormData[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    setErr([])
  }

  return (
    <Modal open title={isEdit ? `Editar Etapa: ${job!.job_name}` : 'Nova Etapa'} onClose={onClose} size="md">
      <div className="flex flex-col gap-4">
        <div className="text-xs text-dim bg-canvas border border-edge rounded-lg px-3 py-2">
          Pipeline: <span className="font-mono text-ink">{pipeline}</span>
        </div>

        <Input
          label="Nome da Etapa *"
          value={form.job_name}
          onChange={e => f('job_name', e.target.value)}
          placeholder="ex: BiCvp_BaseCobranca_01_ext_Parcelas"
          disabled={isEdit}
          className={isEdit ? 'opacity-60' : ''}
        />

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Ordem de execução *</label>
            <input
              type="number" min={1}
              value={form.execution_order}
              onChange={e => f('execution_order', parseInt(e.target.value) || 1)}
              className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <p className="text-xs text-dim/60">Mesma ordem = execução paralela</p>
          </div>

          <Select label="Tipo *" value={form.job_type}
            onChange={e => f('job_type', e.target.value as JobType)}>
            {JOB_TYPES.map(t => <option key={t}>{t}</option>)}
          </Select>
        </div>

        <Input
          label={form.job_type === 'datastage' ? 'Nome do job DataStage' : form.job_type === 'storedproc' ? 'Procedure (ex: dbo.sp_nome)' : 'Comando / Path'}
          value={form.job_command}
          onChange={e => f('job_command', e.target.value)}
          placeholder={
            form.job_type === 'datastage' ? 'ex: BiCvp.job_name' :
            form.job_type === 'shell' ? 'ex: /opt/scripts/run.sh' :
            form.job_type === 'python' ? 'ex: scripts.modulo.run' :
            'ex: dbo.sp_procedure'
          }
        />
        {form.job_type === 'storedproc' && (
          <p className="text-[11px] text-dim/70 -mt-2">Apenas o <strong>nome</strong> da procedure (ex.: <code>dbo.sp_nome</code>). O sistema adiciona o <code>EXEC</code> e os parâmetros automaticamente — <strong>não</strong> escreva “EXEC”. Sem parâmetros cadastrados, a proc é chamada sem nenhum parâmetro.</p>
        )}

        {/* Servidor / banco-alvo da procedure (mesmo servidor da conexão do ORQUESTRA) */}
        {form.job_type === 'storedproc' && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">
              Servidor / Banco {dbServer && <span className="text-dim/60 font-mono">({dbServer})</span>}
            </label>
            <select
              value={form.mssql_database}
              onChange={e => f('mssql_database', e.target.value)}
              className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Banco padrão da conexão</option>
              {dbDatabases.map(d => <option key={d} value={d}>{d}</option>)}
              {form.mssql_database && !dbDatabases.includes(form.mssql_database) && (
                <option value={form.mssql_database}>{form.mssql_database}</option>
              )}
            </select>
            <p className="text-xs text-dim/60">A proc roda no banco escolhido, no mesmo servidor (<code>EXEC [banco].schema.proc</code>). Vazio = banco padrão.</p>
          </div>
        )}

        {/* Depende de — predecessores no mesmo pipeline (grafo de dependências) */}
        {siblings.length > 0 && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">
              Depende de <span className="text-dim/60">(começa quando estes terminarem com sucesso · vazio = inicia no começo)</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {siblings.map(nm => {
                const sel = form.depends_on_jobs.includes(nm)
                return (
                  <button key={nm} type="button"
                    onClick={() => f('depends_on_jobs', sel
                      ? form.depends_on_jobs.filter(d => d !== nm)
                      : [...form.depends_on_jobs, nm])}
                    className={`px-2.5 py-0.5 rounded-full text-xs border transition-colors ${sel
                      ? 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800'
                      : 'bg-panel text-dim border-edge hover:bg-edge/40'}`}>
                    {sel ? '✓ ' : ''}{nm}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* SSH para shell */}
        {form.job_type === 'shell' && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Servidor SSH (conexão Airflow) *</label>
            <select
              value={form.ssh_conn_id}
              onChange={e => f('ssh_conn_id', e.target.value)}
              className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Selecione a conexão SSH...</option>
              {sshConns.map(c => (
                <option key={c.conn_id} value={c.conn_id}>{c.conn_id} {c.host ? `(${c.host})` : ''}</option>
              ))}
            </select>
          </div>
        )}

        {/* Log detalhado para datastage */}
        {form.job_type === 'datastage' && (
          <div className="bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/40 rounded-lg px-3 py-3">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={form.verbose_log}
                onChange={e => f('verbose_log', e.target.checked)}
                className="mt-0.5 accent-amber-400"
              />
              <div>
                <span className="text-sm text-ink font-medium">Log detalhado durante execução</span>
                <p className="text-xs text-dim mt-0.5">
                  Registra o progresso dos jobs filhos a cada 5 min (jobs SEQUENCE).
                  Útil para diagnosticar lentidão — desative após a investigação.
                </p>
              </div>
            </label>
          </div>
        )}

        {err.length > 0 && (
          <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg p-3">
            {err.map((e, i) => <p key={i} className="text-xs text-red-700 dark:text-red-400">{e}</p>)}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1 border-t border-edge">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={saveMut.isPending} onClick={() => { if (validate()) saveMut.mutate() }}>
            <Save size={13} /> {isEdit ? 'Salvar alterações' : 'Criar Etapa'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── BulkModal ──────────────────────────────────────────────────────────────

function BulkModal({ pipeline, onClose }: { pipeline: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<{ ok: boolean; line: string; error?: string; parsed?: { job_name: string; execution_order: number; job_type: string; job_command: string | null } }[]>([])
  const [err, setErr] = useState('')

  function parseLines(raw: string) {
    return raw.split('\n').map(line => {
      const l = line.trim()
      if (!l) return null
      const parts = l.split(',').map(s => s.trim())
      const [job_name, ordem, job_type, ...rest] = parts
      const job_command = rest.join(',').trim() || null
      const execution_order = parseInt(ordem)
      if (!job_name) return { ok: false, line: l, error: 'Nome ausente' }
      if (isNaN(execution_order) || execution_order < 1) return { ok: false, line: l, error: 'Ordem inválida (use número inteiro >= 1)' }
      if (!JOB_TYPES.includes(job_type as JobType)) return { ok: false, line: l, error: `Tipo inválido: "${job_type}" — use: ${JOB_TYPES.join(', ')}` }
      return { ok: true, line: l, parsed: { job_name, execution_order, job_type, job_command } }
    }).filter(Boolean) as { ok: boolean; line: string; error?: string; parsed?: { job_name: string; execution_order: number; job_type: string; job_command: string | null } }[]
  }

  function handleChange(v: string) {
    setText(v)
    setPreview(parseLines(v))
    setErr('')
  }

  const saveMut = useMutation({
    mutationFn: (jobs: { job_name: string; execution_order: number; job_type: string; job_command: string | null }[]) => apiFetch('/pipelines/jobs/register', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name: pipeline,
        require_lineage: false,
        jobs: jobs.map(j => ({ ...j, verbose_log: false, ssh_conn_id: null, operacao: 'upsert' })),
      }),
    }),
    onSuccess: () => {
      toast.success('Etapas criadas com sucesso')
      qc.invalidateQueries({ queryKey: ['jobs'] })
      onClose()
    },
    onError: (e: any) => setErr(e.message),
  })

  const valid = preview.filter(p => p.ok)
  const invalid = preview.filter(p => !p.ok)

  function submit() {
    if (invalid.length > 0) { setErr('Corrija os erros antes de salvar'); return }
    if (valid.length === 0) { setErr('Nenhuma etapa válida para importar'); return }
    saveMut.mutate(valid.map(p => p.parsed!))
  }

  return (
    <Modal open title="Colar lista de Etapas" onClose={onClose} size="lg">
      <div className="flex flex-col gap-4">
        <div className="bg-canvas border border-edge rounded-lg p-3 text-xs text-dim">
          <p className="font-medium text-ink mb-1">Formato: <span className="font-mono">nome,ordem,tipo,comando</span></p>
          <p>Uma etapa por linha. Tipos válidos: <span className="font-mono text-blue-400">datastage</span>, <span className="font-mono text-amber-400">shell</span>, <span className="font-mono text-green-400">python</span>, <span className="font-mono text-purple-400">storedproc</span>.</p>
          <pre className="mt-2 text-dim/80 font-mono bg-panel/50 rounded p-2">BiCvp_Extract_01,1,datastage,BiCvp.Extract_01
BiCvp_Load_A,2,shell,/opt/scripts/load_a.sh
BiCvp_Load_B,2,python,scripts.load_b.run</pre>
        </div>

        <Textarea
          label={`Pipeline: ${pipeline}`}
          value={text}
          onChange={e => handleChange(e.target.value)}
          rows={8}
          placeholder="Cole a lista de etapas aqui..."
          className="font-mono text-xs"
        />

        {preview.length > 0 && (
          <div className="border border-edge rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-canvas border-b border-edge text-xs flex items-center gap-2">
              <span className="text-dim">Pré-visualização:</span>
              {valid.length > 0 && <span className="text-green-400 font-medium">{valid.length} válidos</span>}
              {invalid.length > 0 && <span className="text-red-400 font-medium">{invalid.length} com erro</span>}
            </div>
            <div className="max-h-48 overflow-y-auto">
              {preview.map((p, i) => (
                <div key={i} className={`flex items-center gap-2 px-3 py-1.5 text-xs border-b border-edge/40 ${p.ok ? '' : 'bg-red-50 dark:bg-red-900/10'}`}>
                  <span className={p.ok ? 'text-green-400' : 'text-red-400'}>{p.ok ? '✓' : '✗'}</span>
                  <span className="font-mono text-dim flex-1 truncate">{p.line}</span>
                  {!p.ok && <span className="text-red-400 shrink-0 max-w-[260px] text-right">{p.error}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {err && <p className="text-xs text-red-400">{err}</p>}

        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={saveMut.isPending} onClick={submit} disabled={valid.length === 0}>
            <ClipboardList size={13} /> Importar {valid.length} etapa{valid.length !== 1 ? 's' : ''}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Execution diagram ──────────────────────────────────────────────────────

function ExecDiagram({ jobs }: { jobs: Job[] }) {
  const groups = useMemo(() => {
    const map = new Map<number, Job[]>()
    jobs.forEach(j => {
      const o = j.execution_order
      if (!map.has(o)) map.set(o, [])
      map.get(o)!.push(j)
    })
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0])
  }, [jobs])

  if (groups.length === 0) return null

  const typeStyle: Record<string, { wrap: string; label: string; dot: string }> = {
    datastage:  { wrap: 'border-blue-500   bg-blue-50   dark:bg-blue-900/30   text-blue-800   dark:text-blue-200',   label: 'bg-blue-500   text-white', dot: 'bg-blue-500' },
    shell:      { wrap: 'border-amber-500  bg-amber-50  dark:bg-amber-900/30  text-amber-800  dark:text-amber-200',  label: 'bg-amber-500  text-white', dot: 'bg-amber-500' },
    python:     { wrap: 'border-green-500  bg-green-50  dark:bg-green-900/30  text-green-800  dark:text-green-200',  label: 'bg-green-500  text-white', dot: 'bg-green-500' },
    storedproc: { wrap: 'border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200', label: 'bg-purple-500 text-white', dot: 'bg-purple-500' },
  }
  const fallbackStyle = { wrap: 'border-slate-400 bg-slate-50 dark:bg-slate-800/30 text-slate-700 dark:text-slate-300', label: 'bg-slate-400 text-white', dot: 'bg-slate-400' }

  return (
    <div className="bg-canvas border border-edge rounded-xl p-4 overflow-x-auto">
      {/* Legenda */}
      <div className="flex items-center gap-4 mb-3">
        <p className="text-xs text-dim font-medium">Diagrama de execução (ordens → paralelos)</p>
        <div className="flex items-center gap-3 ml-auto">
          {Object.entries(typeStyle).map(([type, s]) => (
            <span key={type} className="flex items-center gap-1 text-[10px] text-dim">
              <span className={`w-2 h-2 rounded-full ${s.dot}`} />
              {type}
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-0 min-w-max">
        {groups.map(([order, gjobs], gi) => (
          <div key={order} className="flex items-center shrink-0">
            <div className="flex flex-col gap-2">
              {gjobs.map(j => {
                const s = typeStyle[j.job_type] ?? fallbackStyle
                return (
                  <div
                    key={j.job_name}
                    className={`border-2 rounded-lg px-3 py-2 text-xs font-mono min-w-[140px] max-w-[220px] shadow-sm ${s.wrap}`}
                    title={`${j.job_name} · Tipo: ${j.job_type}${j.job_command ? ' · ' + j.job_command : ''}`}
                  >
                    <div className="truncate font-semibold leading-tight">{j.job_name}</div>
                    <div className="flex items-center gap-1 mt-1">
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${s.label}`}>{j.job_type}</span>
                      <span className="text-[9px] opacity-50">#{order}</span>
                    </div>
                  </div>
                )
              })}
            </div>
            {gi < groups.length - 1 && (
              <div className="text-dim text-base mx-3 font-light select-none">→</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Confirmation modal for execute ─────────────────────────────────────────

function ExecConfirmModal({ pipeline, onConfirm, onClose }: { pipeline: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open title="Executar pipeline agora" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Deseja disparar o pipeline <span className="font-mono text-ink font-medium">{pipeline}</span> agora, fora do agendamento?
        </p>
        <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-800/40 rounded-lg px-3 py-2">
          ⚠ Esta ação inicia uma execução imediata no Airflow. Certifique-se que o pipeline não está em execução.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button className="border-green-800/40 text-green-400" onClick={() => { onConfirm(); onClose() }}>
            <Play size={13} /> Executar agora
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Delete confirmation modal ──────────────────────────────────────────────

function DeleteConfirmModal({ job, onConfirm, onClose }: { job: Job; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open title="Remover etapa" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Tem certeza que deseja remover a etapa{' '}
          <span className="font-mono text-ink font-medium">{job.job_name}</span>{' '}
          do pipeline <span className="font-mono text-ink">{job.pipeline_name}</span>?
        </p>
        <p className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/15 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2">
          Esta ação remove a etapa e sua lineage associada. Não pode ser desfeita.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button className="border-red-800/40 text-red-400 hover:text-red-300" onClick={() => { onConfirm(); onClose() }}>
            <Trash2 size={13} /> Remover etapa
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

type SortCol = 'job_name' | 'execution_order' | 'job_type' | 'pipeline_name'
type SortDir = 'asc' | 'desc'

export default function Jobs() {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'
  const airflowUiUrl = useAirflowUrl()

  // Search state — pré-carrega o pipeline da URL (?pipeline=...), p/ deep-link
  // a partir da tela de Pipelines (abre os jobs já filtrados, em nova aba).
  const [searchParams] = useSearchParams()
  const initialPipeline = (searchParams.get('pipeline') ?? '').trim()
  const [pipelineInput, setPipelineInput] = useState(initialPipeline)
  const [nameFilter, setNameFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [searched, setSearched] = useState(initialPipeline)
  const [hasSearched, setHasSearched] = useState(!!initialPipeline)
  const [page, setPage] = useState(0)
  const LIMIT = 50

  // UI state
  const [showDiagram, setShowDiagram] = useState(false)
  // Modo de visualização do pipeline: tabela (Lista) ou canvas (Fluxo).
  const [viewMode, setViewMode] = useState<'lista' | 'fluxo'>('lista')
  const [editJob, setEditJob] = useState<Job | undefined>()
  const [showNew, setShowNew] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [bannerVisible, setBannerVisible] = useState(true)
  const [deleteJob, setDeleteJob] = useState<Job | undefined>()
  const [showExecConfirm, setShowExecConfirm] = useState(false)

  // Sort state
  const [sortCol, setSortCol] = useState<SortCol>('execution_order')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Inline order edits
  const [orderEdits, setOrderEdits] = useState<Record<string, number>>({})
  const orderDirty = Object.keys(orderEdits).length > 0
  const orderEditCount = Object.keys(orderEdits).length

  const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (searched)   qs.set('filter_pipeline', searched)
  if (nameFilter) qs.set('filter_job_name', nameFilter)
  if (typeFilter) qs.set('filter_job_type', typeFilter)

  // Pipeline é opcional: pode-se buscar por pipeline, por nome do job, por tipo,
  // ou qualquer combinação. Pelo menos um filtro é exigido.
  const hasFilter = !!searched || !!nameFilter || !!typeFilter

  const { data, isLoading } = useQuery<{ total: number; pages: number; data: Job[] }>({
    queryKey: ['jobs', searched, nameFilter, typeFilter, page],
    queryFn: () => apiFetch(`/jobs?${qs}`),
    enabled: hasSearched && hasFilter,
  })

  // Sort client-side
  const jobs = useMemo(() => {
    const rows = [...(data?.data ?? [])]
    rows.sort((a, b) => {
      const av = sortCol === 'execution_order'
        ? (a[sortCol] ?? 999)
        : String(a[sortCol] ?? '').toLowerCase()
      const bv = sortCol === 'execution_order'
        ? (b[sortCol] ?? 999)
        : String(b[sortCol] ?? '').toLowerCase()
      return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
    })
    return rows
  }, [data, sortCol, sortDir])

  function toggleSort(col: SortCol) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  function SortBtn({ col, label }: { col: SortCol; label: string }) {
    const active = sortCol === col
    return (
      <button
        className={`flex items-center gap-1 hover:text-ink transition-colors ${active ? 'text-blue-400' : 'text-dim'}`}
        onClick={() => toggleSort(col)}
      >
        {label}
        {active
          ? sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
          : <ArrowUpDown size={11} className="opacity-40" />}
      </button>
    )
  }

  // Reorder mutation
  const reorderMut = useMutation({
    mutationFn: () => {
      const jobsPayload = (data?.data ?? []).map(j => ({
        job_name: j.job_name,
        execution_order: orderEdits[j.job_name] ?? j.execution_order,
      }))
      return apiFetch('/pipelines/jobs/reorder', {
        method: 'POST',
        body: JSON.stringify({ pipeline_name: searched, jobs: jobsPayload }),
      })
    },
    onSuccess: () => {
      toast.success('Ordem salva com sucesso')
      setOrderEdits({})
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  // Delete mutation
  const deleteMut = useMutation({
    mutationFn: (job: Job) =>
      apiFetch(`/pipelines/jobs/${encodeURIComponent(job.pipeline_name)}/${encodeURIComponent(job.job_name)}`, {
        method: 'DELETE',
      }),
    onSuccess: (_d, job) => {
      toast.success(`Etapa "${job.job_name}" removida`)
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  // Execute pipeline via Airflow
  const execMut = useMutation({
    mutationFn: () => {
      const dagId = pipelineToDagId(searched)
      const runId = `manual_orq_${Date.now()}`
      return apiFetch(`/airflow/dags/${encodeURIComponent(dagId)}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: runId, conf: {} }),
      })
    },
    onSuccess: (res: any) => {
      const dagId = pipelineToDagId(searched)
      toast.success(`Pipeline disparado! (${res?.dag_run_id ?? 'ok'})`)
      qc.invalidateQueries({ queryKey: ['jobs'] })
      setTimeout(() => window.open(`${airflowUiUrl}/dags/${dagId}/grid`, '_blank'), 1200)
    },
    onError: (e: any) => {
      const msg = e.message ?? ''
      if (msg.startsWith('404') || msg.includes('not found')) toast.error('DAG não encontrada. Gere o DAG primeiro.')
      else if (msg.startsWith('409') || msg.includes('already')) toast.error('Já existe uma execução ativa.')
      else toast.error(msg || 'Erro ao disparar pipeline')
    },
  })

  function doSearch() {
    if (!pipelineInput.trim() && !nameFilter.trim() && !typeFilter) {
      toast.error('Informe ao menos um filtro: pipeline, nome da etapa ou tipo.')
      return
    }
    setSearched(pipelineInput.trim())
    setHasSearched(true)
    setPage(0)
    setOrderEdits({})
    setShowDiagram(false)
    setViewMode('lista')
  }

  function doClear() {
    setNameFilter(''); setTypeFilter('')
    setSearched(''); setPipelineInput('')
    setHasSearched(false)
    setPage(0); setOrderEdits({})
    setViewMode('lista')
  }

  function handleOrderEdit(jobName: string, val: string) {
    const n = parseInt(val)
    if (!isNaN(n) && n >= 1) setOrderEdits(prev => ({ ...prev, [jobName]: n }))
  }

  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-4">

      {/* Info banner */}
      {bannerVisible && (
        <div className="bg-blue-50 dark:bg-blue-900/15 border border-blue-200 dark:border-blue-800/40 rounded-xl p-4 flex gap-3">
          <span className="text-xl shrink-0">⬡</span>
          <div className="flex-1 text-sm">
            <strong className="text-ink">O que é uma Etapa?</strong>
            <ul className="mt-1.5 space-y-1 text-xs text-dim list-disc list-inside">
              <li>Uma <strong className="text-ink">etapa</strong> é a unidade mínima de trabalho dentro de um pipeline — uma extração, transformação ou carga específica.</li>
              <li><strong className="text-ink">Tipos:</strong> <code className="font-mono">datastage</code> (IBM DataStage), <code className="font-mono">shell</code> (scripts bash), <code className="font-mono">python</code> (scripts .py) e <code className="font-mono">storedproc</code> (procedures SQL).</li>
              <li>A <strong className="text-ink">Ordem</strong> define a sequência: etapas com <em>mesma ordem</em> rodam <strong className="text-ink">em paralelo</strong>; ordens distintas rodam em série.</li>
            </ul>
          </div>
          <button onClick={() => setBannerVisible(false)} className="text-dim hover:text-ink shrink-0">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Filter bar */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <Autocomplete
            label="Pipeline"
            value={pipelineInput}
            onChange={setPipelineInput}
            onSelect={v => { setPipelineInput(v); setSearched(v); setHasSearched(true); setPage(0); setOrderEdits({}) }}
            fetchSuggestions={q =>
              apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                .then(r => r.data.map(p => p.pipeline_name))
            }
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="ex: etl_cobranca_diaria"
            className="w-64"
          />
          <Autocomplete
            label="Nome da etapa"
            value={nameFilter}
            onChange={setNameFilter}
            onSelect={v => { setNameFilter(v) }}
            fetchSuggestions={q =>
              apiFetch<{ data: { job_name: string }[] }>(
                `/jobs?limit=10${searched ? `&filter_pipeline=${encodeURIComponent(searched)}` : ''}&filter_job_name=${encodeURIComponent(q)}`
              ).then(r => r.data.map(j => j.job_name))
            }
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="filtrar por nome..."
            className="w-48"
          />
          <Select label="Tipo" value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)} className="w-36">
            <option value="">Todos</option>
            {JOB_TYPES.map(t => <option key={t}>{t}</option>)}
          </Select>
          <div className="flex gap-2 ml-auto items-end">
            <Button variant="secondary" size="sm" onClick={doClear}>× Limpar</Button>
            <Button size="sm" onClick={doSearch} disabled={!pipelineInput.trim() && !nameFilter.trim() && !typeFilter}>
              Buscar etapas
            </Button>
          </div>
        </div>
        {/* Dica de uso — pipeline é opcional */}
        <div className="mt-3 flex items-start gap-2 text-xs text-dim bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/30 rounded-lg px-3 py-2">
          <span className="text-blue-400 shrink-0">ℹ</span>
          <span>
            O <strong className="text-ink">pipeline é opcional</strong>: você pode filtrar por <strong className="text-ink">nome da etapa</strong> ou
            <strong className="text-ink"> tipo</strong> isoladamente (busca em todos os pipelines).
            Para ver <strong className="text-ink">todas as etapas de um pipeline</strong>, preencha o campo <strong className="text-ink">Pipeline</strong>.
          </span>
        </div>
      </div>

      {/* Empty state before search */}
      {!hasSearched && (
        <div className="bg-panel border border-edge rounded-xl py-16 flex flex-col items-center gap-2 text-dim">
          <span className="text-4xl">⬡</span>
          <p className="text-sm font-medium">Nenhuma etapa carregada</p>
          <p className="text-xs">Preencha um pipeline (para ver todas as etapas dele) <strong className="text-ink">ou</strong> filtre por nome/tipo, e clique em Buscar etapas.</p>
        </div>
      )}

      {hasSearched && isLoading && <PageSpinner />}

      {hasSearched && !isLoading && (
        <>
          {/* Context actions */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-dim flex-1">
              {total} etapa{total !== 1 ? 's' : ''}
              {searched
                ? <> · Pipeline: <span className="font-mono text-ink">{searched}</span></>
                : <> · <span className="text-ink">todos os pipelines</span>{(nameFilter || typeFilter) ? ' (filtrado)' : ''}</>}
            </span>
            {searched && (
              <>
                {/* Toggle Lista / Fluxo — Fluxo é o canvas interativo de etapas. */}
                <div className="inline-flex items-center rounded-md border border-edge bg-canvas p-0.5">
                  <button
                    onClick={() => setViewMode('lista')}
                    className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                      viewMode === 'lista'
                        ? 'bg-panel text-ink shadow-sm'
                        : 'text-dim hover:text-ink'
                    }`}
                  >
                    <List size={13} /> Lista
                  </button>
                  <button
                    onClick={() => setViewMode('fluxo')}
                    className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                      viewMode === 'fluxo'
                        ? 'bg-panel text-ink shadow-sm'
                        : 'text-dim hover:text-ink'
                    }`}
                  >
                    <Workflow size={13} /> Fluxo
                  </button>
                </div>
                {viewMode === 'lista' && (
                  <>
                    <Button variant="secondary" size="sm" onClick={() => setShowDiagram(d => !d)}>
                      <Network size={13} /> {showDiagram ? 'Ocultar' : 'Ver'} diagrama
                    </Button>
                    {!isViewer && (
                      <>
                        <Button
                          variant="secondary" size="sm"
                          disabled={!orderDirty}
                          loading={reorderMut.isPending}
                          onClick={() => reorderMut.mutate()}
                          className={orderDirty ? 'border-blue-600 text-blue-400 ring-1 ring-blue-700/50' : ''}
                        >
                          <Save size={13} /> Salvar ordem
                          {orderDirty && (
                            <span className="ml-1 bg-blue-600 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 leading-none">
                              {orderEditCount}
                            </span>
                          )}
                        </Button>
                        <Button variant="secondary" size="sm" onClick={() => setShowNew(true)}>
                          <Plus size={13} /> Adicionar Etapa
                        </Button>
                        <Button variant="secondary" size="sm" onClick={() => setShowBulk(true)}>
                          <ClipboardList size={13} /> Colar lista
                        </Button>
                        <Button
                          variant="secondary" size="sm"
                          loading={execMut.isPending}
                          onClick={() => setShowExecConfirm(true)}
                          className="border-green-800/40 text-green-400 hover:text-green-300"
                        >
                          <Play size={13} /> Executar agora
                        </Button>
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </div>

          {/* Modo Fluxo — canvas interativo (só faz sentido p/ um pipeline) */}
          {searched && viewMode === 'fluxo' && (
            <div className="h-[calc(100vh-16rem)]">
              <FluxoEditor pipeline={searched} />
            </div>
          )}

          {/* Execution diagram (só faz sentido para um pipeline) */}
          {searched && viewMode === 'lista' && showDiagram && <ExecDiagram jobs={data?.data ?? []} />}

          {/* Results table (modo Lista) */}
          {viewMode === 'lista' && (
          jobs.length === 0 ? (
            <div className="bg-panel border border-edge rounded-xl py-12 flex flex-col items-center gap-2 text-dim">
              <span className="text-3xl">⬡</span>
              <p className="text-sm">Nenhuma etapa encontrada{searched ? ` para "${searched}"` : nameFilter ? ` com nome "${nameFilter}"` : ''}</p>
            </div>
          ) : (
            <div className="bg-panel border border-edge rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs border-b border-edge bg-canvas">
                      <th className="px-3 py-2 text-left w-8 text-dim">#</th>
                      <th className="px-3 py-2 text-left"><SortBtn col="pipeline_name" label="Pipeline" /></th>
                      <th className="px-3 py-2 text-left"><SortBtn col="job_name" label="Etapa" /></th>
                      <th className="px-3 py-2 text-center w-24"><SortBtn col="execution_order" label="Ordem" /></th>
                      <th className="px-3 py-2 text-left"><SortBtn col="job_type" label="Tipo" /></th>
                      <th className="px-3 py-2 text-left">Comando</th>
                      <th className="px-3 py-2 text-left">Log</th>
                      {!isViewer && <th className="px-3 py-2 text-right">Ações</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j, i) => {
                      const currentOrder = orderEdits[j.job_name] ?? j.execution_order
                      const edited = orderEdits[j.job_name] !== undefined
                      return (
                        <tr key={j.job_name} className="border-b border-edge/40 hover:bg-edge/20 transition-colors group">
                          <td className="px-3 py-2 text-dim text-xs">{(page * LIMIT) + i + 1}</td>
                          <td className="px-3 py-2 text-dim text-xs font-mono truncate max-w-[160px]"
                            title={j.pipeline_name}>{j.pipeline_name}</td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-xs text-ink font-medium">{j.job_name}</span>
                              <button
                                onClick={() => copyText(j.job_name)}
                                className="text-dim hover:text-ink opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Copiar nome"
                              >
                                <Copy size={11} />
                              </button>
                            </div>
                          </td>
                          <td className="px-3 py-2 text-center">
                            {!isViewer && searched ? (
                              <input
                                type="number" min={1}
                                value={currentOrder}
                                onChange={e => handleOrderEdit(j.job_name, e.target.value)}
                                className={`w-16 text-center text-xs rounded border px-1.5 py-0.5 bg-canvas focus:outline-none focus:ring-1 focus:ring-blue-500 ${edited ? 'border-blue-500 text-blue-400' : 'border-edge text-dim'}`}
                              />
                            ) : (
                              <span className="text-dim text-xs">{currentOrder}</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${typeBadgeColor(j.job_type)}`}>
                              {j.job_type}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-dim text-xs max-w-[220px]">
                            <div className="truncate" title={j.job_command ?? ''}>
                              {j.job_command || <span className="text-dim/40">—</span>}
                              {j.job_type === 'shell' && j.ssh_conn_id && (
                                <span className="ml-1.5 text-[10px] bg-amber-100 text-amber-700 border border-amber-300 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800/40 px-1.5 py-0.5 rounded font-mono">
                                  {j.ssh_conn_id}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2">
                            {j.job_type === 'datastage' && j.verbose_log
                              ? <span className="text-xs text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-800/40 px-1.5 py-0.5 rounded" title="Log detalhado ativo — registra progresso dos jobs filhos a cada 5 min">🔍 detalhado</span>
                              : <span className="text-dim/40 text-xs">—</span>}
                          </td>
                          {!isViewer && (
                            <td className="px-3 py-2 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button variant="ghost" size="sm" title="Editar etapa" onClick={() => setEditJob(j)}>
                                  <Edit size={13} />
                                </Button>
                                <Button
                                  variant="ghost" size="sm" title="Remover etapa"
                                  loading={deleteMut.isPending && deleteJob?.job_name === j.job_name}
                                  onClick={() => setDeleteJob(j)}
                                  className="text-red-500/60 hover:text-red-400"
                                >
                                  <Trash2 size={13} />
                                </Button>
                              </div>
                            </td>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {(data?.pages ?? 1) > 1 && (
                <div className="px-4 py-2 flex items-center gap-3 border-t border-edge">
                  <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
                  <span className="text-xs text-dim">Página {page + 1} de {data?.pages ?? 1} · {total} etapas</span>
                  <Button variant="ghost" size="sm" disabled={page + 1 >= (data?.pages ?? 1)} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
                </div>
              )}
            </div>
          )
          )}
        </>
      )}

      {/* Modals */}
      {showNew && <JobFormModal pipeline={searched} onClose={() => setShowNew(false)} />}
      {editJob && <JobFormModal job={editJob} pipeline={editJob.pipeline_name || searched} onClose={() => setEditJob(undefined)} />}
      {showBulk && <BulkModal pipeline={searched} onClose={() => setShowBulk(false)} />}
      {deleteJob && (
        <DeleteConfirmModal
          job={deleteJob}
          onConfirm={() => deleteMut.mutate(deleteJob)}
          onClose={() => setDeleteJob(undefined)}
        />
      )}
      {showExecConfirm && (
        <ExecConfirmModal
          pipeline={searched}
          onConfirm={() => execMut.mutate()}
          onClose={() => setShowExecConfirm(false)}
        />
      )}
    </div>
  )
}
