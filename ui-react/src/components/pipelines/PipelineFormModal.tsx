import { useState, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Save, Link2, X, AlertTriangle } from 'lucide-react'
import type { Pipeline } from '../../types/pipeline'
import { DependenciasModal } from './DependenciasModal'
import {
  SCHEDULE_TYPES, SCHEDULE_LABELS, CRITICIDADES, AMBIENTES, MAX_MONTH_DAYS,
  DOW_LABELS,
  type ScheduleConfig, type MonthDayEntry,
  hourlyTimes, parseCustomTimes, computeNextRuns, runsPerDay,
  critColor, buildCron, parseMonthDaysTimes, serializeMonthDaysTimes,
} from './pipelineUtils'

// ── Sub-types ─────────────────────────────────────────────────────────────────

// O wizard cuida apenas dos METADADOS do pipeline. As etapas (jobs), decisões e
// lineage são gerenciados na tela de Etapas (Lista + Fluxo).

interface FormState {
  pipeline_name: string
  project_name: string
  domain: string
  tags_list: string[]
  descricao: string
  schedule_type: string
  schedule_hour: number
  schedule_minute: number
  schedule_dow: number
  schedule_dom: number
  schedule_interval_hours: number
  schedule_start_hour: number
  schedule_end_hour: number
  schedule_custom_times: string
  schedule_weekdays: number[]
  schedule_month_days: MonthDayEntry[]
  somente_dias_uteis: boolean
  calendario_nome: string
  trigger_por_dependencia: boolean
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
  hora_virada: string
  nao_iniciar_antes: string
  hora_limite_dependencia: string
  runbook_md: string
  motivo_inativacao: string
}

// Resultado da sincronização da DAG no Airflow ao salvar (vem de /pipelines/register).
type DagSync = { attempted: boolean; exists: boolean | null; is_paused: boolean | null; error: string | null }

// Mensagem amigável sobre o efeito no Airflow (pausar/despausar a DAG).
function dagSyncMsg(ds?: DagSync | null): { ok: boolean; msg: string } {
  if (!ds || ds.attempted === false) return { ok: true, msg: '' }
  if (ds.error) return { ok: false, msg: `DAG não sincronizada no Airflow: ${ds.error}` }
  if (ds.exists === false) return { ok: true, msg: 'sem DAG no Airflow' }
  if (ds.is_paused === true)  return { ok: true, msg: 'DAG pausada no Airflow' }
  if (ds.is_paused === false) return { ok: true, msg: 'DAG ativada no Airflow' }
  return { ok: true, msg: '' }
}

const defaultForm = (): FormState => ({
  pipeline_name: '', project_name: '', domain: '', tags_list: [], descricao: '',
  schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0,
  schedule_dow: 1, schedule_dom: 1, schedule_interval_hours: 2,
  schedule_start_hour: 8, schedule_end_hour: 18,
  schedule_custom_times: '', schedule_weekdays: [1, 2, 3, 4, 5], schedule_month_days: [],
  somente_dias_uteis: false, calendario_nome: '', trigger_por_dependencia: false,
  active: true, dag_start_date: '',
  envia_msg_inicio: true, envia_msg_fim: true, envia_msg_erro: true,
  criticidade: 'Media', sla_minutos: '', ambiente: 'PROD',
  max_active_runs: 1, retries_count: 1, retry_delay_seconds: 300,
  pool_name: '', depends_on: '', hora_virada: '', nao_iniciar_antes: '',
  hora_limite_dependencia: '', runbook_md: '', motivo_inativacao: '',
})

function pipelineToForm(p: Pipeline): FormState {
  const horarios = (p.horarios_especificos ?? '').trim()
  const diasRaw  = (p.dias_semana ?? '').trim()
  const weekdays = diasRaw ? diasRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [1, 2, 3, 4, 5]
  const monthDays = parseMonthDaysTimes(p.dias_horarios_mes)
  const schedType = monthDays.length > 0 ? 'monthly_days_times' : (horarios ? 'custom' : (p.schedule_type ?? 'daily'))
  return {
    ...defaultForm(),
    pipeline_name:           p.pipeline_name,
    project_name:            p.project_name ?? '',
    domain:                  p.domain ?? '',
    tags_list:               p.tags ? p.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    descricao:               p.descricao ?? '',
    schedule_type:           schedType,
    schedule_hour:           p.schedule_hour ?? 6,
    schedule_minute:         p.schedule_minute ?? 0,
    schedule_dow:            p.schedule_dow ?? 1,
    schedule_dom:            p.schedule_dom ?? 1,
    schedule_custom_times:   horarios,
    schedule_weekdays:       weekdays,
    schedule_month_days:     monthDays,
    somente_dias_uteis:      !!p.somente_dias_uteis,
    calendario_nome:         p.calendario_nome ?? '',
    trigger_por_dependencia: !!p.trigger_por_dependencia,
    active:                  !!p.active,
    dag_start_date:          p.dag_start_date ?? '',
    envia_msg_inicio:        !!p.envia_msg_inicio,
    envia_msg_fim:           !!p.envia_msg_fim,
    envia_msg_erro:          !!p.envia_msg_erro,
    criticidade:             p.criticidade ?? 'Media',
    sla_minutos:             p.sla_minutos != null ? String(p.sla_minutos) : '',
    ambiente:                p.ambiente ?? 'PROD',
    max_active_runs:         p.max_active_runs ?? 1,
    retries_count:           p.retries_count ?? 1,
    retry_delay_seconds:     p.retry_delay_seconds ?? 300,
    pool_name:               p.pool_name ?? '',
    depends_on:              p.depends_on ?? '',
    // Sem cast: o tipo passou a declarar os campos e o GET a devolvê-los. Era o
    // `as unknown as Record<string,string>` que escondia do tsc que a chave não
    // existia no payload — o form carregava vazio e todo save zerava o banco.
    hora_virada:             p.hora_virada ?? '',
    nao_iniciar_antes:       p.nao_iniciar_antes ?? '',
    hora_limite_dependencia: p.hora_limite_dependencia ?? '',
    runbook_md:              p.runbook_md ?? '',
    motivo_inativacao:       p.motivo_inativacao ?? '',
  }
}

