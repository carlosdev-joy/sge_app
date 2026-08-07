// Painel de agendamento do nó Início (F13 — desenho §4, Decisão 8): o
// agendamento mora na MALHA (etl_malha.agendamento_json) e o nó Início é a
// porta — clicar nele abre este painel. Salvar compila: o servidor COPIA os
// campos para as colunas reais de cada raiz ligada + assina agenda_no +
// carimba a republicação, numa transação (POST /malhas/{name}/agendamento).
// O fluxo é o mesmo contrato de gesto da F12: dry_run ANTES do write mostra
// o efeito §7.2 (agendamentos de → para, republicar, avisos) e os erros
// (conflito de assinatura, Decisão 11) BLOQUEIAM com o texto do servidor.
//
// Os campos são o subconjunto do register (§4.1) — mesmos nomes de banco do
// passo Agendamento do wizard, com os helpers compartilhados de
// pipelineUtils (parseCustomTimes/serializeMonthDaysTimes/DOW_LABELS):
// daily/weekly/monthly/biweekly/custom/monthly_days_times + só dias úteis,
// calendário e hora_virada (Decisão 9: UMA virada por malha). 'on_demand'
// não é opção aqui de propósito: desligar raiz do cron é o gesto de
// desligar a aresta/o Início (Decisão 10), nunca um "agendamento vazio".
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import {
  AlertCircle, AlertTriangle, CalendarClock, Info, Plus, Trash2,
} from 'lucide-react'
import {
  DOW_LABELS, MAX_MONTH_DAYS, parseCustomTimes, parseMonthDaysTimes,
  serializeMonthDaysTimes, type MonthDayEntry,
} from '../pipelines/pipelineUtils'

// Tipos oferecidos no painel (rótulos do wizard; sem hourly_n — açúcar de UI
// do wizard que vira 'custom' no banco — e sem on_demand, ver cabeçalho).
const TIPOS_MALHA: [string, string][] = [
  ['daily', 'Diário'], ['weekly', 'Semanal'], ['monthly', 'Mensal'],
  ['biweekly', 'Quinzenal'], ['custom', 'Horários específicos'],
  ['monthly_days_times', 'Dia + Hora Específico'],
]

interface EfeitoAgendamento { pipeline: string; de: string; para: string }
interface AvisoDesenho { no: number | null; nivel: string; mensagem: string }
interface RespostaDry {
  efeito: { agendamentos: EfeitoAgendamento[]; republicar: string[] }
  avisos: AvisoDesenho[]
  erros: string[]
}

interface FormAgendamento {
  schedule_type: string
  schedule_hour: number
  schedule_minute: number
  schedule_dow: number
  schedule_dom: number
  horariosRaw: string          // CSV livre do 'custom' (parse ao enviar)
  diasSemana: Set<number>      // checkboxes do 'custom'
  monthDays: MonthDayEntry[]   // editor do 'monthly_days_times'
  somenteDiasUteis: boolean
  calendarioNome: string
  horaVirada: string           // 'HH:MM' ou vazio
}

const FORM_VAZIO: FormAgendamento = {
  schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0,
  schedule_dow: 1, schedule_dom: 1, horariosRaw: '', diasSemana: new Set(),
  monthDays: [{ dia: 1, horariosRaw: '' }], somenteDiasUteis: false,
  calendarioNome: '', horaVirada: '',
}

// Carrega o form a partir do agendamento salvo na malha (GET /malhas/{name}).
function formDoAgendamento(ag: Record<string, unknown> | null): FormAgendamento {
  if (!ag) return { ...FORM_VAZIO, diasSemana: new Set(), monthDays: [{ dia: 1, horariosRaw: '' }] }
  const dias = new Set<number>()
  for (const d of String(ag.dias_semana ?? '').split(',')) {
    const n = parseInt(d.trim())
    if (!isNaN(n)) dias.add(n)
  }
  const monthDays = parseMonthDaysTimes(ag.dias_horarios_mes as string | null)
  return {
    schedule_type: String(ag.schedule_type ?? 'daily'),
    schedule_hour: Number(ag.schedule_hour ?? 6),
    schedule_minute: Number(ag.schedule_minute ?? 0),
    schedule_dow: Number(ag.schedule_dow ?? 1),
    schedule_dom: Number(ag.schedule_dom ?? 1),
    horariosRaw: String(ag.horarios_especificos ?? ''),
    diasSemana: dias,
    monthDays: monthDays.length > 0 ? monthDays : [{ dia: 1, horariosRaw: '' }],
    somenteDiasUteis: !!Number(ag.somente_dias_uteis ?? 0),
    calendarioNome: String(ag.calendario_nome ?? ''),
    horaVirada: String(ag.hora_virada ?? '').slice(0, 5),
  }
}

