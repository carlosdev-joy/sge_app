import { useState, useRef, type ReactNode } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Tabs } from '../components/ui/Tabs'
import { queryClient } from '../lib/queryClient'
import { renderMarkdown } from '../lib/markdown'
import {
  Edit2, Trash2, Plus, AlertTriangle, ChevronDown, ChevronUp, Save, X,
  CheckCircle2, Eye, Calendar, Download, Megaphone, Bold, Italic, Code, List, RefreshCw, Database,
  Terminal, Copy,
} from 'lucide-react'

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

// Recursos RBAC (espelha RBAC_RECURSOS da UI legada).
const RBAC_RECURSOS: [string, string][] = [
  ['tela_dashboard', 'Dashboard'], ['tela_pipelines', 'Pipelines'],
  ['tela_jobs', 'Jobs'], ['tela_logs', 'Logs'],
  ['tela_governanca', 'Governança'],
  ['tela_malha', 'Malha'], ['tela_admin', 'Admin'],
  ['tela_impacto_campo', 'Impacto Campo'], ['tela_plano_ajuste', 'Plano Ajuste'],
  ['tela_powerbi', 'Power BI'], ['tela_malha_ds', 'Malha DS'],
  ['acao_executar', 'Executar/Rerun/Ack'],
  ['acao_editar', 'Cadastrar/Editar'],
  ['acao_admin', 'Administração'],
]

const adminPost = <T,>(action: string, extra: Record<string, unknown> = {}) =>
  apiFetch<T>('/admin', { method: 'POST', body: JSON.stringify({ action, ...extra }) })

