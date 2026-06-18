import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Modal } from './ui/Modal'
import { Spinner } from './ui/Spinner'
import { ChevronRight, ChevronDown, Share2 } from 'lucide-react'

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

function Row({ node, path, collapsed, toggle, statusMap }: {
  node: TreeNode; path: string; collapsed: Set<string>; toggle: (p: string) => void
  statusMap: Record<string, JobStatus>
}) {
  const st = statusMap[node.name]
  const hasKids = node.children && node.children.length > 0
  const isOpen = !collapsed.has(path)
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
        {node.invocations && node.invocations > 1 && (
          <span className="text-[11px] text-amber-600 dark:text-amber-400 font-semibold">×{node.invocations}</span>
        )}
        {extras.length > 0 && <span className="text-[11px] text-dim">· {extras.join(' · ')}</span>}
      </div>
      {hasKids && isOpen && (
        <div className="ml-4 border-l border-edge/60 pl-2">
          {node.children.map((c, i) => (
            <Row key={`${path}/${c.name}#${i}`} node={c} path={`${path}/${c.name}#${i}`}
              collapsed={collapsed} toggle={toggle} statusMap={statusMap} />
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
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggle = (p: string) => setCollapsed((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n })

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
  const statusMap: Record<string, JobStatus> = {}
  for (const j of status?.jobs ?? []) statusMap[j.job_name] = j

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
      <div className="flex items-center gap-2 text-xs text-dim">
        <Share2 size={13} className="text-[#1A5FA8]" />
        Projeto: <strong className="text-ink">{data.project}</strong>
        {status?.scanned_at && <span className="ml-auto">status de {status.scanned_at}</span>}
      </div>
      <div className="border border-edge rounded-lg p-3 overflow-x-auto bg-canvas/40">
        <Row node={data.tree} path="root" collapsed={collapsed} toggle={toggle} statusMap={statusMap} />
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