// Monta o payload de banco (§4.1) — a mesma tradução do buildSchedulePayload
// do wizard: 'custom' envia horarios_especificos + dias_semana;
// 'monthly_days_times' serializa o editor; o servidor deriva scheduled_time.
function payloadDoForm(f: FormAgendamento): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schedule_type: f.schedule_type,
    schedule_hour: f.schedule_hour,
    schedule_minute: f.schedule_minute,
    schedule_dow: f.schedule_dow,
    schedule_dom: f.schedule_dom,
    somente_dias_uteis: f.somenteDiasUteis ? 1 : 0,
    calendario_nome: f.calendarioNome.trim() || null,
    hora_virada: f.horaVirada.trim() || null,
    horarios_especificos: null,
    dias_semana: null,
    dias_horarios_mes: null,
  }
  if (f.schedule_type === 'custom') {
    base.horarios_especificos = parseCustomTimes(f.horariosRaw).join(',') || null
    base.dias_semana = [...f.diasSemana].sort((a, b) => a - b).join(',') || null
  }
  if (f.schedule_type === 'monthly_days_times') {
    base.dias_horarios_mes = serializeMonthDaysTimes(f.monthDays)
  }
  return base
}

interface Props {
  malha: string
  aberto: boolean
  onClose: () => void
  // Agendamento atual da malha (payload do GET) — null = ainda sem agenda.
  agendamento: Record<string, unknown> | null
  // Contagem de raízes ligadas ao Início (para o texto honesto do rodapé).
  raizes: number
  // F3 da spec-malha-data-unica: a marca de equalização automática da malha
  // (migration 081). undefined = a API ainda não a expõe (deploy parcial) e o
  // controle não é oferecido.
  equalizarData?: number
  // F7 (085): o LIMITE DE SEGURANÇA da malha em horas. `null` = segue o limite
  // global; `undefined` = a API não expõe a chave (deploy parcial) e o controle
  // não é oferecido — botão que não grava é pior que botão ausente.
  tetoHoras?: number | null
  temTeto?: boolean
}

export function AgendamentoInicioModal({ malha, aberto, onClose, agendamento, raizes, equalizarData, tetoHoras, temTeto }: Props) {
  // O corpo só monta com o modal aberto: o useState do form inicializa do
  // agendamento da malha NO MOUNT — reabrir remonta e recarrega, sem
  // setState em efeito (lint react-hooks/set-state-in-effect, a mesma lição
  // do override de orientação do MalhaEditor).
  return (
    <Modal open={aberto} onClose={onClose} title="Agendamento da malha" size="lg">
      {aberto && (
        <CorpoAgendamento malha={malha} onClose={onClose}
          agendamento={agendamento} raizes={raizes}
          equalizarData={equalizarData}
          tetoHoras={tetoHoras} temTeto={temTeto} />
      )}
    </Modal>
  )
}