// ── Confirm Modal ────────────────────────────────────────────────
interface ConfirmProps {
  open: boolean
  title: string
  message: string
  danger?: boolean
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}
function ConfirmModal({ open, title, message, danger, confirmLabel = 'Confirmar', onConfirm, onCancel }: ConfirmProps) {
  if (!open) return null
  return (
    <Modal open onClose={onCancel} title={title} size="sm">
      <div className="flex flex-col gap-5">
        {danger ? (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{message}</p>
          </div>
        ) : <p className="text-sm text-ink">{message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>Cancelar</Button>
          <Button variant={danger ? 'danger' : 'primary'} size="sm" onClick={() => { onConfirm(); onCancel() }}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Markdown render ──────────────────────────────────────────────
function Markdown({ text }: { text?: string }) {
  return <div className="text-ink" dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />
}

// ── Configurações ───────────────────────────────────────────────
function ConfigTab() {
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [delKey, setDelKey] = useState<string | null>(null)
  const [webhookDiag, setWebhookDiag] = useState<any>(null)

  const { data, isLoading } = useQuery<{ config: Record<string, string> }>({
    queryKey: ['admin-config'],
    queryFn: () => adminPost('config_list'),
  })

  const upsertMut = useMutation({
    mutationFn: (p: { config_key: string; config_value: string; descricao?: string }) =>
      adminPost('config_upsert', p),
    onSuccess: (_, vars) => {
      toast.success('Configuração salva')
      queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      setEditValues(prev => { const n = { ...prev }; delete n[vars.config_key]; return n })
      setSavingKey(null)
      if (!data?.config[vars.config_key]) { setNewKey(''); setNewVal(''); setNewDesc('') }
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (config_key: string) => adminPost('config_delete', { config_key }),
    onSuccess: () => { toast.success('Parâmetro removido'); queryClient.invalidateQueries({ queryKey: ['admin-config'] }); setDelKey(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const testWebhook = async () => {
    setWebhookDiag(null)
    try {
      const d = await apiFetch<any>('/admin/test-webhook', { method: 'POST' })
      if (d.ok) toast.success(`Card enviado (HTTP ${d.http_status}). Verifique o canal Teams.`)
      else { toast.error(d.erro ?? 'Falha no webhook'); setWebhookDiag(d) }
    } catch (e: any) { toast.error(e.message) }
  }

  const entries = Object.entries(data?.config ?? {})

  const handleInlineSave = (key: string) => {
    const val = editValues[key]
    if (val === undefined) return
    setSavingKey(key)
    upsertMut.mutate({ config_key: key, config_value: val })
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-dim">Parâmetros do sistema. Edite o valor na célula e clique em Salvar.</p>
        <Button variant="secondary" size="sm" onClick={testWebhook}>🔔 Testar Webhook</Button>
      </div>

      {webhookDiag && (
        <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-red-700 dark:text-red-300">📋 Diagnóstico do Webhook</span>
            <button onClick={() => setWebhookDiag(null)} className="text-red-400 hover:text-red-600"><X size={14} /></button>
          </div>
          <pre className="text-xs text-red-700 dark:text-red-300 overflow-auto max-h-48 whitespace-pre-wrap">{JSON.stringify(webhookDiag, null, 2)}</pre>
        </div>
      )}

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold w-1/3">Chave</th>
                <th className="px-4 py-2.5 text-left font-semibold">Valor</th>
                <th className="px-4 py-2.5 w-28"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, v]) => {
                const current = editValues[k] !== undefined ? editValues[k] : v
                const isDirty = editValues[k] !== undefined && editValues[k] !== v
                const isSaving = savingKey === k && upsertMut.isPending
                return (
                  <tr key={k} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2"><span className="font-mono text-xs text-[#1A5FA8] dark:text-blue-400">{k}</span></td>
                    <td className="px-4 py-2">
                      <input
                        value={current}
                        onChange={e => setEditValues(prev => ({ ...prev, [k]: e.target.value }))}
                        onKeyDown={e => { if (e.key === 'Enter' && isDirty) handleInlineSave(k) }}
                        className="w-full font-mono text-xs text-ink bg-transparent border border-transparent rounded px-2 py-1 hover:border-edge focus:border-[#1A5FA8] focus:ring-1 focus:ring-[#1A5FA8]/30 focus:outline-none transition-colors"
                      />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1 justify-end">
                        {isDirty && (
                          <>
                            <button onClick={() => setEditValues(prev => { const n = { ...prev }; delete n[k]; return n })} className="text-slate-400 hover:text-slate-600 dark:hover:text-dim p-1 rounded" title="Descartar"><X size={12} /></button>
                            <Button size="sm" onClick={() => handleInlineSave(k)} loading={isSaving}><Save size={11} /> Salvar</Button>
                          </>
                        )}
                        <button onClick={() => setDelKey(k)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir parâmetro"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {entries.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-xs text-dim">Nenhuma configuração encontrada.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-xs font-semibold text-dim uppercase tracking-wider mb-3">Adicionar Parâmetro</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <Input label="Chave" value={newKey} onChange={e => setNewKey(e.target.value)} className="w-44" placeholder="NOME_CHAVE" />
          <Input label="Valor" value={newVal} onChange={e => setNewVal(e.target.value)} className="w-52" />
          <Input label="Descrição (opcional)" value={newDesc} onChange={e => setNewDesc(e.target.value)} className="w-56" />
          <Button onClick={() => upsertMut.mutate({ config_key: newKey, config_value: newVal, descricao: newDesc || undefined })} loading={upsertMut.isPending && !savingKey} disabled={!newKey || !newVal}><Plus size={13} /> Adicionar</Button>
        </div>
      </div>

      <ConfirmModal
        open={!!delKey}
        title="Remover Parâmetro"
        message={`Remover "${delKey}"? Se for parâmetro do sistema, o ORQUESTRA usará o valor padrão.`}
        danger confirmLabel="Remover"
        onConfirm={() => delKey && deleteMut.mutate(delKey)}
        onCancel={() => setDelKey(null)}
      />
    </div>
  )
}

// ── Regenerar DAGs ──────────────────────────────────────────────
function RegenDagsTab() {
  const [projeto, setProjeto] = useState('')
  const [log, setLog] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [estimate, setEstimate] = useState('')
  const [confirm, setConfirm] = useState(false)

  const addLog = (m: string) => setLog(prev => [...prev, `[${new Date().toLocaleTimeString('pt-BR')}] ${m}`])

  const doEstimate = async () => {
    setEstimate('⏳ Consultando...')
    try {
      const params = new URLSearchParams({ limit: '1', offset: '0' })
      if (projeto) params.set('filter_project', projeto)
      const d = await apiFetch<{ total: number }>(`/pipelines?${params.toString()}`)
      setEstimate(`📊 ${d.total ?? '?'} pipeline(s) serão regenerados${projeto ? ` no projeto ${projeto}` : ''}.`)
    } catch { setEstimate('Não foi possível estimar — clique em Regenerar para prosseguir.') }
  }

  const regen = async () => {
    setLoading(true); setLog([])
    try {
      addLog('Passo 1/2 — Marcando pipelines para regeneração...')
      const res = await adminPost<any>('regenerate_all_dags', { filter_project: projeto || undefined })
      addLog('✓ ' + (res.mensagem ?? 'Pipelines marcados.'))
      addLog('Passo 2/2 — Disparando etl_dag_factory...')
      const f = await adminPost<any>('factory_trigger', { filter_project: projeto || undefined, force_all: true })
      addLog('✓ ' + (f.mensagem ?? 'Factory disparada.') + ` (${f.detalhes?.dag_run_id ?? ''})`)
      addLog('O Airflow detectará as mudanças no próximo scan.')
      toast.success('DAGs regeneradas com sucesso')
    } catch (e: any) {
      addLog('ERRO: ' + e.message); toast.error(e.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
        <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-800 dark:text-yellow-300">
          Reseta <code className="font-mono text-xs">dag_criada=0</code> e dispara a <code className="font-mono text-xs">etl_dag_factory</code> (force_all) para recriar os arquivos .py com as regras atuais.
        </p>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Filtrar por projeto (opcional)" value={projeto} onChange={e => { setProjeto(e.target.value); setEstimate('') }} className="w-56">
            <option value="">Todos os projetos</option>
            {PROJETOS.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Button variant="secondary" onClick={doEstimate}>Estimar impacto</Button>
          <Button variant="danger" onClick={() => setConfirm(true)} loading={loading}>⟳ Regenerar DAGs</Button>
        </div>
        {estimate && <p className="text-xs text-dim mt-3">{estimate}</p>}
      </div>

      {log.length > 0 && (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge bg-canvas/50 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-500" />
            <span className="text-xs font-medium text-ink">Progresso</span>
          </div>
          <pre className="text-xs text-dim p-4 overflow-auto max-h-64 whitespace-pre-wrap">{log.join('\n')}</pre>
        </div>
      )}

      <ConfirmModal
        open={confirm}
        title="Regenerar DAGs"
        message={`Regenerar todos os pipelines${projeto ? ` do projeto ${projeto}` : ''}? Isso reseta os DAGs e dispara a factory no Airflow.`}
        confirmLabel="Regenerar"
        onConfirm={regen}
        onCancel={() => setConfirm(false)}
      />
    </div>
  )
}

// ── Excluir Pipeline ────────────────────────────────────────────
interface PipelineRow { pipeline_name: string; project_name?: string; dag_criada?: boolean | number; active?: boolean | number }
function DeletePipelineTab() {
  const [nome, setNome] = useState('')
  const [preview, setPreview] = useState<PipelineRow | null>(null)
  const [previewMiss, setPreviewMiss] = useState(false)
  const [loadingPrev, setLoadingPrev] = useState(false)
  const [wizard, setWizard] = useState(false)
  const [typed, setTyped] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  const fetchDeps = async () => {
    if (!nome.trim()) { toast.error('Informe o nome do pipeline.'); return }
    setLoadingPrev(true); setPreview(null); setPreviewMiss(false)
    try {
      const params = new URLSearchParams({ filter_name: nome.trim(), offset: '0', limit: '5' })
      const d = await apiFetch<{ data: PipelineRow[] }>(`/pipelines?${params.toString()}`)
      const found = (d.data ?? []).find(p => p.pipeline_name.toUpperCase() === nome.trim().toUpperCase())
      if (found) setPreview(found)
      else setPreviewMiss(true)
    } catch (e: any) { toast.error(e.message) }
    finally { setLoadingPrev(false) }
  }

  const del = async () => {
    setLoading(true); setResult(null)
    try {
      const res = await adminPost<any>('pipeline_delete', { pipeline_name: preview!.pipeline_name })
      const af = await adminPost<any>('dag_airflow_delete', { pipeline_name: preview!.pipeline_name })
      setResult({ pipeline_delete: res, dag_airflow_delete: af })
      toast.success(`Pipeline "${preview!.pipeline_name}" removido do banco e do Airflow.`)
      setNome(''); setPreview(null); setWizard(false); setTyped('')
    } catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-700">
        <AlertTriangle size={16} className="text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
        <p className="text-sm text-red-800 dark:text-red-300">
          <strong>Atenção:</strong> Operação irreversível. Remove jobs, execuções e lineage do banco <strong>e</strong> a DAG do Airflow (.py + metadata).
        </p>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Input label="Nome do Pipeline" value={nome} onChange={e => { setNome(e.target.value.toUpperCase()); setPreview(null); setPreviewMiss(false) }} className="w-80" placeholder="NOME_EXATO_DO_PIPELINE" />
          <Button variant="secondary" onClick={fetchDeps} loading={loadingPrev} disabled={!nome.trim()}>Verificar dependências</Button>
        </div>

        {previewMiss && <p className="text-xs text-red-500 mt-3">Pipeline não encontrado no banco.</p>}

        {preview && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-canvas border border-edge rounded-lg p-3">
              <div className="text-xs font-semibold text-red-500">Pipeline</div>
              <div className="text-sm text-ink">{preview.pipeline_name}</div>
              <div className="text-xs text-dim">{preview.project_name}</div>
            </div>
            <div className="bg-canvas border border-edge rounded-lg p-3">
              <div className="text-xs font-semibold text-ink">DAG Airflow</div>
              <div className="text-sm text-ink">{preview.dag_criada ? '✅ Criada' : '— Não criada'}</div>
            </div>
            <div className="bg-canvas border border-edge rounded-lg p-3">
              <div className="text-xs font-semibold text-ink">Status</div>
              <div className="text-sm text-ink">{preview.active ? '🟢 Ativo' : '🔴 Inativo'}</div>
            </div>
            <div className="sm:col-span-3">
              <Button variant="danger" onClick={() => { setTyped(''); setWizard(true) }}><Trash2 size={14} /> Excluir Pipeline</Button>
            </div>
          </div>
        )}
      </div>

      {result && (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge bg-canvas/50 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-500" />
            <span className="text-xs font-medium text-ink">Resultado</span>
          </div>
          <pre className="text-xs text-dim p-4 overflow-auto max-h-48 whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}

      {/* Wizard: digitar nome para confirmar */}
      {wizard && preview && (
        <Modal open title="Confirmar Exclusão" onClose={() => setWizard(false)} size="sm">
          <div className="flex flex-col gap-4">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
              <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
              <p className="text-sm text-red-700 dark:text-red-300">Esta ação é irreversível. Para confirmar, digite o nome exato do pipeline.</p>
            </div>
            <Input
              label={`Digite: ${preview.pipeline_name}`}
              value={typed}
              onChange={e => setTyped(e.target.value)}
              placeholder={preview.pipeline_name}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setWizard(false)}>Cancelar</Button>
              <Button variant="danger" size="sm" onClick={del} loading={loading} disabled={typed.trim().toUpperCase() !== preview.pipeline_name.toUpperCase()}>Confirmar Exclusão</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Versões ─────────────────────────────────────────────────────
interface VersaoRow { id: number; versao: string; titulo: string; descricao_md?: string; criado_em?: string; criado_por?: string }
function VersoesTab() {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState({ versao: '', titulo: '', descricao_md: '' })
  const [previewMode, setPreviewMode] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<VersaoRow | null>(null)

  const { data, isLoading } = useQuery<{ data: VersaoRow[] }>({
    queryKey: ['versoes'],
    queryFn: () => apiFetch('/versao'),
  })

  const saveMut = useMutation({
    mutationFn: (v: { id?: number; versao: string; titulo: string; descricao_md: string }) =>
      apiFetch('/versao/register', {
        method: 'POST',
        body: JSON.stringify({ action: v.id ? 'update' : 'create', ...v }),
      }),
    onSuccess: () => {
      toast.success(editId ? 'Versão atualizada' : 'Versão criada')
      queryClient.invalidateQueries({ queryKey: ['versoes'] })
      closeForm()
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiFetch('/versao/register', { method: 'POST', body: JSON.stringify({ action: 'delete', id }) }),
    onSuccess: () => { toast.success('Versão removida'); queryClient.invalidateQueries({ queryKey: ['versoes'] }); setDeleteConfirm(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const openNew = () => { setEditId(null); setForm({ versao: '', titulo: '', descricao_md: '' }); setPreviewMode(false); setShowForm(true) }
  const openEdit = (v: VersaoRow) => { setEditId(v.id); setForm({ versao: v.versao, titulo: v.titulo, descricao_md: v.descricao_md ?? '' }); setPreviewMode(false); setShowForm(true) }
  const closeForm = () => { setShowForm(false); setEditId(null) }

  const toggleExpand = (id: number) => setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  const rows = data?.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-dim">Clique em uma versão para expandir. Edite o texto em markdown.</p>
        <Button size="sm" onClick={openNew}><Plus size={13} /> Nova Versão</Button>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-2">
          {rows.length === 0 && <div className="text-center py-10 text-sm text-dim bg-panel border border-edge rounded-lg">Nenhuma versão registrada.</div>}
          {rows.map(v => {
            const isOpen = expanded.has(v.id)
            return (
              <div key={v.id} className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm transition-shadow hover:shadow-md">
                <button onClick={() => toggleExpand(v.id)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-canvas/60 transition-colors">
                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-[#1A5FA8]/10 text-[#1A5FA8] dark:bg-blue-900/40 dark:text-blue-300 font-bold font-mono text-xs border border-[#1A5FA8]/20 dark:border-blue-700">v{v.versao}</span>
                  <span className="text-ink font-medium text-sm flex-1 text-left">{v.titulo}</span>
                  <span className="text-xs text-dim hidden sm:block">{(v.criado_em ?? '').substring(0, 10)} · {v.criado_por ?? 'admin'}</span>
                  {isOpen ? <ChevronUp size={14} className="text-dim shrink-0" /> : <ChevronDown size={14} className="text-dim shrink-0" />}
                </button>
                {isOpen && (
                  <div className="border-t border-edge px-4 py-4 bg-canvas/30">
                    {v.descricao_md ? <Markdown text={v.descricao_md} /> : <p className="text-sm text-dim italic">Sem descrição.</p>}
                    <div className="flex gap-2 pt-3 mt-3 border-t border-edge/50">
                      <Button variant="secondary" size="sm" onClick={() => openEdit(v)}><Edit2 size={12} /> Editar</Button>
                      <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(v)}><Trash2 size={12} className="text-red-500" /><span className="text-red-500">Excluir</span></Button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showForm && (
        <Modal open title={editId ? 'Editar Versão' : 'Nova Versão'} onClose={closeForm} size="lg">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <Input label="Versão" value={form.versao} onChange={e => setForm(f => ({ ...f, versao: e.target.value }))} placeholder="2.5.0" />
              <Input label="Título" value={form.titulo} onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))} />
            </div>
            <div>
              <div className="flex items-center gap-1 mb-2">
                <button onClick={() => setPreviewMode(false)} className={`px-3 py-1 text-xs rounded ${!previewMode ? 'bg-[#1A5FA8] text-white' : 'bg-canvas text-dim border border-edge'}`}>Editar</button>
                <button onClick={() => setPreviewMode(true)} className={`px-3 py-1 text-xs rounded flex items-center gap-1 ${previewMode ? 'bg-[#1A5FA8] text-white' : 'bg-canvas text-dim border border-edge'}`}><Eye size={12} /> Visualizar</button>
              </div>
              {previewMode ? (
                <div className="border border-edge rounded-md p-3 min-h-[10rem] bg-canvas/30">
                  {form.descricao_md.trim() ? <Markdown text={form.descricao_md} /> : <span className="text-xs text-dim">Nenhum conteúdo para visualizar.</span>}
                </div>
              ) : (
                <Textarea value={form.descricao_md} onChange={e => setForm(f => ({ ...f, descricao_md: e.target.value }))} rows={8} placeholder="## Novidades&#10;- Item 1&#10;- Item 2" />
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={closeForm}>Cancelar</Button>
              <Button onClick={() => saveMut.mutate({ id: editId ?? undefined, ...form })} loading={saveMut.isPending} disabled={!form.versao || !form.titulo}><Save size={13} /> Salvar</Button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Excluir Versão"
        message={`Remover a versão v${deleteConfirm?.versao} — "${deleteConfirm?.titulo}"? Esta ação é irreversível.`}
        danger confirmLabel="Excluir"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}

// ── Tipos de Job ────────────────────────────────────────────────
interface TipoJobRow { id: number; nome: string; descricao?: string; lineage_enabled: boolean; status: boolean }
function TiposJobTab() {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<{ id?: number; nome: string; descricao: string; status: boolean; lineage_enabled: boolean }>({ nome: '', descricao: '', status: true, lineage_enabled: true })
  const [deleteConfirm, setDeleteConfirm] = useState<TipoJobRow | null>(null)

  const { data, isLoading } = useQuery<{ job_types: TipoJobRow[] }>({
    queryKey: ['tipos-job'],
    queryFn: () => apiFetch('/catalogo', { method: 'POST', body: JSON.stringify({ mode: 'list_job_types', include_inactive: true }) }),
  })

  const saveMut = useMutation({
    mutationFn: (f: typeof form) => apiFetch('/catalogo', {
      method: 'POST',
      body: JSON.stringify({ mode: 'save_job_type', data: { id: f.id ?? null, nome: f.nome, descricao: f.descricao, status: f.status, lineage_enabled: f.lineage_enabled } }),
    }),
    onSuccess: () => { toast.success('Tipo de job salvo'); queryClient.invalidateQueries({ queryKey: ['tipos-job'] }); setShowForm(false) },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiFetch('/catalogo', { method: 'POST', body: JSON.stringify({ mode: 'delete_job_type', id }) }),
    onSuccess: () => { toast.success('Tipo removido'); queryClient.invalidateQueries({ queryKey: ['tipos-job'] }); setDeleteConfirm(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const openNew = () => { setForm({ nome: '', descricao: '', status: true, lineage_enabled: true }); setShowForm(true) }
  const openEdit = (t: TipoJobRow) => { setForm({ id: t.id, nome: t.nome, descricao: t.descricao ?? '', status: t.status, lineage_enabled: t.lineage_enabled }); setShowForm(true) }

  const rows = data?.job_types ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-dim">{rows.length} tipos cadastrados</span>
        <Button size="sm" onClick={openNew}><Plus size={13} /> Novo Tipo</Button>
      </div>
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                <th className="px-4 py-2.5 text-left font-semibold">Lineage</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-ink">{t.nome}</td>
                  <td className="px-4 py-2.5 text-xs text-dim">{t.descricao}</td>
                  <td className="px-4 py-2.5"><Badge value={t.lineage_enabled ? 'sim' : 'não'} /></td>
                  <td className="px-4 py-2.5"><Badge value={t.status ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(t)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDeleteConfirm(t)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-xs text-dim">Nenhum tipo de job cadastrado.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal open title={form.id ? 'Editar Tipo de Job' : 'Novo Tipo de Job'} onClose={() => setShowForm(false)}>
          <div className="flex flex-col gap-4">
            <Input label="Nome" value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} autoFocus />
            <Input label="Descrição" value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Status" value={form.status ? '1' : '0'} onChange={e => setForm(f => ({ ...f, status: e.target.value === '1' }))}>
                <option value="1">Ativo</option>
                <option value="0">Inativo</option>
              </Select>
              <label className="flex items-center gap-2 text-sm text-ink mt-6">
                <input type="checkbox" checked={form.lineage_enabled} onChange={e => setForm(f => ({ ...f, lineage_enabled: e.target.checked }))} />
                Lineage habilitado
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
              <Button onClick={() => saveMut.mutate(form)} loading={saveMut.isPending} disabled={!form.nome.trim()}><Save size={13} /> Salvar</Button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Excluir Tipo de Job"
        message={`Excluir o tipo "${deleteConfirm?.nome}"? Pipelines já cadastrados não serão afetados.`}
        danger confirmLabel="Excluir"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}

// ── Agendamento ─────────────────────────────────────────────────
interface CalendarioRow { calendario_nome: string; datas: number; proxima?: string | null }
interface BlackoutRow { id: number; inicio: string; fim?: string; escopo?: string | null; motivo?: string; ativo: number; vigente: number }
function AgendamentoTab() {
  const [freezeLoading, setFreezeLoading] = useState(false)
  const [calNome, setCalNome] = useState(''); const [calDatas, setCalDatas] = useState(''); const [calDesc, setCalDesc] = useState('')
  const [blk, setBlk] = useState({ inicio: '', fim: '', escopo: '', motivo: '' })
  const [freezeConfirm, setFreezeConfirm] = useState<'congelar' | 'descongelar' | null>(null)
  const [delCal, setDelCal] = useState<string | null>(null)
  const [viewCal, setViewCal] = useState<string | null>(null)

  const { data: cal } = useQuery<{ calendarios: CalendarioRow[] }>({ queryKey: ['calendarios'], queryFn: () => apiFetch('/agenda/calendarios') })
  const { data: bo } = useQuery<{ blackouts: BlackoutRow[]; ambiente_congelado: boolean }>({ queryKey: ['blackouts'], queryFn: () => apiFetch('/agenda/blackouts?incluir_historico=1') })
  const { data: calDatasView } = useQuery<{ datas: { data: string; descricao?: string }[] }>({
    queryKey: ['cal-datas', viewCal], queryFn: () => apiFetch(`/agenda/calendarios/${encodeURIComponent(viewCal!)}`), enabled: !!viewCal,
  })

  const freeze = async (acao: 'congelar' | 'descongelar') => {
    setFreezeLoading(true)
    try {
      await apiFetch('/admin/freeze', { method: 'POST', body: JSON.stringify({ acao }) })
      toast.success(acao === 'congelar' ? '❄ Ambiente congelado' : '✓ Ambiente descongelado')
      queryClient.invalidateQueries({ queryKey: ['blackouts'] })
    } catch (e: any) { toast.error(e.message) } finally { setFreezeLoading(false) }
  }

  const addCal = useMutation({
    mutationFn: () => apiFetch('/agenda/calendarios', { method: 'POST', body: JSON.stringify({ calendario_nome: calNome, datas: calDatas.split('\n').map(d => d.trim()).filter(Boolean), descricao: calDesc || undefined }) }),
    onSuccess: () => { toast.success('Calendário atualizado'); queryClient.invalidateQueries({ queryKey: ['calendarios'] }); setCalNome(''); setCalDatas(''); setCalDesc('') },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteCal = useMutation({
    mutationFn: (nome: string) => apiFetch(`/agenda/calendarios/${encodeURIComponent(nome)}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Calendário removido'); queryClient.invalidateQueries({ queryKey: ['calendarios'] }); setDelCal(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const addBlk = useMutation({
    mutationFn: () => apiFetch('/agenda/blackouts', { method: 'POST', body: JSON.stringify({ inicio: blk.inicio.replace('T', ' '), fim: blk.fim.replace('T', ' '), escopo: blk.escopo || undefined, motivo: blk.motivo }) }),
    onSuccess: () => { toast.success('Blackout criado'); queryClient.invalidateQueries({ queryKey: ['blackouts'] }); setBlk({ inicio: '', fim: '', escopo: '', motivo: '' }) },
    onError: (e: any) => toast.error(e.message),
  })

  const encerrarBlackout = (id: number) =>
    apiFetch(`/agenda/blackouts/${id}/encerrar`, { method: 'POST', body: JSON.stringify({}) })
      .then(() => { toast.success('Janela encerrada'); queryClient.invalidateQueries({ queryKey: ['blackouts'] }) })
      .catch((e: any) => toast.error(e.message))

  const congelado = bo?.ambiente_congelado
  const blackouts = (bo?.blackouts ?? []).filter(b => b.motivo !== 'Congelamento manual do ambiente')

  const dateValid = (s: string) => s.split('\n').map(d => d.trim()).filter(Boolean).every(d => /^\d{4}-\d{2}-\d{2}$/.test(d))

  return (
    <div className="flex flex-col gap-5">
      {/* Freeze */}
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Congelamento de Ambiente</h3>
        <div className="flex items-center gap-4">
          <Badge value={congelado ? 'error' : 'success'}>{congelado ? '❄ CONGELADO' : '✓ ATIVO'}</Badge>
          <span className="text-xs text-dim">{congelado ? 'Execuções bloqueadas.' : 'Operação normal.'}</span>
          {congelado
            ? <Button variant="secondary" onClick={() => setFreezeConfirm('descongelar')} loading={freezeLoading}>Descongelar</Button>
            : <Button variant="danger" onClick={() => setFreezeConfirm('congelar')} loading={freezeLoading}>❄ Congelar Ambiente</Button>}
        </div>
      </div>

      {/* Calendários */}
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Calendários de Bloqueio</h3>
        <div className="flex flex-col gap-1.5 mb-4">
          {(cal?.calendarios ?? []).length === 0 && <p className="text-xs text-dim">Nenhum calendário cadastrado.</p>}
          {(cal?.calendarios ?? []).map(c => (
            <div key={c.calendario_nome} className="flex items-center gap-3 text-xs py-1 border-b border-edge/40 last:border-0">
              <span className="font-mono font-medium text-[#1A5FA8] dark:text-blue-400">{c.calendario_nome}</span>
              <span className="text-dim">{c.datas} datas</span>
              {c.proxima && <span className="text-dim">próxima: <span className="text-ink">{c.proxima}</span></span>}
              <div className="ml-auto flex items-center gap-1">
                <button onClick={() => setViewCal(c.calendario_nome)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Ver datas"><Calendar size={13} /></button>
                <button onClick={() => setDelCal(c.calendario_nome)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir calendário"><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end border-t border-edge pt-3">
          <Input label="Nome do Calendário" value={calNome} onChange={e => setCalNome(e.target.value)} className="w-44" list="cal-nomes" />
          <datalist id="cal-nomes">{(cal?.calendarios ?? []).map(c => <option key={c.calendario_nome} value={c.calendario_nome} />)}</datalist>
          <Textarea label="Datas (uma por linha YYYY-MM-DD)" value={calDatas} onChange={e => setCalDatas(e.target.value)} className="w-52" rows={3} error={calDatas && !dateValid(calDatas) ? 'Use AAAA-MM-DD' : undefined} />
          <Input label="Descrição" value={calDesc} onChange={e => setCalDesc(e.target.value)} className="w-48" />
          <Button onClick={() => addCal.mutate()} loading={addCal.isPending} disabled={!calNome || !calDatas || !dateValid(calDatas)}><Plus size={13} /> Adicionar / Atualizar</Button>
        </div>
      </div>

      {/* Blackouts */}
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Janelas de Blackout</h3>
        <div className="flex flex-col gap-2 mb-4">
          {blackouts.length === 0 && <span className="text-xs text-dim">Nenhuma janela de blackout.</span>}
          {blackouts.map(b => (
            <div key={b.id} className="flex items-center gap-3 text-xs py-1.5 border-b border-edge/40 last:border-0">
              <Badge value={b.vigente ? 'warning' : b.ativo ? 'info' : 'neutral'}>{b.vigente ? 'vigente' : b.ativo ? 'agendado' : 'encerrado'}</Badge>
              <span className="text-ink font-mono">{b.inicio} → {b.fim ?? '...'}</span>
              {b.escopo && <span className="text-dim">{b.escopo}</span>}
              {b.motivo && <span className="text-dim italic">{b.motivo}</span>}
              {!!b.ativo && <Button variant="ghost" size="sm" className="ml-auto" onClick={() => encerrarBlackout(b.id)}>Encerrar</Button>}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end border-t border-edge pt-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Início</label>
            <input type="datetime-local" value={blk.inicio} onChange={e => setBlk(b => ({ ...b, inicio: e.target.value }))} className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#1A5FA8]" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Fim</label>
            <input type="datetime-local" value={blk.fim} onChange={e => setBlk(b => ({ ...b, fim: e.target.value }))} className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#1A5FA8]" />
          </div>
          <Input label="Escopo (opcional)" value={blk.escopo} onChange={e => setBlk(b => ({ ...b, escopo: e.target.value }))} className="w-40" placeholder="global" />
          <Input label="Motivo" value={blk.motivo} onChange={e => setBlk(b => ({ ...b, motivo: e.target.value }))} className="w-48" />
          <Button onClick={() => addBlk.mutate()} loading={addBlk.isPending} disabled={!blk.inicio || !blk.fim || !blk.motivo}><Plus size={13} /> Nova Janela</Button>
        </div>
      </div>

      <ConfirmModal
        open={!!freezeConfirm}
        title={freezeConfirm === 'congelar' ? 'Congelar Ambiente' : 'Descongelar Ambiente'}
        message={freezeConfirm === 'congelar' ? 'Nenhuma DAG gerada iniciará execução até descongelar. Execuções em andamento não são interrompidas.' : 'As execuções voltam ao agendamento normal. Confirma?'}
        danger={freezeConfirm === 'congelar'}
        confirmLabel={freezeConfirm === 'congelar' ? '❄ Congelar' : 'Descongelar'}
        onConfirm={() => freezeConfirm && freeze(freezeConfirm)}
        onCancel={() => setFreezeConfirm(null)}
      />

      <ConfirmModal
        open={!!delCal}
        title="Excluir Calendário"
        message={`Excluir o calendário "${delCal}" inteiro? Pipelines que o utilizam deixarão de ter datas bloqueadas.`}
        danger confirmLabel="Excluir"
        onConfirm={() => delCal && deleteCal.mutate(delCal)}
        onCancel={() => setDelCal(null)}
      />

      {viewCal && (
        <Modal open title={`Calendário: ${viewCal}`} onClose={() => setViewCal(null)} size="sm">
          <div className="flex flex-col gap-1 max-h-80 overflow-auto">
            {(calDatasView?.datas ?? []).length === 0 && <span className="text-xs text-dim">Sem datas.</span>}
            {(calDatasView?.datas ?? []).map(d => (
              <div key={d.data} className="flex gap-3 text-xs py-1 border-b border-edge/40 last:border-0">
                <span className="font-mono text-ink">{d.data}</span>
                {d.descricao && <span className="text-dim">{d.descricao}</span>}
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Usuários & Perfis ───────────────────────────────────────────
interface UsuarioRow { matricula: string; perfil: string; primeiro_nome?: string; ultimo_nome?: string; email?: string; ativo: boolean; ultimo_login?: string }
interface PerfilRow { perfil_nome: string; descricao?: string; permissoes: string[] }
interface RoleMapRow { role_airflow: string; perfil_nome: string; ordem_prioridade: number; descricao?: string; ativo: number }
function UsuariosTab() {
  const [userForm, setUserForm] = useState({ matricula: '', perfil: 'consulta' })
  const [deleteUser, setDeleteUser] = useState<string | null>(null)
  // perfis: estado local de permissões editáveis por perfil
  const [permEdits, setPermEdits] = useState<Record<string, Set<string>>>({})
  const [newPerfil, setNewPerfil] = useState({ nome: '', descricao: '' })
  const [deletePerfil, setDeletePerfil] = useState<string | null>(null)
  // role map
  const [rmForm, setRmForm] = useState({ role_airflow: '', perfil_nome: '', ordem_prioridade: 99, descricao: '', ativo: true })
  const [deleteRm, setDeleteRm] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ usuarios: UsuarioRow[] }>({ queryKey: ['admin-usuarios'], queryFn: () => adminPost('user_list') })
  const { data: perfis } = useQuery<{ perfis: PerfilRow[] }>({ queryKey: ['admin-perfis'], queryFn: () => adminPost('perfil_list') })
  const { data: roleMap } = useQuery<{ dados: RoleMapRow[] }>({ queryKey: ['admin-rolemap'], queryFn: () => adminPost('role_map_list') })

  const userUpsert = useMutation({
    mutationFn: (p: { matricula: string; perfil: string }) => adminPost('user_upsert', { ...p, ativo: true }),
    onSuccess: () => { toast.success('Usuário salvo'); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }); setUserForm({ matricula: '', perfil: 'consulta' }) },
    onError: (e: any) => toast.error(e.message),
  })
  const userDelete = useMutation({
    mutationFn: (matricula: string) => adminPost('user_delete', { matricula }),
    onSuccess: () => { toast.success('Usuário removido'); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }); setDeleteUser(null) },
    onError: (e: any) => toast.error(e.message),
  })
  const perfilSave = useMutation({
    mutationFn: (p: { perfil_nome: string; permissoes?: string[]; descricao?: string }) => adminPost('perfil_upsert', p),
    onSuccess: (_, v) => { toast.success(`Perfil "${v.perfil_nome}" salvo`); queryClient.invalidateQueries({ queryKey: ['admin-perfis'] }); setPermEdits(prev => { const n = { ...prev }; delete n[v.perfil_nome]; return n }); setNewPerfil({ nome: '', descricao: '' }) },
    onError: (e: any) => toast.error(e.message),
  })
  const perfilDelete = useMutation({
    mutationFn: (perfil_nome: string) => adminPost('perfil_delete', { perfil_nome }),
    onSuccess: () => { toast.success('Perfil removido'); queryClient.invalidateQueries({ queryKey: ['admin-perfis'] }); setDeletePerfil(null) },
    onError: (e: any) => toast.error(e.message),
  })
  const rmSave = useMutation({
    mutationFn: (p: typeof rmForm) => adminPost('role_map_upsert', p),
    onSuccess: () => { toast.success('Mapeamento salvo'); queryClient.invalidateQueries({ queryKey: ['admin-rolemap'] }); setRmForm({ role_airflow: '', perfil_nome: '', ordem_prioridade: 99, descricao: '', ativo: true }) },
    onError: (e: any) => toast.error(e.message),
  })
  const rmDelete = useMutation({
    mutationFn: (role_airflow: string) => adminPost('role_map_delete', { role_airflow }),
    onSuccess: () => { toast.success('Mapeamento removido'); queryClient.invalidateQueries({ queryKey: ['admin-rolemap'] }); setDeleteRm(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const perfilOpts = perfis?.perfis ?? []
  const perfilNames = perfilOpts.length ? perfilOpts.map(p => p.perfil_nome) : ['admin', 'operador', 'consulta']
  const usuarios = data?.usuarios ?? []

  // helpers de permissão
  const permSet = (p: PerfilRow): Set<string> => permEdits[p.perfil_nome] ?? new Set(p.permissoes ?? [])
  const togglePerm = (perfil: string, rec: string, base: string[]) => {
    setPermEdits(prev => {
      const cur = new Set(prev[perfil] ?? base)
      cur.has(rec) ? cur.delete(rec) : cur.add(rec)
      return { ...prev, [perfil]: cur }
    })
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Usuários */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Usuários</h3>
        {isLoading ? <PageSpinner /> : (
          <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                  <th className="px-4 py-2.5 text-left font-semibold">Matrícula</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Perfil</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Último Login</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Ativo</th>
                  <th className="px-4 py-2.5 w-20"></th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map(u => (
                  <tr key={u.matricula} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs font-medium text-[#1A5FA8] dark:text-blue-400">{u.matricula}</td>
                    <td className="px-4 py-2.5 text-xs text-ink">{[u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || '—'}</td>
                    <td className="px-4 py-2.5"><Badge value={u.perfil} /></td>
                    <td className="px-4 py-2.5 text-xs text-dim">{u.ultimo_login ?? '—'}</td>
                    <td className="px-4 py-2.5 text-xs">{u.ativo ? '✓' : <span className="text-red-500">✕</span>}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => setUserForm({ matricula: u.matricula, perfil: u.perfil })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                        <button onClick={() => setDeleteUser(u.matricula)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Remover"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {usuarios.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-xs text-dim">Nenhum usuário — entram automaticamente no 1º login.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Matrícula" value={userForm.matricula} onChange={e => setUserForm(f => ({ ...f, matricula: e.target.value.toUpperCase() }))} className="w-40" placeholder="C123456" />
          <Select label="Perfil" value={userForm.perfil} onChange={e => setUserForm(f => ({ ...f, perfil: e.target.value }))} className="w-40">
            {perfilNames.map(p => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Button onClick={() => userUpsert.mutate(userForm)} loading={userUpsert.isPending} disabled={!userForm.matricula.trim()}><Plus size={13} /> Adicionar / Atualizar</Button>
        </div>
      </div>

      {/* Perfis e permissões */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Perfis e Permissões</h3>
        <div className="flex flex-col gap-3">
          {(perfis?.perfis ?? []).map(p => {
            const base = p.permissoes ?? []
            const set = permSet(p)
            const dirty = !!permEdits[p.perfil_nome]
            const protegido = p.perfil_nome === 'admin' || p.perfil_nome === 'consulta'
            return (
              <div key={p.perfil_nome} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge value={p.perfil_nome} />
                    <span className="text-xs text-dim">{p.descricao}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" onClick={() => perfilSave.mutate({ perfil_nome: p.perfil_nome, permissoes: Array.from(set) })} loading={perfilSave.isPending} disabled={!dirty}><Save size={11} /> Salvar</Button>
                    {!protegido && <button onClick={() => setDeletePerfil(p.perfil_nome)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir perfil"><Trash2 size={13} /></button>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  {RBAC_RECURSOS.map(([rec, lbl]) => (
                    <label key={rec} className="flex items-center gap-1.5 text-xs text-ink cursor-pointer">
                      <input type="checkbox" checked={set.has(rec)} onChange={() => togglePerm(p.perfil_nome, rec, base)} />
                      {lbl}
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Novo perfil" value={newPerfil.nome} onChange={e => setNewPerfil(f => ({ ...f, nome: e.target.value.toLowerCase() }))} className="w-40" placeholder="ex: auditor" />
          <Input label="Descrição" value={newPerfil.descricao} onChange={e => setNewPerfil(f => ({ ...f, descricao: e.target.value }))} className="w-56" />
          <Button onClick={() => perfilSave.mutate({ perfil_nome: newPerfil.nome, descricao: newPerfil.descricao, permissoes: [] })} loading={perfilSave.isPending} disabled={!newPerfil.nome.trim()}><Plus size={13} /> Criar Perfil</Button>
        </div>
      </div>

      {/* Mapeamento Airflow Role → Perfil */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Mapeamento de Roles (Airflow → Perfil)</h3>
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">Role Airflow</th>
                <th className="px-4 py-2.5 text-left font-semibold">Perfil</th>
                <th className="px-4 py-2.5 text-center font-semibold">Prioridade</th>
                <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                <th className="px-4 py-2.5 text-center font-semibold">Ativo</th>
                <th className="px-4 py-2.5 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {(roleMap?.dados ?? []).map(r => (
                <tr key={r.role_airflow} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-xs text-ink">{r.role_airflow}</td>
                  <td className="px-4 py-2.5"><code className="text-xs text-[#1A5FA8] dark:text-blue-400">{r.perfil_nome}</code></td>
                  <td className="px-4 py-2.5 text-center text-xs text-dim">{r.ordem_prioridade}</td>
                  <td className="px-4 py-2.5 text-xs text-dim">{r.descricao}</td>
                  <td className="px-4 py-2.5 text-center text-xs">{r.ativo ? '✅' : '⏸'}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => setRmForm({ role_airflow: r.role_airflow, perfil_nome: r.perfil_nome, ordem_prioridade: r.ordem_prioridade, descricao: r.descricao ?? '', ativo: !!r.ativo })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDeleteRm(r.role_airflow)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Remover"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {(roleMap?.dados ?? []).length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-xs text-dim">Nenhum mapeamento cadastrado.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Role Airflow" value={rmForm.role_airflow} onChange={e => setRmForm(f => ({ ...f, role_airflow: e.target.value }))} className="w-44" />
          <Select label="Perfil" value={rmForm.perfil_nome} onChange={e => setRmForm(f => ({ ...f, perfil_nome: e.target.value }))} className="w-36">
            <option value="">selecione</option>
            {perfilNames.map(p => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Input label="Prioridade" type="number" value={String(rmForm.ordem_prioridade)} onChange={e => setRmForm(f => ({ ...f, ordem_prioridade: parseInt(e.target.value) || 99 }))} className="w-24" />
          <Input label="Descrição" value={rmForm.descricao} onChange={e => setRmForm(f => ({ ...f, descricao: e.target.value }))} className="w-44" />
          <label className="flex items-center gap-1.5 text-xs text-ink mb-2"><input type="checkbox" checked={rmForm.ativo} onChange={e => setRmForm(f => ({ ...f, ativo: e.target.checked }))} /> Ativo</label>
          <Button onClick={() => rmSave.mutate(rmForm)} loading={rmSave.isPending} disabled={!rmForm.role_airflow.trim() || !rmForm.perfil_nome}><Save size={13} /> Salvar Mapeamento</Button>
        </div>
      </div>

      <ConfirmModal open={!!deleteUser} title="Remover Usuário" message={`Remover "${deleteUser}"? Volta ao perfil "consulta" se logar novamente.`} danger confirmLabel="Remover" onConfirm={() => deleteUser && userDelete.mutate(deleteUser)} onCancel={() => setDeleteUser(null)} />
      <ConfirmModal open={!!deletePerfil} title="Excluir Perfil" message={`Excluir o perfil "${deletePerfil}"? Só é possível se nenhum usuário o utiliza.`} danger confirmLabel="Excluir" onConfirm={() => deletePerfil && perfilDelete.mutate(deletePerfil)} onCancel={() => setDeletePerfil(null)} />
      <ConfirmModal open={!!deleteRm} title="Remover Mapeamento" message={`Remover o mapeamento do role "${deleteRm}"?`} danger confirmLabel="Remover" onConfirm={() => deleteRm && rmDelete.mutate(deleteRm)} onCancel={() => setDeleteRm(null)} />
    </div>
  )
}

// ── Projetos ────────────────────────────────────────────────────
interface ProjectRow { project_name: string; ativo: boolean }

function ProjetosTab() {
  const [newName, setNewName] = useState('')
  const [delProject, setDelProject] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ projects: ProjectRow[] }>({
    queryKey: ['admin-projects-all'],
    queryFn: () => apiFetch('/pipelines/projects/all'),
  })

  const upsert = useMutation({
    mutationFn: (p: { project_name: string; ativo: number }) =>
      apiFetch('/pipelines/projects', { method: 'POST', body: JSON.stringify(p) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-projects-all'] }); queryClient.invalidateQueries({ queryKey: ['pipeline-projects'] }); setNewName('') },
    onError: (e: any) => toast.error(e.message),
  })

  const del = useMutation({
    mutationFn: (name: string) => apiFetch(`/pipelines/projects/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Projeto excluído'); queryClient.invalidateQueries({ queryKey: ['admin-projects-all'] }); queryClient.invalidateQueries({ queryKey: ['pipeline-projects'] }); setDelProject(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const projects = data?.projects ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-1">Projetos cadastrados</h3>
        <p className="text-xs text-dim mb-3">Projetos disponíveis em todas as telas de cadastro (Pipelines, Jobs, etc.). Inative para ocultar sem excluir.</p>

        {isLoading && <p className="text-xs text-dim">Carregando...</p>}
        {!isLoading && projects.length === 0 && <p className="text-xs text-dim">Nenhum projeto cadastrado.</p>}

        <div className="flex flex-col gap-1 mb-4">
          {projects.map(p => (
            <div key={p.project_name} className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-edge/30 text-sm border-b border-edge/40 last:border-0">
              <span className={`font-mono font-medium ${p.ativo ? 'text-ink' : 'text-dim line-through'}`}>{p.project_name}</span>
              <Badge value={p.ativo ? 'success' : 'neutral'}>{p.ativo ? 'ativo' : 'inativo'}</Badge>
              <div className="ml-auto flex items-center gap-1">
                {p.ativo ? (
                  <button
                    onClick={() => upsert.mutate({ project_name: p.project_name, ativo: 0 })}
                    title="Inativar"
                    className="text-slate-400 hover:text-amber-500 p-1 rounded text-xs"
                  >
                    <X size={13} />
                  </button>
                ) : (
                  <button
                    onClick={() => upsert.mutate({ project_name: p.project_name, ativo: 1 })}
                    title="Reativar"
                    className="text-slate-400 hover:text-green-500 p-1 rounded text-xs"
                  >
                    <CheckCircle2 size={13} />
                  </button>
                )}
                <button
                  onClick={() => setDelProject(p.project_name)}
                  title="Excluir"
                  className="text-slate-400 hover:text-red-500 p-1 rounded"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 items-end border-t border-edge pt-3">
          <Input
            label="Nome do Projeto"
            value={newName}
            onChange={e => setNewName(e.target.value.toUpperCase())}
            placeholder="ex: BI_CVP"
            className="w-48"
          />
          <Button
            onClick={() => upsert.mutate({ project_name: newName.trim(), ativo: 1 })}
            loading={upsert.isPending}
            disabled={!newName.trim()}
          >
            <Plus size={13} /> Adicionar Projeto
          </Button>
        </div>
      </div>

      <ConfirmModal
        open={!!delProject}
        title="Excluir Projeto"
        message={`Excluir o projeto "${delProject}"? Só é possível se não houver pipelines vinculados. Para ocultar, prefira inativar.`}
        danger
        confirmLabel="Excluir"
        onConfirm={() => delProject && del.mutate(delProject)}
        onCancel={() => setDelProject(null)}
      />
    </div>
  )
}

// ── Main ────────────────────────────────────────────────────────
// ── SLA Report Tab ───────────────────────────────────────────────────────────

interface SlaRow {
  pipeline: string
  project: string
  criticidade: string
  sla_minutos: number | null
  total_exec: number
  exec_sucesso: number
  exec_falha: number
  exec_estouro_sla: number
  aderencia_sla_pct: number | null
  avg_dur_minutos: number
  max_dur_minutos: number
  ultima_exec: string | null
}

interface SlaReportData {
  periodo: { ini: string; fim: string }
  resumo: { total_pipelines: number; pipelines_com_sla: number; aderencia_media_pct: number | null }
  data: SlaRow[]
}

function SlaReportTab() {
  const today = new Date().toISOString().slice(0, 10)
  const thirtyAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
  const [dateIni, setDateIni] = useState(thirtyAgo)
  const [dateFim, setDateFim] = useState(today)
  const [project, setProject] = useState('')
  const [enabled, setEnabled] = useState(false)

  const { data, isFetching, isError, error, refetch } = useQuery<SlaReportData>({
    queryKey: ['sla-report', dateIni, dateFim, project],
    queryFn: () => {
      const p = new URLSearchParams({ date_ini: dateIni, date_fim: dateFim })
      if (project) p.set('project', project)
      return apiFetch(`/execucoes/sla-report?${p}`)
    },
    enabled,
    staleTime: 60_000,
  })

  function exportCsv() {
    if (!data?.data.length) return
    const esc = (v: string | number | null) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const header = ['Pipeline','Projeto','Criticidade','SLA (min)','Execuções','Sucesso','Falha',
      'Estouro SLA','Aderência %','Dur. Média (min)','Dur. Máx (min)','Última exec']
    const rows = data.data.map(r => [
      r.pipeline, r.project, r.criticidade, r.sla_minutos ?? '',
      r.total_exec, r.exec_sucesso, r.exec_falha, r.exec_estouro_sla,
      r.aderencia_sla_pct ?? 'N/A', r.avg_dur_minutos, r.max_dur_minutos, r.ultima_exec ?? '',
    ].map(esc).join(','))
    const csv = '﻿' + [header.map(esc).join(','), ...rows].join('\r\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = `sla_aderencia_${dateIni}_${dateFim}.csv`
    a.click()
  }

  const critColor = (c: string) => {
    const u = c.toUpperCase()
    if (u === 'ALTA' || u === 'CRITICA') return 'text-red-600 dark:text-red-400'
    if (u === 'MEDIA') return 'text-amber-600 dark:text-amber-400'
    return 'text-green-600 dark:text-green-400'
  }

  const adColor = (pct: number | null) => {
    if (pct === null) return 'text-dim'
    if (pct >= 95) return 'text-green-600 dark:text-green-400 font-semibold'
    if (pct >= 80) return 'text-amber-600 dark:text-amber-400 font-semibold'
    return 'text-red-600 dark:text-red-400 font-semibold'
  }

  const inputCls = 'border border-edge bg-canvas text-ink text-xs rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#1A5FA8]/40'

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-semibold text-ink">Aderência ao SLA</h2>
        <p className="text-xs text-dim mt-0.5">Percentual de pipelines entregues dentro do SLA no período selecionado.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex flex-col gap-0.5">
          <label className="text-[10px] text-dim uppercase tracking-wide">De</label>
          <input type="date" value={dateIni} onChange={e => setDateIni(e.target.value)} className={inputCls} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[10px] text-dim uppercase tracking-wide">Até</label>
          <input type="date" value={dateFim} onChange={e => setDateFim(e.target.value)} className={inputCls} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[10px] text-dim uppercase tracking-wide">Projeto</label>
          <input placeholder="Todos" value={project} onChange={e => setProject(e.target.value)} className={`${inputCls} w-32`} />
        </div>
        <Button size="sm" onClick={() => { setEnabled(true); refetch() }} disabled={isFetching}>
          {isFetching ? 'Carregando…' : 'Gerar relatório'}
        </Button>
        {data && (
          <Button size="sm" variant="secondary" onClick={exportCsv}>
            <Download size={12} /> Exportar CSV
          </Button>
        )}
      </div>

      {isError && (
        <div className="text-sm text-red-600 border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 rounded px-3 py-2">
          Erro: {(error as Error)?.message}
        </div>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div className="flex flex-wrap gap-2">
            {[
              { label: String(data.resumo.total_pipelines), sub: 'pipelines analisados' },
              { label: String(data.resumo.pipelines_com_sla), sub: 'com SLA definido' },
              {
                label: data.resumo.aderencia_media_pct != null ? `${data.resumo.aderencia_media_pct}%` : 'N/A',
                sub: 'aderência média ao SLA',
              },
            ].map(s => (
              <div key={s.sub} className="bg-panel border border-edge rounded px-3 py-2 flex items-center gap-2">
                <strong className="text-ink text-sm font-bold">{s.label}</strong>
                <span className="text-dim text-xs">{s.sub}</span>
              </div>
            ))}
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-canvas border-b border-edge">
                <tr>
                  {['Pipeline','Projeto','Crit.','SLA','Execuções','Sucesso','Falha','Estouro','Aderência','Dur. Méd.','Dur. Máx.'].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-dim font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.data.map(r => (
                  <tr key={r.pipeline} className="border-b border-edge/50 hover:bg-canvas transition-colors">
                    <td className="px-2 py-1.5 font-mono text-ink text-[11px]">{r.pipeline}</td>
                    <td className="px-2 py-1.5 text-dim">{r.project}</td>
                    <td className={`px-2 py-1.5 font-semibold text-[10px] ${critColor(r.criticidade)}`}>{r.criticidade}</td>
                    <td className="px-2 py-1.5 text-dim">{r.sla_minutos != null ? `${r.sla_minutos}min` : '—'}</td>
                    <td className="px-2 py-1.5 text-center">{r.total_exec}</td>
                    <td className="px-2 py-1.5 text-center text-green-600 dark:text-green-400">{r.exec_sucesso}</td>
                    <td className="px-2 py-1.5 text-center text-red-500">{r.exec_falha || '—'}</td>
                    <td className="px-2 py-1.5 text-center text-amber-600">{r.exec_estouro_sla || '—'}</td>
                    <td className={`px-2 py-1.5 text-center ${adColor(r.aderencia_sla_pct)}`}>
                      {r.aderencia_sla_pct != null ? `${r.aderencia_sla_pct}%` : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-center text-dim">{r.avg_dur_minutos}min</td>
                    <td className="px-2 py-1.5 text-center text-dim">{r.max_dur_minutos}min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── Power BI — Guia de Acessos ───────────────────────────────────
interface PbiLayer {
  num: string
  titulo: string
  paraQueServe: React.ReactNode
  dependencias: React.ReactNode
  somenteLeitura: React.ReactNode
  escrita?: React.ReactNode
  recomendacao: React.ReactNode
  endpoints: string
  exigePremium: boolean
}

const PBI_LAYERS: PbiLayer[] = [
  {
    num: '1',
    titulo: 'Admin API',
    paraQueServe: (
      <>
        Ver <strong>todo o tenant</strong> (~100+ workspaces) sem depender de alguém convidar
        manualmente o service principal em cada um. Hoje, se um workspace novo é criado e ninguém
        adiciona o SP como membro, o ORQUESTRA simplesmente não o vê. Com a Admin API, o inventário
        passa a ser automático: descobre workspaces/datasets/reports/dataflows/apps novos, identifica
        quem é o dono de cada um e ajuda a achar "órfãos" (sem responsável claro).
      </>
    ),
    dependencias: (
      <>
        <strong>Pré-requisito único, sem custo:</strong> Fase A do runbook abaixo — (1) consentimento de
        admin no Azure AD para a permissão <code>Tenant.Read.All</code> e (2) o toggle "Allow service
        principals to use Power BI APIs" no Admin Portal, com o grupo de segurança do service principal
        adicionado. Não depende de capacidade Premium — funciona em qualquer licenciamento.
      </>
    ),
    somenteLeitura: (
      <>
        Listar tudo (workspaces, datasets, reports, dataflows, apps, capacities), ver detalhes de cada
        item e quem tem acesso a cada dataset/report. <strong>Não</strong> permite mover workspace de
        capacidade, restaurar workspace excluído nem alterar nada.
      </>
    ),
    escrita: (
      <>
        Com <code>Tenant.ReadWrite.All</code> no Azure AD (em vez de <code>Tenant.Read.All</code>),
        endpoints de escrita da Admin API passam a responder: mover workspaces entre capacidades,
        restaurar workspace excluído, rotacionar chave de encriptação. Nenhum desses é necessário para
        o que o ORQUESTRA faz (sustentação/observabilidade).
      </>
    ),
    recomendacao: 'Pedir só leitura (Tenant.Read.All + "read-only admin APIs"). Não há necessidade de escrita.',
    endpoints: 'admin/groups, admin/datasets, admin/reports, admin/dataflows, admin/apps, admin/capacities, admin/datasets/{id}/users, admin/reports/{id}/users',
    exigePremium: false,
  },
  {
    num: '2',
    titulo: 'Activity Events API',
    paraQueServe: (
      <>
        Auditoria de uso real: saber quem abriu, exportou ou compartilhou cada relatório, quando e a
        partir de onde. Serve para detectar uso indevido, levantar relatórios "zumbis" (sem acesso há
        meses — candidatos a descontinuar) e responder rapidamente "quem acessou esse dado sensível".
      </>
    ),
    dependencias: (
      <>
        <strong>Mesmo gate da camada 1 (Fase A)</strong> — usa a mesma permissão{' '}
        <code>Tenant.Read.All</code> e o mesmo toggle de Admin API liberado para service principals.
        Não exige nenhuma configuração adicional além da Fase A já feita.
      </>
    ),
    somenteLeitura: 'É a única forma de uso que existe — um log de auditoria não tem operação de escrita.',
    recomendacao: 'Sempre leitura. Não há decisão a tomar aqui além de habilitar.',
    endpoints: "admin/activityevents?startDateTime=...&endDateTime=...",
    exigePremium: false,
  },
  {
    num: '3',
    titulo: 'Scanner API',
    paraQueServe: (
      <>
        Documentar automaticamente a <strong>lógica de negócio</strong> dentro dos modelos: toda
        fórmula DAX (medidas) e toda transformação M (Power Query) de cada dataset, sem precisar abrir
        o .pbix manualmente. Permite montar um catálogo de "de onde vem cada métrica" e mapear
        dependências entre datasets (lineage) — essencial para análise de impacto de mudança.
      </>
    ),
    dependencias: (
      <>
        <strong>Duas dependências, as duas obrigatórias:</strong> (1) a Fase A já feita — Scanner API é
        um endpoint <code>admin/*</code>, então usa o <em>mesmo gate</em> da camada 1 (sem ele, dá 401
        mesmo com Premium ativo); e (2) o workspace que será escaneado precisa estar atribuído a uma
        capacidade <strong>Premium, PPU ou Fabric</strong> (Capacity Admin verifica/atribui em Workspace
        → Settings → Premium). Ter só uma das duas não é suficiente — as duas precisam estar prontas.
      </>
    ),
    somenteLeitura: 'A Scanner API só lê metadados — não existe modo de escrita; nunca altera o modelo.',
    recomendacao: 'Sempre leitura. A decisão real de "dá pra usar" depende de checar as duas dependências acima, não só da capacidade.',
    endpoints: 'admin/workspaces/getInfo?datasetSchema=true&datasetExpressions=true&lineage=true&datasourceDetails=true (fluxo assíncrono: getInfo → scanStatus/{id} → scanResult/{id})',
    exigePremium: true,
  },
  {
    num: '4',
    titulo: 'XMLA Endpoint',
    paraQueServe: (
      <>
        Conectar ferramentas especializadas (Tabular Editor, DAX Studio, SSMS) direto no modelo do
        Power BI, como se fosse um banco de dados Analysis Services — visão completa de tabelas,
        relacionamentos, medidas, partições e diagnóstico de performance, em tempo real. Não é REST, é
        o protocolo TOM (Tabular Object Model).
      </>
    ),
    somenteLeitura: (
      <>
        Modo <strong>"Read Only"</strong>: consultar dados via DAX, ver metadados completos do modelo,
        diagnosticar performance de medidas (ex.: DAX Studio). Não permite alterar nada no modelo.
      </>
    ),
    escrita: (
      <>
        Modo <strong>"Read/Write"</strong>: tudo do Read Only, mais publicar alterações no modelo
        remotamente (ex.: editar uma medida no Tabular Editor e publicar sem passar pelo Power BI
        Desktop), gerenciar partições e fazer refresh incremental via XMLA.
      </>
    ),
    dependencias: (
      <>
        <strong>Independente da Fase A</strong> — XMLA não usa endpoints <code>admin/*</code>, então não
        precisa do gate de Admin API. Mas tem duas dependências próprias, as duas obrigatórias: (1)
        capacidade <strong>Premium/PPU/Fabric</strong> com o setting "XMLA Endpoint" mudado de "Off" para
        "Read Only" (ou "Read/Write") pelo Capacity Admin; e (2) o service principal precisa ser{' '}
        <strong>Member, Contributor ou Admin</strong> de cada workspace que será acessado — Viewer não
        basta para conectar via XMLA.
      </>
    ),
    recomendacao: 'Pedir "Read Only". O ORQUESTRA é ferramenta de sustentação/observação, não de edição remota de modelos.',
    endpoints: 'powerbi://api.powerbi.com/v1.0/myorg/{workspace}',
    exigePremium: true,
  },
  {
    num: '5',
    titulo: 'Execute Queries REST',
    paraQueServe: (
      <>
        Rodar uma consulta DAX pontual via API para validar se uma medida está calculando certo, sem
        abrir o relatório no navegador. Também permite testar Row-Level Security simulando um usuário
        específico (parâmetro <code>impersonatedUserName</code>) — útil para confirmar que a segurança
        de linha está funcionando como esperado antes de liberar o relatório.
      </>
    ),
    dependencias: (
      <>
        <strong>Independente da Fase A.</strong> Duas dependências próprias, as duas obrigatórias: (1)
        capacidade <strong>Premium/PPU/Fabric</strong> + tenant setting "Dataset Execute Queries REST
        API" habilitado pelo Power Platform/Fabric Administrator; e (2) permissão de{' '}
        <strong>Build</strong> do service principal no dataset específico (mesma exigência da camada 4,
        mas no nível do dataset em vez do workspace).
      </>
    ),
    somenteLeitura: 'Por natureza só avalia/lê expressões DAX — nunca grava dados de volta no dataset. Não existe modo de escrita aqui.',
    recomendacao: 'Seguro habilitar — não há risco de escrita envolvido.',
    endpoints: 'groups/{id}/datasets/{id}/executeQueries',
    exigePremium: true,
  },
]

interface PbiStep {
  responsavel: string
  texto: React.ReactNode
}

interface PbiPhase {
  id: string
  titulo: string
  subtitulo: string
  premium: boolean
  steps: PbiStep[]
}

const PBI_PHASES: PbiPhase[] = [
  {
    id: 'A',
    titulo: 'Fase A — Habilitar Admin API (camadas 1 e 2)',
    subtitulo: 'Sem custo de licença — só permissão.',
    premium: false,
    steps: [
      {
        responsavel: 'Global Admin / Privileged Role Admin do Azure AD',
        texto: (
          <>
            <strong>Azure AD — permissão de aplicação.</strong> No app registration já usado pelo
            ORQUESTRA (mesmo client_id/secret configurado em <code>powerbi_*</code>), ir em{' '}
            <em>API permissions → Add a permission → Power BI Service → Application permissions</em>.
            Selecionar <code>Tenant.Read.All</code> (somente leitura — suficiente para tudo da Fase A/B)
            ou <code>Tenant.ReadWrite.All</code> (só se formos escrever via admin API). Clicar{' '}
            <em>Grant admin consent for [tenant]</em> — só um Global Admin confirma esse consentimento.
          </>
        ),
      },
      {
        responsavel: 'Power Platform Administrator / Fabric Administrator',
        texto: (
          <>
            <strong>Power BI Admin Portal — liberar o service principal.</strong> Acessar{' '}
            app.powerbi.com → engrenagem → <em>Admin portal → Tenant settings → Developer settings</em>.
            Habilitar <em>"Allow service principals to use Power BI APIs"</em> e em "Specific security
            groups" adicionar o grupo do Azure AD que contém o service principal (criar o grupo se não
            existir). Repetir para <em>"Allow service principals to use read-only Power BI Admin APIs"</em>
            {' '}(mesmo grupo). Salvar — propagação pode levar até 15 min.
            <br />
            <span className="text-dim">
              Com isso, <code>/powerbi/status</code> no backend do ORQUESTRA deve reportar{' '}
              <code>admin_api_liberada: true</code>.
            </span>
          </>
        ),
      },
    ],
  },
  {
    id: 'B',
    titulo: 'Fase B — Scanner API / DAX e M (camada 3)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Capacity Admin',
        texto: (
          <>
            Os workspaces que queremos escanear precisam estar atribuídos a uma capacidade{' '}
            <strong>Premium, PPU ou Fabric</strong> (Admin Portal → Capacity settings, ou Workspace →
            Settings → Premium).
          </>
        ),
      },
      {
        responsavel: '— (nenhum toggle adicional)',
        texto: (
          <>
            A Scanner API usa o mesmo gate da Fase A. Uma vez liberada, já é possível chamar{' '}
            <code>admin/workspaces/getInfo</code> com <code>datasetExpressions=true</code>.
          </>
        ),
      },
    ],
  },
  {
    id: 'C',
    titulo: 'Fase C — XMLA Endpoint (camada 4)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Capacity Admin',
        texto: (
          <>
            <strong>Habilitar XMLA na capacidade.</strong> Admin Portal → Capacity settings →
            capacidade em questão → <em>XMLA Endpoint</em> → mudar de "Off" para{' '}
            <strong>"Read Only"</strong> (ou "Read/Write" só se formos editar modelo remotamente —
            não recomendado por ora).
          </>
        ),
      },
      {
        responsavel: 'Dono de cada workspace',
        texto: (
          <>
            <strong>Permissão de Build no workspace.</strong> O service principal precisa ser{' '}
            <em>Member, Contributor ou Admin</em> do workspace (não basta Viewer) para conectar via
            XMLA com ferramentas como Tabular Editor/DAX Studio.
          </>
        ),
      },
    ],
  },
  {
    id: 'D',
    titulo: 'Fase D — Execute Queries REST (camada 5, opcional)',
    subtitulo: 'Exige capacidade Premium, PPU ou Fabric.',
    premium: true,
    steps: [
      {
        responsavel: 'Power Platform / Fabric Administrator',
        texto: (
          <>
            <strong>Tenant setting.</strong> Admin Portal → Tenant settings →{' '}
            <em>"Dataset Execute Queries REST API"</em> → habilitar (pode restringir a grupo de
            segurança também).
          </>
        ),
      },
      {
        responsavel: 'Dono do dataset',
        texto: (
          <>
            <strong>Permissão de Build no dataset.</strong> Mesma exigência de Build da Fase C, mas em
            nível de dataset específico, se quisermos restringir mais.
          </>
        ),
      },
    ],
  },
]

function PowerBIAccessGuideTab() {
  return (
    <div className="flex flex-col gap-6">
      <div className="bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800 rounded-lg p-4">
        <p className="text-sm text-ink">
          Hoje o ORQUESTRA acessa o Power BI pela <strong>API padrão</strong> — escopo do service
          principal, limitado aos workspaces onde ele é membro. Para ter granularidade tenant-wide e
          ver a lógica interna dos modelos (DAX/M), faltam <strong>4 camadas</strong> de acesso abaixo,
          cada uma com um gate diferente. Esta página serve como referência para a conversa com o time
          de Infra/Segurança/Licenciamento.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {PBI_LAYERS.map((l) => (
          <div key={l.num} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-bold text-ink">
                <span className="text-dim mr-1.5">#{l.num}</span>{l.titulo}
              </h4>
              {l.exigePremium ? <Badge value="warning">Requer Premium/PPU/Fabric</Badge> : <Badge value="success">Sem custo de licença</Badge>}
            </div>

            <div className="mb-3">
              <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">Para que serve</p>
              <p className="text-sm text-ink leading-relaxed">{l.paraQueServe}</p>
            </div>

            <div className="mb-3 bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800 rounded-md p-3 flex gap-2">
              <AlertTriangle size={16} className="shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide mb-1">
                  Dependências para funcionar
                </p>
                <p className="text-sm text-ink leading-relaxed">{l.dependencias}</p>
              </div>
            </div>

            <div className={`grid gap-3 mb-3 ${l.escrita ? 'sm:grid-cols-2' : ''}`}>
              <div className="bg-canvas/50 border border-edge rounded-md p-3">
                <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">
                  <Badge value="success">Somente leitura</Badge> — o que conseguimos fazer
                </p>
                <p className="text-sm text-ink leading-relaxed mt-1.5">{l.somenteLeitura}</p>
              </div>
              {l.escrita && (
                <div className="bg-canvas/50 border border-edge rounded-md p-3">
                  <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">
                    <Badge value="warning">Leitura/Escrita</Badge> — o que mais poderá ser feito
                  </p>
                  <p className="text-sm text-ink leading-relaxed mt-1.5">{l.escrita}</p>
                </div>
              )}
            </div>

            <div className="mb-2">
              <p className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">Recomendação para o chamado</p>
              <p className="text-sm text-ink leading-relaxed">{l.recomendacao}</p>
            </div>

            <p className="text-xs text-dim font-mono mt-2 break-all">{l.endpoints}</p>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-bold text-ink mb-1">Passo a passo da solicitação (runbook de acesso)</h3>
        <p className="text-xs text-dim mb-3">
          Recomendação: peça a Fase A primeiro — é grátis, rápida (2 toggles + 1 consentimento) e já
          desbloqueia o inventário tenant-wide e a auditoria de uso real. As Fases B/C/D só valem a
          pena se já existir (ou estiver nos planos) capacidade Premium/PPU/Fabric.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {PBI_PHASES.map((phase) => (
          <div key={phase.id} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <h4 className="text-sm font-bold text-ink">{phase.titulo}</h4>
              {phase.premium ? <Badge value="warning">Requer Premium/PPU/Fabric</Badge> : <Badge value="success">Sem custo de licença</Badge>}
            </div>
            <p className="text-xs text-dim mb-3">{phase.subtitulo}</p>
            <ol className="flex flex-col gap-3">
              {phase.steps.map((step, i) => (
                <li key={i} className="flex gap-3">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-canvas border border-edge text-xs font-semibold text-dim flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <div className="flex-1">
                    <Badge value="info">{step.responsavel}</Badge>
                    <p className="text-sm text-ink mt-1.5 leading-relaxed">{step.texto}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Comunicados ──────────────────────────────────────────────────
interface ComunicadoRow {
  id: number; titulo: string; tipo: string; formato: string
  publico_tipo: string; publico_desc: string; criado_por: string
  criado_em: string; ativo: boolean; expira_em: string | null
  total: number; vistos: number; confirmados: number
}
interface DestinatarioRow {
  matricula: string; nome: string; perfil: string | null
  entregue_em: string | null; visto_em: string | null; confirmado_em: string | null
}

const TIPO_OPTS = [
  { v: 'info', label: 'Informação (azul)' },
  { v: 'success', label: 'Sucesso (verde)' },
  { v: 'warning', label: 'Aviso (âmbar)' },
  { v: 'error', label: 'Crítico (vermelho)' },
]

const pct = (n: number, d: number) => (d > 0 ? Math.round((n / d) * 100) : 0)

const COM_BAR: Record<string, string> = { info: 'bg-blue-600', success: 'bg-green-600', warning: 'bg-amber-600', error: 'bg-red-600' }
const COM_DOT: Record<string, string> = { info: 'bg-blue-500', success: 'bg-green-500', warning: 'bg-amber-500', error: 'bg-red-500' }

// Botão da barra de formatação Markdown.
function MdBtn({ onClick, title, children }: { onClick: () => void; title: string; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} title={title}
      className="px-1.5 py-1 rounded text-dim hover:text-ink hover:bg-edge/60 transition-colors flex items-center justify-center min-w-[26px]">
      {children}
    </button>
  )
}

// Pré-visualização ao vivo — espelha como o usuário verá (banner ou sininho+toast).
function ComunicadoPreview({ tipo, titulo, mensagem, formato }: { tipo: string; titulo: string; mensagem: string; formato: string }) {
  const tituloView = titulo.trim() || 'Título do comunicado'
  const html = renderMarkdown(mensagem.trim() || 'A prévia da mensagem aparece aqui conforme você escreve.')
  const bar = COM_BAR[tipo] ?? COM_BAR.info
  const dot = COM_DOT[tipo] ?? COM_DOT.info
  const mdClass = 'text-sm text-ink break-words [&_a]:text-blue-400 [&_ul]:list-disc [&_li]:list-disc [&_li]:ml-4 [&_strong]:font-semibold'

  if (formato === 'banner') {
    return (
      <div className="rounded-xl border border-edge overflow-hidden shadow-sm">
        <div className={`px-3 py-2 flex items-center gap-2 text-white ${bar}`}>
          <Megaphone size={14} className="shrink-0" />
          <span className="text-xs font-bold truncate">{tituloView}</span>
        </div>
        <div className="p-3 bg-panel">
          <div className={mdClass} dangerouslySetInnerHTML={{ __html: html }} />
          <div className="mt-3 flex justify-end">
            <span className="text-[10px] px-2.5 py-1 rounded bg-[#1A5FA8] text-white font-medium">Entendi</span>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="rounded-lg border border-edge bg-panel p-2 flex gap-2">
        <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <div className="min-w-0">
          <div className="text-xs font-medium text-ink flex items-center gap-1">
            <Megaphone size={11} className="text-dim shrink-0" />{tituloView}
          </div>
          <div className={`mt-0.5 ${mdClass} [&_*]:text-[11px] [&_*]:text-dim`} dangerouslySetInnerHTML={{ __html: html }} />
        </div>
      </div>
      <div className={`text-[11px] text-white rounded px-2 py-1 inline-flex items-center gap-1 w-fit max-w-full ${bar}`}>
        <span className="truncate">📢 {tituloView}</span>
      </div>
    </div>
  )
}

function ComunicadoDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ comunicado: ComunicadoRow & { mensagem: string }; destinatarios: DestinatarioRow[] }>({
    queryKey: ['comunicado-detail', id],
    queryFn: () => apiFetch(`/admin/comunicados/${id}`),
  })
  const dest = data?.destinatarios ?? []
  return (
    <Modal open onClose={onClose} title="Auditoria do comunicado" size="lg">
      {isLoading && <PageSpinner />}
      {data && (
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-sm font-semibold text-ink">{data.comunicado.titulo}</div>
            <div className="text-xs text-dim mt-1 whitespace-pre-line break-words">{data.comunicado.mensagem}</div>
            <div className="text-[11px] text-dim/70 mt-2">{data.comunicado.publico_desc} · por {data.comunicado.criado_por} · {data.comunicado.criado_em}</div>
          </div>
          <div className="overflow-auto max-h-[50vh] border border-edge rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-edge/30 sticky top-0">
                <tr className="text-left text-dim">
                  <th className="px-3 py-2 font-medium">Usuário</th>
                  <th className="px-3 py-2 font-medium">Perfil</th>
                  <th className="px-3 py-2 font-medium">Entregue</th>
                  <th className="px-3 py-2 font-medium">Visto</th>
                  <th className="px-3 py-2 font-medium">Confirmado</th>
                </tr>
              </thead>
              <tbody>
                {dest.map(d => (
                  <tr key={d.matricula} className="border-t border-edge/40">
                    <td className="px-3 py-1.5"><span className="text-ink">{d.nome}</span> <span className="text-dim/60">{d.matricula}</span></td>
                    <td className="px-3 py-1.5 text-dim">{d.perfil ?? '—'}</td>
                    <td className="px-3 py-1.5 text-dim">{d.entregue_em ?? '—'}</td>
                    <td className="px-3 py-1.5">{d.visto_em ? <span className="text-blue-400">{d.visto_em}</span> : <span className="text-dim/40">—</span>}</td>
                    <td className="px-3 py-1.5">{d.confirmado_em ? <span className="text-green-500">{d.confirmado_em}</span> : <span className="text-dim/40">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Modal>
  )
}

const EMPTY_COM = {
  titulo: '', mensagem: '', tipo: 'info', formato: 'simples', link: '',
  publico_tipo: 'todos', perfis: [] as string[], matriculas: [] as string[], expira_em: '',
}

function ComunicadosTab() {
  const [form, setForm] = useState(EMPTY_COM)
  const [userFilter, setUserFilter] = useState('')
  const [detailId, setDetailId] = useState<number | null>(null)
  const msgRef = useRef<HTMLTextAreaElement>(null)

  const { data: listData, isLoading } = useQuery<{ data: ComunicadoRow[] }>({
    queryKey: ['comunicados-admin'],
    queryFn: () => apiFetch('/admin/comunicados'),
  })
  const { data: perfilData } = useQuery<{ perfis: { perfil_nome: string }[] }>({
    queryKey: ['perfil_list_com'],
    queryFn: () => adminPost('perfil_list'),
  })
  const { data: userData } = useQuery<{ usuarios: { matricula: string; primeiro_nome: string | null; ultimo_nome: string | null; perfil: string; ativo: boolean }[] }>({
    queryKey: ['user_list_com'],
    queryFn: () => adminPost('user_list'),
    enabled: form.publico_tipo === 'usuarios',
  })

  const perfis = perfilData?.perfis ?? []
  const usuarios = (userData?.usuarios ?? []).filter(u => u.ativo)
  const filteredUsers = usuarios.filter(u =>
    !userFilter || `${u.matricula} ${u.primeiro_nome ?? ''} ${u.ultimo_nome ?? ''}`.toLowerCase().includes(userFilter.toLowerCase()))

  const create = useMutation({
    mutationFn: () => apiFetch<{ total_destinatarios: number }>('/admin/comunicados', { method: 'POST', body: JSON.stringify(form) }),
    onSuccess: (r) => {
      toast.success(`Comunicado enviado a ${r.total_destinatarios} usuário(s).`)
      setForm(EMPTY_COM); setUserFilter('')
      queryClient.invalidateQueries({ queryKey: ['comunicados-admin'] })
    },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao enviar comunicado'),
  })
  const toggle = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/comunicados/${id}/toggle`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['comunicados-admin'] }),
  })

  const togglePerfil = (p: string) => setForm(f => ({ ...f, perfis: f.perfis.includes(p) ? f.perfis.filter(x => x !== p) : [...f.perfis, p] }))
  const toggleUser = (m: string) => setForm(f => ({ ...f, matriculas: f.matriculas.includes(m) ? f.matriculas.filter(x => x !== m) : [...f.matriculas, m] }))

  // Editor Markdown — envolve a seleção ou prefixa a linha.
  function applyWrap(before: string, after: string, placeholder: string) {
    const ta = msgRef.current; if (!ta) return
    const s = ta.selectionStart ?? 0, e = ta.selectionEnd ?? 0
    const v = form.mensagem
    const sel = v.substring(s, e) || placeholder
    setForm(f => ({ ...f, mensagem: v.substring(0, s) + before + sel + after + v.substring(e) }))
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(s + before.length, s + before.length + sel.length) })
  }
  function applyLinePrefix(prefix: string) {
    const ta = msgRef.current; if (!ta) return
    const s = ta.selectionStart ?? 0
    const v = form.mensagem
    const ls = v.lastIndexOf('\n', s - 1) + 1
    setForm(f => ({ ...f, mensagem: v.substring(0, ls) + prefix + v.substring(ls) }))
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(s + prefix.length, s + prefix.length) })
  }

  const valid = form.titulo.trim() && form.mensagem.trim() &&
    (form.publico_tipo === 'todos' ||
      (form.publico_tipo === 'perfil' && form.perfis.length > 0) ||
      (form.publico_tipo === 'usuarios' && form.matriculas.length > 0))

  const rows = listData?.data ?? []

  return (
    <div className="flex flex-col gap-6">
      {/* Compositor */}
      <div className="bg-panel border border-edge rounded-lg p-5 shadow-sm flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Megaphone size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <h2 className="text-sm font-bold text-ink">Novo comunicado</h2>
        </div>

        <Input label="Título" value={form.titulo} maxLength={160}
          onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))}
          placeholder="Ex.: Nova política de geração de DAGs" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Select label="Severidade / cor" value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}>
            {TIPO_OPTS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
          </Select>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Formato</label>
            <div className="flex gap-1">
              {(['simples', 'banner'] as const).map(fm => (
                <button key={fm} type="button" onClick={() => setForm(f => ({ ...f, formato: fm }))}
                  className={`flex-1 px-2 py-1.5 rounded text-xs border transition-colors ${form.formato === fm ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]' : 'border-edge text-dim hover:bg-edge/40'}`}>
                  {fm === 'simples' ? 'Sininho + toast' : 'Pop-up banner'}
                </button>
              ))}
            </div>
          </div>
          <Input label="Link (opcional)" value={form.link}
            onChange={e => setForm(f => ({ ...f, link: e.target.value }))} placeholder="/pipelines" />
        </div>

        {/* Editor Markdown + pré-visualização ao vivo */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Mensagem (Markdown)</label>
            <div className="flex flex-wrap items-center gap-0.5 border border-edge border-b-0 rounded-t-md px-1.5 py-1 bg-canvas">
              <MdBtn onClick={() => applyLinePrefix('# ')}  title="Título grande"><span className="text-[11px] font-bold">H1</span></MdBtn>
              <MdBtn onClick={() => applyLinePrefix('## ')} title="Título médio"><span className="text-[11px] font-bold">H2</span></MdBtn>
              <span className="w-px h-4 bg-edge mx-1" />
              <MdBtn onClick={() => applyWrap('**', '**', 'negrito')} title="Negrito"><Bold size={13} /></MdBtn>
              <MdBtn onClick={() => applyWrap('*', '*', 'itálico')}   title="Itálico"><Italic size={13} /></MdBtn>
              <MdBtn onClick={() => applyWrap('`', '`', 'código')}    title="Código"><Code size={13} /></MdBtn>
              <MdBtn onClick={() => applyLinePrefix('- ')}            title="Lista"><List size={13} /></MdBtn>
            </div>
            <textarea ref={msgRef} value={form.mensagem} rows={7}
              onChange={e => setForm(f => ({ ...f, mensagem: e.target.value }))}
              placeholder="Texto do comunicado…  Selecione um trecho e use os botões para formatar."
              className="bg-panel border border-edge rounded-b-md px-3 py-2 text-sm text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y" />
            <span className="text-[10px] text-dim/60">Dica: **negrito**, *itálico*, `código`, # título, - item de lista.</span>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Pré-visualização — como o usuário verá</label>
            <div className="border border-edge rounded-md p-3 bg-canvas/40 min-h-[160px]">
              <ComunicadoPreview tipo={form.tipo} titulo={form.titulo} mensagem={form.mensagem} formato={form.formato} />
            </div>
          </div>
        </div>

        {/* Público-alvo */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-dim font-medium">Público-alvo</label>
          <div className="flex gap-1 mb-1">
            {([['todos', 'Todos'], ['perfil', 'Por perfil'], ['usuarios', 'Usuários específicos']] as const).map(([v, l]) => (
              <button key={v} type="button" onClick={() => setForm(f => ({ ...f, publico_tipo: v }))}
                className={`px-3 py-1.5 rounded text-xs border transition-colors ${form.publico_tipo === v ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]' : 'border-edge text-dim hover:bg-edge/40'}`}>
                {l}
              </button>
            ))}
          </div>
          {form.publico_tipo === 'perfil' && (
            <div className="flex flex-wrap gap-2 p-2 border border-edge rounded-lg">
              {perfis.map(p => (
                <label key={p.perfil_nome} className="flex items-center gap-1.5 text-xs text-ink cursor-pointer px-2 py-1 rounded hover:bg-edge/40">
                  <input type="checkbox" checked={form.perfis.includes(p.perfil_nome)} onChange={() => togglePerfil(p.perfil_nome)} />
                  {p.perfil_nome}
                </label>
              ))}
            </div>
          )}
          {form.publico_tipo === 'usuarios' && (
            <div className="border border-edge rounded-lg p-2">
              <Input placeholder="Filtrar por nome ou matrícula…" value={userFilter} onChange={e => setUserFilter(e.target.value)} className="mb-2" />
              <div className="max-h-44 overflow-y-auto flex flex-col gap-0.5">
                {filteredUsers.map(u => (
                  <label key={u.matricula} className="flex items-center gap-2 text-xs text-ink cursor-pointer px-2 py-1 rounded hover:bg-edge/40">
                    <input type="checkbox" checked={form.matriculas.includes(u.matricula)} onChange={() => toggleUser(u.matricula)} />
                    <span className="font-medium">{[u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || u.matricula}</span>
                    <span className="text-dim/60">{u.matricula}</span>
                    <Badge value={u.perfil} />
                  </label>
                ))}
                {filteredUsers.length === 0 && <div className="text-xs text-dim px-2 py-3 text-center">Nenhum usuário.</div>}
              </div>
              {form.matriculas.length > 0 && <div className="text-[11px] text-dim mt-1">{form.matriculas.length} selecionado(s)</div>}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-3">
          <Input label="Expira em (opcional)" type="date" value={form.expira_em}
            onChange={e => setForm(f => ({ ...f, expira_em: e.target.value }))} className="w-44" />
          <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!valid}>
            <Megaphone size={13} /> Enviar comunicado
          </Button>
        </div>
      </div>

      {/* Lista / auditoria */}
      <div>
        <h2 className="text-sm font-bold text-ink mb-2">Comunicados enviados</h2>
        {isLoading && <PageSpinner />}
        {!isLoading && rows.length === 0 && <div className="text-xs text-dim py-6 text-center">Nenhum comunicado enviado ainda.</div>}
        <div className="flex flex-col gap-2">
          {rows.map(c => (
            <div key={c.id} className="bg-panel border border-edge rounded-lg p-3 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-ink truncate">{c.titulo}</span>
                    <Badge value={c.tipo} />
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-edge text-dim">{c.formato === 'banner' ? 'banner' : 'simples'}</span>
                    {!c.ativo && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-500/20 text-slate-400">encerrado</span>}
                  </div>
                  <div className="text-[11px] text-dim mt-1">{c.publico_desc} · {c.criado_em} · por {c.criado_por}</div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button size="sm" variant="secondary" onClick={() => setDetailId(c.id)}><Eye size={12} /> Detalhes</Button>
                  <Button size="sm" variant={c.ativo ? 'danger' : 'secondary'} onClick={() => toggle.mutate(c.id)}>{c.ativo ? 'Encerrar' : 'Reativar'}</Button>
                </div>
              </div>
              <div className="flex items-center gap-4 mt-2 text-[11px]">
                <span className="text-dim">Entregues: <span className="text-ink font-semibold">{c.total}</span></span>
                <span className="text-dim">Vistos: <span className="text-blue-400 font-semibold">{c.vistos}</span> ({pct(c.vistos, c.total)}%)</span>
                <span className="text-dim">Confirmados: <span className="text-green-500 font-semibold">{c.confirmados}</span> ({pct(c.confirmados, c.total)}%)</span>
                <div className="flex-1 h-1.5 bg-edge/50 rounded-full overflow-hidden max-w-[160px]">
                  <div className="h-full bg-green-500" style={{ width: `${pct(c.confirmados, c.total)}%` }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {detailId != null && <ComunicadoDetail id={detailId} onClose={() => setDetailId(null)} />}
    </div>
  )
}

// ── Backlog ──────────────────────────────────────────────────────
interface BacklogItem {
  id: number; titulo: string; descricao: string | null; tipo: string; area: string | null
  prioridade: string; status: string; estimativa: string | null; responsavel: string | null
  ref_pr: string | null; tags: string | null; criado_por: string | null
  criado_em: string | null; atualizado_em: string | null; concluido_em: string | null
}
const BL_TIPOS = ['feature', 'bug', 'debt', 'spike']
const BL_AREAS = ['backend', 'frontend', 'datastage', 'deploy', 'infra', 'outro']
const BL_PRIOS = ['P0', 'P1', 'P2', 'P3']
const BL_STATUS: { v: string; label: string }[] = [
  { v: 'ideia', label: 'Ideia' },
  { v: 'refinado', label: 'Refinado' },
  { v: 'em_andamento', label: 'Em andamento' },
  { v: 'concluido', label: 'Concluído' },
  { v: 'descartado', label: 'Descartado' },
]
const BL_STATUS_CLS: Record<string, string> = {
  ideia: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  refinado: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  em_andamento: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  concluido: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  descartado: 'bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400',
}
const BL_PRIO_CLS: Record<string, string> = {
  P0: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  P1: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  P2: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  P3: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}
const EMPTY_BL = { titulo: '', descricao: '', tipo: 'feature', area: 'backend', prioridade: 'P2', status: 'ideia', estimativa: '', responsavel: '', ref_pr: '', tags: '' }

function BacklogForm({ initial, onClose }: { initial: Partial<BacklogItem>; onClose: () => void }) {
  const [f, setF] = useState<Record<string, string>>({ ...EMPTY_BL, ...Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, v == null ? '' : String(v)])) })
  const isEdit = !!initial?.id
  const set = (k: string) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const save = useMutation({
    mutationFn: () => isEdit
      ? apiFetch(`/backlog/${initial.id}`, { method: 'PATCH', body: JSON.stringify(f) })
      : apiFetch('/backlog', { method: 'POST', body: JSON.stringify(f) }),
    onSuccess: () => { toast.success(isEdit ? 'Item atualizado.' : 'Item criado.'); queryClient.invalidateQueries({ queryKey: ['backlog'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao salvar'),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar item de backlog' : 'Novo item de backlog'} size="lg">
      <div className="flex flex-col gap-3">
        <Input label="Título *" value={f.titulo} maxLength={200} onChange={set('titulo')} placeholder="Resumo curto do item" />
        <Textarea label="Descrição" rows={3} value={f.descricao} onChange={set('descricao')} placeholder="Contexto, critérios de aceite…" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Select label="Tipo" value={f.tipo} onChange={set('tipo')}>{BL_TIPOS.map(t => <option key={t} value={t}>{t}</option>)}</Select>
          <Select label="Área" value={f.area} onChange={set('area')}>{BL_AREAS.map(a => <option key={a} value={a}>{a}</option>)}</Select>
          <Select label="Prioridade" value={f.prioridade} onChange={set('prioridade')}>{BL_PRIOS.map(p => <option key={p} value={p}>{p}</option>)}</Select>
          <Select label="Status" value={f.status} onChange={set('status')}>{BL_STATUS.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}</Select>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <Input label="Estimativa" value={f.estimativa} onChange={set('estimativa')} placeholder="ex.: 2d, M" />
          <Input label="Responsável" value={f.responsavel} onChange={set('responsavel')} placeholder="matrícula/nome" />
          <Input label="Ref. PR" value={f.ref_pr} onChange={set('ref_pr')} placeholder="#54" />
        </div>
        <Input label="Tags" value={f.tags} onChange={set('tags')} placeholder="separadas por vírgula" />
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={save.isPending} disabled={!f.titulo.trim()} onClick={() => save.mutate()}>{isEdit ? 'Salvar' : 'Criar'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function BacklogTab() {
  const [filtros, setFiltros] = useState({ status: '', tipo: '', area: '', q: '' })
  const [form, setForm] = useState<Partial<BacklogItem> | null>(null)
  const [delItem, setDelItem] = useState<BacklogItem | null>(null)

  const { data, isLoading } = useQuery<{ data: BacklogItem[]; stats: Record<string, number>; total: number }>({
    queryKey: ['backlog', filtros],
    queryFn: () => {
      const p = new URLSearchParams()
      if (filtros.status) p.set('status', filtros.status)
      if (filtros.tipo) p.set('tipo', filtros.tipo)
      if (filtros.area) p.set('area', filtros.area)
      if (filtros.q) p.set('q', filtros.q)
      const qs = p.toString()
      return apiFetch(`/backlog${qs ? '?' + qs : ''}`)
    },
  })
  const items = data?.data ?? []
  const stats = data?.stats ?? {}

  const patchStatus = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiFetch(`/backlog/${v.id}`, { method: 'PATCH', body: JSON.stringify({ status: v.status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backlog'] }),
    onError: (e: Error) => toast.error(e?.message || 'Falha ao mudar status'),
  })
  const del = useMutation({
    mutationFn: (id: number) => apiFetch(`/backlog/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Item removido.'); setDelItem(null); queryClient.invalidateQueries({ queryKey: ['backlog'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })
  const hasFilter = filtros.status || filtros.tipo || filtros.area || filtros.q

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1.5 flex-wrap">
          {BL_STATUS.map(s => (
            <button key={s.v} onClick={() => setFiltros(x => ({ ...x, status: x.status === s.v ? '' : s.v }))}
              className={`px-2.5 py-1 rounded-lg text-xs border transition-all ${filtros.status === s.v ? 'border-[#1A5FA8] ring-1 ring-[#1A5FA8]/40' : 'border-edge'} ${BL_STATUS_CLS[s.v]}`}>
              {s.label}: <strong>{stats[s.v] ?? 0}</strong>
            </button>
          ))}
        </div>
        <Button onClick={() => setForm({})}><Plus size={14} /> Novo item</Button>
      </div>

      <div className="flex gap-2 flex-wrap items-end">
        <Input placeholder="Buscar título/descrição…" value={filtros.q} onChange={e => setFiltros(x => ({ ...x, q: e.target.value }))} className="w-56" />
        <Select value={filtros.tipo} onChange={e => setFiltros(x => ({ ...x, tipo: e.target.value }))} className="w-32"><option value="">Todo tipo</option>{BL_TIPOS.map(t => <option key={t} value={t}>{t}</option>)}</Select>
        <Select value={filtros.area} onChange={e => setFiltros(x => ({ ...x, area: e.target.value }))} className="w-36"><option value="">Toda área</option>{BL_AREAS.map(a => <option key={a} value={a}>{a}</option>)}</Select>
        {hasFilter && <Button variant="secondary" size="sm" onClick={() => setFiltros({ status: '', tipo: '', area: '', q: '' })}>Limpar</Button>}
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && items.length === 0 && <div className="text-xs text-dim py-8 text-center">Nenhum item no backlog.</div>}

      {items.length > 0 && (
        <div className="overflow-x-auto border border-edge rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-edge/30 text-dim">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Prio</th>
                <th className="px-3 py-2 font-medium">Tipo</th>
                <th className="px-3 py-2 font-medium">Título</th>
                <th className="px-3 py-2 font-medium">Área</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Resp.</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id} className="border-t border-edge/40 hover:bg-edge/20">
                  <td className="px-3 py-2"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${BL_PRIO_CLS[it.prioridade] ?? ''}`}>{it.prioridade}</span></td>
                  <td className="px-3 py-2 text-dim text-xs">{it.tipo}</td>
                  <td className="px-3 py-2 min-w-[220px]">
                    <div className="text-ink font-medium">{it.titulo}</div>
                    {it.descricao && <div className="text-[11px] text-dim line-clamp-1">{it.descricao}</div>}
                  </td>
                  <td className="px-3 py-2 text-dim text-xs">{it.area ?? '—'}</td>
                  <td className="px-3 py-2">
                    <select value={it.status} onChange={e => patchStatus.mutate({ id: it.id, status: e.target.value })}
                      className="text-[11px] rounded px-1.5 py-1 border border-edge bg-panel text-ink focus:outline-none focus:ring-1 focus:ring-blue-500">
                      {BL_STATUS.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-dim text-xs">{it.responsavel ?? '—'}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => setForm(it)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDelItem(it)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form !== null && <BacklogForm initial={form} onClose={() => setForm(null)} />}
      <ConfirmModal open={!!delItem} title="Remover item" danger confirmLabel="Remover"
        message={`Remover "${delItem?.titulo}" do backlog? Não pode ser desfeito.`}
        onConfirm={() => delItem && del.mutate(delItem.id)} onCancel={() => setDelItem(null)} />
    </div>
  )
}

// ── Servidor (diagnóstico) ───────────────────────────────────────
interface ServerDb { name: string; state: string; recovery: string; create_date: string | null; size_mb: number | null }

function ServidorTab() {
  const { data, isLoading, refetch, isFetching } = useQuery<{ sucesso: boolean; server: string | null; databases: ServerDb[]; total: number }>({
    queryKey: ['server_databases'],
    queryFn: () => adminPost('server_databases'),
  })
  const dbs = data?.databases ?? []
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <div>
            <h2 className="text-sm font-bold text-ink">Bancos do servidor</h2>
            <p className="text-xs text-dim mt-0.5">
              Lista os bancos do mesmo servidor SQL usando a credencial do ORQUESTRA (<code className="text-[11px]">sys.databases</code>).
              {data?.server && <> Servidor: <span className="font-mono text-ink">{data.server}</span></>}
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()} loading={isFetching}><RefreshCw size={13} /> Atualizar</Button>
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && dbs.length === 0 && (
        <div className="text-xs text-dim py-8 text-center">Nenhum banco retornado (ou a credencial não tem permissão para listar).</div>
      )}
      {dbs.length > 0 && (
        <>
          <div className="text-xs text-dim">{data?.total} banco(s) visível(is) com esta credencial.</div>
          <div className="overflow-x-auto border border-edge rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-edge/30 text-dim">
                <tr className="text-left">
                  <th className="px-3 py-2 font-medium">Banco</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">Recovery</th>
                  <th className="px-3 py-2 font-medium text-right">Tamanho (MB)</th>
                  <th className="px-3 py-2 font-medium">Criado em</th>
                </tr>
              </thead>
              <tbody>
                {dbs.map(d => (
                  <tr key={d.name} className="border-t border-edge/40 hover:bg-edge/20">
                    <td className="px-3 py-2 font-mono text-ink">{d.name}</td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${d.state === 'ONLINE'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}`}>{d.state}</span>
                    </td>
                    <td className="px-3 py-2 text-dim text-xs">{d.recovery}</td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums">{d.size_mb != null ? d.size_mb.toLocaleString('pt-BR') : '—'}</td>
                    <td className="px-3 py-2 text-dim text-xs">{d.create_date ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── Monitoramento de tabelas (observabilidade de dados) ──────────
interface MonitorSnapshot { total_linhas: number | null; ultima_data: string | null; last_write: string | null; qtde_ultimo_dia: number | null; por_dia: { dia: string; qtde: number }[]; captured_at: string | null; erro: string | null }
interface MonitorItem {
  id: number; database_name: string; schema_name: string; table_name: string; coluna_data: string
  coluna_atualizacao: string | null; criticidade: string | null; sla_horas: number | null; ativo: boolean; descricao: string | null
  snapshot: MonitorSnapshot | null
}
interface LiveResult { ok?: boolean; erro?: string; total_linhas?: number | null; ultima_data?: string | null; last_write?: string | null; qtde_ultimo_dia?: number | null; por_dia?: { dia: string; qtde: number }[] }

function freshness(ultima: string | null | undefined): { label: string; cls: string } {
  const red = 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
  if (!ultima) return { label: 'sem dados', cls: red }
  const d = ultima.substring(0, 10)
  const today = new Date().toLocaleDateString('en-CA')
  const yest = new Date(Date.now() - 86400000).toLocaleDateString('en-CA')
  if (d >= today) return { label: 'hoje', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' }
  if (d === yest) return { label: 'ontem', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' }
  return { label: `desde ${d.substring(8, 10)}/${d.substring(5, 7)}`, cls: red }
}

function Sparkbars({ data, h = 28 }: { data: { dia: string; qtde: number }[]; h?: number }) {
  if (!data?.length) return <span className="text-dim/50 text-xs">—</span>
  const max = Math.max(...data.map(d => d.qtde), 1)
  return (
    <div className="flex items-end gap-px" style={{ height: h }} title={data.map(d => `${d.dia}: ${d.qtde.toLocaleString('pt-BR')}`).join('\n')}>
      {data.slice(-40).map((d, i) => (
        <div key={i} className="w-1.5 bg-[#1A5FA8]/70 dark:bg-blue-400/70 rounded-sm" style={{ height: `${Math.max(3, (d.qtde / max) * 100)}%` }} />
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
      <div className="text-[10px] text-dim uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-ink mt-0.5 truncate">{value}</div>
    </div>
  )
}

function AddMonitorModal({ onClose }: { onClose: () => void }) {
  const [database, setDatabase] = useState('')
  const [sel, setSel] = useState<{ schema: string; tabela: string } | null>(null)
  const [colData, setColData] = useState('')
  const [colAtu, setColAtu] = useState('')
  const [crit, setCrit] = useState('')
  const [sla, setSla] = useState('')
  const [tableQ, setTableQ] = useState('')

  const dbsQ = useQuery<{ databases: { name: string }[] }>({ queryKey: ['server_databases'], queryFn: () => adminPost('server_databases') })
  const tabelasQ = useQuery<{ data: { schema: string; tabela: string; linhas: number }[] }>({
    queryKey: ['monitor-tabelas', database], enabled: !!database,
    queryFn: () => apiFetch(`/admin/monitor/tabelas?database=${encodeURIComponent(database)}`),
  })
  const colsQ = useQuery<{ data: { nome: string; tipo: string; is_data: boolean }[] }>({
    queryKey: ['monitor-colunas', database, sel?.schema, sel?.tabela], enabled: !!sel,
    queryFn: () => apiFetch(`/admin/monitor/colunas?database=${encodeURIComponent(database)}&schema=${encodeURIComponent(sel!.schema)}&tabela=${encodeURIComponent(sel!.tabela)}`),
  })
  const save = useMutation({
    mutationFn: () => apiFetch('/admin/monitor', { method: 'POST', body: JSON.stringify({
      database_name: database, schema_name: sel!.schema, table_name: sel!.tabela,
      coluna_data: colData, coluna_atualizacao: colAtu || undefined,
      criticidade: crit || undefined, sla_horas: sla || undefined,
    }) }),
    onSuccess: () => { toast.success('Tabela adicionada ao monitoramento.'); queryClient.invalidateQueries({ queryKey: ['monitor'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao adicionar'),
  })
  const tabelas = (tabelasQ.data?.data ?? []).filter(t => !tableQ || `${t.schema}.${t.tabela}`.toLowerCase().includes(tableQ.toLowerCase()))
  const cols = colsQ.data?.data ?? []
  const dateCols = cols.filter(c => c.is_data)

  return (
    <Modal open onClose={onClose} title="Adicionar tabela ao monitoramento" size="lg">
      <div className="flex flex-col gap-3">
        <Select label="1. Banco" value={database} onChange={e => { setDatabase(e.target.value); setSel(null); setColData('') }}>
          <option value="">Selecione…</option>
          {(dbsQ.data?.databases ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
        </Select>

        {database && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">2. Tabela {tabelasQ.isFetching && <span className="text-dim/60">(carregando…)</span>}</label>
            <Input placeholder="Filtrar tabela…" value={tableQ} onChange={e => setTableQ(e.target.value)} />
            <div className="max-h-48 overflow-y-auto border border-edge rounded-md mt-1">
              {tabelas.map(t => (
                <button key={`${t.schema}.${t.tabela}`} type="button"
                  onClick={() => { setSel({ schema: t.schema, tabela: t.tabela }); setColData(''); setColAtu('') }}
                  className={`w-full text-left px-3 py-1.5 text-xs flex justify-between gap-2 hover:bg-edge/40 ${sel?.schema === t.schema && sel?.tabela === t.tabela ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                  <span className="font-mono text-ink truncate">{t.schema}.{t.tabela}</span>
                  <span className="text-dim tabular-nums shrink-0">{t.linhas.toLocaleString('pt-BR')}</span>
                </button>
              ))}
              {tabelas.length === 0 && !tabelasQ.isFetching && <div className="px-3 py-3 text-xs text-dim text-center">Nenhuma tabela.</div>}
            </div>
          </div>
        )}

        {sel && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <Select label="3. Coluna de data (competência)" value={colData} onChange={e => setColData(e.target.value)}>
              <option value="">Selecione…</option>
              {dateCols.length > 0 && <optgroup label="Colunas de data">{dateCols.map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}</optgroup>}
              {dateCols.length < cols.length && <optgroup label="Outras">{cols.filter(c => !c.is_data).map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}</optgroup>}
            </Select>
            <Select label="Coluna de atualização (opcional)" value={colAtu} onChange={e => setColAtu(e.target.value)}>
              <option value="">—</option>{cols.map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}
            </Select>
            <Select label="Criticidade" value={crit} onChange={e => setCrit(e.target.value)}>
              <option value="">—</option><option>Alta</option><option>Media</option><option>Baixa</option>
            </Select>
            <Input label="SLA de atualização (horas)" type="number" value={sla} onChange={e => setSla(e.target.value)} placeholder="ex.: 24" />
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={save.isPending} disabled={!sel || !colData} onClick={() => save.mutate()}>Adicionar</Button>
        </div>
      </div>
    </Modal>
  )
}

function MonitorDetail({ item, onClose }: { item: MonitorItem; onClose: () => void }) {
  const liveQ = useQuery<LiveResult>({ queryKey: ['monitor-live', item.id], queryFn: () => apiFetch(`/admin/monitor/${item.id}/live?dias=30`) })
  const histQ = useQuery<{ data: { captured_at: string; total_linhas: number | null; ultima_data: string | null; qtde_ultimo_dia: number | null; erro: string | null }[] }>({
    queryKey: ['monitor-hist', item.id], queryFn: () => apiFetch(`/admin/monitor/${item.id}/historico?limit=20`),
  })
  const live = liveQ.data
  return (
    <Modal open onClose={onClose} title={`${item.database_name}.${item.schema_name}.${item.table_name}`} size="lg">
      <div className="flex flex-col gap-4">
        {liveQ.isLoading && <PageSpinner />}
        {live?.erro && <div className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2 break-words">Erro ao consultar: {live.erro}</div>}
        {live?.ok && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Stat label="Total (aprox.)" value={live.total_linhas?.toLocaleString('pt-BR') ?? '—'} />
              <Stat label="Última competência" value={live.ultima_data ?? '—'} />
              <Stat label="Última escrita" value={live.last_write ?? '—'} />
              <Stat label="Qtde último dia" value={live.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'} />
            </div>
            <div>
              <div className="text-xs text-dim mb-1">Volume por dia (coluna <code className="text-[11px]">{item.coluna_data}</code>, últimos 30 dias)</div>
              <div className="border border-edge rounded-lg p-3 overflow-x-auto"><Sparkbars data={live.por_dia ?? []} h={120} /></div>
            </div>
          </>
        )}
        <div>
          <div className="text-xs text-dim mb-1">Histórico de snapshots</div>
          <div className="border border-edge rounded-lg max-h-48 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-edge/30 text-dim sticky top-0"><tr className="text-left">
                <th className="px-3 py-1.5 font-medium">Capturado</th><th className="px-3 py-1.5 font-medium text-right">Total</th>
                <th className="px-3 py-1.5 font-medium">Última comp.</th><th className="px-3 py-1.5 font-medium text-right">Últ. dia</th>
              </tr></thead>
              <tbody>
                {(histQ.data?.data ?? []).map((h, i) => (
                  <tr key={i} className="border-t border-edge/40">
                    <td className="px-3 py-1.5 text-dim">{h.captured_at}</td>
                    <td className="px-3 py-1.5 text-right text-ink tabular-nums">{h.total_linhas?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-1.5 text-dim">{h.ultima_data ?? (h.erro ? <span className="text-red-600 dark:text-red-400">erro</span> : '—')}</td>
                    <td className="px-3 py-1.5 text-right text-dim tabular-nums">{h.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'}</td>
                  </tr>
                ))}
                {(histQ.data?.data ?? []).length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-center text-dim">Sem snapshots ainda. Use "Capturar agora".</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex justify-end border-t border-edge pt-3"><Button variant="secondary" onClick={onClose}>Fechar</Button></div>
      </div>
    </Modal>
  )
}

function MonitoramentoTab() {
  const [add, setAdd] = useState(false)
  const [detail, setDetail] = useState<MonitorItem | null>(null)
  const [delItem, setDelItem] = useState<MonitorItem | null>(null)
  const { data, isLoading } = useQuery<{ data: MonitorItem[] }>({ queryKey: ['monitor'], queryFn: () => apiFetch('/admin/monitor') })
  const items = data?.data ?? []
  const capturar = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/monitor/${id}/capturar`, { method: 'POST' }),
    onSuccess: () => { toast.success('Snapshot capturado.'); queryClient.invalidateQueries({ queryKey: ['monitor'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao capturar'),
  })
  const del = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/monitor/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Removido do monitoramento.'); setDelItem(null); queryClient.invalidateQueries({ queryKey: ['monitor'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <div>
            <h2 className="text-sm font-bold text-ink">Monitoramento de tabelas</h2>
            <p className="text-xs text-dim mt-0.5">Última atualização e volume por dia das tabelas importantes. Snapshot diário automático + alerta de atraso/queda.</p>
          </div>
        </div>
        <Button onClick={() => setAdd(true)}><Plus size={14} /> Adicionar tabela</Button>
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && items.length === 0 && <div className="text-xs text-dim py-8 text-center">Nenhuma tabela monitorada. Clique em "Adicionar tabela".</div>}

      {items.length > 0 && (
        <div className="overflow-x-auto border border-edge rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-edge/30 text-dim">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Tabela</th>
                <th className="px-3 py-2 font-medium">Crit.</th>
                <th className="px-3 py-2 font-medium whitespace-nowrap">Última atualização</th>
                <th className="px-3 py-2 font-medium text-right">Total</th>
                <th className="px-3 py-2 font-medium text-right">Últ. dia</th>
                <th className="px-3 py-2 font-medium">Volume (por dia)</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => {
                const s = it.snapshot
                const fr = freshness(s?.ultima_data)
                return (
                  <tr key={it.id} className={`border-t border-edge/40 hover:bg-edge/20 ${!it.ativo ? 'opacity-60' : ''}`}>
                    <td className="px-3 py-2">
                      <div className="font-mono text-ink text-xs">{it.database_name}.{it.schema_name}.{it.table_name}</div>
                      <div className="text-[10px] text-dim">por {it.coluna_data}{s?.captured_at && <> · snapshot {s.captured_at.substring(0, 16)}</>}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-dim">{it.criticidade ?? '—'}</td>
                    <td className="px-3 py-2"><span className={`text-[10px] px-1.5 py-0.5 rounded ${fr.cls}`}>{fr.label}</span></td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums text-xs">{s?.total_linhas?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums text-xs">{s?.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-2"><Sparkbars data={s?.por_dia ?? []} /></td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => capturar.mutate(it.id)} disabled={capturar.isPending} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded disabled:opacity-50" title="Capturar agora"><RefreshCw size={13} /></button>
                        <button onClick={() => setDetail(it)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Detalhe"><Eye size={13} /></button>
                        <button onClick={() => setDelItem(it)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {add && <AddMonitorModal onClose={() => setAdd(false)} />}
      {detail && <MonitorDetail item={detail} onClose={() => setDetail(null)} />}
      <ConfirmModal open={!!delItem} title="Remover do monitoramento" danger confirmLabel="Remover"
        message={`Parar de monitorar "${delItem?.table_name}"? Os snapshots históricos também serão removidos.`}
        onConfirm={() => delItem && del.mutate(delItem.id)} onCancel={() => setDelItem(null)} />
    </div>
  )
}

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

interface DsLogRun {
  start?: string
  end?: string
  result: 'ok' | 'aborted' | 'running' | 'unknown'
  firstId?: number
  lastId?: number
  children: { job: string; fullJob: string; code: number; text: string }[]
}

// Parser do `dsjob -logsum`: agrupa o log em runs da sequence, com os jobs filhos
// e seus status. Best-effort, tolerante a variações de formato (header numa linha,
// mensagem na seguinte).
function parseLogsum(stdout: string): DsLogRun[] {
  const runs: DsLogRun[] = []
  let cur: DsLogRun | null = null
  let time = ''
  let id = 0
  for (const raw of stdout.split('\n')) {
    const header = raw.match(/^\s*(\d+)\s+[A-Z]+\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+[\d:]+\s+\d{4})\s*$/)
    if (header) { id = Number(header[1]); time = header[2]; continue }
    const msg = raw.trim()
    if (!msg) continue
    if (/^Starting Job\s/.test(msg)) {
      if (cur) runs.push(cur)
      cur = { start: time, result: 'running', children: [], firstId: id, lastId: id }
      continue
    }
    if (!cur) continue
    cur.lastId = id
    if (/^Finished Job\s/.test(msg)) { cur.result = 'ok'; cur.end = time; continue }
    if (/sequence abort requested|aborted due to|fatal error from @/i.test(msg)) { cur.result = 'aborted'; cur.end = time; continue }
    const fin = msg.match(/Job\s+(\S+)\s+has finished, status = (\d+)\s*\(([^)]*)\)/)
    if (fin) {
      cur.children.push({ job: fin[1].replace(/^SeqExecJob\./, ''), fullJob: fin[1], code: Number(fin[2]), text: fin[3] })
      continue
    }
    if (/Job under control finished/.test(msg)) {
      if (!cur.end) cur.end = time
      runs.push(cur); cur = null
    }
  }
  if (cur) runs.push(cur)
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

function DsConsoleTab() {
  const cfg = useQuery<{ configured: boolean; commands: DsCmd[] }>({
    queryKey: ['ds-console-config'],
    queryFn: () => apiFetch('/datastage/console/config'),
  })
  const projetos = useQuery<{ projects: { project_name: string; ativo?: boolean | number }[] }>({
    queryKey: ['admin-projects-all'],
    queryFn: () => apiFetch('/pipelines/projects/all'),
  })

  const [project, setProject] = useState('')
  const [command, setCommand] = useState('jobinfo')
  const [job, setJob] = useState('')
  const [maxLines, setMaxLines] = useState('200')
  const [eventId, setEventId] = useState('')
  const [showCodes, setShowCodes] = useState(false)

  const commands = cfg.data?.commands ?? []
  const current = commands.find(c => c.id === command)
  const needsJob = current?.needs_job ?? true
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

  const exec = useMutation<DsConsoleResult, Error, { command: string; project: string; job?: string; max_lines?: number; event_id?: number }>({
    mutationFn: (vars) => apiFetch<DsConsoleResult>('/datastage/console', {
      method: 'POST',
      body: JSON.stringify(vars),
    }),
    onError: (e: any) => toast.error(e.message),
  })

  const hasMax = command === 'logsum'
  const isLogdetail = command === 'logdetail'
  const canRun = !!project.trim() && (!needsJob || !!job.trim())
    && (!isLogdetail || !!eventId.trim()) && configured && !exec.isPending
  const run = () => {
    if (!canRun) return
    exec.mutate({
      command,
      project: project.trim(),
      job: needsJob ? job.trim() : undefined,
      max_lines: hasMax ? (Number(maxLines) || 200) : undefined,
      event_id: isLogdetail ? (Number(eventId) || undefined) : undefined,
    })
  }
  // Roda um comando específico imediatamente (cliques nos chips de job / filhos / eventos).
  const runFor = (cmd: string, jobName: string, extra?: { max_lines?: number; event_id?: number }) => {
    if (!project.trim() || !configured) return
    setCommand(cmd); setJob(jobName)
    if (extra?.event_id != null) setEventId(String(extra.event_id))
    exec.mutate({ command: cmd, project: project.trim(), job: jobName, ...extra })
  }

  const projectList = (projetos.data?.projects ?? []).map(p => p.project_name)
  const projectOptions = projectList.length ? projectList : PROJETOS

  const result = exec.data
  const isJobinfo = result?.command === 'jobinfo' && result.exit_code === 0
  const jobinfoFields = (isJobinfo && result
    ? result.stdout.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
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

  // De-para do código de erro do dsjob ("Status code = -N") quando o comando falha.
  const errMatch = (result && result.exit_code !== 0)
    ? ((result.stderr || '') + '\n' + (result.stdout || '')).match(/Status code\s*=\s*(-?\d+)/i)
    : null
  const errorCode = errMatch ? Number(errMatch[1]) : null
  const errorMeaning = errorCode != null ? DSJOB_CODE_MEANINGS[errorCode] : undefined

  const copy = (t: string) => navigator.clipboard?.writeText(t).then(
    () => toast.info('Copiado!'), () => toast.error('Erro ao copiar'))

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

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
        <Terminal size={16} className="text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <div className="text-sm text-blue-800 dark:text-blue-300">
          Executa comandos <code className="font-mono text-xs">dsjob</code> de <strong>consulta</strong> (somente leitura) no servidor Unix do DataStage via SSH.
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

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Projeto" value={project} onChange={e => setProject(e.target.value)} className="w-48">
            <option value="">Selecione…</option>
            {projectOptions.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Select label="Comando" value={command} onChange={e => setCommand(e.target.value)} className="w-56">
            {(commands.length ? commands : [{ id: 'jobinfo', label: 'Status do job', needs_job: true }]).map(c =>
              <option key={c.id} value={c.id}>{c.label}</option>)}
          </Select>
          {needsJob && (
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
          <Button onClick={run} loading={exec.isPending} disabled={!canRun}>Executar</Button>
        </div>
        {needsJob && configured && !!project && (
          <p className="text-[11px] text-dim mt-2">
            {jobsQuery.isFetching
              ? 'Carregando jobs do projeto para autocompletar…'
              : jobOptions.length > 0
                ? `Comece a digitar no campo Job — ${jobOptions.length} jobs de ${project} disponíveis para autocompletar.`
                : ''}
          </p>
        )}
      </div>

      {result && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-dim">
            <code className="font-mono px-2 py-1 rounded bg-edge/40 text-ink">
              dsjob -{result.command} {result.project}{result.job ? ' ' + result.job : ''}
            </code>
            <Badge value={result.exit_code === 0 ? 'success' : 'error'}>exit {result.exit_code}</Badge>
            <span>{result.duration_ms} ms</span>
          </div>

          {result.exit_code !== 0 && errorMeaning && (
            <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
              <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
              <p className="text-sm text-amber-800 dark:text-yellow-300">
                <strong>Código {errorCode}:</strong> {errorMeaning}.
                {errorCode === -1004 && <> Confira o nome do job — use o autocompletar do campo Job ou rode <strong>"Listar jobs do projeto"</strong>.</>}
              </p>
            </div>
          )}

          {isJobinfo && jobinfoFields.length > 0 && (
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
          )}

          {logDetailEvents.map((e, i) => (
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
          ))}

          {(errorsByRun.length > 0 || ungroupedErrors.length > 0) && (
            <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg p-4 flex flex-col gap-3">
              <p className="text-xs text-red-800 dark:text-red-300 font-medium">
                Erros e avisos <strong>por run</strong> (cada run é independente) — clique no <strong>nome do job filho</strong> para abrir o log dele, ou no <strong>#id</strong> para o detalhe:
              </p>
              {errorsByRun.slice().reverse().map((g, gi) => (
                <div key={gi} className="border border-red-200/70 dark:border-red-800/60 rounded-lg p-2.5">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <Badge value={g.run.result === 'ok' ? 'success' : g.run.result === 'aborted' ? 'error' : g.run.result === 'running' ? 'info' : 'neutral'}>
                      {g.run.result === 'ok' ? 'Concluído' : g.run.result === 'aborted' ? 'Abortado' : g.run.result === 'running' ? 'Em execução' : 'Run'}
                    </Badge>
                    <span className="text-xs text-ink font-medium">{g.run.start}</span>
                    {g.run.end && g.run.end !== g.run.start && <span className="text-xs text-dim">→ {g.run.end}</span>}
                  </div>
                  <div className="flex flex-col gap-1.5">{g.errors.slice(-12).reverse().map(renderErrRow)}</div>
                </div>
              ))}
              {ungroupedErrors.length > 0 && (
                <div className="border border-edge/70 rounded-lg p-2.5">
                  <p className="text-xs text-dim mb-1.5">Histórico anterior (fora dos runs detectados nesta saída)</p>
                  <div className="flex flex-col gap-1.5">{ungroupedErrors.slice(-12).reverse().map(renderErrRow)}</div>
                </div>
              )}
            </div>
          )}

          {logsumRuns.length > 0 && (
            <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-2">
              <p className="text-xs text-dim mb-1">Resumo dos runs (mais recentes primeiro) — {logsumRuns.length} no log. Clique num job para ver o log dele (logsum):</p>
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
                          <Badge value={dsCodeVariant(c.code)}>{DS_STATUS_MEANINGS[c.code] ?? c.text}</Badge>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {ljobsList.length > 0 && (
            <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
              <p className="text-xs text-dim mb-2">{ljobsList.length} job(s) — clique para inspecionar (jobinfo):</p>
              <div className="flex flex-wrap gap-1.5">
                {ljobsList.map(j => (
                  <button key={j} onClick={() => runFor('jobinfo', j)}
                    className="px-2 py-1 rounded text-xs font-mono bg-edge/40 text-ink hover:bg-[#1A5FA8] hover:text-white transition-colors">
                    {j}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(result.stdout || result.stderr) && (
            <div className="relative">
              <button onClick={() => copy(result.stdout || result.stderr)}
                className="absolute top-2 right-2 px-2 py-1 rounded text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 flex items-center gap-1 z-10">
                <Copy size={12} /> Copiar
              </button>
              <div className="bg-gray-950 rounded-lg p-4 overflow-auto max-h-[55vh] font-mono text-xs leading-relaxed">
                {result.stdout ? dsColorize(result.stdout) : null}
                {result.stderr ? (
                  <div className="mt-2">{result.stderr.split('\n').map((l, i) => <div key={i} className="text-red-400">{l || ' '}</div>)}</div>
                ) : null}
              </div>
            </div>
          )}

          {!result.stdout && !result.stderr && (
            <p className="text-xs text-dim">Comando executado (exit {result.exit_code}) sem saída.</p>
          )}
        </div>
      )}

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
    </div>
  )
}

// Navegação em 2 níveis: grupo (nível 1, sub-abas) → aba (nível 2, pílulas).
const ADMIN_GROUPS = [
  { id: 'sistema', label: 'Sistema', tabs: [
    { id: 'config', label: 'Configurações' },
    { id: 'tipos', label: 'Tipos de Job' },
    { id: 'projetos', label: 'Projetos' },
    { id: 'versoes', label: 'Versões' },
    { id: 'backlog', label: 'Backlog' },
    { id: 'servidor', label: 'Servidor' },
    { id: 'monitor', label: 'Monitoramento' },
    { id: 'ds_console', label: 'Console DataStage' },
  ] },
  { id: 'pipelines', label: 'Pipelines', tabs: [
    { id: 'regen', label: 'Regenerar DAGs' },
    { id: 'delete', label: 'Excluir Pipeline' },
    { id: 'agenda', label: 'Agendamento' },
  ] },
  { id: 'acessos', label: 'Acessos & Comunicação', tabs: [
    { id: 'usuarios', label: 'Usuários & Perfis' },
    { id: 'comunicados', label: 'Comunicados' },
    { id: 'powerbi', label: 'Power BI — Acessos' },
  ] },
  { id: 'relatorios', label: 'Relatórios', tabs: [
    { id: 'sla', label: 'Relatório SLA' },
  ] },
]

export default function Admin() {
  const [tab, setTab] = useState('config')
  const activeGroup = ADMIN_GROUPS.find(g => g.tabs.some(t => t.id === tab)) ?? ADMIN_GROUPS[0]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold text-ink">Administração</h1>
        <p className="text-xs text-dim mt-0.5">Gestão do sistema Orquestra</p>
      </div>

      {/* Nível 1 — grupos */}
      <Tabs
        tabs={ADMIN_GROUPS.map(g => ({ id: g.id, label: g.label }))}
        active={activeGroup.id}
        onChange={gid => { const g = ADMIN_GROUPS.find(x => x.id === gid); if (g) setTab(g.tabs[0].id) }}
        size="md"
      />

      {/* Nível 2 — abas do grupo (pílulas) */}
      {activeGroup.tabs.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {activeGroup.tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t.id ? 'bg-[#1A5FA8] text-white' : 'bg-edge/40 text-dim hover:text-ink hover:bg-edge/70'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
      )}

      <div>
        {tab === 'config' && <ConfigTab />}
        {tab === 'backlog' && <BacklogTab />}
        {tab === 'servidor' && <ServidorTab />}
        {tab === 'monitor' && <MonitoramentoTab />}
        {tab === 'ds_console' && <DsConsoleTab />}
        {tab === 'regen' && <RegenDagsTab />}
        {tab === 'delete' && <DeletePipelineTab />}
        {tab === 'versoes' && <VersoesTab />}
        {tab === 'tipos' && <TiposJobTab />}
        {tab === 'agenda' && <AgendamentoTab />}
        {tab === 'usuarios' && <UsuariosTab />}
        {tab === 'comunicados' && <ComunicadosTab />}
        {tab === 'projetos' && <ProjetosTab />}
        {tab === 'sla' && <SlaReportTab />}
        {tab === 'powerbi' && <PowerBIAccessGuideTab />}
      </div>
    </div>
  )
}
