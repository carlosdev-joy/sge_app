import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { Card, KpiCard } from '../components/ui/Card'
import { Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import {
  Share2, RefreshCw, Upload, Database, Server, ChevronRight, ChevronDown,
  GitBranch, FileCode2, Trash2,
} from 'lucide-react'

// ── Tipos ─────────────────────────────────────────────────────────
interface MalhaHeader {
  project: string; server_name: string | null; ds_version: string | null
  nodes_count: number; edges_count: number; imported_by: string | null; imported_at: string | null
}
interface TreeNode {
  name: string; kind: string; children: TreeNode[]
  routines: number; commands: number; invocations?: number; ref?: boolean
}
interface MalhaDetail { malha: MalhaHeader; roots: string[]; tree: TreeNode }

// ── Badge de tipo de nó ───────────────────────────────────────────
const KIND_CLS: Record<string, string> = {
  SEQ:     'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  JOB:     'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  EXTERNO: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
}
function KindBadge({ k }: { k: string }) {
  const cls = KIND_CLS[k] ?? 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${cls}`}>{k}</span>
}

// ── Árvore (recursiva, colapsável) ────────────────────────────────
function TreeRow({ node, path, collapsed, toggle, termo }: {
  node: TreeNode; path: string; collapsed: Set<string>; toggle: (p: string) => void; termo: string
}) {
  const hasKids = node.children && node.children.length > 0
  const isOpen = !collapsed.has(path)
  const extras: string[] = []
  if (node.routines) extras.push(`${node.routines} rotina(s)`)
  if (node.commands) extras.push(`${node.commands} comando(s)`)
  const hit = termo && node.name.toLowerCase().includes(termo.toLowerCase())
  return (
    <div>
      <div className="flex items-center gap-1.5 py-1 hover:bg-edge/30 rounded px-1">
        {hasKids ? (
          <button onClick={() => toggle(path)} className="text-dim hover:text-ink">
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : <span className="w-[14px] inline-block" />}
        <KindBadge k={node.kind} />
        <span className={`text-sm font-mono ${hit ? 'bg-yellow-300 text-slate-900 rounded px-1' : 'text-ink'}`}>{node.name}</span>
        {node.invocations && node.invocations > 1 && (
          <span className="text-[11px] text-amber-600 dark:text-amber-400 font-semibold">×{node.invocations}</span>
        )}
        {node.ref && <span className="text-[11px] text-dim italic">↑ já detalhado</span>}
        {extras.length > 0 && <span className="text-[11px] text-dim">· {extras.join(' · ')}</span>}
      </div>
      {hasKids && isOpen && (
        <div className="ml-4 border-l border-edge/60 pl-2">
          {node.children.map((c, i) => (
            <TreeRow key={`${path}/${c.name}#${i}`} node={c} path={`${path}/${c.name}#${i}`}
              collapsed={collapsed} toggle={toggle} termo={termo} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Contagens da árvore (objetividade) ────────────────────────────
function countTree(node: TreeNode, acc = { seq: 0, job: 0, ext: 0 }) {
  if (node.kind === 'SEQ') acc.seq++
  else if (node.kind === 'JOB') acc.job++
  else if (node.kind === 'EXTERNO') acc.ext++
  for (const c of node.children || []) countTree(c, acc)
  return acc
}

// ── Página ────────────────────────────────────────────────────────
export default function MalhaDS() {
  const [xmlFile, setXmlFile] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [termo, setTermo] = useState('')

  const { data: xmlData } = useQuery<{ base_dir: string; files: string[] }>({
    queryKey: ['malha-ds-xml'], queryFn: () => apiFetch('/malha-ds/xml-files'),
  })
  const { data: listData, isLoading: loadingList } = useQuery<{ malhas: MalhaHeader[] }>({
    queryKey: ['malha-ds-list'], queryFn: () => apiFetch('/malha-ds'),
  })
  const { data: detail, isFetching: loadingDetail } = useQuery<MalhaDetail>({
    queryKey: ['malha-ds', selected],
    queryFn: () => apiFetch(`/malha-ds/${encodeURIComponent(selected!)}`),
    enabled: !!selected,
  })
  const { data: jobsData } = useQuery<{ jobs: string[] }>({
    queryKey: ['malha-ds-jobs', selected],
    queryFn: () => apiFetch(`/malha-ds/${encodeURIComponent(selected!)}/jobs`),
    enabled: !!selected,
  })

  const importMut = useMutation({
    mutationFn: (project: string) =>
      apiFetch<{ project: string; nodes: number; edges: number }>('/malha-ds/import', {
        method: 'POST', body: JSON.stringify({ project }),
      }),
    onSuccess: (r) => {
      toast.success(`Malha importada: ${r.nodes} nós, ${r.edges} chamadas`)
      queryClient.invalidateQueries({ queryKey: ['malha-ds-list'] })
      queryClient.invalidateQueries({ queryKey: ['malha-ds', r.project] })
      queryClient.invalidateQueries({ queryKey: ['malha-ds-jobs', r.project] })
      setSelected(r.project)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (project: string) => apiFetch(`/malha-ds/${encodeURIComponent(project)}`, { method: 'DELETE' }),
    onSuccess: (_r, project) => {
      toast.success(`Malha de ${project} removida`)
      queryClient.invalidateQueries({ queryKey: ['malha-ds-list'] })
      if (selected === project) setSelected(null)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const handleDelete = (project: string) => {
    if (confirm(`Remover a malha de "${project}" do banco? (não apaga o XML; pode reimportar)`)) {
      deleteMut.mutate(project)
    }
  }

  const toggle = (p: string) => setCollapsed((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n })
  const malhas = listData?.malhas ?? []
  const counts = detail ? countTree(detail.tree) : null

  return (
    <div className="flex flex-col gap-5">
      {/* Cabeçalho */}
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <Share2 size={20} className="text-[#1A5FA8]" /> Malha DataStage
        </h1>
        <p className="text-sm text-dim mt-1">
          Importa a malha de um export <code>.xml</code> e a guarda no banco — depois a análise é
          feita do banco (sem reparsear). Reimporte para atualizar com um XML novo.
        </p>
      </div>

      {/* Importar / Atualizar */}
      <Card title="Importar / atualizar malha">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-72">
            <Select label="Arquivo .xml exportado" value={xmlFile} onChange={(e) => setXmlFile(e.target.value)}>
              <option value="">Selecione…</option>
              {(xmlData?.files ?? []).map((f) => <option key={f} value={f}>{f}.xml</option>)}
            </Select>
          </div>
          <Button onClick={() => xmlFile ? importMut.mutate(xmlFile) : toast.error('Selecione um arquivo .xml')}
            loading={importMut.isPending} className="mb-0.5">
            <Upload size={14} /> Importar
          </Button>
          {xmlData?.base_dir && (
            <span className="text-[11px] text-dim pb-2 flex items-center gap-1">
              <FileCode2 size={12} /> {xmlData.base_dir}
            </span>
          )}
        </div>
        {importMut.isPending && (
          <p className="text-xs text-dim mt-2">Parseando o XML (arquivos grandes podem levar alguns segundos)…</p>
        )}
      </Card>

      {/* Malhas no banco */}
      <Card title="Malhas no banco">
        {loadingList ? <div className="flex justify-center py-6"><Spinner /></div> : (
          malhas.length === 0 ? (
            <p className="text-sm text-dim text-center py-4">Nenhuma malha importada ainda. Selecione um <code>.xml</code> acima e clique em Importar.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {malhas.map((m) => (
                <div key={m.project}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors ${selected === m.project ? 'border-[#1A5FA8] bg-[#1A5FA8]/5' : 'border-edge hover:border-[#1A5FA8]/50'}`}>
                  <button onClick={() => setSelected(m.project)} className="flex items-center gap-3 text-left flex-1 min-w-0">
                    <Database size={15} className="text-[#1A5FA8] shrink-0" />
                    <span className="font-medium text-ink">{m.project}</span>
                    <span className="text-xs text-dim flex items-center gap-1"><Server size={11} /> {m.server_name ?? '—'} · DS {m.ds_version ?? '—'}</span>
                    <span className="text-xs text-dim ml-auto">{m.nodes_count} nós · {m.edges_count} chamadas</span>
                    <span className="text-[11px] text-dim whitespace-nowrap">{m.imported_at} {m.imported_by ? `· ${m.imported_by}` : ''}</span>
                  </button>
                  <Button variant="ghost" size="sm" title="Excluir malha"
                    loading={deleteMut.isPending && deleteMut.variables === m.project}
                    onClick={() => handleDelete(m.project)}>
                    <Trash2 size={14} className="text-dim hover:text-red-500" />
                  </Button>
                </div>
              ))}
            </div>
          )
        )}
      </Card>

      {/* Detalhe / árvore */}
      {selected && (
        <Card
          title={`Malha — ${selected}`}
          action={
            <Button variant="secondary" size="sm" loading={importMut.isPending}
              onClick={() => importMut.mutate(selected)} title="Reimportar com o XML atual">
              <RefreshCw size={13} /> Atualizar malha
            </Button>
          }
        >
          {loadingDetail || !detail ? <div className="flex justify-center py-8"><Spinner size={32} /></div> : (
            <div className="flex flex-col gap-4">
              {/* KPIs (objetividade) */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiCard label="Sequences" value={counts?.seq ?? 0} color="blue" />
                <KpiCard label="Jobs (na árvore)" value={counts?.job ?? 0} color="green" />
                <KpiCard label="Externos (outro export)" value={counts?.ext ?? 0} color="yellow" />
                <KpiCard label="Jobs monitoráveis" value={jobsData?.jobs.length ?? '—'} color="purple"
                  sub="para dsjob -jobinfo" />
              </div>

              {/* Transparência: origem do dado */}
              <div className="text-[11px] text-dim flex flex-wrap gap-x-4 gap-y-1">
                <span><Server size={11} className="inline" /> {detail.malha.server_name ?? '—'} · DataStage {detail.malha.ds_version ?? '—'}</span>
                <span>{detail.malha.nodes_count} nós · {detail.malha.edges_count} chamadas</span>
                <span>Importado: {detail.malha.imported_at ?? '—'} {detail.malha.imported_by ? `por ${detail.malha.imported_by}` : ''}</span>
                <span>Raiz: <strong className="text-ink">{detail.roots.join(', ') || '—'}</strong></span>
              </div>

              {/* Busca dentro da árvore */}
              <input
                className="w-72 bg-panel border border-edge rounded-md px-3 py-1.5 text-sm text-ink placeholder-dim"
                placeholder="filtrar job na árvore…" value={termo} onChange={(e) => setTermo(e.target.value)}
              />

              {/* Árvore (quem chama quem, com executor resolvido) */}
              <div className="border border-edge rounded-lg p-3 overflow-x-auto bg-canvas/40">
                <div className="flex items-center gap-2 text-xs text-dim mb-2">
                  <GitBranch size={13} /> Árvore de execução (executor genérico já resolvido para o job real)
                </div>
                <TreeRow node={detail.tree} path="root" collapsed={collapsed} toggle={toggle} termo={termo} />
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