// ── TagsInput ─────────────────────────────────────────────────────────────────

function TagsInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState('')

  function addTag(raw: string) {
    const parts = raw.split(/[,;]/).map(s => s.trim().toUpperCase()).filter(Boolean)
    if (!parts.length) return
    const next = [...value]
    parts.forEach(t => { if (!next.includes(t)) next.push(t) })
    onChange(next)
    setInput('')
  }

  function removeTag(t: string) { onChange(value.filter(x => x !== t)) }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-dim font-medium">Tags * <span className="text-dim/50 font-normal">(Enter ou vírgula para adicionar)</span></label>
      <div className="min-h-[42px] flex flex-wrap gap-1.5 items-center bg-panel border border-edge rounded-md px-2 py-1.5 focus-within:ring-1 focus-within:ring-blue-500">
        {value.map(t => (
          <span key={t} className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-600/25 dark:text-blue-200 dark:border-blue-600/50 rounded-full px-2 py-0.5 text-xs font-semibold">
            {t}
            <button type="button" onClick={() => removeTag(t)} className="hover:text-red-500 transition-colors leading-none">×</button>
          </span>
        ))}
        <input
          type="text"
          value={input}
          placeholder={value.length === 0 ? 'ex: COBRANCA, DIARIO…' : ''}
          className="flex-1 min-w-[120px] bg-transparent outline-none text-sm text-ink placeholder:text-dim/50"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(input) }
            if (e.key === 'Backspace' && input === '' && value.length > 0) removeTag(value[value.length - 1])
          }}
          onBlur={() => { if (input.trim()) addTag(input) }}
        />
      </div>
    </div>
  )
}

// ── Wizard stepper ────────────────────────────────────────────────────────────

const STEPS = ['Identificação', 'Agendamento', 'Notificações', 'Revisão'] as const
type Step = 0 | 1 | 2 | 3

