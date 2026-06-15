import { useState } from 'react'
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
  CheckCircle2, Eye, Calendar,
} from 'lucide-react'

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

// Recursos RBAC (espelha RBAC_RECURSOS da UI legada).
const RBAC_RECURSOS: [string, string][] = [
  ['tela_dashboard', 'Dashboard'], ['tela_pipelines', 'Pipelines'],
  ['tela_jobs', 'Jobs'], ['tela_logs', 'Logs'],
  ['tela_governanca', 'Governança'],
  ['tela_malha', 'Malha'], ['tela_admin', 'Admin'],
  ['tela_impacto_campo', 'Impacto Campo'], ['tela_plano_ajuste', 'Plano Ajuste'],
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
const ADMIN_TABS = [
  { id: 'config', label: 'Configurações' },
  { id: 'regen', label: 'Regenerar DAGs' },
  { id: 'delete', label: 'Excluir Pipeline' },
  { id: 'versoes', label: 'Versões' },
  { id: 'tipos', label: 'Tipos de Job' },
  { id: 'agenda', label: 'Agendamento' },
  { id: 'usuarios', label: 'Usuários & Perfis' },
  { id: 'projetos', label: 'Projetos' },
]

export default function Admin() {
  const [tab, setTab] = useState('config')
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-bold text-ink">Administração</h1>
        <p className="text-xs text-dim mt-0.5">Gestão do sistema Orquestra</p>
      </div>
      <Tabs tabs={ADMIN_TABS} active={tab} onChange={setTab} size="sm" />
      <div>
        {tab === 'config' && <ConfigTab />}
        {tab === 'regen' && <RegenDagsTab />}
        {tab === 'delete' && <DeletePipelineTab />}
        {tab === 'versoes' && <VersoesTab />}
        {tab === 'tipos' && <TiposJobTab />}
        {tab === 'agenda' && <AgendamentoTab />}
        {tab === 'usuarios' && <UsuariosTab />}
        {tab === 'projetos' && <ProjetosTab />}
      </div>
    </div>
  )
}
