import { useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Select } from '../../ui/Input'
import { toast } from '../../ui/Toast'
import { PROJETOS, adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

// ── Regenerar DAGs ──────────────────────────────────────────────
export function RegenDagsTab() {
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
      addLog('✓ ' + (f.mensagem ?? 'Publicação disparada.') + ` (${f.detalhes?.dag_run_id ?? ''})`)
      addLog('O Airflow detectará as mudanças no próximo scan.')
      toast.success('DAGs publicadas com sucesso')
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
          <Button variant="danger" onClick={() => setConfirm(true)} loading={loading}>⟳ Publicar DAGs</Button>
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
        title="Publicar DAGs"
        message={`Publicar nova versão de todos os pipelines${projeto ? ` do projeto ${projeto}` : ''}? Isso reseta os DAGs e dispara a publicação no Airflow.`}
        confirmLabel="Publicar"
        onConfirm={regen}
        onCancel={() => setConfirm(false)}
      />
    </div>
  )
}