function Stepper({ step, setStep, errors }: { step: Step; setStep: (s: Step) => void; errors: Record<number, string[]> }) {
  return (
    <div className="flex items-center gap-0 mb-1">
      {STEPS.map((label, i) => {
        const hasErr = (errors[i]?.length ?? 0) > 0
        const active = i === step
        const done   = i < step && !hasErr
        return (
          <button
            key={i}
            type="button"
            onClick={() => setStep(i as Step)}
            className="flex items-center gap-0 group"
          >
            <div className="flex flex-col items-center">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold border transition-colors
                ${hasErr ? 'bg-red-500 border-red-500 text-white' :
                  active ? 'bg-blue-600 border-blue-600 text-white' :
                  done   ? 'bg-green-600 border-green-600 text-white' :
                           'bg-panel border-edge text-dim'}`}>
                {hasErr ? '!' : done ? '✓' : i + 1}
              </div>
              <span className={`text-[9px] mt-0.5 whitespace-nowrap transition-colors
                ${hasErr ? 'text-red-500 font-semibold' : active ? 'text-blue-600 dark:text-blue-300 font-semibold' : done ? 'text-green-600 dark:text-green-400' : 'text-dim'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-6 h-0.5 mt-[-10px] mx-0.5 transition-colors
                ${i < step ? 'bg-green-500' : 'bg-edge'}`} />
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── PipelineFormModal (wizard) ────────────────────────────────────────────────

export function PipelineFormModal({ pipeline, onClose }: { pipeline?: Pipeline; onClose: () => void }) {
  const qc     = useQueryClient()
  const user   = useAuthStore(s => s.user)
  const isEdit = !!pipeline

  const [form,  setForm]  = useState<FormState>(pipeline ? pipelineToForm(pipeline) : defaultForm())
  const [step,  setStep]  = useState<Step>(0)
  const [stepErrors, setStepErrors] = useState<Record<number, string[]>>({})
  const [confirmClose, setConfirmClose] = useState(false)
  const [askGenerate, setAskGenerate]   = useState<string | null>(null)
  const [depModalAberto, setDepModalAberto] = useState(false)

  // O CSV continua sendo o que vai para a API (o back mantém tabela e CSV em
  // espelho até a F6); na tela ele vira lista, que é como a pessoa pensa.
  const depsSelecionadas = useMemo(
    () => form.depends_on.split(',').map(s => s.trim()).filter(Boolean),
    [form.depends_on])

  const aplicarDeps = (nomes: string[]) => {
    setForm(prev => ({
      ...prev,
      depends_on: nomes.join(','),
      // Sem dependência não há janela nem limite a respeitar: manter os valores
      // deixaria configuração órfã no banco, sem nada na tela que a explique.
      nao_iniciar_antes: nomes.length ? prev.nao_iniciar_antes : '',
      hora_limite_dependencia: nomes.length ? prev.hora_limite_dependencia : '',
    }))
    // Dependência decide o `schedule` da DAG (com ela, schedule=None). Sem esta
    // marca o modal não oferecia republicar: o cadastro mudava e a DAG no
    // Airflow continuava com o cron antigo, rodando por horário E sendo
    // disparada pelo predecessor. `markDagDirty` só era chamado dentro de `f()`,
    // e aqui o estado é alterado direto.
    markDagDirty()
  }

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  // Domínios já existentes — para autocompletar e evitar variações parecidas
  const { data: domData } = useQuery<{ domains: string[] }>({
    queryKey: ['pipeline-domains'],
    queryFn: () => apiFetch('/pipelines/domains'),
    staleTime: 300_000,
  })
  const domains = domData?.domains ?? []

  // limit alto de propósito: a escolha de dependências deixou de ter campo de
  // texto livre, então um pipeline fora desta fatia ficaria IMPOSSÍVEL de
  // escolher — o datalist antigo era só sugestão, dava para digitar o nome.
  // O modal avisa se o teto for atingido.
  const { data: allPipes } = useQuery<{ data: Pipeline[]; total?: number }>({
    queryKey: ['pipelines', 'todos-para-dependencia'],
    queryFn: () => apiFetch('/pipelines?limit=2000'),
    staleTime: 60_000,
  })
  // A lista completa vai inteira para o DependenciasModal — ele precisa do
  // projeto e do active de cada um, não só do nome (o datalist antigo só tinha
  // nomes, e era isso que escondia dependência de pipeline inativo).

  const { data: calData } = useQuery<{ calendarios: { calendario_nome: string; datas: number }[] }>({
    queryKey: ['agenda-calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
    staleTime: 300_000,
  })
  const calendarios = calData?.calendarios ?? []

  // "Dirty" cirúrgico: marca só quando muda algo que AFETA a DAG (não cadastro
  // puro). Usado para perguntar "Regenerar a DAG?" só quando precisa.
  const dagDirtyRef = useRef(false)
  const CADASTRO_FIELDS = new Set<string>([
    'tags_list', 'criticidade', 'descricao', 'runbook_md', 'sla_minutos',
    'active', 'motivo_inativacao',
  ])
  function markDagDirty() {
    dagDirtyRef.current = true
  }

  function f<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    if (!CADASTRO_FIELDS.has(k as string)) markDagDirty()
  }

  const schedCfg: ScheduleConfig = {
    type: form.schedule_type,
    hour: form.schedule_hour, minute: form.schedule_minute,
    dow: form.schedule_dow, dom: form.schedule_dom,
    intervalH: form.schedule_interval_hours,
    startH: form.schedule_start_hour, endH: form.schedule_end_hour,
    customTimes: form.schedule_custom_times,
    weekdays: form.schedule_weekdays,
    businessDaysOnly: form.somente_dias_uteis,
    monthDays: form.schedule_month_days.map(e => ({ dia: e.dia, horarios: parseCustomTimes(e.horariosRaw) })),
  }
  const showBizToggle = !['custom', 'on_demand', 'monthly_days_times'].includes(form.schedule_type)
  const nextRuns = useMemo(
    () => computeNextRuns(schedCfg, form.schedule_type === 'biweekly' ? 2 : 5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(schedCfg)],
  )
  const perDay   = runsPerDay(schedCfg)

  function validateStep(s: number): string[] {
    if (s === 0) {
      const e: string[] = []
      if (!form.pipeline_name.trim()) e.push('Nome do pipeline é obrigatório')
      if (!form.project_name)         e.push('Projeto é obrigatório')
      if (!form.domain.trim())        e.push('Domínio é obrigatório')
      if (form.tags_list.length === 0) e.push('Ao menos uma tag é obrigatória')
      if (!form.descricao.trim())     e.push('Descrição é obrigatória')
      if (!form.active && form.motivo_inativacao.trim().length < 5)
        e.push('Motivo da inativação é obrigatório (mín. 5 caracteres)')
      return e
    }
    if (s === 1) {
      const e: string[] = []
      const t = form.schedule_type
      if (t === 'on_demand') return []
      if (t === 'hourly_n') {
        if (form.schedule_interval_hours < 1 || form.schedule_interval_hours > 23) e.push('Intervalo deve ser entre 1 e 23 horas')
        if (form.schedule_start_hour < 0 || form.schedule_start_hour > 23) e.push('Hora de início inválida (0–23)')
        if (form.schedule_end_hour < 0 || form.schedule_end_hour > 23) e.push('Hora de término inválida (0–23)')
        if (form.schedule_end_hour < form.schedule_start_hour) e.push('Hora de término deve ser ≥ hora de início')
        if (form.schedule_minute < 0 || form.schedule_minute > 59) e.push('Minuto inválido (0–59)')
      } else if (t === 'custom') {
        if (parseCustomTimes(form.schedule_custom_times).length === 0) e.push('Informe ao menos um horário válido (HH:MM)')
        if (form.schedule_weekdays.length === 0) e.push('Selecione ao menos um dia da semana')
      } else if (t === 'monthly_days_times') {
        if (form.schedule_month_days.length === 0) e.push('Adicione ao menos um dia do mês')
        const seenDias = new Set<number>()
        form.schedule_month_days.forEach(entry => {
          if (seenDias.has(entry.dia)) e.push(`Dia ${entry.dia} duplicado`)
          seenDias.add(entry.dia)
          const times = parseCustomTimes(entry.horariosRaw)
          if (times.length === 0) e.push(`Dia ${entry.dia}: informe ao menos um horário válido (HH:MM)`)
          if (times.length > 5) e.push(`Dia ${entry.dia}: no máximo 5 horários`)
        })
      } else {
        if (form.schedule_hour < 0 || form.schedule_hour > 23) e.push('Hora inválida (0–23)')
        if (form.schedule_minute < 0 || form.schedule_minute > 59) e.push('Minuto inválido (0–59)')
        if (t === 'weekly' && (form.schedule_dow < 0 || form.schedule_dow > 6)) e.push('Dia da semana inválido')
        if (t === 'monthly' && (form.schedule_dom < 1 || form.schedule_dom > 28)) e.push('Dia do mês inválido (1–28)')
        if (t === 'biweekly' && (form.schedule_dom < 1 || form.schedule_dom > 13)) e.push('Dia da 1ª quinzena inválido (1–13)')
      }
      return e
    }
    return []
  }

  function goNext() {
    const e = validateStep(step)
    if (e.length) {
      setStepErrors(prev => ({ ...prev, [step]: e }))
      return
    }
    setStepErrors(prev => ({ ...prev, [step]: [] }))
    if (step < 3) setStep((step + 1) as Step)
  }

  function goPrev() { if (step > 0) setStep((step - 1) as Step) }

  function buildSchedulePayload() {
    const t = form.schedule_type
    const h = String(form.schedule_hour).padStart(2, '0')
    const m = String(form.schedule_minute).padStart(2, '0')
    const base: Record<string, unknown> = {
      schedule_dow: form.schedule_dow,
      schedule_dom: form.schedule_dom,
      somente_dias_uteis: form.somente_dias_uteis ? 1 : 0,
      calendario_nome: form.calendario_nome.trim() || null,
      horarios_especificos: null,
      dias_semana: null,
      dias_horarios_mes: null,
    }
    if (t === 'hourly_n') {
      return {
        ...base,
        scheduled_time: `${String(form.schedule_start_hour).padStart(2, '0')}:${m}:00`,
        schedule_type: 'custom',
        schedule_hour: form.schedule_start_hour,
        schedule_minute: form.schedule_minute,
        horarios_especificos: hourlyTimes(schedCfg).join(','),
      }
    }
    if (t === 'custom') {
      return {
        ...base,
        scheduled_time: `${(parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00')}:00`,
        schedule_type: 'custom',
        schedule_hour: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(0, 2)),
        schedule_minute: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(3)),
        horarios_especificos: parseCustomTimes(form.schedule_custom_times).join(','),
        dias_semana: [...form.schedule_weekdays].sort((a, b) => a - b).join(','),
      }
    }
    if (t === 'monthly_days_times') {
      const serialized = serializeMonthDaysTimes(form.schedule_month_days)
      const firstTime = schedCfg.monthDays?.find(e => e.horarios.length > 0)?.horarios[0] ?? '06:00'
      return {
        ...base,
        scheduled_time: `${firstTime}:00`,
        schedule_type: 'monthly_days_times',
        schedule_hour: parseInt(firstTime.slice(0, 2)),
        schedule_minute: parseInt(firstTime.slice(3)),
        dias_horarios_mes: serialized,
      }
    }
    return {
      ...base,
      scheduled_time: `${h}:${m}:00`,
      schedule_type: t,
      schedule_hour: form.schedule_hour,
      schedule_minute: form.schedule_minute,
    }
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      const pname = form.pipeline_name.trim().toUpperCase()
      const body: Record<string, unknown> = {
        pipeline_name:       pname,
        project_name:        form.project_name,
        domain:              form.domain.trim().toUpperCase(),
        tags:                form.tags_list.join(','),
        descricao:           form.descricao.trim() || null,
        active:              form.active ? 1 : 0,
        motivo_inativacao:   form.active ? null : (form.motivo_inativacao.trim() || null),
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
        hora_virada:             form.hora_virada || null,
        nao_iniciar_antes:       form.nao_iniciar_antes || null,
        hora_limite_dependencia: form.hora_limite_dependencia || null,
        trigger_por_dependencia: form.trigger_por_dependencia ? 1 : 0,
        runbook_md:          form.runbook_md.trim() || null,
        changed_by:          user?.matricula ?? 'react-ui',
        dag_criada:          pipeline?.dag_criada ?? 0,
        ...buildSchedulePayload(),
      }
      const reg = await apiFetch<{ dag_sync?: DagSync | null }>('/pipelines/register', { method: 'POST', body: JSON.stringify(body) })
      const dagSync = reg?.dag_sync ?? null
      return { pname, dagSync }
    },
    onSuccess: (res: { pname: string; dagSync?: DagSync | null }) => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      const dag = dagSyncMsg(res.dagSync)
      const base = isEdit ? 'Pipeline atualizado!' : 'Pipeline criado com sucesso!'
      if (!dag.ok) toast.error(`${base} Atenção: ${dag.msg}`)
      else toast.success(dag.msg ? `${base} · ${dag.msg}` : base)
      // Criação: sempre oferece. Edição: só pergunta se houve mudança que afeta
      // a DAG (não pergunta em consulta nem em alteração só de cadastro).
      if (!isEdit || dagDirtyRef.current) { setAskGenerate(res.pname); return }
      onClose()
    },
    onError: (e: any) => {
      setStepErrors(prev => ({ ...prev, 3: [e?.message || 'Erro ao salvar pipeline'] }))
    },
  })

  // Gerar DAG logo após criar — mesmo disparo do botão "Gerar DAG".
  const genDagMut = useMutation({
    mutationFn: (pname: string) => apiFetch(`/pipelines/${encodeURIComponent(pname)}/gerar-dag`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('Geração da DAG solicitada — o ORQUESTRA avisa quando estiver ativa no Airflow.')
      setAskGenerate(null); onClose()
    },
    onError: (e: any) => {
      toast.error(e?.message || 'Falha ao solicitar a geração da DAG')
      setAskGenerate(null); onClose()
    },
  })

  // Fechar com confirmação se há conteúdo preenchido (evita perder o trabalho).
  const hasContent = isEdit
    ? step > 0
    : (!!form.pipeline_name?.trim() || step > 0)
  function requestClose() {
    if (saveMut.isPending || genDagMut.isPending) return
    if (hasContent) setConfirmClose(true)
    else onClose()
  }

  function validateAllAndSave() {
    const allErrors: Record<number, string[]> = {}
    let firstBad = -1
    for (const s of [0, 1]) {
      const e = validateStep(s)
      if (e.length) { allErrors[s] = e; if (firstBad < 0) firstBad = s }
    }
    if (firstBad >= 0) {
      setStepErrors(prev => ({ ...prev, ...allErrors }))
      setStep(firstBad as Step)
      return
    }
    saveMut.mutate()
  }

  const curStepErrors = stepErrors[step] ?? []

  return (
    <>
    <Modal open title={isEdit ? `Editar: ${pipeline!.pipeline_name}` : 'Novo Pipeline'} onClose={requestClose} size="xl">
      <div className="flex flex-col gap-4">

        <Stepper step={step} setStep={setStep} errors={stepErrors} />

        {curStepErrors.length > 0 && (
          <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2">
            {curStepErrors.map((e, i) => (
              <p key={i} className="text-xs text-red-700 dark:text-red-400">⚠ {e}</p>
            ))}
          </div>
        )}

        {/* ── STEP 0: IDENTIFICAÇÃO ── */}
        {step === 0 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <Input
              label="Nome do pipeline *"
              value={form.pipeline_name}
              onChange={e => f('pipeline_name', e.target.value.toUpperCase())}
              placeholder="ex: ETL_COBRANCA_DIARIA"
              disabled={isEdit}
              className={`font-mono ${isEdit ? 'opacity-60' : ''}`}
            />
            {!isEdit && <p className="text-[10px] text-dim -mt-2">Apenas letras, números e _ (será convertido para maiúsculas)</p>}

            <div className="grid grid-cols-2 gap-3">
              <Select label="Projeto *" value={form.project_name} onChange={e => f('project_name', e.target.value)}>
                <option value="">Selecione…</option>
                {projects.map(p => <option key={p}>{p}</option>)}
              </Select>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Domínio *</label>
                <input
                  type="text"
                  list="pipeline-domains"
                  value={form.domain}
                  onChange={e => f('domain', e.target.value.toUpperCase())}
                  placeholder="ex: COBRANCA"
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <datalist id="pipeline-domains">
                  {domains.map(d => <option key={d} value={d} />)}
                </datalist>
                {domains.length > 0 && (
                  <p className="text-[10px] text-dim/70">
                    {domains.length} domínio(s) já em uso — selecione um existente para padronizar.
                  </p>
                )}
              </div>
            </div>

            <TagsInput value={form.tags_list} onChange={v => f('tags_list', v)} />

            <Textarea label="Descrição *" value={form.descricao} onChange={e => f('descricao', e.target.value)}
              rows={3} placeholder="Descreva a finalidade deste pipeline, fonte de dados, consumidores…" />

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

            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.active} onChange={e => f('active', e.target.checked)} className="accent-blue-500" />
              <span className="text-sm text-ink">Pipeline ativo</span>
            </label>

            {!form.active && (
              <div className="flex flex-col gap-1 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/40 rounded-lg p-3">
                <Textarea
                  label="Motivo da inativação *"
                  rows={2}
                  value={form.motivo_inativacao}
                  onChange={e => f('motivo_inativacao', e.target.value)}
                  placeholder="Ex.: aguardando correção da origem X / migração em andamento / solicitado pela área Y…"
                />
                <span className="text-[11px] text-dim">
                  Obrigatório ao inativar. Fica visível na lista e nos detalhes do pipeline,
                  para a equipe saber por que o fluxo está indisponível para execução.
                </span>
              </div>
            )}
          </div>
        )}

        {/* ── STEP 1: AGENDAMENTO ── */}
        {step === 1 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            {/* Dependência vem ANTES do horário e não em "Configurações
                Avançadas", onde estava: ela não é um ajuste fino, é a regra que
                SUBSTITUI o agendamento. Quem tem dependência não roda por
                horário — e ver isso depois de configurar o cron é tarde. */}
            <div className="flex flex-col gap-2 rounded-lg border border-edge bg-canvas px-3 py-2.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div>
                  <p className="text-xs font-medium text-ink">Depende de outros pipelines</p>
                  <p className="text-[10px] text-dim">
                    Só inicia quando todos concluírem com sucesso na mesma data de referência.
                  </p>
                </div>
                <Button variant="secondary" size="sm" onClick={() => setDepModalAberto(true)}>
                  <Link2 size={13} /> {depsSelecionadas.length ? 'Alterar' : 'Escolher'}
                </Button>
              </div>

              {depsSelecionadas.length === 0 ? (
                <p className="text-[11px] text-dim">
                  Nenhuma — este pipeline roda pelo horário configurado abaixo.
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {depsSelecionadas.map(nome => (
                      <span key={nome}
                        className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 text-[11px] text-blue-700 dark:text-blue-300">
                        <span className="font-mono">{nome}</span>
                        <button
                          onClick={() => aplicarDeps(depsSelecionadas.filter(n => n !== nome))}
                          aria-label={`Remover ${nome}`}
                          className="hover:text-red-600 dark:hover:text-red-400">
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                  {/* Progressive disclosure: janela e limite só existem para quem
                      tem dependência, e poluiriam a tela dos demais. */}
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-dim font-medium">Não iniciar antes de</label>
                      <input type="time" value={form.nao_iniciar_antes}
                        onChange={e => f('nao_iniciar_antes', e.target.value)}
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                      <p className="text-[10px] text-dim">Liberou antes? Espera até esta hora.</p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-dim font-medium">Avisar se não liberar até</label>
                      <input type="time" value={form.hora_limite_dependencia}
                        onChange={e => f('hora_limite_dependencia', e.target.value)}
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                      <p className="text-[10px] text-dim">Em branco, não avisa. O pipeline não falha.</p>
                    </div>
                  </div>
                </>
              )}
            </div>

            {depsSelecionadas.length > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/15 px-3 py-2">
                <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <p className="text-[11px] text-amber-800 dark:text-amber-300">
                  Com dependência, <strong>o horário abaixo deixa de valer</strong>: o pipeline é
                  disparado assim que a última dependência concluir.
                </p>
              </div>
            )}

            <div className={depsSelecionadas.length > 0 ? 'opacity-50' : ''}>
            <Select label="Tipo de agendamento" value={form.schedule_type} onChange={e => f('schedule_type', e.target.value)}>
              {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{SCHEDULE_LABELS[t]}</option>)}
            </Select>

            {form.schedule_type === 'hourly_n' && (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">A cada quantas horas? (1–23)</label>
                    <input type="number" min={1} max={23} value={form.schedule_interval_hours}
                      onChange={e => f('schedule_interval_hours', Math.min(23, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Começa às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_start_hour}
                      onChange={e => f('schedule_start_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Termina às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_end_hour}
                      onChange={e => f('schedule_end_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                <p className="text-[10px] text-dim">Ex: a cada 2h entre 08 e 18 → roda às 08, 10, 12, 14, 16 e 18.</p>
              </div>
            )}

            {form.schedule_type === 'custom' && (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Horários de execução</label>
                  <input type="text" value={form.schedule_custom_times}
                    onChange={e => f('schedule_custom_times', e.target.value)}
                    placeholder="ex: 09:00, 10:30, 13:00, 15:30"
                    className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  <p className="text-[10px] text-dim">Vários horários separados por vírgula no formato <span className="font-mono">HH:MM</span>.</p>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Dias da semana</label>
                  <div className="flex flex-wrap gap-1.5">
                    {DOW_LABELS.map(([v, l]) => {
                      const on = form.schedule_weekdays.includes(v)
                      return (
                        <button key={v} type="button"
                          onClick={() => f('schedule_weekdays', on ? form.schedule_weekdays.filter(d => d !== v) : [...form.schedule_weekdays, v])}
                          className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${on
                            ? 'bg-blue-600 border-blue-600 text-white'
                            : 'bg-panel border-edge text-dim hover:text-ink'}`}>
                          {l}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}

            {form.schedule_type === 'monthly_days_times' && (
              <div className="flex flex-col gap-3">
                {form.schedule_month_days.map((entry, di) => {
                  const usedDays = new Set(form.schedule_month_days.map(x => x.dia))
                  const times = parseCustomTimes(entry.horariosRaw)
                  return (
                    <div key={di} className="bg-canvas border border-edge rounded-lg p-3 flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-dim font-medium shrink-0">Dia do mês</label>
                        <select value={entry.dia}
                          onChange={e => {
                            const dia = parseInt(e.target.value)
                            f('schedule_month_days', form.schedule_month_days.map((x, i) => i === di ? { ...x, dia } : x))
                          }}
                          className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
                          {Array.from({ length: 28 }, (_, i) => i + 1)
                            .filter(d => d === entry.dia || !usedDays.has(d))
                            .map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <button type="button"
                          onClick={() => f('schedule_month_days', form.schedule_month_days.filter((_, i) => i !== di))}
                          className="ml-auto text-xs text-red-400 hover:text-red-300">Remover dia</button>
                      </div>
                      <input type="text" value={entry.horariosRaw}
                        onChange={e => f('schedule_month_days', form.schedule_month_days.map((x, i) =>
                          i === di ? { ...x, horariosRaw: e.target.value } : x))}
                        placeholder="ex: 09:00, 14:00, 18:00"
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                      <p className="text-[10px] text-dim">
                        {times.length > 0
                          ? `${times.length} horário${times.length > 1 ? 's' : ''}: ${times.join(', ')}`
                          : 'Informe ao menos um horário válido (HH:MM)'}
                      </p>
                    </div>
                  )
                })}
                {form.schedule_month_days.length < MAX_MONTH_DAYS && (
                  <button type="button"
                    onClick={() => {
                      const used = new Set(form.schedule_month_days.map(x => x.dia))
                      const nextDia = Array.from({ length: 28 }, (_, i) => i + 1).find(d => !used.has(d)) ?? 1
                      f('schedule_month_days', [...form.schedule_month_days, { dia: nextDia, horariosRaw: '' }])
                    }}
                    className="self-start text-xs text-blue-400 hover:text-blue-300 font-medium border border-edge rounded-md px-3 py-1.5">
                    + Adicionar dia
                  </button>
                )}
                <p className="text-[10px] text-dim">Até 5 dias do mês, cada um com até 5 horários próprios (ex: dia 1 às 09:00 · dia 15 às 14:00 e 18:00).</p>
              </div>
            )}

            {!['on_demand', 'hourly_n', 'custom', 'monthly_days_times'].includes(form.schedule_type) && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Hora (0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_hour}
                      onChange={e => f('schedule_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                {form.schedule_type === 'weekly' && (
                  <Select label="Dia da semana" value={form.schedule_dow} onChange={e => f('schedule_dow', parseInt(e.target.value))}>
                    {[['0','Domingo'],['1','Segunda'],['2','Terça'],['3','Quarta'],['4','Quinta'],['5','Sexta'],['6','Sábado']].map(([v,l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </Select>
                )}
                {(form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">
                      {form.schedule_type === 'biweekly' ? 'Dia da 1ª quinzena (1–13)' : 'Dia do mês (1–28)'}
                    </label>
                    <input type="number" min={1} max={form.schedule_type === 'biweekly' ? 13 : 28} value={form.schedule_dom}
                      onChange={e => {
                        const cap = form.schedule_type === 'biweekly' ? 13 : 28
                        f('schedule_dom', Math.min(cap, Math.max(1, parseInt(e.target.value) || 1)))
                      }}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    {form.schedule_type === 'biweekly' &&
                      <p className="text-[10px] text-dim">Roda neste dia e 15 dias depois (ex: dia 1 → roda nos dias 1 e 16).</p>}
                  </div>
                )}
              </>
            )}

            {showBizToggle && (
              <label className="flex items-center gap-2 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2">
                <input type="checkbox" checked={form.somente_dias_uteis}
                  onChange={e => f('somente_dias_uteis', e.target.checked)} className="accent-blue-500" />
                <span className="text-sm text-ink">Somente dias úteis (não roda sáb/dom)</span>
              </label>
            )}

            {form.schedule_type !== 'on_demand' && (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Calendário de bloqueio (opcional)</label>
                <select value={form.calendario_nome} onChange={e => f('calendario_nome', e.target.value)}
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="">— nenhum —</option>
                  {calendarios.map(c => (
                    <option key={c.calendario_nome} value={c.calendario_nome}>{c.calendario_nome} ({c.datas} data{c.datas !== 1 ? 's' : ''})</option>
                  ))}
                </select>
                <p className="text-[10px] text-dim">Datas do calendário (feriados/fechamento) em que o pipeline <strong>não roda</strong>. Gerencie em Admin ▸ Agendamento.</p>
              </div>
            )}

            <Input label="Data de início DAG (opcional)" type="date" value={form.dag_start_date}
              onChange={e => f('dag_start_date', e.target.value)} />

            <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5">
              {form.schedule_type === 'on_demand' ? (
                <p className="text-xs text-dim">Sem agendamento automático — execução apenas manual ou por dependência.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-[10px] text-dim font-bold uppercase tracking-wider">
                      {form.schedule_type === 'biweekly' ? 'Próximas 2 execuções' : 'Próximas execuções'}
                    </p>
                    {(form.schedule_type === 'hourly_n' || form.schedule_type === 'custom') && perDay > 0 && (
                      <span className="text-[10px] font-bold text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-800/40 rounded-full px-2 py-0.5">
                        {perDay}× por dia
                      </span>
                    )}
                  </div>
                  {nextRuns.length > 0 ? (
                    <ul className="flex flex-col gap-0.5">
                      {nextRuns.map((t, i) => (
                        <li key={i} className="text-[11px] text-ink flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                          {t}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-[11px] text-dim/60 italic">Preencha os campos para ver a simulação.</p>
                  )}
                </>
              )}
            </div>
            </div>
          </div>
        )}

        {/* ── STEP 2: NOTIFICAÇÕES + AVANÇADO ── */}
        {step === 2 && (
          <div className="flex flex-col gap-4 overflow-y-auto max-h-[55vh] pr-1">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2">Notificações Teams / E-mail</p>
              <div className="flex flex-col gap-2">
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
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2">Configurações Avançadas</p>
              <div className="flex flex-col gap-3">
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
                  {/* A escolha das dependências foi para o passo Agendamento —
                      é lá que se decide QUANDO o pipeline roda, e dependência
                      substitui horário. Aqui fica só a virada do dia, que é
                      mesmo configuração avançada. */}
                  <label className="text-xs text-dim font-medium">Virada do dia (data de referência)</label>
                  <input type="time" value={form.hora_virada}
                    onChange={e => f('hora_virada', e.target.value)}
                    className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  <p className="text-[10px] text-dim">
                    Em branco usa a virada global. Preencha só se o pipeline atravessa a
                    meia-noite: com virada 20:00, o que roda 31/07 23:30 pertence ao dia 01/08.
                  </p>
                </div>
                <Textarea label="Runbook (Markdown)" value={form.runbook_md}
                  onChange={e => f('runbook_md', e.target.value)} rows={3}
                  placeholder="Como monitorar, tratar falhas, contato responsável…" />
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 3: REVISÃO ── */}
        {step === 3 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <p className="text-xs text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/30 rounded-lg px-3 py-2">
              Revise todas as informações antes de salvar. Use o stepper acima para corrigir qualquer etapa.
            </p>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Identificação</span>
              </div>
              <div className="p-3 text-xs flex flex-col gap-1.5">
                <div className="flex flex-wrap gap-x-8 gap-y-1.5">
                  <div className="min-w-0"><span className="text-dim">Nome: </span><span className="font-mono font-bold text-ink break-all">{form.pipeline_name || '—'}</span></div>
                  <div><span className="text-dim">Projeto: </span><span className="text-ink">{form.project_name || '—'}</span></div>
                  <div className="min-w-0"><span className="text-dim">Domínio: </span><span className="text-ink break-all">{form.domain || '—'}</span></div>
                  <div><span className="text-dim">Ambiente: </span><span className={`font-medium ${form.ambiente === 'PROD' ? 'text-red-400' : 'text-yellow-400'}`}>{form.ambiente}</span></div>
                  <div><span className="text-dim">Criticidade: </span><span className={`font-medium ${critColor(form.criticidade)}`}>{form.criticidade}</span></div>
                  <div><span className="text-dim">Status: </span><span className={form.active ? 'text-green-400' : 'text-dim'}>{form.active ? 'Ativo' : 'Inativo'}</span></div>
                </div>
                {form.tags_list.length > 0 && (
                  <div className="flex items-center flex-wrap gap-1">
                    <span className="text-dim mr-1">Tags:</span>
                    {form.tags_list.map(t => (
                      <span key={t} className="bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-600/25 dark:text-blue-200 dark:border-blue-600/50 rounded-full px-2 py-0.5 text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                )}
                {form.descricao && <div className="text-dim/80 break-words"><span className="text-dim">Descrição: </span><span className="text-ink">{form.descricao}</span></div>}
              </div>
            </div>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Agendamento</span>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 p-3 text-xs">
                <div><span className="text-dim">Tipo:</span> <span className="text-ink">{SCHEDULE_LABELS[form.schedule_type] ?? form.schedule_type}</span></div>
                {form.schedule_type === 'hourly_n' && (
                  <div><span className="text-dim">Janela:</span> <span className="text-ink">a cada {form.schedule_interval_hours}h, {String(form.schedule_start_hour).padStart(2,'0')}h–{String(form.schedule_end_hour).padStart(2,'0')}h ({perDay}×/dia)</span></div>
                )}
                {form.schedule_type === 'custom' && (
                  <div className="col-span-2"><span className="text-dim">Horários:</span> <span className="font-mono text-ink">{parseCustomTimes(form.schedule_custom_times).join(', ') || '—'}</span> <span className="text-dim">· dias:</span> <span className="text-ink">{form.schedule_weekdays.length ? form.schedule_weekdays.slice().sort((a,b)=>a-b).map(d => DOW_LABELS.find(([v])=>v===d)?.[1]).join(', ') : '—'}</span></div>
                )}
                {form.schedule_type === 'monthly_days_times' && (
                  <div className="col-span-2 flex flex-col gap-0.5">
                    <span className="text-dim">Dias e horários:</span>
                    {(schedCfg.monthDays?.length ?? 0) > 0 ? schedCfg.monthDays!.map(e => (
                      <span key={e.dia} className="text-ink font-mono text-[11px]">Dia {e.dia} às {e.horarios.join(', ')}</span>
                    )) : <span className="text-dim/60 italic text-xs">—</span>}
                  </div>
                )}
                {form.schedule_type === 'weekly' && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">{DOW_LABELS.find(([v])=>v===form.schedule_dow)?.[1]} {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {(form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">dia {form.schedule_dom}{form.schedule_type === 'biweekly' ? ` e ${form.schedule_dom+15}` : ''} às {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {form.schedule_type === 'daily' && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">diariamente às {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {showBizToggle && form.somente_dias_uteis && <div><span className="text-dim">Restrição:</span> <span className="text-ink">somente dias úteis</span></div>}
                {form.calendario_nome && <div><span className="text-dim">Calendário:</span> <span className="text-ink">{form.calendario_nome}</span></div>}
                {depsSelecionadas.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-dim">Depende de:</span>{' '}
                    <span className="font-mono text-ink">{depsSelecionadas.join(', ')}</span>
                    <span className="text-amber-600 dark:text-amber-400"> · disparado ao concluírem (o horário não vale)</span>
                    {form.nao_iniciar_antes && <span className="text-dim"> · não antes de {form.nao_iniciar_antes}</span>}
                    {form.hora_limite_dependencia && <span className="text-dim"> · avisa se não liberar até {form.hora_limite_dependencia}</span>}
                  </div>
                )}
                {form.hora_virada && <div className="col-span-2"><span className="text-dim">Virada do dia:</span> <span className="text-ink">{form.hora_virada}</span></div>}
                {form.dag_start_date && <div><span className="text-dim">Início DAG:</span> <span className="text-ink">{form.dag_start_date}</span></div>}
                {form.sla_minutos && <div><span className="text-dim">SLA:</span> <span className="text-ink">{form.sla_minutos} min</span></div>}
                {nextRuns.length > 0 && (
                  <div className="col-span-2 border-t border-edge/50 pt-1.5 mt-0.5">
                    <span className="text-dim">Próximas:</span> <span className="text-ink">{nextRuns.slice(0, 3).join('  ·  ')}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-blue-50 border border-blue-200 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-300 rounded-lg px-3 py-2 text-xs">
              As etapas deste pipeline (jobs, decisões e lineage) são gerenciadas na tela <strong>Etapas</strong> (Lista + Fluxo), não neste cadastro.
            </div>

            {saveMut.isError && (
              <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2 text-xs text-red-700 dark:text-red-400">
                Erro ao salvar: {(saveMut.error as any)?.message}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between items-center pt-1 border-t border-edge">
          <Button variant="secondary" onClick={step === 0 ? requestClose : goPrev}>
            {step === 0 ? 'Cancelar' : '← Voltar'}
          </Button>
          <div className="flex gap-2">
            {step < 3
              ? <Button onClick={goNext}>Próximo →</Button>
              : <Button loading={saveMut.isPending} onClick={validateAllAndSave}>
                  <Save size={13} /> {isEdit ? 'Salvar alterações' : 'Criar pipeline'}
                </Button>
            }
          </div>
        </div>
      </div>
    </Modal>

    {/* Confirmação ao sair sem finalizar (evita perder dados preenchidos) */}
    {confirmClose && (
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/60" onClick={() => setConfirmClose(false)} />
        <div className="relative w-full max-w-sm bg-panel border border-edge rounded-xl shadow-2xl p-5 flex flex-col gap-4">
          <h3 className="text-base font-semibold text-ink">Sair sem finalizar?</h3>
          <p className="text-sm text-dim">Você tem informações preenchidas que ainda <strong className="text-ink">não foram salvas</strong>. Se sair agora, vai perder tudo.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirmClose(false)}>Continuar editando</Button>
            <Button variant="danger" onClick={() => { setConfirmClose(false); onClose() }}>Sair sem salvar</Button>
          </div>
        </div>
      </div>
    )}

    {/* Montado só quando aberto. Renderizar sempre deixava o `useState` interno
        preso no valor do PRIMEIRO mount: "Cancelar" não descartava a seleção, e
        uma dependência removida pelo X do chip voltava na próxima confirmação.
        O `Modal` esconde o painel com `open`, mas não desmonta este componente. */}
    {depModalAberto && (
      <DependenciasModal
        open
        onClose={() => setDepModalAberto(false)}
        pipelineAtual={form.pipeline_name}
        selecionadas={depsSelecionadas}
        pipelines={allPipes?.data ?? []}
        onConfirmar={aplicarDeps}
      />
    )}

    {/* Após criar: oferece gerar a DAG agora (mesmo disparo do botão Gerar DAG) */}
    {askGenerate && (
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/60" />
        <div className="relative w-full max-w-sm bg-panel border border-edge rounded-xl shadow-2xl p-5 flex flex-col gap-4">
          <h3 className="text-base font-semibold text-ink">Publicar a DAG agora?</h3>
          <p className="text-sm text-ink">Pipeline <span className="font-mono font-medium">{askGenerate}</span> {isEdit ? 'atualizado' : 'criado'}! As mudanças só passam a valer no Airflow após publicar {isEdit ? 'a nova versão da' : 'a'} DAG. Deseja publicar agora?</p>
          <p className="text-xs text-dim">Equivale a clicar em “Publicar DAG”. O ORQUESTRA avisa quando a DAG estiver ativa.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" disabled={genDagMut.isPending} onClick={() => { setAskGenerate(null); onClose() }}>Agora não</Button>
            <Button loading={genDagMut.isPending} onClick={() => genDagMut.mutate(askGenerate)}>
              <Save size={13} /> {isEdit ? 'Publicar nova versão' : 'Publicar DAG'}
            </Button>
          </div>
        </div>
      </div>
    )}
    </>
  )
}

// re-export buildCron for ViewModal (used in PipelineModals)
export { buildCron }
