// Inventário de Consumidores — cadastro documental de quais endpoints/serviços
// consomem quais views/procs/tabelas de um banco (caso motivador: BUCC).
// Em alterações de schema, os consumidores registrados aqui são ajustados
// PRIMEIRO e o banco por último.
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { toast } from '../components/ui/Toast'
import { Cable, Pencil, Plus, Search, Trash2 } from 'lucide-react'

interface ObjetoInv {
  id: number
  objeto: string
  tipo: string               // view | proc | tabela
  status_validacao: string   // pendente | validado | com_erro
  observacao: string | null
}

interface EndpointInv {
  id: number
  endpoint: string
  plataforma: string | null
  consumidor: string | null
  banco: string
  descricao: string | null
  responsavel: string | null
  criado_por: string | null
  criado_em: string | null
  atualizado_por: string | null
  atualizado_em: string | null
  objetos: ObjetoInv[]
}

const STATUS_LABEL: Record<string, string> = {
  pendente: 'Pendente', validado: 'Validado', com_erro: 'Com erro',
}
// Par claro + escuro (tokens do projeto): pendente=âmbar, validado=verde, com_erro=vermelho.
const STATUS_CLS: Record<string, string> = {
  pendente: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
  validado: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  com_erro: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
}
const TIPOS_OBJETO = ['view', 'proc', 'tabela'] as const

