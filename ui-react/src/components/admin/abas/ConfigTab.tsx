import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Trash2, Plus, Save, X, Workflow } from 'lucide-react'

// ── Configurações ───────────────────────────────────────────────
export function ConfigTab() {
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [delKey, setDelKey] = useState<string | null>(null)

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

  const entries = Object.entries(data?.config ?? {})

  const handleInlineSave = (key: string) => {
    const val = editValues[key]
    if (val === undefined) return
    setSavingKey(key)
    upsertMut.mutate({ config_key: key, config_value: val })
  }

  return (
    <div className="flex flex-col gap-5">
      {/* O botão "Testar Webhook" (e o quadro de diagnóstico dele) ficava à
          direita desta frase. Decisão explícita da spec
          (docs/spec-admin-reestruturacao.md, F3): foi para o card "Webhook
          padrão" no fim de Comunicação › Teams (abas/NotificacoesTab.tsx). */}
      <p className="text-sm text-dim">Parâmetros do sistema. Edite o valor na célula e clique em Salvar.</p>

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

      {/* Configurações de fluxo — vieram da aba NOTIFICAÇÕES, onde estavam
          renderizadas no rodapé dos canais do Teams. Ninguém procura o timeout
          da prévia de SQL ali, e quem precisava dele não o encontrava. Entram
          no FIM desta aba, para não reordenar o que já existe aqui. */}
      <FlowConfigSection />

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

// ── Configurações de fluxo ──────────────────────────────────────
// Parâmetros do motor de fluxo (decisões/SQL). Hoje só o timeout de
// preview/simulação de SQL — GET/PUT /jobs/flow-config (degrada se a
// tabela/endpoint não existir: backend devolve o default).
//
// Renderizada na aba SISTEMA › CONFIGURAÇÕES (F2 da spec de tabela do SQL).
// Antes morava no rodapé da aba de Notificações, entre os canais do Teams:
// quem precisava aumentar o tempo da prévia de SQL não achava o campo, e a
// prévia seguia sendo cancelada no valor de fábrica.
function FlowConfigSection() {
  const [timeout, setTimeoutVal] = useState('')

  const { data, isLoading } = useQuery<{ sql_preview_timeout_s: number }>({
    queryKey: ['flow-config'],
    queryFn: () => apiFetch('/jobs/flow-config'),
  })

  // Sincroniza o input com o valor carregado (sem sobrescrever edição em curso
  // após salvar: ao trocar `data` o input reflete o servidor).
  const carregado = data?.sql_preview_timeout_s
  const valorInput = timeout !== '' ? timeout : (carregado != null ? String(carregado) : '')

  const saveMut = useMutation({
    mutationFn: (sql_preview_timeout_s: number) =>
      apiFetch('/jobs/flow-config', { method: 'PUT', body: JSON.stringify({ sql_preview_timeout_s }) }),
    onSuccess: () => {
      toast.success('Configurações de fluxo salvas')
      queryClient.invalidateQueries({ queryKey: ['flow-config'] })
      // A MESMA chave aparece crua na tabela de parâmetros no topo desta aba
      // (`config_list` devolve tudo de etl_app_config). Sem invalidar as duas,
      // a tabela acima continuaria mostrando o valor velho por até 30s — dois
      // números diferentes para a mesma configuração, na mesma tela.
      queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      setTimeoutVal('')
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao salvar configurações de fluxo'),
  })

  const n = parseInt(valorInput, 10)
  // Teto 280s, o mesmo do backend: o nginx corta a resposta em 300s, e sem a
  // folga o erro viria do proxy, sem explicação.
  const valido = Number.isFinite(n) && n >= 1 && n <= 280

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Workflow size={16} className="text-[#1A5FA8] dark:text-blue-400" />
        <h2 className="text-sm font-bold text-ink">Configurações de fluxo</h2>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        {isLoading ? <PageSpinner /> : (
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1">
              <Input
                label="Timeout de preview/simulação (s)"
                type="number"
                min={1}
                max={280}
                value={valorInput}
                onChange={e => setTimeoutVal(e.target.value)}
                className="w-56"
                error={valorInput !== '' && !valido ? 'Use um valor entre 1 e 280' : undefined}
              />
              <p className="text-[11px] text-dim">
                Tempo máximo que um preview/simulação de SQL roda antes de ser cancelado no
                servidor. Padrão 60s, teto 280s. Cada prévia em andamento ocupa um processo
                da API — valores altos com muita gente prevendo ao mesmo tempo deixam o
                sistema lento para todos.
              </p>
            </div>
            <Button
              onClick={() => saveMut.mutate(n)}
              loading={saveMut.isPending}
              disabled={!valido}
            >
              <Save size={13} /> Salvar
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
