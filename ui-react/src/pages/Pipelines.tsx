import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import {
  ChevronRight, ChevronDown, Plus, Edit, Eye, GitBranch,
  History, Play, PowerOff, Settings, Save,
} from 'lucide-react'

// ── types ──────────────────────────────────────────────────────────────────

interface Pipeline {
  pipeline_name: string
  project_name: string | null
  domain: string | null
  tags: string | null
  scheduled_time: string | null
  schedule_type: string | null
  schedule_hour: number | null
  schedule_minute: number | null
  schedule_dow: number | null
  schedule_dom: number | null
  active: number
  dag_criada: number
  envia_msg_inicio: number
  envia_msg_fim: number
  envia_msg_erro: number
  depends_on: string | null
  dag_start_date: string | null
  descricao: string | null
  criticidade: string
  sla_minutos: number | null
  ambiente: string
  max_active_runs: number
  retries_count: number
  retry_delay_seconds: number
  pool_name: string | null
  runbook_md: string | null
  last_execution: string | null
  created_at: string | null
  updated_at: string | null
}

interface AuditRow {
  changed_at: string
  changed_by: string
  field_name: string
  old_value: string | null
  new_value: string | null
}

interface LineageObject {
  object_name: string
  object_type: string
  database_name?: string
}

interface LineageJob {
  job_name: string
  origens: LineageObject[]
  destinos: LineageObject[]
}

// ── constants ──────────────────────────────────────────────────────────────

const SCHEDULE_TYPES = ['daily', 'weekly', 'monthly', 'hourly', 'biweekly', 'on_demand'] as const
const SCHEDULE_LABELS: Record<string, string> = {
  daily: 'Diário', weekly: 'Semanal', monthly: 'Mensal',
  hourly: 'A cada hora', biweekly: 'Quinzenal', on_demand: 'Sob demanda',
}
const CRITICIDADES   = ['Alta', 'Media', 'Baixa'] as const
const AMBIENTES      = ['PROD', 'HML', 'DEV'] as const
const DAG_FACTORY_ID = 'etl_dag_factory'
const AIRFLOW_UI     = 'https://airflow.caixavidaeprevidencia.intranet'

// ── helpers ────────────────────────────────────────────────────────────────

function pipelineToDagId(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9_]/g, '_')
}

function buildCron(type: string, h: number, m: number, dow: number, dom: number) {
  if (type === 'on_demand') return '(sem agendamento automático)'
  if (type === 'hourly')   return `${m} * * * *`
  if (type === 'daily')    return `${m} ${h} * * *`
  if (type === 'weekly')   return `${m} ${h} * * ${dow}`
  if (type === 'monthly')  return `${m} ${h} ${dom} * *`
  if (type === 'biweekly') return `${m} ${h} ${dom},${dom + 15} * *`
  return `${m} ${h} * * *`
}

function critColor(c: string) {
  return c === 'Alta' ? 'text-red-400' : c === 'Media' ? 'text-yellow-400' : 'text-green-400'
}

// ── PipelineFormModal ──────────────────────────────────────────────────────

interface FormState {
  pipeline_name: string
  project_name: string
  domain: string
  tags: string
  descricao: string
  schedule_type: string
  schedule_hour: number
  schedule_minute: number
  schedule_dow: number
  schedule_dom: number
  active: boolean
  dag_start_date: string
  envia_msg_inicio: boolean
  envia_msg_fim: boolean
  envia_msg_erro: boolean
  criticidade: string
  sla_minutos: string
  ambiente: string
  max_active_runs: number
  retries_count: number
  retry_delay_seconds: number
  pool_name: string
  depends_on: string
  runbook_md: string
}

const defaultForm = (): FormState => ({
  pipeline_name: '', project_name: '', domain: '', tags: '', descricao: '',
  schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0,
  schedule_dow: 1, schedule_dom: 1, active: true,
  dag_start_date: '', envia_msg_inicio: true, envia_msg_fim: true, envia_msg_erro: true,
  criticidade: 'Media', sla_minutos: '', ambiente: 'PROD',
  max_active_runs: 1, retries_count: 1, retry_delay_seconds: 300,
  pool_name: '', depends_on: '', runbook_md: '',
})

function pipelineToForm(p: Pipeline): FormState {
  return {
    pipeline_name:      p.pipeline_name,
    project_name:       p.project_name ?? '',
    domain:             p.domain ?? '',
    tags:               p.tags ?? '',
    descricao:          p.descricao ?? '',
    schedule_type:      p.schedule_type ?? 'daily',
    schedule_hour:      p.schedule_hour ?? 6,
    schedule_minute:    p.schedule_minute ?? 0,
    schedule_dow:       p.schedule_dow ?? 1,
    schedule_dom:       p.schedule_dom ?? 1,
    active:             !!p.active,
    dag_start_date:     p.dag_start_date ?? '',
    envia_msg_inicio:   !!p.envia_msg_inicio,
    envia_msg_fim:      !!p.envia_msg_fim,
    envia_msg_erro:     !!p.envia_msg_erro,
    criticidade:        p.criticidade ?? 'Media',
    sla_minutos:        p.sla_minutos != null ? String(p.sla_minutos) : '',
    ambiente:           p.ambiente ?? 'PROD',
    max_active_runs:    p.max_active_runs ?? 1,
    retries_count:      p.retries_count ?? 1,
    retry_delay_seconds: p.retry_delay_seconds ?? 300,
    pool_name:          p.pool_name ?? '',
    depends_on:         p.depends_on ?? '',
    runbook_md:         p.runbook_md ?? '',
  }
}

