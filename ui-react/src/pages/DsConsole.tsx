import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { toast } from '../components/ui/Toast'
import { Tabs } from '../components/ui/Tabs'
import { DsRunGraphModal, type DsGraphStatus, type DsGraphNode, type DsRunGraph } from '../components/console/DsRunGraphModal'
import { dsTimeInfo, dsParseTime } from '../lib/dsTime'
import { Terminal, Copy, Network, Crosshair, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'

// Lista de projetos usada apenas como fallback se a API não retornar projetos.
const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

// ── Console DataStage (dsjob via SSH, somente leitura) ──────────────────────
interface DsCmd { id: string; label: string; needs_job: boolean }
interface DsConsoleResult {
  command: string; project: string; job: string | null
  exit_code: number; stdout: string; stderr: string; duration_ms: number
}

// Colorização estilo terminal (fundo fixo escuro — exceção da seção 4 de docs/ui-temas-cores.md).
function dsColorize(text: string) {
  return text.split('\n').map((line, i) => {
    const cls = /ERROR|EXCEPTION|CRITICAL|FATAL|ABORT|FAIL/i.test(line) ? 'text-red-400'
      : /WARNING|WARN/i.test(line) ? 'text-amber-400'
      : /\bOK\b|SUCCESS|FINISHED/i.test(line) ? 'text-green-400'
      : /INFO/i.test(line) ? 'text-blue-300'
      : 'text-gray-300'
    return <div key={i} className={cls}>{line || ' '}</div>
  })
}

// Mapeia o texto do "Job Status" do -jobinfo para uma variante de Badge.
function dsStatusVariant(v: string): string {
  if (/ABORT|FAIL|CRASH|STOPPED/i.test(v)) return 'error'
  if (/WARNING/i.test(v)) return 'warning'
  if (/RUNNING/i.test(v)) return 'info'
  if (/\bOK\b|FINISHED|RESET|VALIDATED/i.test(v)) return 'success'
  return 'neutral'
}

// De-para: código de status do job (dsjob -jobinfo "… (N)") → nome claro p/ o usuário.
const DS_STATUS_MEANINGS: Record<number, string> = {
  0: 'Em execução',
  1: 'Concluído com sucesso',
  2: 'Concluído com avisos',
  3: 'Abortado (falhou)',
  11: 'Validado com sucesso',
  12: 'Validado com avisos',
  13: 'Validação falhou',
  21: 'Resetado',
  96: 'Crash (falha grave)',
  97: 'Parado pelo operador',
  98: 'Não compilado / não executável',
  99: 'Nunca executado',
}

// De-para: código de retorno do dsjob ("Status code = -N") → explicação.
const DSJOB_CODE_MEANINGS: Record<number, string> = {
  [-1]: 'Handle de job inválido',
  [-2]: 'Job em estado inválido para a operação (ex.: não compilado ou em execução)',
  [-3]: 'Parâmetro inválido',
  [-7]: 'Stage desconhecido no job',
  [-9]: 'Link desconhecido no job',
  [-10]: 'Job bloqueado por outro processo',
  [-11]: 'Job foi excluído',
  [-12]: 'Nome de projeto inválido',
  [-14]: 'Tempo esgotado (timeout)',
  [-1001]: 'Fim da lista (não há mais itens)',
  [-1002]: 'Projeto não encontrado / não foi possível abrir',
  [-1003]: 'DataStage/engine indisponível',
  [-1004]: 'Job não encontrado no projeto (falha ao abrir)',
  [-1005]: 'Memória insuficiente no servidor',
  [-9999]: 'Erro do dsjob (comando ou sintaxe inválida)',
}

// Extrai o inteiro entre parênteses do "Job Status" (código de status).
function dsStatusCode(v: string): number | null {
  const m = v.match(/\((-?\d+)\)/)
  return m ? Number(m[1]) : null
}

// Variante de Badge a partir do código numérico de status do job.
function dsCodeVariant(code: number): string {
  if (code === 1 || code === 11) return 'success'
  if (code === 2 || code === 12) return 'warning'
  if (code === 21) return 'info'
  if (code === 3 || code === 13 || code === 96 || code === 97 || code === 98) return 'error'
  return 'neutral'
}

// Código numérico de status do job -> status do diagrama.
function dsCodeToStatus(code: number): DsGraphStatus {
  if (code === 1 || code === 11) return 'ok'
  if (code === 2 || code === 12) return 'warning'
  if (code === 21) return 'reset'
  if (code === 3 || code === 13 || code === 96 || code === 97 || code === 98) return 'aborted'
  return 'unknown'
}


interface DsChild { job: string; fullJob: string; code: number | null; text: string; start?: string; end?: string }
interface DsLogRun {
  start?: string
  end?: string
  result: 'ok' | 'aborted' | 'running' | 'unknown'
  firstId?: number
  lastId?: number
  // code: null = disparado mas ainda não terminou (em execução / aguardando).
  children: DsChild[]
}

// Parser do `dsjob -logsum`: agrupa o log em runs da sequence com TODOS os jobs
// filhos (disparados, aguardando e terminados) e seus status. Os que foram
// disparados mas não terminaram ficam com code=null (em execução). Best-effort.
function parseLogsum(stdout: string): DsLogRun[] {
  const runs: DsLogRun[] = []
  let cur: DsLogRun | null = null
  let map: Map<string, DsChild> | null = null
  let time = ''
  let id = 0
  const ensure = (full: string) => {
    if (map && !map.has(full)) map.set(full, { job: full.replace(/^SeqExecJob\./, ''), fullJob: full, code: null, text: 'Em execução', start: time })
  }
  const flush = () => { if (cur && map) { cur.children = [...map.values()]; runs.push(cur) } }
  for (const raw of stdout.split('\n')) {
    const header = raw.match(/^\s*(\d+)\s+[A-Z]+\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+[\d:]+\s+\d{4})\s*$/)
    if (header) { id = Number(header[1]); time = header[2]; continue }
    const msg = raw.trim()
    if (!msg) continue
    if (/^Starting Job\s/.test(msg)) {
      flush()
      cur = { start: time, result: 'running', children: [], firstId: id, lastId: id }
      map = new Map()
      continue
    }
    if (!cur || !map) continue
    cur.lastId = id
    if (/^Finished Job\s/.test(msg)) { cur.result = 'ok'; cur.end = time; continue }
    if (/sequence abort requested|aborted due to|fatal error from @/i.test(msg)) { cur.result = 'aborted'; cur.end = time; continue }
    // filho terminou com status
    const fin = msg.match(/Job\s+(\S+)\s+has finished, status = (\d+)\s*\(([^)]*)\)/)
    if (fin) {
      const ex = map.get(fin[1])
      map.set(fin[1], { job: fin[1].replace(/^SeqExecJob\./, ''), fullJob: fin[1], code: Number(fin[2]), text: fin[3], start: ex?.start, end: time })
      continue
    }
    // filho disparado:  SeqX -> (JobName): Job run/reset requested
    const req = msg.match(/->\s*\(([A-Za-z0-9_.]+)\):\s*Job (?:run|reset) requested/i)
    if (req) { ensure(req[1]); continue }
    // aguardando job iniciar
    const ws = msg.match(/Waiting for job\s+([A-Za-z0-9_.]+)\s+to start/i)
    if (ws) { ensure(ws[1]); continue }
    // aguardando A+B+C terminar (quando a linha não vem truncada)
    const wf = msg.match(/Waiting for job\s+(.+?)\s+to finish/i)
    if (wf) { for (const j of wf[1].split('+')) { const jn = j.trim(); if (/^[A-Za-z0-9_.]+$/.test(jn)) ensure(jn) } continue }
    if (/Job under control finished/.test(msg)) {
      if (!cur.end) cur.end = time
      flush(); cur = null; map = null
    }
  }
  flush()
  return runs
}

