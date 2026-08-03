// Próxima execução do agendamento da MALHA (F15 — desenho §8, linha do
// Início): helper DISPLAY-ONLY, mesmo estatuto do calcularDataRef da F5 — a
// AUTORIDADE do gatilho é o scheduler do Airflow; este texto é orientação de
// leitura no modo Execução, nunca promessa. Módulo puro (sem React, sem
// fetch): o agendamento chega do payload do detalhe (etl_malha.
// agendamento_json, schema §4.1 = subconjunto do register).
//
// Honestidade nos limites (a regra F9 de nunca inventar):
//   • agendamento ausente/ilegível → null (o card não mostra a linha);
//   • somente_dias_uteis → o helper PULA sáb/dom (a mesma regra que o motor
//     julga), mas calendário de feriados é do servidor — quando há
//     calendario_nome o texto ganha o sufixo "(sujeito ao calendário)";
//   • hourly → texto de cadência ("a cada hora no minuto MM"), sem fingir
//     um instante exato.

interface Agendamento {
  schedule_type?: unknown
  schedule_hour?: unknown
  schedule_minute?: unknown
  schedule_dow?: unknown
  schedule_dom?: unknown
  horarios_especificos?: unknown
  dias_semana?: unknown
  dias_horarios_mes?: unknown
  somente_dias_uteis?: unknown
  calendario_nome?: unknown
}

// Convenção cron da casa (D05): 0 = domingo — igual ao getDay() do JS.
const DOW_NOMES = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb']

function int(v: unknown, def: number): number {
  const n = typeof v === 'number' ? v : parseInt(String(v ?? ''), 10)
  return Number.isFinite(n) ? n : def
}

function hm(h: number, m: number): string {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

// 'HH:MM,HH:MM' → lista válida ordenada (entrada ilegível é descartada).
function parseHorarios(raw: unknown): string[] {
  return String(raw ?? '')
    .split(',')
    .map(s => s.trim())
    .filter(s => /^\d{1,2}:\d{2}$/.test(s))
    .map(s => hm(int(s.split(':')[0], 0), int(s.split(':')[1], 0)))
    .sort()
}

// Horários aplicáveis num dia de CALENDÁRIO, pelo schedule_type (ordenados).
function horariosDoDia(ag: Agendamento, d: Date): string[] {
  const st = String(ag.schedule_type ?? '').trim().toLowerCase()
  const hora = hm(int(ag.schedule_hour, 6), int(ag.schedule_minute, 0))
  const dow = int(ag.schedule_dow, 1)
  const dom = int(ag.schedule_dom, 1)
  switch (st) {
    case 'daily':
      return [hora]
    case 'weekly':
      return d.getDay() === dow ? [hora] : []
    case 'monthly':
      return d.getDate() === dom ? [hora] : []
    case 'biweekly':
      return (d.getDate() === dom || d.getDate() === dom + 15) ? [hora] : []
    case 'custom': {
      const dias = String(ag.dias_semana ?? '')
        .split(',').map(s => s.trim()).filter(Boolean).map(Number)
      if (dias.length > 0 && !dias.includes(d.getDay())) return []
      return parseHorarios(ag.horarios_especificos)
    }
    case 'monthly_days_times': {
      try {
        const entradas = JSON.parse(String(ag.dias_horarios_mes ?? '[]')) as
          { dia?: unknown; horarios?: unknown }[]
        const doDia = entradas.filter(e => int(e.dia, -1) === d.getDate())
        return doDia
          .flatMap(e => (Array.isArray(e.horarios) ? e.horarios : []))
          .filter((s): s is string => typeof s === 'string'
            && /^\d{1,2}:\d{2}$/.test(s))
          .sort()
      } catch {
        return []
      }
    }
    default:
      return []
  }
}

// Rótulo relativo do dia: hoje / amanhã / "sex 08/08".
function rotuloDia(d: Date, agora: Date): string {
  const mesmoDia = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
  if (mesmoDia(d, agora)) return 'hoje'
  const amanha = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + 1)
  if (mesmoDia(d, amanha)) return 'amanhã'
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${DOW_NOMES[d.getDay()]} ${dd}/${mm}`
}

// Texto da próxima execução do agendamento, ou null quando não dá para dizer
// com honestidade (sem agendamento, on_demand, tipo desconhecido, nada num
// horizonte de 62 dias — cobre o mensal de dia 28 com folga).
export function proximaExecucaoTexto(
  ag: Record<string, unknown> | null | undefined,
  agora: Date = new Date(),
): string | null {
  if (!ag || typeof ag !== 'object') return null
  const a = ag as Agendamento
  const st = String(a.schedule_type ?? '').trim().toLowerCase()
  if (!st || st === 'on_demand') return null
  const sufixo = a.calendario_nome ? ' (sujeito ao calendário)' : ''
  if (st === 'hourly') {
    return `a cada hora no minuto ${String(int(a.schedule_minute, 0)).padStart(2, '0')}${sufixo}`
  }
  const soUteis = a.somente_dias_uteis === 1 || a.somente_dias_uteis === true
  const agoraHm = hm(agora.getHours(), agora.getMinutes())
  for (let i = 0; i <= 62; i++) {
    const d = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + i)
    if (soUteis && (d.getDay() === 0 || d.getDay() === 6)) continue
    for (const h of horariosDoDia(a, d)) {
      // No próprio dia, só horário ainda por vir (comparação lexicográfica
      // de 'HH:MM' zero-padded é a ordem do relógio).
      if (i === 0 && h <= agoraHm) continue
      return `${rotuloDia(d, agora)} ${h}${sufixo}`
    }
  }
  return null
}
