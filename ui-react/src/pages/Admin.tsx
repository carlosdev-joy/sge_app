import React, { useState } from 'react'
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
import { Edit2, Trash2, Plus, AlertTriangle, ChevronDown, ChevronUp, Save, X, CheckCircle2 } from 'lucide-react'

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

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
        {danger && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{message}</p>
          </div>
        )}
        {!danger && <p className="text-sm text-ink">{message}</p>}
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

// ── Configurações ───────────────────────────────────────────────
function ConfigTab() {
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newDesc, setNewDesc] = useState('')

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

  const testWebhook = () =>
    apiFetch('/admin/test-webhook', { method: 'POST' })
      .then(() => toast.success('Webhook de teste enviado'))
      .catch((e: any) => toast.error(e.message))

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
        <p className="text-sm text-dim">Parâmetros do sistema. Edite o valor diretamente na célula e clique em Salvar.</p>
        <Button variant="secondary" size="sm" onClick={testWebhook}>🔔 Testar Webhook</Button>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold w-1/3">Chave</th>
                <th className="px-4 py-2.5 text-left font-semibold">Valor</th>
                <th className="px-4 py-2.5 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, v]) => {
                const current = editValues[k] !== undefined ? editValues[k] : v
                const isDirty = editValues[k] !== undefined && editValues[k] !== v
                const isSaving = savingKey === k && upsertMut.isPending
                return (
                  <tr key={k} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2">
                      <span className="font-mono text-xs text-[#1A5FA8] dark:text-blue-400">{k}</span>
                    </td>
                    <td className="px-4 py-2">
                      <input
                        value={current}
                        onChange={e => setEditValues(prev => ({ ...prev, [k]: e.target.value }))}
                        onKeyDown={e => { if (e.key === 'Enter' && isDirty) handleInlineSave(k) }}
                        className="w-full font-mono text-xs text-ink bg-transparent border border-transparent rounded px-2 py-1 hover:border-edge focus:border-[#1A5FA8] focus:ring-1 focus:ring-[#1A5FA8]/30 focus:outline-none transition-colors"
                      />
                    </td>
                    <td className="px-4 py-2 text-right">
                      {isDirty && (
                        <div className="flex items-center gap-1 justify-end">
                          <button
                            onClick={() => setEditValues(prev => { const n = { ...prev }; delete n[k]; return n })}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-dim p-1 rounded"
                            title="Descartar"
                          >
                            <X size={12} />
                          </button>
                          <Button size="sm" onClick={() => handleInlineSave(k)} loading={isSaving}>
                            <Save size={11} /> Salvar
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-xs text-dim">Nenhuma configuração encontrada.</td>
                </tr>
              )}
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
          <Button
            onClick={() => upsertMut.mutate({ config_key: newKey, config_value: newVal, descricao: newDesc || undefined })}
            loading={upsertMut.isPending && !savingKey}
            disabled={!newKey || !newVal}
          >
            <Plus size={13} /> Adicionar
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Regenerar DAGs ──────────────────────────────────────────────
function RegenDagsTab() {
  const [projeto, setProjeto] = useState('')
  const [log, setLog] = useState('')
  const [loading, setLoading] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const regen = async () => {
    setLoading(true); setLog('')
    try {
      const res = await adminPost<any>('regenerate_all_dags', { filter_project: projeto || undefined })
      setLog(JSON.stringify(res, null, 2))
      toast.success(res.mensagem ?? 'Regeneração concluída')
    } catch (e: any) {
      toast.error(e.message); setLog(e.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
        <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-800 dark:text-yellow-300">
          Marca os pipelines para regeneração (<code className="font-mono text-xs">dag_criada=0</code>). A <code className="font-mono text-xs">etl_dag_factory</code> recria os DAGs no próximo ciclo do Airflow.
        </p>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Filtrar por projeto (opcional)" value={projeto} onChange={e => setProjeto(e.target.value)} className="w-56">
            <option value="">Todos os projetos</option>
            {PROJETOS.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Button variant="danger" onClick={() => setConfirm(true)} loading={loading}>
            ⟳ Regenerar DAGs
          </Button>
        </div>
      </div>

      {log && (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge bg-canvas/50 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-500" />
            <span className="text-xs font-medium text-ink">Resultado</span>
          </div>
          <pre className="text-xs text-dim p-4 overflow-auto max-h-64">{log}</pre>
        </div>
      )}

      <ConfirmModal
        open={confirm}
        title="Regenerar DAGs"
        message={`Marcar todos os pipelines${projeto ? ` do projeto ${projeto}` : ''} para regeneração? Esta ação afeta o Airflow no próximo ciclo.`}
        confirmLabel="Regenerar"
        onConfirm={regen}
        onCancel={() => setConfirm(false)}
      />
    </div>
  )
}

// ── Excluir Pipeline ────────────────────────────────────────────
function DeletePipelineTab() {
  const [nome, setNome] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [confirm, setConfirm] = useState(false)

  const del = async () => {
    setLoading(true); setResult(null)
    try {
      const res = await adminPost<any>('pipeline_delete', { pipeline_name: nome })
      setResult(res)
      toast.success(res.mensagem ?? 'Pipeline excluído')
      setNome('')
    } catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-700">
        <AlertTriangle size={16} className="text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
        <p className="text-sm text-red-800 dark:text-red-300">
          <strong>Atenção:</strong> Esta operação é irreversível. Todos os jobs, execuções e lineage do pipeline serão permanentemente removidos.
        </p>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Input
            label="Nome do Pipeline"
            value={nome}
            onChange={e => setNome(e.target.value)}
            className="w-80"
            placeholder="nome_exato_do_pipeline"
          />
          <Button variant="danger" onClick={() => setConfirm(true)} loading={loading} disabled={!nome.trim()}>
            <Trash2 size={14} /> Excluir Pipeline
          </Button>
        </div>
      </div>

      {result && (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge bg-canvas/50 flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-500" />
            <span className="text-xs font-medium text-ink">Resultado</span>
          </div>
          <pre className="text-xs text-dim p-4 overflow-auto max-h-48">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}

      <ConfirmModal
        open={confirm}
        title="Excluir Pipeline"
        message={`Excluir permanentemente o pipeline "${nome}"? Todos os jobs, execuções e lineage associados serão removidos. Esta ação não pode ser desfeita.`}
        danger
        confirmLabel="Sim, excluir"
        onConfirm={del}
        onCancel={() => setConfirm(false)}
      />
    </div>
  )
}

// ── Versões ─────────────────────────────────────────────────────
interface VersaoRow { id: number; versao: string; titulo: string; descricao_md?: string; criado_em?: string }

function VersoesTab() {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [nova, setNova] = useState({ versao: '', titulo: '', descricao_md: '' })
  const [deleteConfirm, setDeleteConfirm] = useState<VersaoRow | null>(null)

  const { data, isLoading } = useQuery<{ data: VersaoRow[] }>({
    queryKey: ['versoes'],
    queryFn: () => apiFetch('/versao'),
  })

  const createMut = useMutation({
    mutationFn: (v: typeof nova) =>
      apiFetch('/versao/register', { method: 'POST', body: JSON.stringify({ action: 'create', ...v }) }),
    onSuccess: () => {
      toast.success('Versão criada')
      queryClient.invalidateQueries({ queryKey: ['versoes'] })
      setShowForm(false)
      setNova({ versao: '', titulo: '', descricao_md: '' })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, descricao_md }: { id: number; descricao_md: string }) =>
      apiFetch('/versao/register', { method: 'POST', body: JSON.stringify({ action: 'update', id, descricao_md }) }),
    onSuccess: () => {
      toast.success('Versão atualizada')
      queryClient.invalidateQueries({ queryKey: ['versoes'] })
      setEditingId(null)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) =>
      apiFetch('/versao/register', { method: 'POST', body: JSON.stringify({ action: 'delete', id }) }),
    onSuccess: () => {
      toast.success('Versão removida')
      queryClient.invalidateQueries({ queryKey: ['versoes'] })
      setDeleteConfirm(null)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const toggleExpand = (id: number) => {
    if (editingId === id) return
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  const startEdit = (v: VersaoRow, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(v.id)
    setEditText(v.descricao_md ?? '')
    setExpanded(prev => new Set([...prev, v.id]))
  }

  const cancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(null)
  }

  const rows = data?.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-dim">Clique em uma versão para expandir os detalhes.</p>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus size={13} /> Nova Versão
        </Button>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-2">
          {rows.length === 0 && (
            <div className="text-center py-10 text-sm text-dim bg-panel border border-edge rounded-lg">
              Nenhuma versão registrada.
            </div>
          )}
          {rows.map(v => {
            const isOpen = expanded.has(v.id)
            const isEditing = editingId === v.id
            return (
              <div key={v.id} className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm transition-shadow hover:shadow-md">
                <button
                  onClick={() => toggleExpand(v.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-canvas/60 transition-colors"
                >
                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-[#1A5FA8]/10 text-[#1A5FA8] dark:bg-blue-900/40 dark:text-blue-300 font-bold font-mono text-xs border border-[#1A5FA8]/20 dark:border-blue-700">
                    {v.versao}
                  </span>
                  <span className="text-ink font-medium text-sm flex-1 text-left">{v.titulo}</span>
                  {v.criado_em && (
                    <span className="text-xs text-dim hidden sm:block">{v.criado_em}</span>
                  )}
                  {isOpen
                    ? <ChevronUp size={14} className="text-dim shrink-0" />
                    : <ChevronDown size={14} className="text-dim shrink-0" />
                  }
                </button>

                {isOpen && (
                  <div className="border-t border-edge px-4 py-4 bg-canvas/30">
                    {isEditing ? (
                      <div className="flex flex-col gap-3">
                        <Textarea
                          label="Descrição (markdown)"
                          value={editText}
                          onChange={e => setEditText(e.target.value)}
                          rows={6}
                        />
                        <div className="flex gap-2 justify-end">
                          <Button variant="secondary" size="sm" onClick={cancelEdit}>Cancelar</Button>
                          <Button size="sm" onClick={() => updateMut.mutate({ id: v.id, descricao_md: editText })} loading={updateMut.isPending}>
                            <Save size={12} /> Salvar
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {v.descricao_md ? (
                          <p className="text-sm text-ink whitespace-pre-wrap leading-relaxed">{v.descricao_md}</p>
                        ) : (
                          <p className="text-sm text-dim italic">Sem descrição.</p>
                        )}
                        <div className="flex gap-2 pt-1 border-t border-edge/50">
                          <Button variant="secondary" size="sm" onClick={e => startEdit(v, e)}>
                            <Edit2 size={12} /> Editar Texto
                          </Button>
                          <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); setDeleteConfirm(v) }}>
                            <Trash2 size={12} className="text-red-500" />
                            <span className="text-red-500">Excluir</span>
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showForm && (
        <Modal open title="Nova Versão" onClose={() => setShowForm(false)}>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <Input label="Versão" value={nova.versao} onChange={e => setNova(n => ({ ...n, versao: e.target.value }))} placeholder="v2.5.0" />
              <Input label="Título" value={nova.titulo} onChange={e => setNova(n => ({ ...n, titulo: e.target.value }))} />
            </div>
            <Textarea
              label="Descrição (markdown)"
              value={nova.descricao_md}
              onChange={e => setNova(n => ({ ...n, descricao_md: e.target.value }))}
              rows={6}
              placeholder="## Novidades&#10;- Item 1&#10;- Item 2"
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
              <Button onClick={() => createMut.mutate(nova)} loading={createMut.isPending} disabled={!nova.versao || !nova.titulo}>
                <Save size={13} /> Salvar Versão
              </Button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Excluir Versão"
        message={`Remover a versão ${deleteConfirm?.versao} — "${deleteConfirm?.titulo}"? Esta ação não pode ser desfeita.`}
        danger
        confirmLabel="Excluir"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}

// ── Tipos de Job ────────────────────────────────────────────────
interface TipoJobRow { id: number; nome: string; descricao?: string; lineage_enabled: boolean; status: boolean }
function TiposJobTab() {
  const { data, isLoading } = useQuery<{ job_types: TipoJobRow[] }>({
    queryKey: ['tipos-job'],
    queryFn: () => apiFetch('/catalogo', { method: 'POST', body: JSON.stringify({ mode: 'list_job_types', include_inactive: true }) }),
  })

  const rows = data?.job_types ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-dim">{rows.length} tipos cadastrados</span>
        <Badge value={`${rows.filter(t => t.status).length} ativos`} />
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
              </tr>
            </thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-ink">{t.nome}</td>
                  <td className="px-4 py-2.5 text-xs text-dim">{t.descricao}</td>
                  <td className="px-4 py-2.5"><Badge value={t.lineage_enabled ? 'sim' : 'não'} /></td>
                  <td className="px-4 py-2.5"><Badge value={t.status ? 'ativo' : 'inativo'} /></td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-xs text-dim">Nenhum tipo de job cadastrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Agendamento ─────────────────────────────────────────────────
interface CalendarioRow { calendario_nome: string; datas: number; proxima?: string | null }
interface BlackoutRow { id: number; inicio: string; fim?: string; escopo?: string | null; motivo?: string; ativo: number; vigente: number }

function AgendamentoTab() {
  const [freezeLoading, setFreezeLoading] = useState(false)
  const [calNome, setCalNome] = useState('')
  const [calDatas, setCalDatas] = useState('')
  const [calDesc, setCalDesc] = useState('')
  const [freezeConfirm, setFreezeConfirm] = useState<'congelar' | 'descongelar' | null>(null)

  const { data: cal } = useQuery<{ calendarios: CalendarioRow[] }>({
    queryKey: ['calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
  })
  const { data: bo } = useQuery<{ blackouts: BlackoutRow[]; ambiente_congelado: boolean }>({
    queryKey: ['blackouts'],
    queryFn: () => apiFetch('/agenda/blackouts?incluir_historico=1'),
  })

  const freeze = async (acao: 'congelar' | 'descongelar') => {
    setFreezeLoading(true)
    try {
      await apiFetch('/admin/freeze', { method: 'POST', body: JSON.stringify({ acao }) })
      toast.success(acao === 'congelar' ? '❄ Ambiente congelado' : '✓ Ambiente descongelado')
      queryClient.invalidateQueries({ queryKey: ['blackouts'] })
    } catch (e: any) { toast.error(e.message) }
    finally { setFreezeLoading(false) }
  }

  const addCal = useMutation({
    mutationFn: () => apiFetch('/agenda/calendarios', {
      method: 'POST',
      body: JSON.stringify({
        calendario_nome: calNome,
        datas: calDatas.split('\n').map(d => d.trim()).filter(Boolean),
        descricao: calDesc || undefined,
      }),
    }),
    onSuccess: () => {
      toast.success('Calendário atualizado')
      queryClient.invalidateQueries({ queryKey: ['calendarios'] })
      setCalNome(''); setCalDatas(''); setCalDesc('')
    },
    onError: (e: any) => toast.error(e.message),
  })

  const encerrarBlackout = (id: number) =>
    apiFetch(`/agenda/blackouts/${id}/encerrar`, { method: 'POST', body: JSON.stringify({}) })
      .then(() => { toast.success('Janela encerrada'); queryClient.invalidateQueries({ queryKey: ['blackouts'] }) })
      .catch((e: any) => toast.error(e.message))

  const congelado = bo?.ambiente_congelado
  const blackouts = (bo?.blackouts ?? []).filter(b => b.motivo !== 'FREEZE_GLOBAL')

  return (
    <div className="flex flex-col gap-5">
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Congelamento de Ambiente</h3>
        <div className="flex items-center gap-4">
          <Badge value={congelado ? 'error' : 'success'}>
            {congelado ? '❄ CONGELADO' : '✓ ATIVO'}
          </Badge>
          <span className="text-xs text-dim">
            {congelado ? 'Todas as execuções estão bloqueadas.' : 'Ambiente em operação normal.'}
          </span>
          {congelado
            ? <Button variant="secondary" onClick={() => setFreezeConfirm('descongelar')} loading={freezeLoading}>Descongelar</Button>
            : <Button variant="danger" onClick={() => setFreezeConfirm('congelar')} loading={freezeLoading}>❄ Congelar Ambiente</Button>
          }
        </div>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Calendários de Bloqueio</h3>
        <div className="flex flex-col gap-1.5 mb-4">
          {(cal?.calendarios ?? []).length === 0 && (
            <p className="text-xs text-dim">Nenhum calendário cadastrado.</p>
          )}
          {(cal?.calendarios ?? []).map(c => (
            <div key={c.calendario_nome} className="flex items-center gap-3 text-xs py-1">
              <span className="font-mono font-medium text-[#1A5FA8] dark:text-blue-400">{c.calendario_nome}</span>
              <span className="text-dim">{c.datas} datas</span>
              {c.proxima && <span className="text-dim">próxima: <span className="text-ink">{c.proxima}</span></span>}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end border-t border-edge pt-3">
          <Input label="Nome do Calendário" value={calNome} onChange={e => setCalNome(e.target.value)} className="w-44" />
          <Textarea label="Datas (uma por linha YYYY-MM-DD)" value={calDatas} onChange={e => setCalDatas(e.target.value)} className="w-52" rows={3} />
          <Input label="Descrição" value={calDesc} onChange={e => setCalDesc(e.target.value)} className="w-48" />
          <Button onClick={() => addCal.mutate()} loading={addCal.isPending} disabled={!calNome || !calDatas}>
            <Plus size={13} /> Adicionar / Atualizar
          </Button>
        </div>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Janelas de Blackout</h3>
        <div className="flex flex-col gap-2">
          {blackouts.length === 0 && <span className="text-xs text-dim">Nenhuma janela de blackout ativa.</span>}
          {blackouts.map(b => (
            <div key={b.id} className="flex items-center gap-3 text-xs py-1.5 border-b border-edge/40 last:border-0">
              <Badge value={b.vigente ? 'warning' : b.ativo ? 'info' : 'neutral'}>
                {b.vigente ? 'vigente' : b.ativo ? 'agendado' : 'encerrado'}
              </Badge>
              <span className="text-ink font-mono">{b.inicio} → {b.fim ?? '...'}</span>
              {b.escopo && <span className="text-dim">{b.escopo}</span>}
              {b.motivo && <span className="text-dim italic">{b.motivo}</span>}
              {!!b.ativo && (
                <Button variant="ghost" size="sm" className="ml-auto" onClick={() => encerrarBlackout(b.id)}>
                  Encerrar
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>

      <ConfirmModal
        open={!!freezeConfirm}
        title={freezeConfirm === 'congelar' ? 'Congelar Ambiente' : 'Descongelar Ambiente'}
        message={
          freezeConfirm === 'congelar'
            ? 'Congelar o ambiente bloqueará todas as execuções de pipelines. Confirma?'
            : 'Descongelar o ambiente retomará as execuções normais. Confirma?'
        }
        danger={freezeConfirm === 'congelar'}
        confirmLabel={freezeConfirm === 'congelar' ? '❄ Congelar' : 'Descongelar'}
        onConfirm={() => freezeConfirm && freeze(freezeConfirm)}
        onCancel={() => setFreezeConfirm(null)}
      />
    </div>
  )
}

// ── Usuários & Perfis ───────────────────────────────────────────
interface UsuarioRow { matricula: string; perfil: string; primeiro_nome?: string; email?: string; ativo: boolean; ultimo_login?: string }
interface PerfilRow { perfil_nome: string; descricao?: string; permissoes: string[] }

function UsuariosTab() {
  const [novoMat, setNovoMat] = useState('')
  const [novoPerfil, setNovoPerfil] = useState('consulta')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ usuarios: UsuarioRow[] }>({
    queryKey: ['admin-usuarios'],
    queryFn: () => adminPost('user_list'),
  })
  const { data: perfis } = useQuery<{ perfis: PerfilRow[] }>({
    queryKey: ['admin-perfis'],
    queryFn: () => adminPost('perfil_list'),
  })

  const upsertMut = useMutation({
    mutationFn: ({ matricula, perfil }: { matricula: string; perfil: string }) =>
      adminPost('user_upsert', { matricula, perfil }),
    onSuccess: () => {
      toast.success('Usuário salvo com sucesso')
      queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] })
      setNovoMat('')
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (matricula: string) => adminPost('user_delete', { matricula }),
    onSuccess: () => {
      toast.success('Usuário removido')
      queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] })
      setDeleteConfirm(null)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const perfilOpts: PerfilRow[] = perfis?.perfis ?? [
    { perfil_nome: 'admin', descricao: '', permissoes: [] },
    { perfil_nome: 'operador', descricao: '', permissoes: [] },
    { perfil_nome: 'consulta', descricao: '', permissoes: [] },
  ]

  const usuarios = data?.usuarios ?? []

  return (
    <div className="flex flex-col gap-5">
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">Matrícula</th>
                <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                <th className="px-4 py-2.5 text-left font-semibold">Perfil</th>
                <th className="px-4 py-2.5 text-left font-semibold">E-mail</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 text-left font-semibold">Último Login</th>
                <th className="px-4 py-2.5 w-12"></th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map(u => (
                <tr key={u.matricula} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-[#1A5FA8] dark:text-blue-400">{u.matricula}</td>
                  <td className="px-4 py-2.5 text-xs text-ink">{u.primeiro_nome ?? '—'}</td>
                  <td className="px-4 py-2.5"><Badge value={u.perfil} /></td>
                  <td className="px-4 py-2.5 text-xs text-dim">{u.email ?? '—'}</td>
                  <td className="px-4 py-2.5"><Badge value={u.ativo ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2.5 text-xs text-dim">{u.ultimo_login ?? '—'}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => setDeleteConfirm(u.matricula)}
                      className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors p-1 rounded"
                      title={`Remover ${u.matricula}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
              {usuarios.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-6 text-center text-xs text-dim">Nenhum usuário cadastrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-xs font-semibold text-dim uppercase tracking-wider mb-3">Adicionar / Atualizar Usuário</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <Input label="Matrícula" value={novoMat} onChange={e => setNovoMat(e.target.value)} className="w-40" placeholder="C123456" />
          <Select label="Perfil" value={novoPerfil} onChange={e => setNovoPerfil(e.target.value)} className="w-40">
            {perfilOpts.map(p => <option key={p.perfil_nome} value={p.perfil_nome}>{p.perfil_nome}</option>)}
          </Select>
          <Button
            onClick={() => upsertMut.mutate({ matricula: novoMat, perfil: novoPerfil })}
            loading={upsertMut.isPending}
            disabled={!novoMat.trim()}
          >
            <Plus size={13} /> Adicionar / Atualizar
          </Button>
        </div>
      </div>

      {(perfis?.perfis ?? []).length > 0 && (
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
          <h3 className="text-xs font-semibold text-dim uppercase tracking-wider mb-3">Perfis e Permissões</h3>
          <div className="flex flex-col gap-3">
            {(perfis?.perfis ?? []).map(p => (
              <div key={p.perfil_nome} className="flex items-start gap-3">
                <Badge value={p.perfil_nome} />
                <span className="text-xs text-dim flex-1">{p.descricao}</span>
                <div className="flex flex-wrap gap-1">
                  {(p.permissoes ?? []).map(rec => (
                    <span key={rec} className="text-[10px] bg-canvas border border-edge rounded px-1.5 py-0.5 text-dim font-mono">
                      {rec}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Remover Usuário"
        message={`Remover o usuário "${deleteConfirm}" do sistema? O acesso será revogado imediatamente.`}
        danger
        confirmLabel="Remover"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}

// ── Main ────────────────────────────────────────────────────────
const ADMIN_TABS = [
  { id: 'config',   label: 'Configurações' },
  { id: 'regen',    label: 'Regenerar DAGs' },
  { id: 'delete',   label: 'Excluir Pipeline' },
  { id: 'versoes',  label: 'Versões' },
  { id: 'tipos',    label: 'Tipos de Job' },
  { id: 'agenda',   label: 'Agendamento' },
  { id: 'usuarios', label: 'Usuários & Perfis' },
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
        {tab === 'config'   && <ConfigTab />}
        {tab === 'regen'    && <RegenDagsTab />}
        {tab === 'delete'   && <DeletePipelineTab />}
        {tab === 'versoes'  && <VersoesTab />}
        {tab === 'tipos'    && <TiposJobTab />}
        {tab === 'agenda'   && <AgendamentoTab />}
        {tab === 'usuarios' && <UsuariosTab />}
      </div>
    </div>
  )
}