function CorpoAgendamento({ malha, onClose, agendamento, raizes, equalizarData, tetoHoras, temTeto }: Omit<Props, 'aberto'>) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormAgendamento>(
    () => formDoAgendamento(agendamento))
  // null = fase de formulário; preenchido = fase de confirmação (dry_run ok).
  const [preview, setPreview] = useState<RespostaDry | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [aplicando, setAplicando] = useState(false)
  // F3: a marca vive na MALHA (081) e é salva pelo PATCH — o agendamento tem
  // porta própria, e misturar os dois payloads faria um gesto escrever no
  // contrato do outro.
  const [equalizarLocal, setEqualizarLocal] = useState(!!Number(equalizarData ?? 0))
  // F7: o limite de segurança da malha, como TEXTO — vazio significa "segue o
  // limite global", que é um estado legítimo e diferente de zero. Um `number`
  // aqui obrigaria a inventar um sentinela para o vazio.
  const [tetoLocal, setTetoLocal] = useState(
    tetoHoras === null || tetoHoras === undefined ? '' : String(tetoHoras))

  const { data: calData } = useQuery<{ calendarios: { calendario_nome: string }[] }>({
    queryKey: ['agenda-calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
  })
  const calendarios = calData?.calendarios ?? []

  const set = (patch: Partial<FormAgendamento>) => setForm(f => ({ ...f, ...patch }))

  // Quinzenal roda em D e D+15: dom > 13 estoura o mês (cron com dia 32-43 =
  // Broken DAG) — a MESMA regra e mensagem do wizard (defeito GRAVE da
  // revisão adversarial da F13); o servidor recusa com 422 por baixo.
  const domMax = form.schedule_type === 'biweekly' ? 13 : 28

  async function verEfeito() {
    if (carregando) return
    if (form.schedule_type === 'biweekly'
        && (form.schedule_dom < 1 || form.schedule_dom > 13)) {
      toast.error('Dia da 1ª quinzena inválido (1–13)')
      return
    }
    setCarregando(true)
    try {
      const r = await apiFetch<RespostaDry>(
        `/malhas/${encodeURIComponent(malha)}/agendamento`, {
          method: 'POST',
          body: JSON.stringify({ agendamento: payloadDoForm(form), dry_run: true }),
        })
      setPreview(r)
    } catch (err) {
      // 422 de validação (as mesmas funções do register) / 503 de migration.
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao validar o agendamento')
    } finally {
      setCarregando(false)
    }
  }

  async function confirmar() {
    if (aplicando) return
    setAplicando(true)
    try {
      const r = await apiFetch<RespostaDry & {
        ok: boolean; agendamento_resumo: string; virada_equalizada?: string[]
      }>(
        `/malhas/${encodeURIComponent(malha)}/agendamento`, {
          method: 'POST',
          body: JSON.stringify({ agendamento: payloadDoForm(form) }),
        })
      // A marca de equalização mora na MALHA e tem porta própria (PATCH): o
      // agendamento não pode escrever no contrato dela. Só vai se MUDOU.
      const tetoNovo = tetoLocal.trim() === '' ? null : Number(tetoLocal.trim())
      const tetoMudou = temTeto && tetoNovo !== (tetoHoras ?? null)
      if (equalizarLocal !== !!Number(equalizarData ?? 0) || tetoMudou) {
        try {
          await apiFetch(`/malhas/${encodeURIComponent(malha)}`, {
            method: 'PATCH',
            body: JSON.stringify({
              equalizar_data: equalizarLocal ? 1 : 0,
              // A chave só vai quando MUDOU: mandar `teto_horas` em todo save
              // faria um deploy sem a 085 responder `migration_085_pendente`
              // para quem nem mexeu no campo.
              ...(tetoMudou ? { teto_horas: tetoNovo } : {}),
            }),
          })
          if (tetoMudou) {
            toast.info(tetoNovo === null
              ? 'Limite de segurança da malha: volta a seguir o limite global. Vale do PRÓXIMO ciclo — o limite do ciclo em voo foi fixado quando ele abriu.'
              : `Limite de segurança da malha: ${tetoNovo}h. Vale do PRÓXIMO ciclo — o limite do ciclo em voo foi fixado quando ele abriu.`)
          }
        } catch (e2) {
          // O agendamento JÁ foi salvo — falhar aqui não pode parecer que
          // nada aconteceu, nem que a marca pegou.
          const err2 = e2 as Error
          toast.error(`Agendamento salvo, mas a configuração da malha não: ${err2.message}`)
        }
      }
      toast.success(`Agendamento da malha salvo: ${r.agendamento_resumo}.`)
      if (r.virada_equalizada?.length) {
        toast.info(`${r.virada_equalizada.length} pipeline(s) alinhados à hora de virada da malha — republique-os.`)
      }
      if (r.efeito.agendamentos.length > 0) {
        toast.info(`${r.efeito.agendamentos.length} raiz(es) receberam o agendamento da malha.`)
      }
      r.efeito.republicar.slice(0, 3).forEach(nome => toast.info(
        `A DAG de ${nome} precisa ser republicada (Pipelines ▸ Publicar nova versão).`))
      if (r.efeito.republicar.length > 3) {
        toast.info(`+${r.efeito.republicar.length - 3} DAGs precisam ser republicadas.`)
      }
      qc.invalidateQueries({ queryKey: ['malha'] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      onClose()
    } catch (err) {
      // O servidor RECOMPUTA no write (§7.2): um 422 aqui é edição
      // concorrente (ex.: conflito de assinatura que nasceu no vão).
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao salvar o agendamento')
      setPreview(null)
    } finally {
      setAplicando(false)
    }
  }

  const inputCls =
    'rounded-md border border-edge bg-canvas px-2 py-1 text-xs text-ink ' +
    'focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40'
  const labelCls = 'text-[11px] font-medium text-dim'

  return (
    <div className="flex flex-col gap-3">
        <p className="text-[12px] leading-relaxed text-dim">
          O agendamento pertence à <strong className="text-ink">malha</strong> e
          é <strong className="text-ink">copiado para as raízes</strong> ligadas
          ao Início — todas disparam no mesmo tick, em paralelo, cada uma na
          própria DAG. A hora de virada vale para todas (uma malha, um dia
          operacional).
        </p>

        {preview === null ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Tipo</span>
                <select
                  value={form.schedule_type}
                  onChange={e => {
                    const t = e.target.value
                    // Trocar p/ quinzenal com dom fora da 1ª quinzena: o
                    // clamp acompanha o teto novo (1–13), nunca fica lixo.
                    set({ schedule_type: t,
                          ...(t === 'biweekly' && form.schedule_dom > 13
                            ? { schedule_dom: 13 } : {}) })
                  }}
                  className={inputCls}
                >
                  {TIPOS_MALHA.map(([v, rotulo]) => (
                    <option key={v} value={v}>{rotulo}</option>
                  ))}
                </select>
              </label>
              {['daily', 'weekly', 'monthly', 'biweekly'].includes(form.schedule_type) && (
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Horário</span>
                  <div className="flex items-center gap-1">
                    <input type="number" min={0} max={23} value={form.schedule_hour}
                      onChange={e => set({ schedule_hour: Math.min(23, Math.max(0, Number(e.target.value))) })}
                      className={`${inputCls} w-16`} />
                    <span className="text-xs text-dim">:</span>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      onChange={e => set({ schedule_minute: Math.min(59, Math.max(0, Number(e.target.value))) })}
                      className={`${inputCls} w-16`} />
                  </div>
                </label>
              )}
              {form.schedule_type === 'weekly' && (
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Dia da semana</span>
                  <select value={form.schedule_dow}
                    onChange={e => set({ schedule_dow: Number(e.target.value) })}
                    className={inputCls}>
                    {DOW_LABELS.map(([v, rotulo]) => (
                      <option key={v} value={v}>{rotulo}</option>
                    ))}
                  </select>
                </label>
              )}
              {['monthly', 'biweekly'].includes(form.schedule_type) && (
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>
                    {form.schedule_type === 'biweekly'
                      ? 'Dia da 1ª quinzena (1–13 — roda em D e D+15)'
                      : 'Dia do mês'}
                  </span>
                  <input type="number" min={1} max={domMax} value={form.schedule_dom}
                    onChange={e => set({ schedule_dom: Math.min(domMax, Math.max(1, Number(e.target.value))) })}
                    className={`${inputCls} w-20`} />
                </label>
              )}
            </div>

            {form.schedule_type === 'custom' && (
              <div className="flex flex-col gap-2">
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Horários (HH:MM, separados por vírgula)</span>
                  <input value={form.horariosRaw}
                    onChange={e => set({ horariosRaw: e.target.value })}
                    placeholder="ex.: 06:00, 12:30, 18:00"
                    className={inputCls} />
                </label>
                <div className="flex flex-col gap-1">
                  <span className={labelCls}>Dias da semana (vazio = todos)</span>
                  <div className="flex flex-wrap gap-2">
                    {DOW_LABELS.map(([v, rotulo]) => (
                      <label key={v} className="flex items-center gap-1 text-[11px] text-ink">
                        <input type="checkbox"
                          checked={form.diasSemana.has(v)}
                          onChange={e => {
                            const dias = new Set(form.diasSemana)
                            if (e.target.checked) dias.add(v)
                            else dias.delete(v)
                            set({ diasSemana: dias })
                          }} />
                        {rotulo}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {form.schedule_type === 'monthly_days_times' && (
              <div className="flex flex-col gap-1.5">
                <span className={labelCls}>Dias do mês e horários (1-28, até {MAX_MONTH_DAYS} dias)</span>
                {form.monthDays.map((entry, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input type="number" min={1} max={28} value={entry.dia}
                      onChange={e => {
                        const monthDays = [...form.monthDays]
                        monthDays[i] = { ...entry, dia: Math.min(28, Math.max(1, Number(e.target.value))) }
                        set({ monthDays })
                      }}
                      className={`${inputCls} w-16`} />
                    <input value={entry.horariosRaw}
                      onChange={e => {
                        const monthDays = [...form.monthDays]
                        monthDays[i] = { ...entry, horariosRaw: e.target.value }
                        set({ monthDays })
                      }}
                      placeholder="horários — ex.: 09:00, 14:00"
                      className={`${inputCls} flex-1`} />
                    <button
                      onClick={() => set({ monthDays: form.monthDays.filter((_, j) => j !== i) })}
                      disabled={form.monthDays.length <= 1}
                      title="Remover o dia"
                      className="text-dim hover:text-red-600 disabled:opacity-30"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
                {form.monthDays.length < MAX_MONTH_DAYS && (
                  <button
                    onClick={() => set({ monthDays: [...form.monthDays, { dia: 1, horariosRaw: '' }] })}
                    className="inline-flex w-fit items-center gap-1 rounded-md border border-edge bg-canvas px-2 py-1 text-[11px] text-dim hover:text-ink"
                  >
                    <Plus size={11} /> adicionar dia
                  </button>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 border-t border-edge pt-2">
              {!['custom', 'monthly_days_times'].includes(form.schedule_type) && (
                <label className="flex items-center gap-1.5 text-[11px] text-ink">
                  <input type="checkbox" checked={form.somenteDiasUteis}
                    onChange={e => set({ somenteDiasUteis: e.target.checked })} />
                  Somente dias úteis
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Calendário (opcional)</span>
                <select value={form.calendarioNome}
                  onChange={e => set({ calendarioNome: e.target.value })}
                  className={inputCls}>
                  <option value="">— nenhum —</option>
                  {calendarios.map(c => (
                    <option key={c.calendario_nome} value={c.calendario_nome}>
                      {c.calendario_nome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Hora de virada (ODATE) — a régua de data da malha</span>
                <input type="time" value={form.horaVirada}
                  onChange={e => set({ horaVirada: e.target.value })}
                  className={`${inputCls} w-28`} />
              </label>
            </div>

            <p className="text-[11px] text-dim">
              {raizes === 0
                ? 'O Início ainda não está ligado a nenhum pipeline — o agendamento fica guardado na malha e nada é alterado nos pipelines.'
                : `Ao confirmar, ${raizes === 1 ? '1 raiz ligada recebe' : `${raizes} raízes ligadas recebem`} este agendamento — o efeito é mostrado antes de gravar.`}
            </p>
            <p className="text-[11px] text-dim">
              A <strong>hora de virada</strong> vale para a malha inteira, não
              só para as raízes: é ela que decide a data de referência de quem
              dispara por agenda. Ao salvar, todos os membros fora dessa régua
              são alinhados e passam a pedir republicação.
            </p>

            {/* F3 da spec-malha-data-unica: a marca do "não pare para
                perguntar". Sem ela, data divergente barra o disparo. */}
            <label className="flex items-start gap-2 rounded-md border border-edge bg-canvas px-3 py-2">
              <input
                type="checkbox"
                checked={equalizarLocal}
                onChange={e => setEqualizarLocal(e.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#1A5FA8]"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-ink">
                  Equalizar a data automaticamente
                </span>
                <span className="text-[11px] text-dim">
                  Se, na hora de começar, algum membro estiver com data de
                  referência diferente, a malha carimba todos com a data dela e
                  segue — sem parar para o operador avaliar. A mudança fica
                  registrada no histórico. Desmarcado, o disparo é bloqueado com
                  a lista de quem está fora.
                </span>
              </span>
            </label>

            {/* F7 (Decisão 61) — o LIMITE DE SEGURANÇA da malha. Ele mora
                aqui, ao lado da hora de virada, porque os dois são relógios da
                MALHA (e não do pipeline). O texto diz o que ele NÃO é: teto não
                é SLA, é anti-travamento — o que ele evita é a corrida travada
                bloquear o disparo para sempre, e por isso ele nunca encerra
                trabalho vivo. */}
            {temTeto && (
              <div className="flex flex-col gap-1 rounded-md border border-edge bg-canvas px-3 py-2">
                <label className={labelCls} htmlFor="malha-teto-horas">
                  Limite de segurança da corrida (horas)
                </label>
                <input
                  id="malha-teto-horas"
                  type="number" min={1} max={168} step={1}
                  value={tetoLocal}
                  placeholder="segue o limite global (24h)"
                  onChange={e => setTetoLocal(e.target.value)}
                  className={`${inputCls} w-56`}
                />
                <span className="text-[11px] text-dim">
                  Passado esse tempo <strong>sem nenhum pipeline em execução</strong>,
                  o ciclo é encerrado e o disparo volta a funcionar. Com
                  pipeline rodando, o limite só <strong>avisa</strong> — ele
                  nunca encerra trabalho vivo. O tempo em que a malha ficar
                  segurada é devolvido ao limite. Em branco, vale o limite
                  global. Preencher aqui também faz a barra de limite aparecer
                  no painel desta malha.
                </span>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={onClose}>Cancelar</Button>
              <Button onClick={() => void verEfeito()} loading={carregando}>
                <CalendarClock size={13} /> Ver efeito e salvar
              </Button>
            </div>
          </>
        ) : (
          <>
            {/* Fase de confirmação — o efeito §7.2, dito antes de gravar. */}
            {preview.erros.map((e, i) => (
              <div key={i}
                className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{e}</span>
              </div>
            ))}
            {preview.erros.length > 0 && (
              <p className="text-[11px] text-dim">
                O gesto está bloqueado — nada foi gravado na malha nem nos
                pipelines.
              </p>
            )}
            {preview.erros.length === 0 && (
              <div className="flex max-h-[46vh] flex-col gap-2 overflow-y-auto">
                {preview.efeito.agendamentos.length === 0 ? (
                  <p className="text-[12px] text-dim">
                    Nenhuma raiz muda de agendamento — o JSON da malha é salvo
                    (raízes já compiladas ou nenhuma ligada ao Início).
                  </p>
                ) : (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Agendamentos aplicados às raízes
                    </p>
                    {preview.efeito.agendamentos.map(a => (
                      <div key={a.pipeline}
                        className="flex items-start gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <CalendarClock size={12} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                        <span className="min-w-0 text-xs text-ink">
                          <span className="font-mono">{a.pipeline}</span>
                          <span className="block text-[10px] text-dim">
                            {a.de} <span className="mx-0.5">→</span> {a.para}
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {preview.efeito.republicar.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                    <strong>Republicação necessária:</strong>{' '}
                    {preview.efeito.republicar.join(', ')} — depois de
                    confirmar, publique nova versão (Pipelines ▸ Publicar nova
                    versão).
                  </div>
                )}
                {preview.avisos.length > 0 && (
                  <div className="flex flex-col gap-0.5">
                    {preview.avisos.map((a, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                        {a.nivel === 'forte'
                          ? <AlertTriangle size={12} className="shrink-0" />
                          : <Info size={12} className="shrink-0" />}
                        <span>{a.mensagem}</span>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-dim">
                  O servidor recalcula o efeito ao confirmar — se algo mudou
                  nesse meio tempo, o resultado real é reportado no aviso.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={() => setPreview(null)}
                disabled={aplicando}>
                {preview.erros.length > 0 ? 'Voltar' : 'Ajustar'}
              </Button>
              {preview.erros.length === 0 && (
                <Button onClick={() => void confirmar()} loading={aplicando}>
                  <CalendarClock size={13} /> Salvar agendamento
                </Button>
              )}
          </div>
        </>
      )}
    </div>
  )
}