type FormSection = 'basic' | 'schedule' | 'notify' | 'advanced'

function PipelineFormModal({ pipeline, onClose }: { pipeline?: Pipeline; onClose: () => void }) {
  const qc    = useQueryClient()
  const user  = useAuthStore(s => s.user)
  const isEdit = !!pipeline
  const [form, setForm]     = useState<FormState>(pipeline ? pipelineToForm(pipeline) : defaultForm())
  const [errs, setErrs]     = useState<string[]>([])
  const [errTabs, setErrTabs] = useState<Set<FormSection>>(new Set())
  const [section, setSection] = useState<FormSection>('basic')

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  const { data: allPipes } = useQuery<{ data: Pipeline[] }>({
    queryKey: ['pipelines', '', '', '', 0],
    queryFn: () => apiFetch('/pipelines?limit=200'),
    staleTime: 60_000,
  })
  const otherPipelines = (allPipes?.data ?? [])
    .map(p => p.pipeline_name)
    .filter(n => n !== form.pipeline_name)

  function f<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    setErrs([])
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const h = String(form.schedule_hour).padStart(2, '0')
      const m = String(form.schedule_minute).padStart(2, '0')
      return apiFetch('/pipelines/register', {
        method: 'POST',
        body: JSON.stringify({
          pipeline_name:       form.pipeline_name.trim().toUpperCase(),
          project_name:        form.project_name,
          domain:              form.domain.trim().toUpperCase() || 'Geral',
          tags:                form.tags.trim().toUpperCase(),
          descricao:           form.descricao.trim() || null,
          scheduled_time:      `${h}:${m}:00`,
          schedule_type:       form.schedule_type,
          schedule_hour:       form.schedule_hour,
          schedule_minute:     form.schedule_minute,
          schedule_dow:        form.schedule_dow,
          schedule_dom:        form.schedule_dom,
          active:              form.active ? 1 : 0,
          dag_start_date:      form.dag_start_date || null,
          envia_msg_inicio:    form.envia_msg_inicio ? 1 : 0,
          envia_msg_fim:       form.envia_msg_fim ? 1 : 0,
          envia_msg_erro:      form.envia_msg_erro ? 1 : 0,
          criticidade:         form.criticidade,
          sla_minutos:         form.sla_minutos ? parseInt(form.sla_minutos) : null,
          ambiente:            form.ambiente,
          max_active_runs:     form.max_active_runs,
          retries_count:       form.retries_count,
          retry_delay_seconds: form.retry_delay_seconds,
          pool_name:           form.pool_name.trim() || null,
          depends_on:          form.depends_on.trim() || null,
          runbook_md:          form.runbook_md.trim() || null,
          changed_by:          user?.matricula ?? 'react-ui',
          dag_criada:          pipeline?.dag_criada ?? 0,
        }),
      })
    },
    onSuccess: (res: any) => {
      toast.success(isEdit ? 'Pipeline atualizado' : `Pipeline criado · cron: ${res?.cron ?? ''}`)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      onClose()
    },
    onError: (e: any) => setErrs([e.message]),
  })

  function validate() {
    const e: string[] = []
    const badTabs = new Set<FormSection>()
    if (!form.pipeline_name.trim()) { e.push('Nome do pipeline é obrigatório'); badTabs.add('basic') }
    if (!form.project_name) { e.push('Projeto é obrigatório'); badTabs.add('basic') }
    if (form.schedule_type !== 'on_demand') {
      if (form.schedule_hour < 0 || form.schedule_hour > 23) { e.push('Hora inválida (0–23)'); badTabs.add('schedule') }
      if (form.schedule_minute < 0 || form.schedule_minute > 59) { e.push('Minuto inválido (0–59)'); badTabs.add('schedule') }
      if ((form.schedule_type === 'weekly' || form.schedule_type === 'biweekly') && (form.schedule_dow < 0 || form.schedule_dow > 6)) {
        e.push('Dia da semana inválido (0–6)'); badTabs.add('schedule')
      }
      if ((form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (form.schedule_dom < 1 || form.schedule_dom > 28)) {
        e.push('Dia do mês inválido (1–28)'); badTabs.add('schedule')
      }
    }
    setErrs(e)
    setErrTabs(badTabs)
    if (badTabs.size > 0 && !badTabs.has(section)) {
      setSection([...badTabs][0])
    }
    return e.length === 0
  }

  const tabs: { id: FormSection; label: string }[] = [
    { id: 'basic',    label: 'Identificação' },
    { id: 'schedule', label: 'Agendamento' },
    { id: 'notify',   label: 'Notificações' },
    { id: 'advanced', label: 'Avançado' },
  ]

  return (
    <Modal open title={isEdit ? `Editar: ${pipeline!.pipeline_name}` : 'Novo Pipeline'} onClose={onClose} size="lg">
      <div className="flex flex-col gap-4">

        {/* Section tabs */}
        <div className="flex gap-1 border-b border-edge">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setSection(t.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors relative ${section === t.id ? 'bg-blue-600/20 text-blue-300 border-b-2 border-blue-500' : 'text-dim hover:text-ink'}`}
            >
              {t.label}
              {errTabs.has(t.id) && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-red-500" title="Campos inválidos nesta aba" />
              )}
            </button>
          ))}
        </div>

        {/* ── IDENTIFICAÇÃO ── */}
        {section === 'basic' && (
          <div className="flex flex-col gap-3">
            <Input
              label="Nome do pipeline *"
              value={form.pipeline_name}
              onChange={e => f('pipeline_name', e.target.value.toUpperCase())}
              placeholder="ex: ETL_COBRANCA_DIARIA"
              disabled={isEdit}
              className={`font-mono ${isEdit ? 'opacity-60' : ''}`}
            />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Projeto *" value={form.project_name} onChange={e => f('project_name', e.target.value)}>
                <option value="">Selecione…</option>
                {projects.map(p => <option key={p}>{p}</option>)}
              </Select>
              <Input label="Domínio" value={form.domain}
                onChange={e => f('domain', e.target.value.toUpperCase())} placeholder="ex: COBRANCA" />
            </div>
            <Input label="Tags (separadas por vírgula)" value={form.tags}
              onChange={e => f('tags', e.target.value.toUpperCase())} placeholder="ex: COBRANCA,DIARIO,PROD" />
            <Textarea label="Descrição" value={form.descricao} onChange={e => f('descricao', e.target.value)}
              rows={3} placeholder="Descreva a finalidade deste pipeline…" />
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.active} onChange={e => f('active', e.target.checked)} className="accent-blue-500" />
              <span className="text-sm text-ink">Pipeline ativo</span>
            </label>
          </div>
        )}

        {/* ── AGENDAMENTO ── */}
        {section === 'schedule' && (
          <div className="flex flex-col gap-3">
            <Select label="Tipo" value={form.schedule_type} onChange={e => f('schedule_type', e.target.value)}>
              {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{SCHEDULE_LABELS[t]}</option>)}
            </Select>
            {form.schedule_type !== 'on_demand' && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Hora (0–23)</label>
                    <input type="number" min={0} max={23}
                      value={form.schedule_hour === 0 ? '' : form.schedule_hour}
                      onChange={e => f('schedule_hour', e.target.value === '' ? 0 : Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59}
                      value={form.schedule_minute === 0 ? '' : form.schedule_minute}
                      onChange={e => f('schedule_minute', e.target.value === '' ? 0 : Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                {(form.schedule_type === 'weekly' || form.schedule_type === 'biweekly') && (
                  <Select label="Dia da semana" value={form.schedule_dow}
                    onChange={e => f('schedule_dow', parseInt(e.target.value))}>
                    {[['0','Domingo'],['1','Segunda'],['2','Terça'],['3','Quarta'],['4','Quinta'],['5','Sexta'],['6','Sábado']].map(([v, l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </Select>
                )}
                {(form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Dia do mês (1–28)</label>
                    <input type="number" min={1} max={28} value={form.schedule_dom}
                      onChange={e => f('schedule_dom', Math.min(28, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                )}
                <Input label="Data de início DAG (opcional)" type="date" value={form.dag_start_date}
                  onChange={e => f('dag_start_date', e.target.value)} />
              </>
            )}
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2 text-xs text-dim font-mono">
              {form.schedule_type === 'on_demand'
                ? 'Sem agendamento automático — execução apenas manual ou por dependência'
                : `CRON: ${buildCron(form.schedule_type, form.schedule_hour, form.schedule_minute, form.schedule_dow, form.schedule_dom)}`}
            </div>
          </div>
        )}

        {/* ── NOTIFICAÇÕES ── */}
        {section === 'notify' && (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-dim">Configure quando enviar notificação Teams/e-mail.</p>
            {([
              ['envia_msg_inicio', '▶ Início da execução'],
              ['envia_msg_fim',    '✓ Conclusão bem-sucedida'],
              ['envia_msg_erro',   '⚠ Falha / erro'],
            ] as [keyof FormState, string][]).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2.5 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2.5">
                <input type="checkbox" checked={form[key] as boolean}
                  onChange={e => f(key, e.target.checked)} className="accent-blue-500" />
                <span className="text-sm text-ink">{label}</span>
              </label>
            ))}
          </div>
        )}

        {/* ── AVANÇADO ── */}
        {section === 'advanced' && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-3 gap-3">
              <Select label="Criticidade" value={form.criticidade} onChange={e => f('criticidade', e.target.value)}>
                {CRITICIDADES.map(c => <option key={c}>{c}</option>)}
              </Select>
              <Select label="Ambiente" value={form.ambiente} onChange={e => f('ambiente', e.target.value)}>
                {AMBIENTES.map(a => <option key={a}>{a}</option>)}
              </Select>
              <Input label="SLA (minutos)" type="number" value={form.sla_minutos}
                onChange={e => f('sla_minutos', e.target.value)} placeholder="ex: 60" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Runs simultâneas</label>
                <input type="number" min={1} max={10} value={form.max_active_runs}
                  onChange={e => f('max_active_runs', parseInt(e.target.value) || 1)}
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Retries</label>
                <input type="number" min={0} max={10} value={form.retries_count}
                  onChange={e => f('retries_count', parseInt(e.target.value) || 0)}
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Delay retry (s)</label>
                <input type="number" min={0} value={form.retry_delay_seconds}
                  onChange={e => f('retry_delay_seconds', parseInt(e.target.value) || 300)}
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
              </div>
            </div>
            <Input label="Fila de execução (pool)" value={form.pool_name}
              onChange={e => f('pool_name', e.target.value)} placeholder="padrão do Airflow" />
            <div className="flex flex-col gap-1">
              <label className="text-xs text-dim font-medium">Depende de (pipelines, separados por vírgula)</label>
              <input
                list="dep-list"
                value={form.depends_on}
                onChange={e => f('depends_on', e.target.value)}
                placeholder="ex: ETL_BASE_CLIENTES, ETL_CARTEIRA"
                className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <datalist id="dep-list">
                {otherPipelines.map(n => <option key={n} value={n} />)}
              </datalist>
            </div>
            <Textarea label="Runbook (Markdown)" value={form.runbook_md}
              onChange={e => f('runbook_md', e.target.value)} rows={4}
              placeholder="Documentação operacional: como monitorar, tratar falhas, contato responsável..." />
          </div>
        )}

        {errs.length > 0 && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg p-3">
            {errs.map((e, i) => <p key={i} className="text-xs text-red-400">{e}</p>)}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1 border-t border-edge">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={saveMut.isPending} onClick={() => { if (validate()) saveMut.mutate() }}>
            <Save size={13} /> {isEdit ? 'Salvar alterações' : 'Criar pipeline'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── ViewModal ──────────────────────────────────────────────────────────────

function ViewModal({ pipeline: p, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const pill = (v: string, active = false) => (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${active ? 'bg-green-900/20 text-green-400 border-green-800/40' : 'bg-panel text-dim border-edge'}`}>{v}</span>
  )
  // Célula individual do grid
  const cell = (label: string, val: React.ReactNode, spanFull = false) => (
    <div className={`flex flex-col gap-0.5 ${spanFull ? 'col-span-2' : ''}`}>
      <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{label}</span>
      <div className="text-sm font-medium text-ink min-h-[1.25rem]">
        {val || <span className="text-dim/50 italic text-xs">—</span>}
      </div>
    </div>
  )
  const notifs = [p.envia_msg_inicio && 'Início', p.envia_msg_fim && 'Conclusão', p.envia_msg_erro && 'Erro'].filter(Boolean)
  const cron = p.schedule_type && p.schedule_type !== 'on_demand'
    ? buildCron(p.schedule_type, p.schedule_hour ?? 6, p.schedule_minute ?? 0, p.schedule_dow ?? 1, p.schedule_dom ?? 1)
    : null

  return (
    <Modal open title={p.pipeline_name} onClose={onClose} size="lg">
      {/* Scroll interno — modal não cresce além da viewport */}
      <div className="overflow-y-auto max-h-[70vh] pr-1">
        {/* Seção: Identificação */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Identificação</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Projeto',     p.project_name)}
            {cell('Domínio',     p.domain)}
            {cell('Ambiente',    p.ambiente)}
            {cell('Criticidade', <span className={`font-semibold ${critColor(p.criticidade)}`}>{p.criticidade}</span>)}
            {cell('Status',
              <div className="flex flex-wrap gap-1.5">
                {pill(p.active ? 'Ativo' : 'Inativo', !!p.active)}
                {pill(p.dag_criada ? 'DAG ✓' : 'DAG não gerada', !!p.dag_criada)}
              </div>
            )}
            {cell('Tags',
              p.tags
                ? <div className="flex flex-wrap gap-1">{p.tags.split(',').map(t => pill(t.trim(), true))}</div>
                : null
            )}
          </div>
        </div>

        {/* Seção: Agendamento */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Agendamento</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Tipo',          p.schedule_type ? SCHEDULE_LABELS[p.schedule_type] ?? p.schedule_type : null)}
            {cell('Horário',       p.scheduled_time)}
            {cell('Expressão CRON', cron)}
            {cell('Data início',   p.dag_start_date || 'Imediato')}
            {cell('SLA',           p.sla_minutos ? `${p.sla_minutos} min` : null)}
            {cell('Depende de',
              p.depends_on
                ? <div className="flex flex-wrap gap-1">{p.depends_on.split(',').map(d => pill(d.trim()))}</div>
                : null
            )}
          </div>
        </div>

        {/* Seção: Execução */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Execução</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Runs simultâneas', p.max_active_runs ?? 1)}
            {cell('Retries',          `${p.retries_count ?? 1}x · delay ${p.retry_delay_seconds ?? 300}s`)}
            {cell('Fila (pool)',       p.pool_name || 'padrão')}
            {cell('Notificações',      notifs.length ? notifs.join(' · ') : null)}
            {cell('Última execução',   p.last_execution)}
          </div>
        </div>

        {/* Seção: Metadados */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Metadados</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Criado em',  p.created_at)}
            {cell('Atualizado', p.updated_at)}
          </div>
        </div>

        {/* Descrição — full width */}
        {p.descricao && (
          <div className="mb-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Descrição</p>
            <p className="text-xs text-ink whitespace-pre-wrap leading-relaxed">{p.descricao}</p>
          </div>
        )}

        {/* Runbook — full width */}
        {p.runbook_md && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Runbook</p>
            <pre className="text-xs text-dim whitespace-pre-wrap font-mono bg-canvas border border-edge rounded-lg p-3 leading-relaxed">{p.runbook_md}</pre>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── AuditModal ─────────────────────────────────────────────────────────────

function AuditGroup({ day, rows }: { day: string; rows: AuditRow[] }) {
  const [open, setOpen] = useState(false)
  const fmt  = day.split('-').reverse().join('/')
  const user = rows[0]?.changed_by ?? '—'
  return (
    <div className="border border-edge rounded-lg mb-2 overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-canvas hover:bg-edge/20 transition-colors text-left">
        <span className="text-sm font-semibold">{fmt}</span>
        <span className="text-xs text-dim">{user} · {rows.length} campo(s)</span>
        {open ? <ChevronDown size={14} className="text-dim" /> : <ChevronRight size={14} className="text-dim" />}
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-t border-edge bg-canvas/50 text-dim">
                {['Hora','Usuário','Campo','Antes','Depois'].map(h => (
                  <th key={h} className="px-3 py-1.5 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const time = r.changed_at.includes('T')
                  ? r.changed_at.split('T')[1].substring(0, 8)
                  : r.changed_at.substring(11, 19)
                return (
                  <tr key={i} className="border-t border-edge/40">
                    <td className="px-3 py-1.5 text-dim">{time}</td>
                    <td className="px-3 py-1.5">{r.changed_by || '—'}</td>
                    <td className="px-3 py-1.5 font-medium">{r.field_name || '—'}</td>
                    <td className="px-3 py-1.5 text-dim truncate max-w-[150px]" title={r.old_value ?? ''}>{(r.old_value ?? '—').substring(0, 60)}</td>
                    <td className="px-3 py-1.5 truncate max-w-[150px]" title={r.new_value ?? ''}>{(r.new_value ?? '—').substring(0, 60)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AuditModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ data: AuditRow[] }>({
    queryKey: ['pipeline-audit', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/audit?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}&limit=50`),
  })
  const rows = data?.data ?? []
  const byDate = useMemo(() => {
    const m: Record<string, AuditRow[]> = {}
    rows.forEach(r => {
      const day = (r.changed_at || '').substring(0, 10) || 'Desconhecido'
      if (!m[day]) m[day] = []
      m[day].push(r)
    })
    return Object.entries(m).sort(([a], [b]) => b.localeCompare(a))
  }, [rows])

  return (
    <Modal open title={`Histórico — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      <div className="text-xs text-dim bg-canvas border border-edge rounded-lg px-3 py-2 mb-3">
        📌 São exibidas as <strong className="text-ink">últimas 50 alterações</strong>. O registro de criação é sempre preservado.
      </div>
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando…</div>}
      {!isLoading && rows.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <History size={32} className="opacity-30" />
          <p className="text-sm">Sem histórico registrado</p>
          <p className="text-xs">Alterações futuras aparecerão aqui.</p>
        </div>
      )}
      {byDate.map(([day, dayRows]) => <AuditGroup key={day} day={day} rows={dayRows} />)}
    </Modal>
  )
}

// ── LineageModal ───────────────────────────────────────────────────────────

function LineageModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading, error } = useQuery<{ pipeline_name: string; jobs: LineageJob[] }>({
    queryKey: ['pipeline-lineage', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}`),
  })
  const jobs = data?.jobs ?? []

  const origens = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.origens || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  const destinos = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.destinos || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  return (
    <Modal open title={`Lineage — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando lineage…</div>}
      {!!error && <p className="text-red-400 text-sm py-4">Erro ao carregar lineage</p>}
      {!isLoading && !error && jobs.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <GitBranch size={32} className="opacity-30" />
          <p className="text-sm">Nenhum job cadastrado</p>
          <p className="text-xs">Adicione jobs ao pipeline para visualizar o lineage.</p>
        </div>
      )}
      {!isLoading && jobs.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[1fr_36px_auto_36px_1fr] gap-2 items-start py-2 min-w-[480px]">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 text-center">
                  Origens ({origens.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {origens.length ? origens.map(o => (
                    <div key={o.object_name}
                      className="border border-blue-800/40 bg-blue-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-blue-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem origens</span>}
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div className="flex flex-col items-center mt-4">
                <div className="border border-edge bg-panel rounded-xl px-4 py-3 min-w-[140px] text-center">
                  <div className="font-mono text-sm font-bold text-ink truncate">{pipeline.pipeline_name}</div>
                  <div className="text-[10px] text-dim mt-0.5">{jobs.length} job(s)</div>
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-green-400 mb-2 text-center">
                  Destinos ({destinos.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {destinos.length ? destinos.map(o => (
                    <div key={o.object_name}
                      className="border border-green-800/40 bg-green-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-green-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem destinos</span>}
                </div>
              </div>
            </div>
          </div>
          <p className="text-xs text-dim/60 text-center border-t border-edge pt-2 mt-1">
            Visualização consolidada — para detalhe por job, use Governança › Lineage.
          </p>
        </>
      )}
    </Modal>
  )
}

// ── InactivateModal ────────────────────────────────────────────────────────

function InactivateModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const qc   = useQueryClient()
  const user = useAuthStore(s => s.user)
  const mut  = useMutation({
    mutationFn: () => apiFetch('/pipelines/register', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name:       pipeline.pipeline_name,
        scheduled_time:      pipeline.scheduled_time ?? '00:00:00',
        schedule_type:       pipeline.schedule_type,
        schedule_hour:       pipeline.schedule_hour,
        schedule_minute:     pipeline.schedule_minute,
        schedule_dow:        pipeline.schedule_dow,
        schedule_dom:        pipeline.schedule_dom,
        active:              0,
        envia_msg_inicio:    pipeline.envia_msg_inicio,
        envia_msg_fim:       pipeline.envia_msg_fim,
        envia_msg_erro:      pipeline.envia_msg_erro,
        project_name:        pipeline.project_name ?? '',
        domain:              pipeline.domain ?? '',
        tags:                pipeline.tags ?? '',
        dag_criada:          pipeline.dag_criada,
        descricao:           pipeline.descricao ?? null,
        criticidade:         pipeline.criticidade ?? 'Media',
        sla_minutos:         pipeline.sla_minutos ?? null,
        ambiente:            pipeline.ambiente ?? 'PROD',
        max_active_runs:     pipeline.max_active_runs ?? 1,
        retries_count:       pipeline.retries_count ?? 1,
        retry_delay_seconds: pipeline.retry_delay_seconds ?? 300,
        pool_name:           pipeline.pool_name ?? null,
        depends_on:          pipeline.depends_on ?? null,
        runbook_md:          pipeline.runbook_md ?? null,
        dag_start_date:      pipeline.dag_start_date ?? null,
        changed_by:          user?.matricula ?? 'react-ui',
      }),
    }),
    onSuccess: () => {
      toast.success(`Pipeline "${pipeline.pipeline_name}" inativado`)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.message),
  })
  return (
    <Modal open title="Inativar pipeline" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Inativar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>?
          Pode ser reativado a qualquer momento pela edição.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={mut.isPending} className="border-amber-800/40 text-amber-400"
            onClick={() => mut.mutate()}>
            <PowerOff size={13} /> Inativar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── GenDagModal ────────────────────────────────────────────────────────────

function GenDagModal({ pipeline, onConfirm, onClose, loading }: {
  pipeline: Pipeline; onConfirm: () => void; onClose: () => void; loading: boolean
}) {
  return (
    <Modal open title={pipeline.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'} onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          {pipeline.dag_criada
            ? <>Regenerar a DAG de <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>? Isso irá atualizar a DAG no Airflow com as configurações atuais.</>
            : <>Gerar a DAG para <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> no Airflow via etl_dag_factory?</>}
        </p>
        {pipeline.dag_criada ? (
          <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
            ⚠ A DAG existente será sobrescrita com as configurações atuais do pipeline.
          </p>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button loading={loading} className="border-blue-800/40 text-blue-400" onClick={onConfirm}>
            <Settings size={13} /> {pipeline.dag_criada ? 'Regenerar' : 'Gerar DAG'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── ExecModal ──────────────────────────────────────────────────────────────

function ExecModal({ pipeline, onConfirm, onClose, loading }: {
  pipeline: Pipeline; onConfirm: () => void; onClose: () => void; loading: boolean
}) {
  return (
    <Modal open title="Executar pipeline agora" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Disparar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> agora, fora do agendamento?
        </p>
        <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
          ⚠ Inicia uma execução imediata no Airflow. Certifique-se que não há execução ativa.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button loading={loading} className="border-green-800/40 text-green-400" onClick={onConfirm}>
            <Play size={13} /> Executar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Pipeline row ───────────────────────────────────────────────────────────

function PipelineRow({ pipeline: p, isViewer, onView, onEdit, onLineage, onAudit, onInactivate, onGenDag, onExec }: {
  pipeline: Pipeline; isViewer: boolean
  onView: () => void; onEdit: () => void; onLineage: () => void
  onAudit: () => void; onInactivate: () => void; onGenDag: () => void; onExec: () => void
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-edge/30 hover:bg-edge/10 transition-colors group">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${p.active ? 'bg-green-500' : 'bg-slate-600'}`}
        title={p.active ? 'Ativo' : 'Inativo'} />
      <span className="font-mono text-xs text-ink font-medium flex-1 truncate min-w-0" title={p.pipeline_name}>
        {p.pipeline_name}
      </span>
      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 hidden sm:inline ${critColor(p.criticidade)}`}
        title={`Criticidade: ${p.criticidade}`}>
        {p.criticidade}
      </span>
      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 ${p.dag_criada ? 'text-green-400 border-green-800/40 bg-green-900/10' : 'text-dim border-edge bg-canvas'}`}>
        {p.dag_criada ? 'DAG ✓' : 'DAG —'}
      </span>
      {p.scheduled_time && (
        <span className="text-[10px] text-dim flex-shrink-0 hidden md:block">{p.scheduled_time}</span>
      )}
      {(p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro) && (
        <span className="text-[10px] text-dim flex-shrink-0"
          title={['Início','Conclusão','Erro'].filter((_,i) => [p.envia_msg_inicio,p.envia_msg_fim,p.envia_msg_erro][i]).join(', ')}>
          ✉
        </span>
      )}
      {/* Coluna de ações com largura fixa — botões condicionais ficam invisíveis, não removidos */}
      <div className="flex items-center gap-0.5 flex-shrink-0 w-[154px] justify-end opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        {/* View — sempre visível */}
        <Button variant="ghost" size="sm" title="Visualizar" aria-label={`Visualizar ${p.pipeline_name}`} onClick={onView}><Eye size={12} /></Button>
        {/* Edit — apenas não-viewer */}
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Editar" aria-label={`Editar ${p.pipeline_name}`} onClick={onEdit}><Edit size={12} /></Button>
        </span>
        {/* Lineage — sempre visível */}
        <Button variant="ghost" size="sm" title="Lineage" aria-label={`Ver lineage de ${p.pipeline_name}`} onClick={onLineage}><GitBranch size={12} /></Button>
        {/* Audit — sempre visível */}
        <Button variant="ghost" size="sm" title="Histórico" aria-label={`Ver histórico de ${p.pipeline_name}`} onClick={onAudit}><History size={12} /></Button>
        {/* Inativar — apenas não-viewer && ativo */}
        <span className={isViewer || !p.active ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Inativar" aria-label={`Inativar ${p.pipeline_name}`} onClick={onInactivate}
            className="text-amber-500/60 hover:text-amber-400"><PowerOff size={12} /></Button>
        </span>
        {/* Gerar/Regenerar DAG — apenas não-viewer */}
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm"
            title={p.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'}
            aria-label={p.dag_criada ? `Regenerar DAG de ${p.pipeline_name}` : `Gerar DAG para ${p.pipeline_name}`}
            onClick={onGenDag}
            className={p.dag_criada ? 'text-blue-400/70 hover:text-blue-300' : 'text-dim hover:text-ink'}>
            <Settings size={12} />
          </Button>
        </span>
        {/* Executar — apenas não-viewer && dag_criada */}
        <span className={isViewer || !p.dag_criada ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Executar agora" aria-label={`Executar ${p.pipeline_name} agora`} onClick={onExec}
            className="text-green-500/60 hover:text-green-400"><Play size={12} /></Button>
        </span>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function Pipelines() {
  const qc      = useQueryClient()
  const user    = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  const [nameFilter,    setNameFilter]    = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [activeFilter,  setActiveFilter]  = useState('')
  const [page, setPage] = useState(0)
  const LIMIT = 50

  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const [viewPipeline,        setViewPipeline]        = useState<Pipeline | undefined>()
  const [editPipeline,        setEditPipeline]        = useState<Pipeline | undefined>()
  const [showNew,             setShowNew]             = useState(false)
  const [auditPipeline,       setAuditPipeline]       = useState<Pipeline | undefined>()
  const [lineagePipeline,     setLineagePipeline]     = useState<Pipeline | undefined>()
  const [inactivatePipeline,  setInactivatePipeline]  = useState<Pipeline | undefined>()
  const [execPipeline,        setExecPipeline]        = useState<Pipeline | undefined>()
  const [genDagPipeline,      setGenDagPipeline]      = useState<Pipeline | undefined>()
  const revalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current) }
  }, [])

  const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (nameFilter)         qs.set('filter_name',    nameFilter)
  if (projectFilter)      qs.set('filter_project', projectFilter)
  if (activeFilter !== '') qs.set('filter_active', activeFilter)

  const { data, isLoading } = useQuery<{ total: number; pages: number; data: Pipeline[] }>({
    queryKey: ['pipelines', nameFilter, projectFilter, activeFilter, page],
    queryFn: () => apiFetch(`/pipelines?${qs}`),
  })

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  const tree = useMemo(() => {
    const t: Record<string, Record<string, Pipeline[]>> = {}
    ;(data?.data ?? []).forEach(p => {
      const proj = p.project_name || '(sem projeto)'
      const dom  = p.domain       || '(sem domínio)'
      if (!t[proj]) t[proj] = {}
      if (!t[proj][dom]) t[proj][dom] = []
      t[proj][dom].push(p)
    })
    return t
  }, [data])

  const projNames = useMemo(() => Object.keys(tree).sort(), [tree])

  // Gerar DAG via factory
  const genDagMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const runId = `orquestra_ui_${Date.now()}`
      return apiFetch(`/airflow/dags/${DAG_FACTORY_ID}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: runId, conf: { pipeline_name: p.pipeline_name } }),
      })
    },
    onSuccess: (_d, p) => {
      toast.success(`Factory disparada para "${p.pipeline_name}" — aguarde para ver resultado.`)
      setGenDagPipeline(undefined)
      // Revalida após 10s para refletir dag_criada=1
      if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current)
      revalidateTimerRef.current = setTimeout(() => qc.invalidateQueries({ queryKey: ['pipelines'] }), 10_000)
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Erro inesperado'
      toast.error(`Erro ao gerar DAG: ${msg}`)
    },
  })

  // Executar agora
  const execMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      return apiFetch<{ dag_run_id?: string }>(`/airflow/dags/${encodeURIComponent(dagId)}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: `manual_orq_${Date.now()}`, conf: {} }),
      })
    },
    onSuccess: (res, p) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      setExecPipeline(undefined)
      toast.success(`Pipeline disparado! (${res?.dag_run_id ?? 'ok'})`)
      window.open(`${AIRFLOW_UI}/dags/${dagId}/grid`, '_blank')
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : ''
      if (msg.startsWith('404')) toast.error('DAG não encontrada. Gere o DAG primeiro.')
      else if (msg.startsWith('409')) toast.error('Já existe uma execução ativa para este pipeline.')
      else toast.error(msg || 'Erro ao executar')
    },
  })

  const fetchPipelineNames = useCallback(
    (q: string) =>
      apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
        .then(r => r.data.map(p => p.pipeline_name)),
    [],
  )

  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  return (
    <div className="flex flex-col gap-4">

      {/* Filter bar */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <Autocomplete
            label="Nome"
            value={nameFilter}
            onChange={v => { setNameFilter(v); setPage(0) }}
            fetchSuggestions={fetchPipelineNames}
            placeholder="filtrar por nome…"
            className="w-64"
          />
          <Select label="Projeto" value={projectFilter}
            onChange={e => { setProjectFilter(e.target.value); setPage(0) }} className="w-40">
            <option value="">Todos</option>
            {projects.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Select label="Status" value={activeFilter}
            onChange={e => { setActiveFilter(e.target.value); setPage(0) }} className="w-32">
            <option value="">Todos</option>
            <option value="1">Ativos</option>
            <option value="0">Inativos</option>
          </Select>
          <div className="flex gap-2 ml-auto items-end">
            <Button variant="secondary" size="sm" onClick={() => { setNameFilter(''); setProjectFilter(''); setActiveFilter(''); setPage(0) }}>
              × Limpar
            </Button>
            {!isViewer && (
              <Button size="sm" onClick={() => setShowNew(true)}>
                <Plus size={13} /> Novo pipeline
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Count + pagination */}
      {!isLoading && (
        <div className="flex items-center justify-between text-xs text-dim px-1">
          <span>{total} pipeline{total !== 1 ? 's' : ''}</span>
          {pages > 1 && (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
              <span>Página {page + 1} de {pages}</span>
              <Button variant="ghost" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
            </div>
          )}
        </div>
      )}

      {isLoading && <PageSpinner />}

      {!isLoading && total === 0 && (
        <div className="bg-panel border border-edge rounded-xl py-16 flex flex-col items-center gap-2 text-dim">
          <span className="text-4xl">◎</span>
          <p className="text-sm font-medium">Nenhum pipeline encontrado</p>
          <p className="text-xs">Ajuste os filtros ou crie um novo pipeline.</p>
        </div>
      )}

      {/* Tree: projeto → domínio → pipelines */}
      {!isLoading && projNames.map(proj => {
        const isCollapsed = collapsed.has(proj)
        const domNames    = Object.keys(tree[proj]).sort()
        const totalProj   = domNames.reduce((s, d) => s + tree[proj][d].length, 0)
        const activeProj  = domNames.reduce((s, d) => s + tree[proj][d].filter(p => p.active).length, 0)
        return (
          <div key={proj} className="bg-panel border border-edge rounded-xl overflow-hidden">
            <button
              onClick={() => setCollapsed(s => { const n = new Set(s); n.has(proj) ? n.delete(proj) : n.add(proj); return n })}
              className="w-full flex items-center gap-2 px-4 py-3 bg-canvas hover:bg-edge/20 transition-colors text-left"
            >
              {isCollapsed ? <ChevronRight size={15} className="text-dim flex-shrink-0" /> : <ChevronDown size={15} className="text-dim flex-shrink-0" />}
              <span className="font-semibold text-ink text-sm">{proj}</span>
              <span className="text-xs text-dim">
                {totalProj} pipeline{totalProj !== 1 ? 's' : ''} · {activeProj} ativo{activeProj !== 1 ? 's' : ''}
              </span>
            </button>

            {!isCollapsed && domNames.map(dom => (
              <div key={dom}>
                <div className="px-5 py-1 bg-panel/60 border-t border-edge/30">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{dom}</span>
                  <span className="text-[10px] text-dim/40 ml-2">({tree[proj][dom].length})</span>
                </div>
                {tree[proj][dom].map(p => (
                  <PipelineRow
                    key={p.pipeline_name}
                    pipeline={p}
                    isViewer={isViewer}
                    onView={()        => setViewPipeline(p)}
                    onEdit={()        => setEditPipeline(p)}
                    onLineage={()     => setLineagePipeline(p)}
                    onAudit={()       => setAuditPipeline(p)}
                    onInactivate={()  => setInactivatePipeline(p)}
                    onGenDag={()      => setGenDagPipeline(p)}
                    onExec={()        => setExecPipeline(p)}
                  />
                ))}
              </div>
            ))}
          </div>
        )
      })}

      {/* Modals */}
      {showNew            && <PipelineFormModal onClose={() => setShowNew(false)} />}
      {editPipeline       && <PipelineFormModal pipeline={editPipeline} onClose={() => setEditPipeline(undefined)} />}
      {viewPipeline       && <ViewModal pipeline={viewPipeline} onClose={() => setViewPipeline(undefined)} />}
      {auditPipeline      && <AuditModal pipeline={auditPipeline} onClose={() => setAuditPipeline(undefined)} />}
      {lineagePipeline    && <LineageModal pipeline={lineagePipeline} onClose={() => setLineagePipeline(undefined)} />}
      {inactivatePipeline && <InactivateModal pipeline={inactivatePipeline} onClose={() => setInactivatePipeline(undefined)} />}
      {execPipeline       && (
        <ExecModal
          pipeline={execPipeline}
          loading={execMut.isPending}
          onConfirm={() => execMut.mutate(execPipeline)}
          onClose={() => { if (!execMut.isPending) setExecPipeline(undefined) }}
        />
      )}
      {genDagPipeline     && (
        <GenDagModal
          pipeline={genDagPipeline}
          loading={genDagMut.isPending}
          onConfirm={() => genDagMut.mutate(genDagPipeline)}
          onClose={() => { if (!genDagMut.isPending) setGenDagPipeline(undefined) }}
        />
      )}
    </div>
  )
}
