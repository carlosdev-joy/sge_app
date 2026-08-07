import { useState, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Save } from 'lucide-react'
import type { Pipeline } from '../../types/pipeline'
import {
  SCHEDULE_TYPES, SCHEDULE_LABELS, CRITICIDADES, AMBIENTES, MAX_MONTH_DAYS,
  DOW_LABELS,
  type ScheduleConfig, type MonthDayEntry,
  hourlyTimes, parseCustomTimes, computeNextRuns, runsPerDay,
  critColor, parseMonthDaysTimes, serializeMonthDaysTimes,
} from './pipelineUtils'
import { DependenciasModal } from './DependenciasModal'

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
  motivo_inativacao: string
  // Janela e virada (migration 067) — 'HH:MM' ou '' (= sem regra → NULL).
  // hora_virada é rótulo ODATE de QUALQUER pipeline (o caso motivador é um
  // PAI com virada 20:00); os outros dois são da liberação por dependência.
  hora_virada: string
  nao_iniciar_antes: string
  hora_limite_dependencia: string
}

// Espelho DISPLAY-ONLY da regra canônica do ODATE (dags/utils/data_referencia
// → api/services/data_referencia): hora >= virada → dia seguinte. A autoridade
// continua sendo o servidor — este valor NUNCA decide nada, só ilustra o campo
// (risco 4 da spec: a virada sem exemplo vivo era ilegível).
function calcularDataRef(agora: Date, virada: string): Date {
  const [h, m] = virada.split(':').map(Number)
  const d = new Date(agora)
  if ((h !== 0 || m !== 0) && agora.getHours() * 60 + agora.getMinutes() >= h * 60 + m) d.setDate(d.getDate() + 1)
  return d
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
  somente_dias_uteis: false, calendario_nome: '',
  active: true, dag_start_date: '',
  envia_msg_inicio: true, envia_msg_fim: true, envia_msg_erro: true,
  criticidade: 'Media', sla_minutos: '', ambiente: 'PROD',
  max_active_runs: 1, retries_count: 1, retry_delay_seconds: 300,
  pool_name: '', depends_on: '', runbook_md: '', motivo_inativacao: '',
  hora_virada: '', nao_iniciar_antes: '', hora_limite_dependencia: '',
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
    runbook_md:              p.runbook_md ?? '',
    motivo_inativacao:       p.motivo_inativacao ?? '',
    // Round-trip D26: os três chegam do GET ('HH:MM' ou null) — antes eram
    // write-only e todo save os zerava no banco.
    hora_virada:             p.hora_virada ?? '',
    nao_iniciar_antes:       p.nao_iniciar_antes ?? '',
    hora_limite_dependencia: p.hora_limite_dependencia ?? '',
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

// Campos de HORA ficam visíveis porém INERTES quando há dependência (F3/D03:
// regra de relógio é só de disparo por agenda) — o title explica o porquê.
const TITULO_HORA_INERTE =
  'Com dependência, o horário não vale — o gatilho é a conclusão dos predecessores'

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
  // D31: o DependenciasModal só é MONTADO enquanto aberto — render condicional.
  const [depsModalAberto, setDepsModalAberto] = useState(false)

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

  const { data: calData } = useQuery<{ calendarios: { calendario_nome: string; datas: number }[] }>({
    queryKey: ['agenda-calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
    staleTime: 300_000,
  })
  const calendarios = calData?.calendarios ?? []

  // "Dirty" cirúrgico: marca só quando muda algo que AFETA a DAG (não cadastro
  // puro). Usado para perguntar "Regenerar a DAG?" só quando precisa.
  // Alinhado com CAMPOS_QUE_AFETAM_DAG do servidor (achado 1 da revisão da
  // F5): sla_minutos vira dagrun_timeout e criticidade vira queue do
  // DataStage no gerador — mudá-los TEM que disparar o prompt imediato.
  const dagDirtyRef = useRef(false)
  const CADASTRO_FIELDS = new Set<string>([
    'tags_list', 'descricao', 'runbook_md',
    'active', 'motivo_inativacao',
  ])
  function markDagDirty() {
    dagDirtyRef.current = true
  }

  function f<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    if (!CADASTRO_FIELDS.has(k as string)) markDagDirty()
  }

  const temDependencia = form.depends_on.trim() !== ''
  const dependenciasLista = form.depends_on.split(',').map(s => s.trim()).filter(Boolean)

  // Resultado do DependenciasModal. Criação: a lista vira o CSV que viaja no
  // body do register (Decisão 1 — replace-all inofensivo sobre tabela vazia).
  // Edição: o modal JÁ aplicou o diff no servidor (aresta a aresta, F8) — aqui
  // só se espelha o estado local. Remover a ÚLTIMA dependência limpa janela e
  // hora-limite (D34): o form zera os dois e envia '' (chave presente → NULL)
  // — nada de configuração órfã no banco.
  function aplicarDependencias(nomes: string[]) {
    const tinha = form.depends_on.trim() !== ''
    const limpaJanela = tinha && nomes.length === 0
    setForm(prev => ({
      ...prev,
      depends_on: nomes.join(','),
      ...(limpaJanela ? { nao_iniciar_antes: '', hora_limite_dependencia: '' } : {}),
    }))
    if (limpaJanela) {
      toast.info('Última dependência removida — janela e hora-limite serão limpos ao salvar.')
    }
    markDagDirty()
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
        // Com dependência os campos de HORA estão inertes (F3/D03): não podem
        // reprovar o passo — só as restrições de DIA seguem obrigatórias.
        if (!temDependencia) {
          if (form.schedule_interval_hours < 1 || form.schedule_interval_hours > 23) e.push('Intervalo deve ser entre 1 e 23 horas')
          if (form.schedule_start_hour < 0 || form.schedule_start_hour > 23) e.push('Hora de início inválida (0–23)')
          if (form.schedule_end_hour < 0 || form.schedule_end_hour > 23) e.push('Hora de término inválida (0–23)')
          if (form.schedule_end_hour < form.schedule_start_hour) e.push('Hora de término deve ser ≥ hora de início')
          if (form.schedule_minute < 0 || form.schedule_minute > 59) e.push('Minuto inválido (0–59)')
        }
      } else if (t === 'custom') {
        if (!temDependencia && parseCustomTimes(form.schedule_custom_times).length === 0) e.push('Informe ao menos um horário válido (HH:MM)')
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
        // Decisão 1/2: na CRIAÇÃO a seleção do modal viaja no register
        // (replace-all inofensivo — a tabela do recém-criado está vazia); na
        // EDIÇÃO a chave é OMITIDA: as arestas já foram gravadas na hora pelo
        // modal (porta da F8) e chave ausente = "não mexa", nunca "apague".
        ...(isEdit ? {} : { depends_on: form.depends_on.trim() || null }),
        // trigger_por_dependencia NÃO é mais enviado (Decisão 3): a chave
        // ausente preserva o valor no banco — zerar reabriria o hazard de
        // deploy API-antes-de-dags (sensor de volta na regeneração).
        // Janela e virada: chaves SEMPRE presentes no wizard ('' → NULL no
        // banco — "limpo de verdade", não configuração órfã; D34/D35).
        hora_virada:             form.hora_virada.trim(),
        nao_iniciar_antes:       temDependencia ? form.nao_iniciar_antes.trim() : '',
        hora_limite_dependencia: temDependencia ? form.hora_limite_dependencia.trim() : '',
        runbook_md:          form.runbook_md.trim() || null,
        changed_by:          user?.matricula ?? 'react-ui',
        dag_criada:          pipeline?.dag_criada ?? 0,
        ...buildSchedulePayload(),
      }
      const reg = await apiFetch<{ dag_sync?: DagSync | null; avisos?: string[] }>('/pipelines/register', { method: 'POST', body: JSON.stringify(body) })
      const dagSync = reg?.dag_sync ?? null
      return { pname, dagSync, avisos: reg?.avisos ?? [] }
    },
    onSuccess: (res: { pname: string; dagSync?: DagSync | null; avisos?: string[] }) => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      // D35: hora inválida virou NULL no servidor — o descarte nunca é mudo.
      res.avisos?.forEach(a => toast.info(`Atenção: ${a}`))
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
            {/* Dependências — escolhidas SÓ pelo modal (nunca texto livre, D33).
                Semântica corrigida pela F3 (D03/D04): com dependência o HORÁRIO
                deixa de valer, mas as restrições de DIA continuam valendo. */}
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Dependências</span>
                <Button variant="secondary" size="sm" onClick={() => setDepsModalAberto(true)}>
                  {temDependencia ? 'Editar dependências' : 'Escolher dependências'}
                </Button>
              </div>
              {temDependencia ? (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {dependenciasLista.map(n => (
                      <span key={n} className="inline-flex items-center px-2 py-0.5 rounded-full border border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 text-[11px] font-mono text-blue-700 dark:text-blue-300">
                        {n}
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-dim">
                    Com dependência, o <strong className="text-ink">horário</strong> deixa de valer
                    (o gatilho é a conclusão dos predecessores); as restrições de{' '}
                    <strong className="text-ink">dia</strong> — semanal, mensal, dias úteis,
                    calendário — continuam valendo.
                  </p>
                </>
              ) : (
                <p className="text-[11px] text-dim">
                  Sem dependências — o pipeline dispara pelo agendamento abaixo.
                </p>
              )}
            </div>

            <Select label="Tipo de agendamento" value={form.schedule_type} onChange={e => f('schedule_type', e.target.value)}>
              {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{SCHEDULE_LABELS[t]}</option>)}
            </Select>

            {form.schedule_type === 'hourly_n' && (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">A cada quantas horas? (1–23)</label>
                    <input type="number" min={1} max={23} value={form.schedule_interval_hours}
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_interval_hours', Math.min(23, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Começa às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_start_hour}
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_start_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Termina às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_end_hour}
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_end_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
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
                    disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                    onChange={e => f('schedule_custom_times', e.target.value)}
                    placeholder="ex: 09:00, 10:30, 13:00, 15:30"
                    className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  <p className="text-[10px] text-dim">
                    {temDependencia
                      ? 'Com dependência o horário não vale — só os dias da semana abaixo continuam restringindo.'
                      : <>Vários horários separados por vírgula no formato <span className="font-mono">HH:MM</span>.</>}
                  </p>
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
                        disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                        onChange={e => f('schedule_month_days', form.schedule_month_days.map((x, i) =>
                          i === di ? { ...x, horariosRaw: e.target.value } : x))}
                        placeholder="ex: 09:00, 14:00, 18:00"
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
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
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      disabled={temDependencia} title={temDependencia ? TITULO_HORA_INERTE : undefined}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50" />
                  </div>
                </div>
                {temDependencia && (
                  <p className="text-[10px] text-dim -mt-1">
                    Hora/minuto inertes: com dependência o gatilho é a conclusão dos predecessores.
                    A restrição de <strong>dia</strong> abaixo continua valendo.
                  </p>
                )}
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

            {/* hora_virada NÃO é campo de dependente — é o rótulo ODATE de
                QUALQUER pipeline (o caso motivador é um PAI com virada 20:00,
                que pode nem ter dependência). Aparece SEMPRE (§3.3). */}
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5 flex flex-col gap-1.5">
              <label className="text-xs text-dim font-medium">Hora de virada do dia (ODATE) — opcional</label>
              <input type="time" value={form.hora_virada}
                onChange={e => f('hora_virada', e.target.value)}
                className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-1 focus:ring-blue-500" />
              {form.hora_virada ? (
                <div className="text-[10px] text-dim flex flex-col gap-0.5">
                  {/* Espelho display-only da regra canônica — nunca decide nada. */}
                  <span>
                    agora ({new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })})
                    {' → '}data de referência{' '}
                    <strong className="text-ink">
                      {calcularDataRef(new Date(), form.hora_virada).toLocaleDateString('pt-BR')}
                    </strong>
                  </span>
                  <span>início ≥ {form.hora_virada} conta para o dia seguinte
                    {' '}(ex.: virada 20:00 · início 23:30 → dia seguinte).</span>
                </div>
              ) : (
                <p className="text-[10px] text-dim">
                  Em branco = a data de referência é a do calendário. Com virada 20:00, uma corrida
                  iniciada 23:30 (ou 00:40) já pertence ao dia seguinte — as duas pontas da
                  meia-noite viram o MESMO ciclo de negócio.
                </p>
              )}
            </div>

            {/* Janela e hora-limite são da LIBERAÇÃO por dependência: só
                aparecem com dependência e são limpos ao remover a última (D34). */}
            {temDependencia && (
              <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5 flex flex-col gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Janela da liberação</span>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Não iniciar antes de (opcional)</label>
                    <input type="time" value={form.nao_iniciar_antes}
                      onChange={e => f('nao_iniciar_antes', e.target.value)}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    <p className="text-[10px] text-dim">
                      Liberou antes disso? O disparo espera a hora (a guardiã dispara na janela).
                    </p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Avisar se não liberar até (opcional)</label>
                    <input type="time" value={form.hora_limite_dependencia}
                      onChange={e => f('hora_limite_dependencia', e.target.value)}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    <p className="text-[10px] text-dim">
                      Ao passar da hora, o Orquestra <strong>alerta e mantém pendente</strong> —
                      não bloqueia nem falha.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5">
              {temDependencia ? (
                <p className="text-xs text-dim">
                  <span className="text-[10px] font-bold uppercase tracking-wider block mb-1">Disparo</span>
                  disparo pelos predecessores: <span className="font-mono text-ink">{dependenciasLista.join(', ')}</span>
                </p>
              ) : form.schedule_type === 'on_demand' ? (
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
                {/* O campo de texto "Depende de" e o checkbox "Disparar quando
                    as dependências concluírem" morreram na F5: dependência é
                    escolhida SÓ pelo modal do passo Agendamento (D33) e ter
                    dependência JÁ significa disparo por ela (F3/Decisão 3). */}
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
                {temDependencia && (
                  <div className="col-span-2">
                    <span className="text-dim">Depende de:</span>{' '}
                    <span className="font-mono text-ink">{dependenciasLista.join(', ')}</span>
                    <span className="text-amber-600 dark:text-amber-400">
                      {' '}· o horário deixa de valer (dispara na conclusão dos predecessores); as restrições de dia continuam valendo
                    </span>
                  </div>
                )}
                {form.hora_virada && <div><span className="text-dim">Virada (ODATE):</span> <span className="text-ink">{form.hora_virada}</span></div>}
                {temDependencia && form.nao_iniciar_antes && <div><span className="text-dim">Não iniciar antes:</span> <span className="text-ink">{form.nao_iniciar_antes}</span></div>}
                {temDependencia && form.hora_limite_dependencia && <div><span className="text-dim">Avisar se não liberar até:</span> <span className="text-ink">{form.hora_limite_dependencia}</span></div>}
                {form.dag_start_date && <div><span className="text-dim">Início DAG:</span> <span className="text-ink">{form.dag_start_date}</span></div>}
                {form.sla_minutos && <div><span className="text-dim">SLA:</span> <span className="text-ink">{form.sla_minutos} min</span></div>}
                {!temDependencia && nextRuns.length > 0 && (
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

    {/* D31: DependenciasModal MONTADO só enquanto aberto — "Cancelar" descarta
        a seleção local e a próxima abertura re-hidrata do servidor; chip
        removido não ressuscita (o Modal da casa esconde mas não desmonta). */}
    {depsModalAberto && (
      <DependenciasModal
        pipelineAtual={(form.pipeline_name.trim() || 'NOVO_PIPELINE').toUpperCase()}
        isEdit={isEdit}
        selecionadas={dependenciasLista}
        onClose={() => setDepsModalAberto(false)}
        onConfirmar={aplicarDependencias}
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