// Lista as entradas do log (id, tipo, hora, mensagem) — usado para destacar erros
// e oferecer o id de evento ao logdetail.
function parseLogEntries(stdout: string): { id: number; type: string; time: string; message: string }[] {
  const lines = stdout.split('\n')
  const headerRe = /^\s*(\d+)\s+([A-Z]+)\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+[\d:]+\s+\d{4})\s*$/
  const entries: { id: number; type: string; time: string; message: string }[] = []
  for (let i = 0; i < lines.length; i++) {
    const h = lines[i].match(headerRe)
    if (!h) continue
    const msg: string[] = []
    for (let j = i + 1; j < lines.length && !headerRe.test(lines[j]); j++) {
      if (lines[j].trim()) msg.push(lines[j].trim())
    }
    entries.push({ id: Number(h[1]), type: h[2], time: h[3], message: msg.join(' ') })
  }
  return entries
}

// Mapeia activity da sequence (@ODS_Propostas_U) -> job real (SeqSsdPrs_ODS_Propostas),
// lendo as linhas "(@activity): Report on job: <job>" e "(@activity): Job <job> ..." do log.
// Permite resolver o job filho mesmo quando o erro só cita a activity.
function buildActivityJobMap(entries: { message: string }[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const e of entries) {
    const r1 = e.message.match(/\(@([A-Za-z0-9_.]+)\):\s*Report on job:\s*([A-Za-z0-9_.]+)/i)
    if (r1) map[r1[1]] = r1[2]
    const r2 = e.message.match(/\(@([A-Za-z0-9_.]+)\):\s*Job\s+([A-Za-z0-9_.]+)\s+(?:has finished|did not finish)/i)
    if (r2) map[r2[1]] = r2[2]
  }
  return map
}

