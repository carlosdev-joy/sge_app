import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Modal } from './ui/Modal'
import { Spinner } from './ui/Spinner'
import { ChevronRight, ChevronDown, Share2, Filter } from 'lucide-react'

// Vínculo por NOME: dado o nome do job (do pipeline), mostra a árvore da malha
// enraizada nele (+ status). Autocontido — não depende da tela Malha DS.
// MalhaTreeView é o conteúdo reutilizável (sem Modal); MalhaTreeModal e
// PipelineMalhaModal o embrulham para os diferentes pontos de entrada.

interface TreeNode { name: string; kind: string; children: TreeNode[]; routines: number; commands: number; invocations?: number; ref?: boolean }
interface JobStatus { job_name: string; status_code: number | null; status_label: string | null; info: string | null }
interface SubtreeResp { found: boolean; job: string; project: string | null; tree: TreeNode | null }
interface StatusResp { jobs: JobStatus[]; scanned_at: string | null }
interface PipeMatch { job_name: string; project: string; is_sequence: boolean; execution_order: number }
interface PipeResp { pipeline: string; matches: PipeMatch[] }

const KIND_CLS: Record<string, string> = {
  SEQ:     'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  JOB:     'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  EXTERNO: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
}
const ST_CLS: Record<string, string> = {
  OK:      'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  WARNING: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
  ABORTED: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  RUNNING: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
}
const badgeCls = (m: Record<string, string>, k: string) =>
  m[k] ?? 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'

// Status "não-OK" (destacados no resumo / filtro): aviso, falha e rodando
const isWarn = (lbl?: string | null) => (lbl ?? '').toUpperCase() === 'WARNING'
const isFail = (lbl?: string | null) => { const s = (lbl ?? '').toUpperCase(); return s === 'ABORTED' || s === 'FAILED' }
const isRun  = (lbl?: string | null) => (lbl ?? '').toUpperCase() === 'RUNNING'
const isFlagged = (lbl?: string | null) => isWarn(lbl) || isFail(lbl) || isRun(lbl)

interface ProblemInfo { w: number; f: number; r: number }
type ProblemMap = Map<TreeNode, ProblemInfo>

// Filtro por situação: f=falha, w=aviso, r=rodando. Vazio = sem filtro.
type Cat = 'f' | 'w' | 'r'
const inFilter = (info: ProblemInfo, filter: Set<Cat>) =>
  filter.size === 0 ||
  (filter.has('f') && info.f > 0) ||
  (filter.has('w') && info.w > 0) ||
  (filter.has('r') && info.r > 0)

/** Conta WARNING/FAILED/RUNNING de cada nó + descendentes (uma passada). */
function buildProblemMap(root: TreeNode | null, statusMap: Record<string, JobStatus>): ProblemMap {
  const map: ProblemMap = new Map()
  const walk = (n: TreeNode): ProblemInfo => {
    const lbl = statusMap[n.name]?.status_label
    let w = isWarn(lbl) ? 1 : 0
    let f = isFail(lbl) ? 1 : 0
    let r = isRun(lbl) ? 1 : 0
    for (const c of n.children ?? []) { const ci = walk(c); w += ci.w; f += ci.f; r += ci.r }
    const info = { w, f, r }
    map.set(n, info)
    return info
  }
  if (root) walk(root)
  return map
}

/** Todos os caminhos da árvore (mesmo esquema de path do Row) — para expandir tudo. */
function allPaths(node: TreeNode, path = 'root', acc: string[] = []): string[] {
  acc.push(path)
  ;(node.children ?? []).forEach((c, i) => allPaths(c, `${path}/${c.name}#${i}`, acc))
  return acc
}

