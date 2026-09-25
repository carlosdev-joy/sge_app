import { useState, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select, Textarea } from '../../ui/Input'
import { PlaceholderPicker } from '../../ui/PlaceholderPicker'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal } from '../ComumUI'
import { Edit2, Trash2, Plus, Save, Bell, MessageSquare } from 'lucide-react'

// ── Notificações Teams — Grupos (canais) + Modelos de card ───────────────────
interface MsgGrupoRow { id: number; nome: string; descricao: string | null; has_webhook: boolean; ativo: boolean }
interface MsgFact { label: string; value: string }
interface MsgTemplateRow {
  id: number; grupo_id: number | null; nome: string; titulo: string | null; corpo: string
  facts: MsgFact[]; cor: string | null; botao_texto: string | null; botao_url: string | null; ativo: boolean
}

const CARD_PLACEHOLDERS = '{pipeline} {job} {linhas} {status} {data}'

const CARD_COR_OPTS: { v: string; label: string }[] = [
  { v: 'auto', label: 'Automática (segue o status do pipeline)' },
  { v: 'info', label: 'Informação (azul)' },
  { v: 'success', label: 'Sucesso (verde)' },
  { v: 'warning', label: 'Aviso (âmbar)' },
  { v: 'error', label: 'Erro (vermelho)' },
]