// Mensagens que indicam erro mesmo quando o Type é INFO (activity de erro, abort de filho).
const DS_ERR_MSG_RE = /will execute error activity|erro no job|status = 3 \(|status = '?(aborted|crashed)|did not finish OK/i

// Severidade de uma entrada de log combinando Type + mensagem.
function dsEntrySeverity(type: string, message: string): string {
  if (/FATAL|REJECT/i.test(type)) return 'error'
  if (/WARNING/i.test(type)) return 'warning'
  if (DS_ERR_MSG_RE.test(message)) return 'warning'
  return 'info'
}

// Variante de Badge a partir do "Type" de uma entrada de log (FATAL/WARNING/INFO…).
function dsTypeVariant(t?: string): string {
  if (!t) return 'neutral'
  if (/FATAL|REJECT|ABORT/i.test(t)) return 'error'
  if (/WARN/i.test(t)) return 'warning'
  if (/INFO|STARTED|BATCH|RESET/i.test(t)) return 'info'
  return 'neutral'
}

interface DsLogDetail {
  eventId?: string; time?: string; type?: string
  user?: string; messageId?: string; invocationId?: string
  message: string
}

// Parser do `dsjob -logdetail -full`: campos (Event Id/Time/Type/User/Message Id/
// Invocation Id) + corpo de Message (multilinha). Suporta vários eventos.
function parseLogdetail(stdout: string): DsLogDetail[] {
  const keyRe = /^\s*(Event Id|Time|Type|User|Message Id|Invocation Id|Message)\s*:\s?(.*)$/
  const events: DsLogDetail[] = []
  let cur: DsLogDetail | null = null
  let inMessage = false
  let msg: string[] = []
  const flush = () => { if (cur) { cur.message = msg.join('\n').trim(); events.push(cur) } }
  for (const raw of stdout.split('\n')) {
    const m = raw.match(keyRe)
    if (m) {
      const key = m[1], val = m[2]
      if (key === 'Event Id') { flush(); cur = { message: '' }; msg = []; inMessage = false; cur.eventId = val.trim(); continue }
      if (!cur) continue
      if (key === 'Time') cur.time = val.trim()
      else if (key === 'Type') cur.type = val.trim()
      else if (key === 'User') cur.user = val.trim()
      else if (key === 'Message Id') cur.messageId = val.trim()
      else if (key === 'Invocation Id') cur.invocationId = val.trim()
      else if (key === 'Message') { inMessage = true; if (val.trim()) msg.push(val.trim()) }
      if (key !== 'Message') inMessage = false
      continue
    }
    if (cur && inMessage) msg.push(raw.replace(/^\s{0,4}/, ''))
  }
  flush()
  return events
}

// Monta os runs do diagrama a partir do stdout do logsum (função pura, reusável
// pelo auto-trace). Junta filhos diretos + jobs vindos de activity de erro.
function buildGraphRuns(stdout: string, rootJob: string): DsRunGraph[] {
  const runs = parseLogsum(stdout)
  const entries = parseLogEntries(stdout)
  const activityMap = buildActivityJobMap(entries)
  const errors = entries.filter(e => /FATAL|REJECT|WARNING/i.test(e.type) || DS_ERR_MSG_RE.test(e.message))
  return runs.map(r => {
    const m = new Map<string, DsGraphNode>()
    for (const c of r.children) m.set(c.fullJob, { job: c.fullJob, status: c.code != null ? dsCodeToStatus(c.code) : 'running', label: c.text, time: dsTimeInfo(c.start, c.end), start: c.start, end: c.end })
    for (const e of errors) {
      if (r.firstId == null || r.lastId == null || e.id < r.firstId || e.id > r.lastId) continue
      const explicit = (e.message.match(/\bJob\s+([A-Za-z0-9_.]+)\s+(?:has finished, status|did not finish OK)/i) || [])[1]
      const act = (e.message.match(/\(@([A-Za-z0-9_.]+)\)/) || [])[1]
      const job = explicit || (act ? activityMap[act] : undefined)
      if (!job || job === rootJob) continue
      const cur = m.get(job)
      if (!cur || cur.status === 'ok' || cur.status === 'unknown') {
        m.set(job, { job, status: 'aborted', label: /did not finish OK|status = 3/i.test(e.message) ? 'Abortado' : 'Erro' })
      }
    }
    return { result: r.result, start: r.start, end: r.end, children: [...m.values()] }
  })
}

// Índice do run: contém o targetTime; senão (preferAborted) o abortado mais
// recente; senão o último.
function pickRunIndex(runs: DsRunGraph[], targetTime: string | null | undefined, preferAborted: boolean): number {
  const t = targetTime ? dsParseTime(targetTime)?.getTime() : null
  if (t != null) {
    let best = -1, bestDelta = Infinity, contained = false
    runs.forEach((r, i) => {
      const s = dsParseTime(r.start)?.getTime(); if (s == null) return
      const e = dsParseTime(r.end)?.getTime()
      if (s <= t && (e == null || t <= e)) { if (!contained) { contained = true; best = i } }
      else if (!contained) { const d = Math.abs(s - t); if (d < bestDelta) { bestDelta = d; best = i } }
    })
    if (best >= 0) return best
  }
  if (preferAborted) for (let i = runs.length - 1; i >= 0; i--) if (runs[i].result === 'aborted') return i
  return runs.length - 1
}

export default function DsConsole() {
  const cfg = useQuery<{ configured: boolean; commands: DsCmd[] }>({
    queryKey: ['ds-console-config'],
    queryFn: () => apiFetch('/datastage/console/config'),
  })
  const projetos = useQuery<{ projects: { project_name: string; ativo?: boolean | number }[] }>({
    queryKey: ['admin-projects-all'],
    queryFn: () => apiFetch('/pipelines/projects/all'),
  })

  // Aba ativa (cada aba = um comando dsjob; "geral" = jobinfo + logsum juntos).
  const [activeTab, setActiveTab] = useState('geral')

  // Inputs compartilhados entre abas (projeto + job) — persistem ao trocar de aba.
  const [project, setProject] = useState('')
  const [job, setJob] = useState('')
  const [maxLines, setMaxLines] = useState('200')
  const [eventId, setEventId] = useState('')
  const [showCodes, setShowCodes] = useState(false)
  const [showGraph, setShowGraph] = useState(false)
  const [graphTargetTime, setGraphTargetTime] = useState<string | null>(null)
  const [graphPath, setGraphPath] = useState<{ job: string; targetTime: string | null }[]>([])
  const [tracing, setTracing] = useState(false)
  // Grupos de erro expandidos no card "Erros e avisos por run" (índice do grupo).
  const [openErrGroups, setOpenErrGroups] = useState<Set<number>>(new Set([0]))

  const configured = cfg.data?.configured ?? false

  // Autocomplete do campo Job: roda `ljobs` do projeto selecionado (best-effort, cacheado).
  const jobsQuery = useQuery<DsConsoleResult>({
    queryKey: ['ds-ljobs', project],
    queryFn: () => apiFetch<DsConsoleResult>('/datastage/console', {
      method: 'POST',
      body: JSON.stringify({ command: 'ljobs', project: project.trim() }),
    }),
    enabled: configured && !!project.trim(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
  const jobOptions = (jobsQuery.data?.exit_code === 0)
    ? jobsQuery.data.stdout.split('\n').map(s => s.trim()).filter(Boolean)
    : []

  // Mutation de comando único (usado pelas abas que não são "Visão geral" e pelos
  // drills/cliques que substituem o resultado em foco).
  const exec = useMutation<DsConsoleResult, Error, { command: string; project: string; job?: string; max_lines?: number; event_id?: number }>({
    mutationFn: (vars) => apiFetch<DsConsoleResult>('/datastage/console', {
      method: 'POST',
      body: JSON.stringify(vars),
    }),
    onError: (e: any) => toast.error(e.message),
  })

  // Resultado do jobinfo na "Visão geral" (mantido separado do logsum para exibir os dois juntos).
  // O logsum cai no `exec.data` (alimenta diagrama, erros, resumo de runs); o jobinfo fica aqui.
  const [overviewJobinfo, setOverviewJobinfo] = useState<DsConsoleResult | null>(null)
  const overviewExec = useMutation<DsConsoleResult, Error, { project: string; job: string }>({
    mutationFn: (vars) => apiFetch<DsConsoleResult>('/datastage/console', {
      method: 'POST',
      body: JSON.stringify({ command: 'jobinfo', project: vars.project, job: vars.job }),
    }),
    onSuccess: (jobinfo, vars) => {
      setOverviewJobinfo(jobinfo)
      // dispara o logsum em sequência — ele vira o "result" em foco.
      exec.mutate({ command: 'logsum', project: vars.project, job: vars.job, max_lines: Number(maxLines) || 200 })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const isLogdetail = activeTab === 'logdetail'
  // "Visão geral" roda logsum por baixo, então oferece o controle de máx. linhas.
  const hasMax = activeTab === 'geral'
  // Cada aba mapeia para um comando dsjob (a "Visão geral" combina jobinfo + logsum).
  const tabNeedsJob = activeTab !== 'ljobs'
  const tabCommand: Record<string, string> = {
    logdetail: 'logdetail', lstages: 'lstages', lparams: 'lparams', report: 'report', ljobs: 'ljobs',
  }

  const busy = exec.isPending || overviewExec.isPending
  const canRun = !!project.trim() && (!tabNeedsJob || !!job.trim())
    && (!isLogdetail || !!eventId.trim()) && configured && !busy

  // Executa o comando da aba atual.
  const run = () => {
    if (!canRun) return
    if (activeTab === 'geral') {
      overviewExec.mutate({ project: project.trim(), job: job.trim() })
      return
    }
    const command = tabCommand[activeTab] ?? 'jobinfo'
    exec.mutate({
      command,
      project: project.trim(),
      job: tabNeedsJob ? job.trim() : undefined,
      max_lines: command === 'logsum' ? (Number(maxLines) || 200) : undefined,
      event_id: command === 'logdetail' ? (Number(eventId) || undefined) : undefined,
    })
  }

  // Roda um comando específico imediatamente (cliques nos chips de job / filhos / eventos).
  const runFor = (cmd: string, jobName: string, extra?: { max_lines?: number; event_id?: number }) => {
    if (!project.trim() || !configured) return
    setJob(jobName)
    if (extra?.event_id != null) setEventId(String(extra.event_id))
    exec.mutate({ command: cmd, project: project.trim(), job: jobName, ...extra })
  }

  // Auto-trace ("Causa-raiz"): a partir de initialPath, desce sozinho pela cadeia
  // de jobs abortados (1 logsum por nível) até o job folha, montando o breadcrumb.
  const autoTrace = async (initialPath: { job: string; targetTime: string | null }[]) => {
    if (!project.trim() || !configured || initialPath.length === 0 || tracing) return
    setTracing(true); setShowGraph(true)
    const path = [...initialPath]
    let { job: cjob, targetTime: ctt } = path[path.length - 1]
    setGraphPath([...path]); setGraphTargetTime(ctt)
    try {
      for (let depth = 0; depth < 12; depth++) {
        setJob(cjob)
        const res = await exec.mutateAsync({ command: 'logsum', project: project.trim(), job: cjob, max_lines: 200 })
        if (res.exit_code !== 0) break
        const runs = buildGraphRuns(res.stdout, cjob)
        const run = runs[pickRunIndex(runs, ctt, true)]
        // fixa o run analisado neste nível para o diagrama mostrá-lo
        if (run?.start) { path[path.length - 1] = { job: cjob, targetTime: run.start }; ctt = run.start }
        setGraphPath([...path]); setGraphTargetTime(path[path.length - 1].targetTime)
        const ab = run?.children.find(c => c.status === 'aborted')
        if (!ab) { toast.info(`Causa-raiz: ${cjob} — veja o erro no card "Erros e avisos"`); break }
        cjob = ab.job; ctt = ab.start ?? null
        path.push({ job: cjob, targetTime: ctt })
        setGraphPath([...path]); setGraphTargetTime(ctt)
      }
    } catch { /* erro já notificado pela mutation */ }
    finally { setTracing(false) }
  }

  const projectList = (projetos.data?.projects ?? []).map(p => p.project_name)
  const projectOptions = projectList.length ? projectList : PROJETOS

  const result = exec.data
  // Na "Visão geral", o jobinfo vem do estado próprio; nas outras abas, do result em foco.
  const jobinfoResult = activeTab === 'geral' ? overviewJobinfo : (result?.command === 'jobinfo' ? result : null)
  const isJobinfo = jobinfoResult?.exit_code === 0
  const jobinfoFields = (isJobinfo && jobinfoResult
    ? jobinfoResult.stdout.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
        const i = l.indexOf(':')
        return i === -1 ? null : { label: l.slice(0, i).trim(), value: l.slice(i + 1).trim() }
      })
    : []
  ).filter((e): e is { label: string; value: string } => !!e && !!e.label)
  const statusField = jobinfoFields.find(f => /^Job Status/i.test(f.label))
  const statusCode = statusField ? dsStatusCode(statusField.value) : null
  const statusMeaning = statusCode != null ? DS_STATUS_MEANINGS[statusCode] : undefined

  const ljobsList = (result?.command === 'ljobs' && result.exit_code === 0)
    ? result.stdout.split('\n').map(s => s.trim()).filter(Boolean)
    : []

  const logsumRuns = (result?.command === 'logsum' && result.exit_code === 0)
    ? parseLogsum(result.stdout)
    : []
  const logAllEntries = (result?.command === 'logsum' && result.exit_code === 0)
    ? parseLogEntries(result.stdout)
    : []
  const activityJobMap = buildActivityJobMap(logAllEntries)
  const logErrors = logAllEntries.filter(e => /FATAL|REJECT|WARNING/i.test(e.type) || DS_ERR_MSG_RE.test(e.message))
  const logDetailEvents = (result?.command === 'logdetail' && result.exit_code === 0)
    ? parseLogdetail(result.stdout)
    : []

  // Agrupa os erros por run (via faixa de event id de cada run) para não misturar dias.
  const errorsByRun = logsumRuns
    .map(r => ({ run: r, errors: logErrors.filter(e => r.firstId != null && r.lastId != null && e.id >= r.firstId && e.id <= r.lastId) }))
    .filter(g => g.errors.length > 0)
  const groupedErrIds = new Set(errorsByRun.flatMap(g => g.errors.map(e => e.id)))
  const ungroupedErrors = logErrors.filter(e => !groupedErrIds.has(e.id))

  // Diagrama (CTRL-M): runs montados a partir do logsum (função pura reusável).
  const graphRuns: DsRunGraph[] = (result?.command === 'logsum' && result.exit_code === 0 && result.job)
    ? buildGraphRuns(result.stdout, result.job) : []
  const hasGraph = graphRuns.some(r => r.children.length > 0)

  // Snapshot do diagrama: mantém o último logsum válido para o modal não desmontar
  // durante o drill (enquanto exec.isPending zera o result). Atualiza só em sucesso.
  const graphRunsRef = useRef(graphRuns)
  graphRunsRef.current = graphRuns
  const [graphData, setGraphData] = useState<{ rootJob: string; runs: DsRunGraph[] } | null>(null)
  useEffect(() => {
    if (result?.command === 'logsum' && result.exit_code === 0 && result.job) {
      setGraphData({ rootJob: result.job, runs: graphRunsRef.current })
    }
  }, [result])

  // Sempre que chega um novo logsum, reabre o grupo de erros mais recente.
  useEffect(() => {
    if (result?.command === 'logsum') setOpenErrGroups(new Set([0]))
  }, [result])

  // De-para do código de erro do dsjob ("Status code = -N") quando o comando falha.
  const errMatch = (result && result.exit_code !== 0)
    ? ((result.stderr || '') + '\n' + (result.stdout || '')).match(/Status code\s*=\s*(-?\d+)/i)
    : null
  const errorCode = errMatch ? Number(errMatch[1]) : null
  const errorMeaning = errorCode != null ? DSJOB_CODE_MEANINGS[errorCode] : undefined

  const copy = (t: string) => navigator.clipboard?.writeText(t).then(
    () => toast.info('Copiado!'), () => toast.error('Erro ao copiar'))

  const toggleErrGroup = (gi: number) => setOpenErrGroups(prev => {
    const s = new Set(prev)
    s.has(gi) ? s.delete(gi) : s.add(gi)
    return s
  })

  // Uma linha do card de erros (id clicável → logdetail; nome do filho → logsum dele).
  const renderErrRow = (e: { id: number; type: string; time: string; message: string }) => {
    const explicitChild = (e.message.match(/\bJob\s+([A-Za-z0-9_.]+)\s+(?:has finished, status|did not finish OK)/i) || [])[1]
    const activity = (e.message.match(/\(@([A-Za-z0-9_.]+)\)/) || [])[1]
    const child = explicitChild || (activity ? activityJobMap[activity] : undefined)
    return (
      <div key={e.id} className="flex items-start gap-2 text-xs flex-wrap">
        <Badge value={dsEntrySeverity(e.type, e.message)}>{e.type}</Badge>
        <button onClick={() => runFor('logdetail', result?.job ?? '', { event_id: e.id })}
          title="Ver detalhe completo deste evento (logdetail)"
          className="font-mono text-blue-700 dark:text-blue-400 hover:underline shrink-0">#{e.id}</button>
        <span className="text-dim shrink-0 hidden sm:inline">{e.time}</span>
        <span className="text-ink break-all">{e.message.slice(0, 240)}</span>
        {child && child !== result?.job && (
          <button onClick={() => runFor('logsum', child)}
            title={`Abrir o log de ${child} (logsum) — drill-down até o erro real`}
            className="inline-flex items-center gap-0.5 font-mono text-[11px] px-1.5 py-0.5 rounded bg-edge/50 text-ink hover:bg-[#1A5FA8] hover:text-white transition-colors shrink-0">
            → {child}
          </button>
        )}
      </div>
    )
  }

  // ── Blocos de renderização reusáveis ──────────────────────────────────────

  // Cabeçalho do resultado em foco (linha de comando + exit + duração).
  const resultHeader = (r: DsConsoleResult) => (
    <div className="flex flex-wrap items-center gap-2 text-xs text-dim">
      <code className="font-mono px-2 py-1 rounded bg-edge/40 text-ink">
        dsjob -{r.command} {r.project}{r.job ? ' ' + r.job : ''}
      </code>
      <Badge value={r.exit_code === 0 ? 'success' : 'error'}>exit {r.exit_code}</Badge>
      <span>{r.duration_ms} ms</span>
    </div>
  )

  // Caixa de erro (de-para do "Status code = -N").
  const errorBox = (r: DsConsoleResult) => {
    if (r.exit_code === 0 || !errorMeaning) return null
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
        <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-800 dark:text-yellow-300">
          <strong>Código {errorCode}:</strong> {errorMeaning}.
          {errorCode === -1004 && <> Confira o nome do job — use o autocompletar do campo Job ou rode <strong>"Listar jobs"</strong>.</>}
        </p>
      </div>
    )
  }

  // Card de status do job (jobinfo).
  const jobinfoCard = () => {
    if (!isJobinfo || jobinfoFields.length === 0) return null
    return (
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        {statusField && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-dim">Status:</span>
            <Badge value={dsStatusVariant(statusField.value)}>{statusField.value}</Badge>
            {statusMeaning && <span className="text-xs text-ink font-medium">— {statusMeaning}</span>}
          </div>
        )}
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
          {jobinfoFields.filter(f => !/^Job Status/i.test(f.label)).map((f, i) => (
            <div key={i} className="flex justify-between gap-3 border-b border-edge/50 py-1">
              <dt className="text-xs text-dim shrink-0">{f.label}</dt>
              <dd className="text-xs text-ink font-medium text-right break-all">{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    )
  }

  // Cards de detalhe de evento (logdetail).
  const logdetailCards = () => logDetailEvents.map((e, i) => (
    <div key={i} className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Badge value={dsTypeVariant(e.type)}>{e.type || '—'}</Badge>
        {e.eventId && <span className="text-xs text-dim">Evento <span className="font-mono text-ink">#{e.eventId}</span></span>}
        {e.time && <span className="text-xs text-dim">{e.time}</span>}
        {e.user && <span className="text-xs text-dim">por <span className="text-ink">{e.user}</span></span>}
        {e.messageId && <span className="text-xs text-dim">cód. <span className="font-mono text-ink">{e.messageId}</span></span>}
      </div>
      {e.message && (
        <div className={`rounded-lg p-3 text-sm whitespace-pre-wrap break-words font-mono leading-relaxed ${
          /FATAL|REJECT|ABORT/i.test(e.type || '')
            ? 'bg-red-50 border border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300'
            : /WARN/i.test(e.type || '')
              ? 'bg-amber-50 border border-amber-200 text-amber-800 dark:bg-yellow-900/20 dark:border-yellow-700 dark:text-yellow-300'
              : 'bg-canvas border border-edge text-ink'}`}>
          {e.message}
        </div>
      )}
      {/FATAL/i.test(e.type || '') && /previous unrecoverable errors|aborted due to|abort requested/i.test(e.message) && (
        <p className="text-xs text-dim">
          Falha genérica do <strong>coordenador da sequence</strong> — a causa-raiz está num <strong>job filho</strong>. Volte ao <strong>Resumo do log (logsum)</strong> e clique no job filho abortado para ver o erro real.
        </p>
      )}
    </div>
  ))

  // Card de erros e avisos por run (cada run começa colapsado; clique expande).
  const errorsCard = () => {
    if (errorsByRun.length === 0 && ungroupedErrors.length === 0) return null
    const groups = errorsByRun.slice().reverse()
    return (
      <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg p-4 flex flex-col gap-3">
        <p className="text-xs text-red-800 dark:text-red-300 font-medium">
          Erros e avisos <strong>por run</strong> (cada run é independente) — clique no cabeçalho para expandir, no <strong>nome do job filho</strong> para abrir o log dele, ou no <strong>#id</strong> para o detalhe:
        </p>
        {groups.map((g, gi) => {
          const open = openErrGroups.has(gi)
          return (
            <div key={gi} className="border border-red-200/70 dark:border-red-800/60 rounded-lg overflow-hidden">
              <button onClick={() => toggleErrGroup(gi)}
                className="w-full flex flex-wrap items-center gap-2 px-2.5 py-2 text-left hover:bg-red-100/50 dark:hover:bg-red-900/30 transition-colors">
                {open ? <ChevronUp size={14} className="text-red-700 dark:text-red-300 shrink-0" /> : <ChevronDown size={14} className="text-red-700 dark:text-red-300 shrink-0" />}
                <Badge value={g.run.result === 'ok' ? 'success' : g.run.result === 'aborted' ? 'error' : g.run.result === 'running' ? 'info' : 'neutral'}>
                  {g.run.result === 'ok' ? 'Concluído' : g.run.result === 'aborted' ? 'Abortado' : g.run.result === 'running' ? 'Em execução' : 'Run'}
                </Badge>
                <span className="text-xs text-ink font-medium">{g.run.start}</span>
                {g.run.end && g.run.end !== g.run.start && <span className="text-xs text-dim">→ {g.run.end}</span>}
                <span className="ml-auto text-xs text-red-700 dark:text-red-300 font-medium">{g.errors.length} erro(s)/aviso(s)</span>
              </button>
              {open && (
                <div className="flex flex-col gap-1.5 px-2.5 pb-2.5 pt-0.5 border-t border-red-200/70 dark:border-red-800/60">
                  {g.errors.slice(-12).reverse().map(renderErrRow)}
                </div>
              )}
            </div>
          )
        })}
        {ungroupedErrors.length > 0 && (
          <div className="border border-edge/70 rounded-lg p-2.5">
            <p className="text-xs text-dim mb-1.5">Histórico anterior (fora dos runs detectados nesta saída)</p>
            <div className="flex flex-col gap-1.5">{ungroupedErrors.slice(-12).reverse().map(renderErrRow)}</div>
          </div>
        )}
      </div>
    )
  }

  // Card de resumo dos runs (logsum) + botões de diagrama / causa-raiz.
  const runsCard = () => {
    if (logsumRuns.length === 0) return null
    return (
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <p className="text-xs text-dim">Resumo dos runs (mais recentes primeiro) — {logsumRuns.length} no log. Clique num job para ver o log dele (logsum):</p>
          {hasGraph && (
            <div className="ml-auto flex items-center gap-2">
              <Button size="sm" variant="secondary" loading={tracing}
                onClick={() => autoTrace([{ job: result!.job!, targetTime: null }])}>
                <Crosshair size={14} className="mr-1" /> Causa-raiz (auto)
              </Button>
              <Button size="sm" variant="secondary"
                onClick={() => { setGraphTargetTime(null); setGraphPath([{ job: result!.job!, targetTime: null }]); setShowGraph(true) }}>
                <Network size={14} className="mr-1" /> Ver diagrama
              </Button>
            </div>
          )}
        </div>
        {logsumRuns.slice().reverse().slice(0, 15).map((r, i) => (
          <div key={i} className="border border-edge/60 rounded-lg p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge value={r.result === 'ok' ? 'success' : r.result === 'aborted' ? 'error' : r.result === 'running' ? 'info' : 'neutral'}>
                {r.result === 'ok' ? 'Concluído' : r.result === 'aborted' ? 'Abortado' : r.result === 'running' ? 'Em execução' : 'Indefinido'}
              </Badge>
              <span className="text-xs text-ink font-medium">{r.start}</span>
              {r.end && r.end !== r.start && <span className="text-xs text-dim">→ {r.end}</span>}
              {r.children.length > 0 && <span className="text-xs text-dim">· {r.children.length} job(s)</span>}
            </div>
            {r.children.length > 0 && (
              <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2">
                {r.children.map((c, j) => (
                  <button key={j} onClick={() => runFor('logsum', c.fullJob)}
                    title={`Ver o log de ${c.fullJob} (logsum)`}
                    className="inline-flex items-center gap-1.5 hover:opacity-80 transition-opacity">
                    <span className="font-mono text-[11px] text-ink break-all underline decoration-dotted decoration-edge underline-offset-2">{c.job}</span>
                    <Badge value={c.code != null ? dsCodeVariant(c.code) : 'info'}>{c.code != null ? (DS_STATUS_MEANINGS[c.code] ?? c.text) : 'Em execução'}</Badge>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    )
  }

  // Lista de jobs (ljobs) — cada job abre jobinfo.
  const ljobsCard = () => {
    if (ljobsList.length === 0) return null
    return (
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <p className="text-xs text-dim mb-2">{ljobsList.length} job(s) — clique para inspecionar (jobinfo) na aba Visão geral:</p>
        <div className="flex flex-wrap gap-1.5">
          {ljobsList.map(j => (
            <button key={j} onClick={() => { setJob(j); setActiveTab('geral'); overviewExec.mutate({ project: project.trim(), job: j }) }}
              className="px-2 py-1 rounded text-xs font-mono bg-edge/40 text-ink hover:bg-[#1A5FA8] hover:text-white transition-colors">
              {j}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // Saída crua (terminal colorizado, fundo fixo escuro — exceção da seção 4).
  const rawOutput = (r: DsConsoleResult) => {
    if (!r.stdout && !r.stderr) {
      return <p className="text-xs text-dim">Comando executado (exit {r.exit_code}) sem saída.</p>
    }
    return (
      <div className="relative">
        <button onClick={() => copy(r.stdout || r.stderr)}
          className="absolute top-2 right-2 px-2 py-1 rounded text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 flex items-center gap-1 z-10">
          <Copy size={12} /> Copiar
        </button>
        <div className="bg-gray-950 rounded-lg p-4 overflow-auto max-h-[55vh] font-mono text-xs leading-relaxed">
          {r.stdout ? dsColorize(r.stdout) : null}
          {r.stderr ? (
            <div className="mt-2">{r.stderr.split('\n').map((l, i) => <div key={i} className="text-red-400">{l || ' '}</div>)}</div>
          ) : null}
        </div>
      </div>
    )
  }

  const TABS = [
    { id: 'geral', label: 'Visão geral' },
    { id: 'ljobs', label: 'Listar jobs' },
    { id: 'logdetail', label: 'Detalhe do log' },
    { id: 'lstages', label: 'Stages' },
    { id: 'lparams', label: 'Parâmetros' },
    { id: 'report', label: 'Relatório' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold text-ink">Console DataStage</h1>
        <p className="text-xs text-dim mt-0.5">
          Comandos <code className="font-mono">dsjob</code> de consulta (somente leitura) no servidor Unix do DataStage via SSH.
        </p>
      </div>

      <div className="flex items-start gap-3 p-4 rounded-lg bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
        <Terminal size={16} className="text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <div className="text-sm text-blue-800 dark:text-blue-300">
          Selecione o <strong>projeto</strong> e o <strong>job</strong> e use as abas abaixo. Em <strong>Visão geral</strong>, um clique mostra o status do job e o resumo do último run juntos.
          Ex.: <code className="font-mono text-xs">dsjob -jobinfo BI_VIDA SeqSsdVida7Peps</code>.
        </div>
      </div>

      {cfg.isSuccess && !configured && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
          <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
          <div className="text-sm text-amber-800 dark:text-yellow-300">
            SSH do DataStage não configurado no servidor. Defina <code className="font-mono text-xs">DS_SSH_HOST</code>, <code className="font-mono text-xs">DS_SSH_USER</code> e <code className="font-mono text-xs">DS_SSH_PASSWORD</code> (ou <code className="font-mono text-xs">DS_SSH_KEY_FILE</code>) no ambiente da API e reinicie o container.
          </div>
        </div>
      )}

      {/* Inputs compartilhados — persistem ao trocar de aba */}
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Projeto" value={project} onChange={e => setProject(e.target.value)} className="w-48">
            <option value="">Selecione…</option>
            {projectOptions.map(p => <option key={p}>{p}</option>)}
          </Select>
          {tabNeedsJob && (
            <Input label="Job" value={job} onChange={e => setJob(e.target.value)}
              placeholder="ex.: SeqSsdVida7Peps" className="w-64" list="ds-job-list"
              onKeyDown={e => { if (e.key === 'Enter') run() }} />
          )}
          <datalist id="ds-job-list">
            {jobOptions.map(j => <option key={j} value={j} />)}
          </datalist>
          {hasMax && (
            <Input label="Máx. linhas" type="number" value={maxLines}
              onChange={e => setMaxLines(e.target.value)} className="w-28" />
          )}
          {isLogdetail && (
            <Input label="Evento (id)" type="number" value={eventId}
              onChange={e => setEventId(e.target.value)} placeholder="id do logsum" className="w-32"
              onKeyDown={e => { if (e.key === 'Enter') run() }} />
          )}
          <Button onClick={run} loading={busy} disabled={!canRun}>Executar</Button>
        </div>
        {tabNeedsJob && configured && !!project && (
          <p className="text-[11px] text-dim mt-2">
            {jobsQuery.isFetching
              ? 'Carregando jobs do projeto para autocompletar…'
              : jobOptions.length > 0
                ? `Comece a digitar no campo Job — ${jobOptions.length} jobs de ${project} disponíveis para autocompletar.`
                : ''}
          </p>
        )}
      </div>

      {/* Abas por comando */}
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} size="md" />

      <div className="flex flex-col gap-3">
        {activeTab === 'geral' && (
          <>
            {jobinfoResult && resultHeader(jobinfoResult)}
            {jobinfoResult && errorBox(jobinfoResult)}
            {jobinfoCard()}
            {result?.command === 'logsum' && errorBox(result)}
            {errorsCard()}
            {runsCard()}
            {result?.command === 'logsum' && rawOutput(result)}
            {!jobinfoResult && !result && (
              <p className="text-xs text-dim">Selecione projeto e job e clique em <strong>Executar</strong> para ver o status e o resumo do log.</p>
            )}
          </>
        )}

        {activeTab === 'ljobs' && (
          <>
            {result?.command === 'ljobs' && resultHeader(result)}
            {result?.command === 'ljobs' && errorBox(result)}
            {ljobsCard()}
            {result?.command === 'ljobs' && !ljobsList.length && rawOutput(result)}
            {result?.command !== 'ljobs' && <p className="text-xs text-dim">Selecione o projeto e clique em <strong>Executar</strong> para listar os jobs.</p>}
          </>
        )}

        {activeTab === 'logdetail' && (
          <>
            {result?.command === 'logdetail' && resultHeader(result)}
            {result?.command === 'logdetail' && errorBox(result)}
            {logdetailCards()}
            {result?.command === 'logdetail' && !logDetailEvents.length && rawOutput(result)}
            {result?.command !== 'logdetail' && <p className="text-xs text-dim">Informe projeto, job e o <strong>id do evento</strong> (visto no logsum) e clique em <strong>Executar</strong>.</p>}
          </>
        )}

        {(activeTab === 'lstages' || activeTab === 'lparams' || activeTab === 'report') && (
          <>
            {result?.command === tabCommand[activeTab] && resultHeader(result)}
            {result?.command === tabCommand[activeTab] && errorBox(result)}
            {result?.command === tabCommand[activeTab] && rawOutput(result)}
            {result?.command !== tabCommand[activeTab] && <p className="text-xs text-dim">Selecione projeto e job e clique em <strong>Executar</strong>.</p>}
          </>
        )}
      </div>

      {/* Tabela de códigos (de-para) — colapsável no rodapé */}
      <div className="border-t border-edge pt-3">
        <button onClick={() => setShowCodes(v => !v)}
          className="text-xs text-dim hover:text-ink flex items-center gap-1">
          {showCodes ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          Tabela de códigos de status do job (de-para)
        </button>
        {showCodes && (
          <div className="mt-2 bg-panel border border-edge rounded-lg overflow-hidden max-w-md">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-dim border-b border-edge bg-canvas/50">
                  <th className="text-left px-3 py-1.5 font-medium w-20">Código</th>
                  <th className="text-left px-3 py-1.5 font-medium">Significado</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(DS_STATUS_MEANINGS).map(([code, meaning]) => (
                  <tr key={code} className="border-b border-edge/50 last:border-0">
                    <td className="px-3 py-1 font-mono text-ink">{code}</td>
                    <td className="px-3 py-1 text-ink">{meaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showGraph && graphData && (
        <DsRunGraphModal
          open={showGraph}
          onClose={() => setShowGraph(false)}
          rootJob={graphData.rootJob}
          graphRuns={graphData.runs}
          loading={exec.isPending || tracing}
          tracing={tracing}
          onAutoTrace={() => autoTrace(graphPath.length ? graphPath : [{ job: graphData.rootJob, targetTime: graphTargetTime }])}
          targetTime={graphTargetTime}
          path={graphPath.map(p => p.job)}
          onNavigate={(index) => {
            const target = graphPath[index]
            if (!target) return
            setGraphTargetTime(target.targetTime)
            setGraphPath(graphPath.slice(0, index + 1))
            runFor('logsum', target.job)
          }}
          onDrill={(job, targetTime) => {
            setGraphTargetTime(targetTime ?? null)
            setGraphPath(p => [...p, { job, targetTime: targetTime ?? null }])
            runFor('logsum', job)
          }}
        />
      )}
    </div>
  )
}
