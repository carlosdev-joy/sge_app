import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Textarea } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal } from '../ComumUI'
import { Trash2, Plus, Calendar } from 'lucide-react'

// ── Agendamento ─────────────────────────────────────────────────
interface CalendarioRow { calendario_nome: string; datas: number; proxima?: string | null }
interface BlackoutRow { id: number; inicio: string; fim?: string; escopo?: string | null; motivo?: string; ativo: number; vigente: number }
export function AgendamentoTab() {
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
