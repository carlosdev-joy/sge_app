import { useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { Modal } from '../../ui/Modal'
import { toast } from '../../ui/Toast'
import { adminPost } from '../comum'
import { Trash2, AlertTriangle, CheckCircle2 } from 'lucide-react'

// ── Excluir Pipeline ────────────────────────────────────────────
interface PipelineRow { pipeline_name: string; project_name?: string; dag_criada?: boolean | number; active?: boolean | number }
export function DeletePipelineTab() {
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
