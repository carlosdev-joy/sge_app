// Helpers de tempo do DataStage (formato "Mon Jun 22 14:33:26 2026").
// Compartilhado entre o console (Admin) e o diagrama do run.

const MONTHS: Record<string, number> = {
  Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
  Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11,
}

export function dsParseTime(s?: string): Date | null {
  if (!s) return null
  const m = s.match(/\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})/)
  if (!m || MONTHS[m[1]] == null) return null
  return new Date(Number(m[6]), MONTHS[m[1]], Number(m[2]), Number(m[3]), Number(m[4]), Number(m[5]))
}

const hm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

export function dsFmtDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(s / 3600), mi = Math.floor((s % 3600) / 60), se = s % 60
  if (h) return `${h}h${String(mi).padStart(2, '0')}m`
  if (mi) return `${mi}m${String(se).padStart(2, '0')}s`
  return `${se}s`
}

// "14:33 → 17:12 · 2h38m" (ou "início 17:40" se ainda rodando).
export function dsTimeInfo(start?: string, end?: string): string | undefined {
  const s = dsParseTime(start), e = dsParseTime(end)
  if (s && e) return `${hm(s)} → ${hm(e)} · ${dsFmtDuration(e.getTime() - s.getTime())}`
  if (s) return `início ${hm(s)}`
  return undefined
}