function ObjetoBadge({ obj }: { obj: ObjetoInv }) {
  const cls = STATUS_CLS[obj.status_validacao] ?? STATUS_CLS.pendente
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono border whitespace-nowrap ${cls}`}
      title={`${obj.tipo} · ${STATUS_LABEL[obj.status_validacao] ?? obj.status_validacao}${obj.observacao ? ` — ${obj.observacao}` : ''}`}
    >
      {obj.objeto}
      <span className="opacity-70 font-sans">· {obj.tipo}</span>
    </span>
  )
}

export default function Inventario() {
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeEditar = isAdmin() || !!user?.permissoes?.includes('tela_inventario')

  const [busca, setBusca] = useState('')
  const [q, setQ] = useState('')            // busca com debounce (vira ?q=)
  const [banco, setBanco] = useState('')
  const [modalAberto, setModalAberto] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [excluir, setExcluir] = useState<EndpointInv | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setQ(busca.trim()), 300)
    return () => clearTimeout(t)
  }, [busca])

  const { data, isLoading } = useQuery<{ data: EndpointInv[] }>({
    queryKey: ['inventario', q, banco],
    queryFn: () => apiFetch(
      `/inventario/endpoints?q=${encodeURIComponent(q)}&banco=${encodeURIComponent(banco)}`),
  })
  const endpoints = data?.data ?? []

  // Bancos já vistos nesta sessão (para o filtro continuar oferecendo todos
  // mesmo com a lista atual filtrada por um deles).
  const bancosVistos = useRef<Set<string>>(new Set())
  endpoints.forEach(e => e.banco && bancosVistos.current.add(e.banco))
  const bancos = Array.from(bancosVistos.current).sort()

  const delMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/inventario/endpoints/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Endpoint excluído do inventário')
      setExcluir(null)
      queryClient.invalidateQueries({ queryKey: ['inventario'] })
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao excluir'),
  })

  const emEdicao = editId != null ? endpoints.find(e => e.id === editId) ?? null : null

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Cable size={20} className="text-[#1A5FA8]" /> Inventário de Consumidores
          </h1>
          <p className="text-sm text-dim mt-1">
            Endpoints e serviços que consomem views/procs de cada banco (ex.: BUCC),
            com o status de validação de cada objeto.
          </p>
        </div>
        {podeEditar && (
          <Button onClick={() => { setEditId(null); setModalAberto(true) }}>
            <Plus size={14} /> Novo endpoint
          </Button>
        )}
      </div>

      <InfoBanner storageKey="inventario_consumidores">
        Documente aqui quem consome cada view/proc do banco — em alterações de schema,
        os consumidores são ajustados primeiro e o banco por último.
      </InfoBanner>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-dim pointer-events-none" />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar endpoint, consumidor ou objeto…"
            className="w-72 bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
        <Select value={banco} onChange={e => setBanco(e.target.value)} title="Filtrar por banco">
          <option value="">Todos os bancos</option>
          {bancos.map(b => <option key={b} value={b}>{b}</option>)}
        </Select>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge">
            <span className="text-xs text-dim">
              {endpoints.length} endpoint{endpoints.length !== 1 ? 's' : ''}
            </span>
          </div>

          {endpoints.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">
              Nenhum endpoint no inventário{q || banco ? ' para os filtros atuais' : ''} —
              {podeEditar ? ' clique em “Novo endpoint” para documentar o primeiro consumidor.'
                          : ' peça a um desenvolvedor/admin para cadastrar.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                    <th className="px-4 py-2.5 text-left font-semibold">Endpoint</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Plataforma</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Consumidor</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Banco</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Objetos consumidos</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Responsável</th>
                    <th className="px-4 py-2.5 w-20"></th>
                  </tr>
                </thead>
                <tbody>
                  {endpoints.map(e => (
                    <tr key={e.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors align-top">
                      <td className="px-4 py-2.5">
                        <span className="text-xs font-medium text-ink">{e.endpoint}</span>
                        {e.descricao && (
                          <span className="block text-[11px] text-dim mt-0.5 max-w-xs">{e.descricao}</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink">{e.plataforma ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs text-ink">{e.consumidor ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-ink">{e.banco}</td>
                      <td className="px-4 py-2.5">
                        {e.objetos.length === 0
                          ? <span className="text-[11px] text-dim italic">sem objetos mapeados</span>
                          : (
                            <div className="flex flex-wrap gap-1 max-w-md">
                              {e.objetos.map(o => <ObjetoBadge key={o.id} obj={o} />)}
                            </div>
                          )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink">{e.responsavel ?? '—'}</td>
                      <td className="px-4 py-2.5 whitespace-nowrap text-right">
                        {podeEditar && (
                          <>
                            <Button variant="ghost" size="sm" title="Editar"
                              onClick={() => { setEditId(e.id); setModalAberto(true) }}>
                              <Pencil size={14} />
                            </Button>
                            <Button variant="ghost" size="sm" title="Excluir"
                              onClick={() => setExcluir(e)}>
                              <Trash2 size={14} className="text-dim" />
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {modalAberto && (
        <EndpointModal
          key={editId ?? 'novo'}
          endpoint={emEdicao}
          onClose={() => { setModalAberto(false); setEditId(null) }}
          onCriado={id => setEditId(id)}
        />
      )}

      <Modal open={excluir != null} onClose={() => setExcluir(null)} title="Excluir endpoint" size="sm">
        <p className="text-sm text-ink">
          Excluir <strong>{excluir?.endpoint}</strong> do inventário?
        </p>
        <p className="text-xs text-dim mt-1">
          O registro é desativado (soft delete) — o histórico permanece no banco.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="secondary" size="sm" onClick={() => setExcluir(null)}>Cancelar</Button>
          <Button variant="danger" size="sm" loading={delMut.isPending}
            onClick={() => excluir && delMut.mutate(excluir.id)}>
            <Trash2 size={14} /> Excluir
          </Button>
        </div>
      </Modal>
    </div>
  )
}

// ── Modal de criar/editar endpoint (+ gestão dos objetos na edição) ─────────
function EndpointModal({ endpoint, onClose, onCriado }: {
  endpoint: EndpointInv | null
  onClose: () => void
  onCriado: (id: number) => void
}) {
  const editando = endpoint != null
  const [form, setForm] = useState({
    endpoint: endpoint?.endpoint ?? '',
    plataforma: endpoint?.plataforma ?? '',
    consumidor: endpoint?.consumidor ?? '',
    banco: endpoint?.banco ?? 'BUCC',
    responsavel: endpoint?.responsavel ?? '',
    descricao: endpoint?.descricao ?? '',
  })
  const set = (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(f => ({ ...f, [k]: e.target.value }))

  const [novoObjeto, setNovoObjeto] = useState('')
  const [novoTipo, setNovoTipo] = useState<string>('view')

  const invalidar = () => queryClient.invalidateQueries({ queryKey: ['inventario'] })

  const saveMut = useMutation({
    mutationFn: () => apiFetch<{ id: number; criado: boolean }>('/inventario/endpoints', {
      method: 'POST',
      body: JSON.stringify({ ...(editando ? { id: endpoint!.id } : {}), ...form }),
    }),
    onSuccess: d => {
      toast.success(editando ? 'Endpoint atualizado' : 'Endpoint criado — agora mapeie os objetos consumidos')
      invalidar()
      if (!editando) onCriado(d.id)   // permanece no modal, já em modo edição
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao salvar'),
  })

  const addObjMut = useMutation({
    mutationFn: () => apiFetch(`/inventario/endpoints/${endpoint!.id}/objetos`, {
      method: 'POST',
      body: JSON.stringify({ objeto: novoObjeto, tipo: novoTipo }),
    }),
    onSuccess: () => { setNovoObjeto(''); invalidar() },
    onError: (e: any) => toast.error(e?.message || 'Falha ao adicionar objeto'),
  })

  const patchObj = async (oid: number, body: Record<string, unknown>) => {
    try {
      await apiFetch(`/inventario/objetos/${oid}`, { method: 'PATCH', body: JSON.stringify(body) })
      invalidar()
    } catch (e: any) { toast.error(e?.message || 'Falha ao atualizar objeto') }
  }

  const delObj = async (oid: number) => {
    try {
      await apiFetch(`/inventario/objetos/${oid}`, { method: 'DELETE' })
      invalidar()
    } catch (e: any) { toast.error(e?.message || 'Falha ao remover objeto') }
  }

  return (
    <Modal open onClose={onClose} size="lg"
      title={editando ? `Editar endpoint — ${endpoint!.endpoint}` : 'Novo endpoint'}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="sm:col-span-2">
            <Input label="Endpoint / serviço *" value={form.endpoint} onChange={set('endpoint')}
              placeholder="ex.: GBE_ConsultaContratos" />
          </div>
          <Input label="Plataforma" value={form.plataforma} onChange={set('plataforma')}
            placeholder="ex.: GI, Salesforce, Genesys" />
          <Input label="Consumidor (quem chama)" value={form.consumidor} onChange={set('consumidor')}
            placeholder="ex.: Salesforce, Equipe Jordan" />
          <Input label="Banco" value={form.banco} onChange={set('banco')} placeholder="BUCC" />
          <Input label="Responsável" value={form.responsavel} onChange={set('responsavel')}
            placeholder="quem responde por este consumidor" />
          <div className="sm:col-span-2">
            <Textarea label="Descrição" rows={2} value={form.descricao} onChange={set('descricao')}
              placeholder="contexto, incidentes, pendências de validação…" />
          </div>
        </div>

        <div className="border-t border-edge pt-4">
          <h3 className="text-sm font-semibold text-ink mb-1">Objetos consumidos</h3>
          {!editando ? (
            <p className="text-xs text-dim">
              Salve o endpoint para começar a mapear as views/procs/tabelas consumidas.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {endpoint!.objetos.length === 0 && (
                <p className="text-xs text-dim">Nenhum objeto mapeado ainda.</p>
              )}
              {endpoint!.objetos.map(o => (
                <div key={o.id} className="flex items-center gap-2 flex-wrap bg-canvas/50 border border-edge/50 rounded-md px-2.5 py-1.5">
                  <span className="font-mono text-xs text-ink">{o.objeto}</span>
                  <span className="text-[11px] text-dim">({o.tipo})</span>
                  <select
                    className={`rounded px-1.5 py-0.5 text-xs border ${STATUS_CLS[o.status_validacao] ?? STATUS_CLS.pendente}`}
                    value={o.status_validacao}
                    onChange={e => patchObj(o.id, { status_validacao: e.target.value })}
                  >
                    {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <input
                    className="flex-1 min-w-40 bg-panel border border-edge rounded px-1.5 py-0.5 text-xs text-ink placeholder-dim"
                    defaultValue={o.observacao ?? ''} placeholder="observação"
                    onBlur={e => { if (e.target.value !== (o.observacao ?? '')) patchObj(o.id, { observacao: e.target.value }) }}
                  />
                  <Button variant="ghost" size="sm" title="Remover objeto" onClick={() => delObj(o.id)}>
                    <Trash2 size={13} className="text-dim" />
                  </Button>
                </div>
              ))}

              <div className="flex items-end gap-2 mt-1">
                <div className="flex-1">
                  <Input label="Novo objeto" value={novoObjeto}
                    onChange={e => setNovoObjeto(e.target.value)}
                    placeholder="ex.: VW_CLIENTES_EMAIL_TELEFONE_CVP"
                    onKeyDown={e => { if (e.key === 'Enter' && novoObjeto.trim()) addObjMut.mutate() }} />
                </div>
                <Select label="Tipo" value={novoTipo} onChange={e => setNovoTipo(e.target.value)}>
                  {TIPOS_OBJETO.map(t => <option key={t} value={t}>{t}</option>)}
                </Select>
                <Button variant="secondary" size="md" loading={addObjMut.isPending}
                  disabled={!novoObjeto.trim()} onClick={() => addObjMut.mutate()}>
                  <Plus size={14} /> Adicionar
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-edge pt-4">
          <Button variant="secondary" onClick={onClose}>Fechar</Button>
          <Button loading={saveMut.isPending} disabled={!form.endpoint.trim()}
            onClick={() => saveMut.mutate()}>
            {editando ? 'Salvar alterações' : 'Criar endpoint'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