// Form de Grupo (canal Teams). O webhook é mascarado na leitura (has_webhook):
// no edit o campo começa vazio e só é enviado se o usuário digitar um novo valor.
function GrupoFormModal({ grupo, onClose }: { grupo: MsgGrupoRow | null; onClose: () => void }) {
  const isEdit = !!grupo
  const [nome, setNome] = useState(grupo?.nome ?? '')
  const [descricao, setDescricao] = useState(grupo?.descricao ?? '')
  const [webhook, setWebhook] = useState('')
  const [ativo, setAtivo] = useState(grupo?.ativo ?? true)

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { nome, descricao, ativo }
      // Mascaramento: só envia webhook_url se o usuário digitou algo. Omitir a
      // chave preserva o webhook atual no backend (PUT). Vazio nunca é enviado.
      if (webhook.trim()) body.webhook_url = webhook.trim()
      return isEdit
        ? apiFetch(`/msg/grupos/${grupo!.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : apiFetch('/msg/grupos', { method: 'POST', body: JSON.stringify(body) })
    },
    onSuccess: () => { toast.success(isEdit ? 'Canal atualizado' : 'Canal criado'); queryClient.invalidateQueries({ queryKey: ['msg-grupos'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao salvar canal'),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar canal Teams' : 'Novo canal Teams'}>
      <div className="flex flex-col gap-4">
        <Input label="Nome *" value={nome} onChange={e => setNome(e.target.value)} placeholder="ex.: Alertas BI Vida" autoFocus />
        <Input label="Descrição" value={descricao} onChange={e => setDescricao(e.target.value)} placeholder="Para que serve este canal" />
        <div className="flex flex-col gap-1">
          <Input
            label={isEdit ? 'Webhook do canal (deixe vazio p/ manter)' : 'Webhook do canal Teams'}
            type="password"
            value={webhook}
            onChange={e => setWebhook(e.target.value)}
            placeholder={isEdit
              ? (grupo!.has_webhook ? '•••••• webhook configurado — vazio mantém' : 'deixe vazio p/ manter')
              : 'https://outlook.office.com/webhook/…'}
          />
          {isEdit && (
            <span className="text-[10px] text-dim">
              {grupo!.has_webhook
                ? 'Já existe um webhook salvo (oculto por segurança). Digite um novo só para substituir.'
                : 'Nenhum webhook salvo ainda.'}
            </span>
          )}
        </div>
        <Select label="Status" value={ativo ? '1' : '0'} onChange={e => setAtivo(e.target.value === '1')}>
          <option value="1">Ativo</option>
          <option value="0">Inativo</option>
        </Select>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!nome.trim()}><Save size={13} /> Salvar</Button>
        </div>
      </div>
    </Modal>
  )
}

// Form de Modelo de card. Inclui o editor dinâmico de fatos (lista de {label,value}),
// a cor estruturada e o botão opcional. facts é enviado como lista de objetos.
function TemplateFormModal({ template, grupos, onClose }: { template: MsgTemplateRow | null; grupos: MsgGrupoRow[]; onClose: () => void }) {
  const isEdit = !!template
  const [nome, setNome] = useState(template?.nome ?? '')
  const [grupoId, setGrupoId] = useState(template?.grupo_id != null ? String(template.grupo_id) : '')
  const [titulo, setTitulo] = useState(template?.titulo ?? '')
  const [corpo, setCorpo] = useState(template?.corpo ?? '')
  const [facts, setFacts] = useState<MsgFact[]>(template?.facts?.length ? template.facts : [])
  const [cor, setCor] = useState(template?.cor ?? 'auto')
  const [botaoTexto, setBotaoTexto] = useState(template?.botao_texto ?? '')
  const [botaoUrl, setBotaoUrl] = useState(template?.botao_url ?? '')
  const [ativo, setAtivo] = useState(template?.ativo ?? true)
  const corpoRef = useRef<HTMLTextAreaElement>(null)
  const tituloRef = useRef<HTMLInputElement>(null)
  const factValueRefs = useRef<(HTMLInputElement | null)[]>([])
  const [activeFactIdx, setActiveFactIdx] = useState(0)
  const CARD_PH_LIST = CARD_PLACEHOLDERS.replace(/[{}]/g, '').split(' ')

  const addFact = () => setFacts(f => [...f, { label: '', value: '' }])
  const removeFact = (i: number) => setFacts(f => f.filter((_, idx) => idx !== i))
  const setFact = (i: number, key: keyof MsgFact, val: string) =>
    setFacts(f => f.map((it, idx) => idx === i ? { ...it, [key]: val } : it))

  const save = useMutation({
    mutationFn: () => {
      const body = {
        grupo_id: grupoId ? Number(grupoId) : null,
        nome, titulo, corpo,
        // Envia só fatos com label preenchido; lista de objetos, conforme contrato.
        facts: facts.filter(f => f.label.trim()).map(f => ({ label: f.label, value: f.value })),
        cor,
        botao_texto: botaoTexto,
        botao_url: botaoUrl,
        ativo,
      }
      return isEdit
        ? apiFetch(`/msg/templates/${template!.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : apiFetch('/msg/templates', { method: 'POST', body: JSON.stringify(body) })
    },
    onSuccess: () => { toast.success(isEdit ? 'Modelo atualizado' : 'Modelo criado'); queryClient.invalidateQueries({ queryKey: ['msg-templates'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao salvar modelo'),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar modelo de card' : 'Novo modelo de card'} size="lg">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input label="Nome *" value={nome} onChange={e => setNome(e.target.value)} placeholder="ex.: Falha de pipeline" autoFocus />
          <Select label="Canal sugerido (opcional)" value={grupoId} onChange={e => setGrupoId(e.target.value)}>
            <option value="">— Nenhum</option>
            {grupos.map(g => <option key={g.id} value={String(g.id)}>{g.nome}</option>)}
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <Input ref={tituloRef} label="Título do card" value={titulo} onChange={e => setTitulo(e.target.value)} placeholder="ex.: Pipeline {pipeline} falhou" />
          <PlaceholderPicker label="Inserir:" placeholders={CARD_PH_LIST} targetRef={tituloRef} value={titulo} onChange={setTitulo} />
        </div>

        <div className="flex flex-col gap-1">
          <Textarea ref={corpoRef} label="Corpo *" rows={4} value={corpo} onChange={e => setCorpo(e.target.value)}
            placeholder="Texto da mensagem. Use os placeholders abaixo." />
          <PlaceholderPicker
            label="Inserir:"
            placeholders={CARD_PLACEHOLDERS.replace(/[{}]/g, '').split(' ')}
            targetRef={corpoRef}
            value={corpo}
            onChange={setCorpo}
          />
        </div>

        {/* Editor de fatos: lista dinâmica de pares {label,value} */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="text-xs text-dim font-medium">Fatos (FactSet do card)</label>
            <Button size="sm" variant="secondary" onClick={addFact}><Plus size={12} /> Adicionar fato</Button>
          </div>
          {facts.length === 0 && (
            <p className="text-[11px] text-dim italic">Nenhum fato. Fatos viram uma lista de "rótulo: valor" no card (o valor aceita placeholders).</p>
          )}
          <div className="flex flex-col gap-2">
            {facts.map((f, i) => (
              <div key={i} className="flex items-end gap-2">
                <Input label={i === 0 ? 'Rótulo' : undefined} value={f.label} onChange={e => setFact(i, 'label', e.target.value)} placeholder="ex.: Linhas" className="w-40" />
                <Input label={i === 0 ? 'Valor' : undefined} ref={el => { factValueRefs.current[i] = el }} onFocus={() => setActiveFactIdx(i)} value={f.value} onChange={e => setFact(i, 'value', e.target.value)} placeholder="ex.: {linhas}" className="flex-1" />
                <button onClick={() => removeFact(i)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1.5 rounded mb-0.5" title="Remover fato"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
          {facts.length > 0 && (
            <PlaceholderPicker
              label="Inserir no valor do fato em foco:"
              placeholders={CARD_PH_LIST}
              targetRef={{ current: factValueRefs.current[activeFactIdx] ?? null }}
              value={facts[activeFactIdx]?.value ?? ''}
              onChange={v => setFact(activeFactIdx, 'value', v)}
            />
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Select label="Cor do card" value={cor} onChange={e => setCor(e.target.value)}>
            {CARD_COR_OPTS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
          </Select>
          <Select label="Status" value={ativo ? '1' : '0'} onChange={e => setAtivo(e.target.value === '1')}>
            <option value="1">Ativo</option>
            <option value="0">Inativo</option>
          </Select>
        </div>

        {/* Botão opcional do card */}
        <div className="border border-edge rounded-lg p-3 bg-canvas/40 flex flex-col gap-3">
          <span className="text-xs text-dim font-medium">Botão de ação (opcional)</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Texto do botão" value={botaoTexto} onChange={e => setBotaoTexto(e.target.value)} placeholder="ex.: Abrir no Orquestra" />
            <Input label="URL do botão" value={botaoUrl} onChange={e => setBotaoUrl(e.target.value)} placeholder="https://…" />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!nome.trim() || !corpo.trim()}><Save size={13} /> Salvar</Button>
        </div>
      </div>
    </Modal>
  )
}

export function NotificacoesTab() {
  const [grupoForm, setGrupoForm] = useState<{ open: boolean; grupo: MsgGrupoRow | null }>({ open: false, grupo: null })
  const [delGrupo, setDelGrupo] = useState<MsgGrupoRow | null>(null)
  const [tplForm, setTplForm] = useState<{ open: boolean; template: MsgTemplateRow | null }>({ open: false, template: null })
  const [delTpl, setDelTpl] = useState<MsgTemplateRow | null>(null)

  const gruposQ = useQuery<{ data: MsgGrupoRow[] }>({ queryKey: ['msg-grupos'], queryFn: () => apiFetch('/msg/grupos') })
  const templatesQ = useQuery<{ data: MsgTemplateRow[] }>({ queryKey: ['msg-templates'], queryFn: () => apiFetch('/msg/templates') })

  const grupos = gruposQ.data?.data ?? []
  const templates = templatesQ.data?.data ?? []
  const grupoNome = (id: number | null) => (id == null ? '—' : grupos.find(g => g.id === id)?.nome ?? `#${id}`)

  const delGrupoMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/msg/grupos/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Canal removido'); queryClient.invalidateQueries({ queryKey: ['msg-grupos'] }); setDelGrupo(null) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })
  const delTplMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/msg/templates/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Modelo removido'); queryClient.invalidateQueries({ queryKey: ['msg-templates'] }); setDelTpl(null) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
        <Bell size={16} className="text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-800 dark:text-blue-300">
          Catálogo de notificações do Teams: cadastre os <strong>canais</strong> (webhooks) e os{' '}
          <strong>modelos de card</strong> que o nó de notificação dispara. O webhook fica oculto após salvo.
        </p>
      </div>

      {/* Seção 1 — Canais (grupos) */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <MessageSquare size={16} className="text-[#1A5FA8] dark:text-blue-400" />
            <h2 className="text-sm font-bold text-ink">Canais (webhooks do Teams)</h2>
          </div>
          <Button size="sm" onClick={() => setGrupoForm({ open: true, grupo: null })}><Plus size={13} /> Novo canal</Button>
        </div>

        {gruposQ.isLoading ? <PageSpinner /> : (
          <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                  <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Webhook</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                  <th className="px-4 py-2.5 w-20"></th>
                </tr>
              </thead>
              <tbody>
                {grupos.map(g => (
                  <tr key={g.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2.5 font-medium text-xs text-ink">{g.nome}</td>
                    <td className="px-4 py-2.5 text-xs text-dim">{g.descricao || '—'}</td>
                    <td className="px-4 py-2.5">
                      {g.has_webhook
                        ? <Badge value="success">configurado</Badge>
                        : <Badge value="warning">sem webhook</Badge>}
                    </td>
                    <td className="px-4 py-2.5"><Badge value={g.ativo ? 'ativo' : 'inativo'} /></td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => setGrupoForm({ open: true, grupo: g })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                        <button onClick={() => setDelGrupo(g)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {grupos.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-xs text-dim">Nenhum canal cadastrado. Crie um para começar a enviar cards no Teams.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Seção 2 — Modelos de card */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Bell size={16} className="text-[#1A5FA8] dark:text-blue-400" />
            <h2 className="text-sm font-bold text-ink">Modelos de card</h2>
          </div>
          <Button size="sm" onClick={() => setTplForm({ open: true, template: null })}><Plus size={13} /> Novo modelo</Button>
        </div>

        {templatesQ.isLoading ? <PageSpinner /> : (
          <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                  <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Canal sugerido</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Fatos</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                  <th className="px-4 py-2.5 w-20"></th>
                </tr>
              </thead>
              <tbody>
                {templates.map(t => (
                  <tr key={t.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                    <td className="px-4 py-2.5 text-xs text-ink">
                      <div className="font-medium">{t.nome}</div>
                      {t.titulo && <div className="text-[11px] text-dim truncate max-w-[260px]">{t.titulo}</div>}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-dim">{grupoNome(t.grupo_id)}</td>
                    <td className="px-4 py-2.5 text-xs text-dim">{t.facts?.length ? `${t.facts.length} fato(s)` : '—'}</td>
                    <td className="px-4 py-2.5"><Badge value={t.ativo ? 'ativo' : 'inativo'} /></td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => setTplForm({ open: true, template: t })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                        <button onClick={() => setDelTpl(t)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {templates.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-xs text-dim">Nenhum modelo de card cadastrado.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {grupoForm.open && <GrupoFormModal grupo={grupoForm.grupo} onClose={() => setGrupoForm({ open: false, grupo: null })} />}
      {tplForm.open && <TemplateFormModal template={tplForm.template} grupos={grupos} onClose={() => setTplForm({ open: false, template: null })} />}

      <ConfirmModal
        open={!!delGrupo}
        title="Excluir canal"
        message={`Excluir o canal "${delGrupo?.nome}"? Modelos que o sugerem ficarão sem canal sugerido.`}
        danger confirmLabel="Excluir"
        onConfirm={() => delGrupo && delGrupoMut.mutate(delGrupo.id)}
        onCancel={() => setDelGrupo(null)}
      />
      <ConfirmModal
        open={!!delTpl}
        title="Excluir modelo"
        message={`Excluir o modelo "${delTpl?.nome}"? Esta ação não pode ser desfeita.`}
        danger confirmLabel="Excluir"
        onConfirm={() => delTpl && delTplMut.mutate(delTpl.id)}
        onCancel={() => setDelTpl(null)}
      />
    </div>
  )
}
