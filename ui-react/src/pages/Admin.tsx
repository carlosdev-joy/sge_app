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
import type { AdminConfig, Usuario, Perfil, Versao, TipoJob, Calendario, Blackout } from '../types'
import { queryClient } from '../lib/queryClient'
import { Edit, Trash2, Plus, AlertTriangle } from 'lucide-react'

// ── Configurações ───────────────────────────────────────────────
function ConfigTab() {
  const [editItem, setEditItem] = useState<AdminConfig | null>(null)
  const [newKey, setNewKey] = useState(''); const [newVal, setNewVal] = useState(''); const [newDesc, setNewDesc] = useState('')

  const { data, isLoading } = useQuery<{ configs: AdminConfig[] }>({
    queryKey: ['admin-config'],
    queryFn: () => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'config_list' }) }),
  })

  const upsertMut = useMutation({
    mutationFn: (c: AdminConfig) => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'config_upsert', ...c }) }),
    onSuccess: () => { toast.success('Configuração salva'); queryClient.invalidateQueries({ queryKey: ['admin-config'] }); setEditItem(null); setNewKey(''); setNewVal(''); setNewDesc('') },
    onError: (e: any) => toast.error(e.message),
  })
  const deleteMut = useMutation({
    mutationFn: (chave: string) => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'config_delete', chave }) }),
    onSuccess: () => { toast.success('Removido'); queryClient.invalidateQueries({ queryKey: ['admin-config'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  const testWebhook = () => apiFetch('/admin/test-webhook', { method: 'POST' }).then(() => toast.success('Webhook enviado')).catch((e: any) => toast.error(e.message))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={testWebhook}>🔔 Testar Webhook</Button>
      </div>
      {isLoading ? <PageSpinner /> : (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
              <th className="px-4 py-2 text-left">Chave</th><th className="px-4 py-2 text-left">Valor</th><th className="px-4 py-2 text-left">Descrição</th><th className="px-4 py-2 text-right">Ações</th>
            </tr></thead>
            <tbody>
              {(data?.configs ?? []).map((c) => (
                <tr key={c.chave} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                  <td className="px-4 py-2 font-mono text-xs text-blue-400">{c.chave}</td>
                  <td className="px-4 py-2 font-mono text-xs text-[#e2e8f0]">{c.valor}</td>
                  <td className="px-4 py-2 text-xs text-[#94a3b8]">{c.descricao}</td>
                  <td className="px-4 py-2 flex justify-end gap-1.5">
                    <Button variant="ghost" size="sm" onClick={() => setEditItem(c)}><Edit size={13} /></Button>
                    <Button variant="ghost" size="sm" onClick={() => { if(confirm(`Remover ${c.chave}?`)) deleteMut.mutate(c.chave) }}><Trash2 size={13} className="text-red-400" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* Novo parâmetro */}
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Input label="Chave" value={newKey} onChange={e => setNewKey(e.target.value)} className="w-48" />
        <Input label="Valor" value={newVal} onChange={e => setNewVal(e.target.value)} className="w-48" />
        <Input label="Descrição" value={newDesc} onChange={e => setNewDesc(e.target.value)} className="w-56" />
        <Button onClick={() => upsertMut.mutate({ chave: newKey, valor: newVal, descricao: newDesc })} disabled={!newKey || !newVal}><Plus size={13} /> Adicionar</Button>
      </div>

      {editItem && (
        <Modal open title={`Editar: ${editItem.chave}`} onClose={() => setEditItem(null)}>
          <div className="flex flex-col gap-3">
            <Input label="Valor" defaultValue={editItem.valor} id="edit-val" />
            <Input label="Descrição" defaultValue={editItem.descricao} id="edit-desc" />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditItem(null)}>Cancelar</Button>
              <Button onClick={() => {
                const val = (document.getElementById('edit-val') as HTMLInputElement).value
                const desc = (document.getElementById('edit-desc') as HTMLInputElement).value
                upsertMut.mutate({ chave: editItem.chave, valor: val, descricao: desc })
              }}>Salvar</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Regenerar DAGs ──────────────────────────────────────────────
function RegenDagsTab() {
  const [projeto, setProjeto] = useState('')
  const [log, setLog] = useState('')
  const [loading, setLoading] = useState(false)

  const regen = async () => {
    setLoading(true); setLog('')
    try {
      const res = await apiFetch<any>('/admin', {
        method: 'POST',
        body: JSON.stringify({ operacao: 'regen_dags', projeto: projeto || undefined }),
      })
      setLog(JSON.stringify(res, null, 2))
      toast.success('Regeneração concluída')
    } catch (e: any) {
      toast.error(e.message)
      setLog(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-3 flex items-start gap-2 text-sm text-yellow-300">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        A regeneração de DAGs dispara a etl_dag_factory. Todos os DAGs do projeto serão recriados no Airflow.
      </div>
      <div className="flex gap-3 items-end">
        <Select label="Projeto (opcional)" value={projeto} onChange={e => setProjeto(e.target.value)} className="w-48">
          <option value="">Todos</option>
          {['BI_CVP','BI_VIDA','BI_PREVIDENCIA','BI_PRESTAMISTA'].map(p => <option key={p}>{p}</option>)}
        </Select>
        <Button onClick={regen} loading={loading} variant="danger">⟳ Regenerar DAGs</Button>
      </div>
      {log && <pre className="text-xs text-[#94a3b8] bg-[#0f1117] rounded-lg p-4 overflow-auto max-h-64">{log}</pre>}
    </div>
  )
}

// ── Excluir Pipeline ────────────────────────────────────────────
function DeletePipelineTab() {
  const [nome, setNome] = useState('')
  const [preview, setPreview] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const fetchDeps = async () => {
    setLoading(true)
    try {
      const res = await apiFetch<any>('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'pipeline_delete_preview', pipeline_name: nome }) })
      setPreview(res)
    } catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  const del = async () => {
    if (!confirm(`ATENÇÃO: Excluir "${nome}" é irreversível. Confirma?`)) return
    setLoading(true)
    try {
      await apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'pipeline_delete', pipeline_name: nome }) })
      toast.success('Pipeline excluído'); setNome(''); setPreview(null)
    } catch (e: any) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-3 flex items-start gap-2 text-sm text-red-300">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        Esta operação é irreversível. Todos os jobs, execuções e lineage do pipeline serão removidos.
      </div>
      <div className="flex gap-3 items-end">
        <Input label="Nome do Pipeline" value={nome} onChange={e => setNome(e.target.value)} className="w-72" placeholder="nome exato" />
        <Button variant="secondary" onClick={fetchDeps} loading={loading} disabled={!nome}>Ver Dependências</Button>
        {preview && <Button variant="danger" onClick={del} loading={loading}>Excluir</Button>}
      </div>
      {preview && (
        <pre className="text-xs text-[#94a3b8] bg-[#0f1117] rounded-lg p-4 overflow-auto max-h-48">{JSON.stringify(preview, null, 2)}</pre>
      )}
    </div>
  )
}

// ── Versões ─────────────────────────────────────────────────────
function VersoesTab() {
  const [nova, setNova] = useState<Partial<Versao>>({})
  const [showForm, setShowForm] = useState(false)

  const { data, isLoading } = useQuery<{ versoes: Versao[] }>({
    queryKey: ['versoes'],
    queryFn: () => apiFetch('/versao'),
  })

  const mut = useMutation({
    mutationFn: (v: Versao) => apiFetch('/versao/register', { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: () => { toast.success('Versão salva'); queryClient.invalidateQueries({ queryKey: ['versoes'] }); setShowForm(false); setNova({}) },
    onError: (e: any) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowForm(true)}><Plus size={13} /> Nova Versão</Button>
      </div>
      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-3">
          {(data?.versoes ?? []).map((v) => (
            <div key={v.versao} className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-blue-400 font-bold font-mono">{v.versao}</span>
                <span className="text-[#e2e8f0] font-medium">{v.titulo}</span>
                {v.data && <span className="text-xs text-[#94a3b8] ml-auto">{v.data}</span>}
              </div>
              {v.descricao && <p className="text-sm text-[#94a3b8] whitespace-pre-wrap">{v.descricao}</p>}
            </div>
          ))}
        </div>
      )}
      {showForm && (
        <Modal open title="Nova Versão" onClose={() => setShowForm(false)}>
          <div className="flex flex-col gap-4">
            <Input label="Versão" value={nova.versao ?? ''} onChange={e => setNova(n => ({ ...n, versao: e.target.value }))} placeholder="v2.5.0" />
            <Input label="Título" value={nova.titulo ?? ''} onChange={e => setNova(n => ({ ...n, titulo: e.target.value }))} />
            <Textarea label="Descrição (markdown)" value={nova.descricao ?? ''} onChange={e => setNova(n => ({ ...n, descricao: e.target.value }))} rows={5} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
              <Button onClick={() => mut.mutate(nova as Versao)} loading={mut.isPending}>Salvar</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Tipos de Job ────────────────────────────────────────────────
function TiposJobTab() {
  const { data, isLoading } = useQuery<{ tipos: TipoJob[] }>({
    queryKey: ['tipos-job'],
    queryFn: () => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'tipo_job_list' }) }),
  })

  return (
    <div className="flex flex-col gap-4">
      {isLoading ? <PageSpinner /> : (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
              <th className="px-4 py-2 text-left">Nome</th><th className="px-4 py-2 text-left">Descrição</th><th className="px-4 py-2 text-left">Lineage</th><th className="px-4 py-2 text-left">Status</th>
            </tr></thead>
            <tbody>
              {(data?.tipos ?? []).map((t) => (
                <tr key={t.nome} className="border-b border-[#2a2d3a]/50">
                  <td className="px-4 py-2 font-mono text-xs text-[#e2e8f0]">{t.nome}</td>
                  <td className="px-4 py-2 text-xs text-[#94a3b8]">{t.descricao}</td>
                  <td className="px-4 py-2"><Badge value={t.lineage_habilitado ? 'sim' : 'não'} /></td>
                  <td className="px-4 py-2"><Badge value={t.ativo ? 'ativo' : 'inativo'} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Agendamento ─────────────────────────────────────────────────
function AgendamentoTab() {
  const [freezeLoading, setFreezeLoading] = useState(false)
  const [novoCalNome, setNovoCalNome] = useState(''); const [novoCalDatas, setNovoCalDatas] = useState(''); const [novoCalDesc, setNovoCalDesc] = useState('')

  const { data: calendarios } = useQuery<{ calendarios: Calendario[] }>({
    queryKey: ['calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
  })
  const { data: blackouts } = useQuery<{ blackouts: Blackout[] }>({
    queryKey: ['blackouts'],
    queryFn: () => apiFetch('/agenda/blackouts'),
  })

  const freeze = async () => {
    setFreezeLoading(true)
    try { await apiFetch('/admin/freeze', { method: 'POST' }); toast.success('Ambiente alternado') }
    catch (e: any) { toast.error(e.message) }
    finally { setFreezeLoading(false) }
  }

  const addCal = useMutation({
    mutationFn: () => apiFetch('/agenda/calendarios', {
      method: 'POST',
      body: JSON.stringify({ nome: novoCalNome, datas: novoCalDatas.split('\n').map(d=>d.trim()).filter(Boolean), descricao: novoCalDesc }),
    }),
    onSuccess: () => { toast.success('Calendário adicionado'); queryClient.invalidateQueries({ queryKey: ['calendarios'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-6">
      {/* Freeze */}
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#e2e8f0] mb-3">Congelamento de Ambiente</h3>
        <div className="flex items-center gap-3">
          <Button variant="danger" onClick={freeze} loading={freezeLoading}>❄ Alternar Freeze</Button>
          <span className="text-xs text-[#94a3b8]">Congela/descongela o disparo de pipelines no ambiente.</span>
        </div>
      </div>

      {/* Calendários */}
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#e2e8f0] mb-3">Calendários de Bloqueio</h3>
        <div className="flex flex-col gap-2 mb-4">
          {(calendarios?.calendarios ?? []).map(c => (
            <div key={c.nome} className="flex items-center gap-3 text-sm">
              <span className="text-blue-400 font-mono">{c.nome}</span>
              <span className="text-[#94a3b8] text-xs">{c.datas?.length ?? 0} datas</span>
              {c.descricao && <span className="text-xs text-[#94a3b8]">{c.descricao}</span>}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end border-t border-[#2a2d3a] pt-3">
          <Input label="Nome" value={novoCalNome} onChange={e => setNovoCalNome(e.target.value)} className="w-36" />
          <Textarea label="Datas (uma por linha, YYYY-MM-DD)" value={novoCalDatas} onChange={e => setNovoCalDatas(e.target.value)} className="w-48" rows={3} />
          <Input label="Descrição" value={novoCalDesc} onChange={e => setNovoCalDesc(e.target.value)} className="w-48" />
          <Button onClick={() => addCal.mutate()} loading={addCal.isPending} disabled={!novoCalNome}><Plus size={13} /> Adicionar</Button>
        </div>
      </div>

      {/* Blackouts */}
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#e2e8f0] mb-3">Janelas de Blackout</h3>
        <div className="flex flex-col gap-2">
          {(blackouts?.blackouts ?? []).map(b => (
            <div key={b.id} className="flex items-center gap-3 text-sm">
              <Badge value={b.ativo ? 'ativo' : 'encerrado'} />
              <span className="text-[#e2e8f0] text-xs">{b.inicio} → {b.fim ?? '...'}</span>
              {b.motivo && <span className="text-[#94a3b8] text-xs">{b.motivo}</span>}
              {b.ativo && (
                <Button variant="ghost" size="sm" onClick={() => apiFetch(`/agenda/blackouts/${b.id}/encerrar`, { method: 'POST' }).then(() => { toast.success('Encerrado'); queryClient.invalidateQueries({ queryKey: ['blackouts'] }) })}>
                  Encerrar
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Usuários & Perfis ───────────────────────────────────────────
function UsuariosTab() {
  const [novoMat, setNovoMat] = useState(''); const [novoPerfil, setNovoPerfil] = useState('operador')

  const { data, isLoading } = useQuery<{ usuarios: Usuario[] }>({
    queryKey: ['admin-usuarios'],
    queryFn: () => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'user_list' }) }),
  })
  const { data: perfis } = useQuery<{ perfis: Perfil[] }>({
    queryKey: ['admin-perfis'],
    queryFn: () => apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'perfil_list' }) }),
  })

  const upsertMut = useMutation({
    mutationFn: ({ matricula, perfil }: { matricula: string; perfil: string }) =>
      apiFetch('/admin', { method: 'POST', body: JSON.stringify({ operacao: 'user_upsert', matricula, perfil }) }),
    onSuccess: () => { toast.success('Usuário salvo'); queryClient.invalidateQueries({ queryKey: ['admin-usuarios'] }); setNovoMat('') },
    onError: (e: any) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-4">
      {isLoading ? <PageSpinner /> : (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
              <th className="px-4 py-2 text-left">Matrícula</th><th className="px-4 py-2 text-left">Nome</th><th className="px-4 py-2 text-left">Perfil</th><th className="px-4 py-2 text-left">Email</th><th className="px-4 py-2 text-left">Status</th><th className="px-4 py-2 text-left">Último Login</th>
            </tr></thead>
            <tbody>
              {(data?.usuarios ?? []).map(u => (
                <tr key={u.matricula} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                  <td className="px-4 py-2 font-mono text-xs text-blue-400">{u.matricula}</td>
                  <td className="px-4 py-2 text-xs text-[#e2e8f0]">{u.primeiro_nome}</td>
                  <td className="px-4 py-2"><Badge value={u.perfil} /></td>
                  <td className="px-4 py-2 text-xs text-[#94a3b8]">{u.email}</td>
                  <td className="px-4 py-2"><Badge value={u.ativo ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2 text-xs text-[#94a3b8]">{u.ultimo_login}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Input label="Matrícula" value={novoMat} onChange={e => setNovoMat(e.target.value)} className="w-36" placeholder="C123456" />
        <Select label="Perfil" value={novoPerfil} onChange={e => setNovoPerfil(e.target.value)} className="w-36">
          {(perfis?.perfis ?? [{ nome: 'admin' },{ nome: 'operador' },{ nome: 'consulta' }]).map(p => <option key={p.nome}>{p.nome}</option>)}
        </Select>
        <Button onClick={() => upsertMut.mutate({ matricula: novoMat, perfil: novoPerfil })} loading={upsertMut.isPending} disabled={!novoMat}><Plus size={13} /> Adicionar/Atualizar</Button>
      </div>
    </div>
  )
}

// ── Main ────────────────────────────────────────────────────────
const ADMIN_TABS = [
  { id: 'config',     label: 'Configurações' },
  { id: 'regen',      label: 'Regenerar DAGs' },
  { id: 'delete',     label: 'Excluir Pipeline' },
  { id: 'versoes',    label: 'Versões' },
  { id: 'tipos',      label: 'Tipos de Job' },
  { id: 'agenda',     label: 'Agendamento' },
  { id: 'usuarios',   label: 'Usuários & Perfis' },
]

export default function Admin() {
  const [tab, setTab] = useState('config')
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold text-[#e2e8f0]">⚙ Admin</h1>
      <Tabs tabs={ADMIN_TABS} active={tab} onChange={setTab} size="sm" />
      <div className="mt-2">
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