function Row({ node, path, expanded, toggle, statusMap, problemMap, filter }: {
  node: TreeNode; path: string; expanded: Set<string>; toggle: (p: string) => void
  statusMap: Record<string, JobStatus>; problemMap: ProblemMap; filter: Set<Cat>
}) {
  const info = problemMap.get(node) ?? { w: 0, f: 0, r: 0 }
  const active = filter.size > 0
  // Filtrando, esconde ramos que não levam à(s) situação(ões) selecionada(s)
  if (active && !inFilter(info, filter)) return null

  const st = statusMap[node.name]
  const selfFlagged = isFlagged(st?.status_label)
  const branchBelow = !selfFlagged && (info.w > 0 || info.f > 0 || info.r > 0)

  const allKids = node.children ?? []
  const kids = active
    ? allKids.filter(c => { const ci = problemMap.get(c); return !!ci && inFilter(ci, filter) })
    : allKids
  const hasKids = kids.length > 0
  // Filtrando, mantém o caminho até o ponto apontado aberto
  const isOpen = active ? true : expanded.has(path)

  const extras: string[] = []
  if (node.routines) extras.push(`${node.routines} rotina(s)`)
  if (node.commands) extras.push(`${node.commands} comando(s)`)
  return (
    <div>
      <div className="flex items-center gap-1.5 py-1 hover:bg-edge/30 rounded px-1">
        {hasKids ? (
          <button onClick={() => toggle(path)} className="text-dim hover:text-ink">
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : <span className="w-[14px] inline-block" />}
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${badgeCls(KIND_CLS, node.kind)}`}>{node.kind}</span>
        <span className="text-sm font-mono text-ink">{node.name}</span>
        {st?.status_label && (
          <span title={st.info ?? undefined} className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${badgeCls(ST_CLS, st.status_label)}`}>{st.status_label}</span>
        )}
        {branchBelow && (
          <span
            title="Há job(s) não-OK neste ramo (aviso, falha ou rodando)"
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold border border-edge text-dim"
          >
            ↳
            {info.f > 0 && <span className="text-red-600 dark:text-red-400">{info.f}✗</span>}
            {info.w > 0 && <span className="text-amber-600 dark:text-amber-400">{info.w}⚠</span>}
            {info.r > 0 && <span className="text-blue-600 dark:text-blue-400">{info.r}▶</span>}
          </span>
        )}
        {node.invocations && node.invocations > 1 && (
          <span className="text-[11px] text-amber-600 dark:text-amber-400 font-semibold">×{node.invocations}</span>
        )}
        {extras.length > 0 && <span className="text-[11px] text-dim">· {extras.join(' · ')}</span>}
      </div>
      {hasKids && isOpen && (
        <div className="ml-4 border-l border-edge/60 pl-2">
          {kids.map((c, i) => (
            <Row key={`${path}/${c.name}#${i}`} node={c} path={`${path}/${c.name}#${i}`}
              expanded={expanded} toggle={toggle} statusMap={statusMap}
              problemMap={problemMap} filter={filter} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Conteúdo reutilizável: árvore da malha de UM job (por nome) + status ──────

export function MalhaTreeView({ jobName, project: projectHint, enabled = true }: {
  jobName: string; project?: string; enabled?: boolean
}) {
  // Recolhida por padrão: só o nó-raiz aberto (mostra as segmentações de 1º nível)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['root']))
  const [filter, setFilter] = useState<Set<Cat>>(new Set())
  const toggle = (p: string) => setExpanded((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n })
  const toggleCat = (c: Cat) => setFilter((s) => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n })

  const { data, isLoading } = useQuery<SubtreeResp>({
    queryKey: ['malha-subtree', jobName, projectHint ?? null],
    queryFn: () => apiFetch(
      `/malha-ds/subtree?job=${encodeURIComponent(jobName)}${projectHint ? `&project=${encodeURIComponent(projectHint)}` : ''}`
    ),
    enabled: enabled && !!jobName,
  })
  const project = data?.project ?? projectHint ?? null
  const { data: status } = useQuery<StatusResp>({
    queryKey: ['malha-ds-status', project],
    queryFn: () => apiFetch(`/malha-ds/${encodeURIComponent(project!)}/status`),
    enabled: enabled && !!project,
    refetchInterval: 30_000,
  })

  const statusMap = useMemo(() => {
    const m: Record<string, JobStatus> = {}
    for (const j of status?.jobs ?? []) m[j.job_name] = j
    return m
  }, [status])

  // Conta não-OK no nó-raiz (jobs distintos) e por subárvore (filtro/marcador)
  const problemMap = useMemo(() => buildProblemMap(data?.tree ?? null, statusMap), [data, statusMap])
  const { warn, fail, run } = useMemo(() => {
    const seen = new Set<string>()
    let w = 0, f = 0, r = 0
    const walk = (n: TreeNode) => {
      if (!seen.has(n.name)) {
        seen.add(n.name)
        const lbl = statusMap[n.name]?.status_label
        if (isFail(lbl)) f++; else if (isWarn(lbl)) w++; else if (isRun(lbl)) r++
      }
      n.children?.forEach(walk)
    }
    if (data?.tree) walk(data.tree)
    return { warn: w, fail: f, run: r }
  }, [data, statusMap])
  const hasFlag = warn > 0 || fail > 0 || run > 0

  // Categorias presentes (têm contagem) e se o filtro cobre todas elas
  const presentCats = useMemo(() => {
    const s = new Set<Cat>()
    if (fail > 0) s.add('f'); if (warn > 0) s.add('w'); if (run > 0) s.add('r')
    return s
  }, [fail, warn, run])
  const allSelected = presentCats.size > 0 && filter.size === presentCats.size &&
    [...presentCats].every(c => filter.has(c))

  const paths = useMemo(() => (data?.tree ? allPaths(data.tree) : []), [data])
  const allExpanded = paths.length > 0 && expanded.size >= paths.length

  if (isLoading) return <div className="flex justify-center py-10"><Spinner size={32} /></div>
  if (!data?.found || !data.tree) {
    return (
      <p className="text-sm text-dim text-center py-8">
        Malha não encontrada para <strong>{jobName}</strong>. Importe o projeto na tela <strong>Malha DS</strong>.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-xs text-dim flex-wrap">
        <Share2 size={13} className="text-[#1A5FA8]" />
        Projeto: <strong className="text-ink">{data.project}</strong>
        {/* Resumo de não-OK — clicáveis: filtram só a situação correspondente */}
        {fail > 0 && (
          <button
            onClick={() => toggleCat('f')}
            title={filter.has('f') ? 'Remover filtro de falhas' : 'Filtrar só falhas'}
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border transition-all cursor-pointer bg-red-100 text-red-700 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800 ${filter.has('f') ? 'ring-2 ring-red-500 dark:ring-red-400' : 'hover:brightness-95'}`}
          >
            {fail} ✗ falha{fail > 1 ? 's' : ''}
          </button>
        )}
        {warn > 0 && (
          <button
            onClick={() => toggleCat('w')}
            title={filter.has('w') ? 'Remover filtro de avisos' : 'Filtrar só avisos'}
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border transition-all cursor-pointer bg-amber-100 text-amber-800 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800 ${filter.has('w') ? 'ring-2 ring-amber-500 dark:ring-amber-400' : 'hover:brightness-95'}`}
          >
            {warn} ⚠ aviso{warn > 1 ? 's' : ''}
          </button>
        )}
        {run > 0 && (
          <button
            onClick={() => toggleCat('r')}
            title={filter.has('r') ? 'Remover filtro de rodando' : 'Filtrar só rodando'}
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border transition-all cursor-pointer bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800 ${filter.has('r') ? 'ring-2 ring-blue-500 dark:ring-blue-400' : 'hover:brightness-95'}`}
          >
            {run} ▶ rodando
          </button>
        )}
        {!hasFlag && status?.scanned_at && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800">
            tudo OK
          </span>
        )}
        {hasFlag && (
          <button
            onClick={() => setFilter(allSelected ? new Set() : new Set(presentCats))}
            title="Mostra todos os ramos não-OK (aviso, falha ou rodando)"
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold border transition-colors ${
              allSelected
                ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]'
                : 'border-edge text-dim hover:text-ink'
            }`}
          >
            <Filter size={11} /> {allSelected ? 'Mostrando só não-OK' : 'Só não-OK'}
          </button>
        )}
        {filter.size > 0 && !allSelected && (
          <button
            onClick={() => setFilter(new Set())}
            title="Limpar filtro"
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border border-edge text-dim hover:text-ink transition-colors"
          >
            × limpar
          </button>
        )}
        {paths.length > 1 && (
          <button
            onClick={() => setExpanded(allExpanded ? new Set() : new Set(paths))}
            title={allExpanded ? 'Recolher todos os ramos' : 'Expandir todos os ramos'}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold border border-edge text-dim hover:text-ink transition-colors"
          >
            {allExpanded ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
            {allExpanded ? 'Recolher tudo' : 'Expandir tudo'}
          </button>
        )}
        {status?.scanned_at && <span className="ml-auto">status de {status.scanned_at}</span>}
      </div>
      <div className="border border-edge rounded-lg p-3 overflow-x-auto bg-canvas/40">
        <Row node={data.tree} path="root" expanded={expanded} toggle={toggle}
          statusMap={statusMap} problemMap={problemMap} filter={filter} />
      </div>
    </div>
  )
}

// ── Modal por job (usado na tela Jobs e no log da seq) ───────────────────────

export function MalhaTreeModal({ jobName, open, onClose }: { jobName: string; open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={`Malha — ${jobName}`} size="xl">
      <MalhaTreeView jobName={jobName} enabled={open} />
    </Modal>
  )
}

// ── Modal por pipeline (usado nos cards de execução do dashboard) ────────────

export function PipelineMalhaModal({ pipeline, open, onClose }: { pipeline: string; open: boolean; onClose: () => void }) {
  const [sel, setSel] = useState<string>('')

  const { data, isLoading } = useQuery<PipeResp>({
    queryKey: ['malha-by-pipeline', pipeline],
    queryFn: () => apiFetch(`/malha-ds/by-pipeline?pipeline=${encodeURIComponent(pipeline)}`),
    enabled: open && !!pipeline,
  })
  const matches = data?.matches ?? []
  const selected = matches.find(m => m.job_name === sel) ?? matches[0]

  return (
    <Modal open={open} onClose={onClose} title={`Malha — ${pipeline}`} size="xl">
      {isLoading ? (
        <div className="flex justify-center py-10"><Spinner size={32} /></div>
      ) : matches.length === 0 ? (
        <p className="text-sm text-dim text-center py-8">
          Nenhum job DataStage deste pipeline foi encontrado nas malhas importadas.
          Importe o projeto na tela <strong>Malha DS</strong>.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {matches.length > 1 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-dim">Job (raiz):</span>
              <select
                value={selected?.job_name ?? ''}
                onChange={e => setSel(e.target.value)}
                className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono flex-1"
              >
                {matches.map(m => (
                  <option key={m.job_name} value={m.job_name}>
                    {m.job_name} ({m.project}){m.is_sequence ? ' · sequence' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
          {selected && (
            <MalhaTreeView jobName={selected.job_name} project={selected.project} enabled={open} />
          )}
        </div>
      )}
    </Modal>
  )
}
