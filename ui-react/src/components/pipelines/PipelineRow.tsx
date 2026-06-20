import { Button } from '../ui/Button'
import { Eye, Edit, GitBranch, History, Play, PowerOff, Settings, Boxes } from 'lucide-react'
import type { Pipeline } from '../../types/pipeline'
import { critColor } from './pipelineUtils'

export function PipelineRow({ pipeline: p, isViewer, onView, onEdit, onLineage, onAudit, onInactivate, onGenDag, onExec }: {
  pipeline: Pipeline; isViewer: boolean
  onView: () => void; onEdit: () => void; onLineage: () => void
  onAudit: () => void; onInactivate: () => void; onGenDag: () => void; onExec: () => void
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-edge/30 hover:bg-edge/10 transition-colors group">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${p.active ? 'bg-green-500' : 'bg-slate-600'}`}
        title={p.active ? 'Ativo' : (p.motivo_inativacao ? `Inativo — ${p.motivo_inativacao}` : 'Inativo')} />
      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 w-[46px] text-center ${p.dag_criada ? 'text-green-400 border-green-800/40 bg-green-900/10' : 'text-dim border-edge bg-canvas'}`}>
        {p.dag_criada ? 'DAG ✓' : 'DAG —'}
      </span>
      <span className="text-[10px] text-dim flex-shrink-0 tabular-nums w-[42px]">
        {p.scheduled_time ? p.scheduled_time.substring(0, 5) : '—:——'}
      </span>
      <span className="text-[10px] flex-shrink-0 w-4 text-center"
        title={p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro
          ? ['Início','Conclusão','Erro'].filter((_,i) => [p.envia_msg_inicio,p.envia_msg_fim,p.envia_msg_erro][i]).join(', ')
          : 'Sem notificações'}>
        {(p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro) ? '✉' : ''}
      </span>

      <span className={`text-[9px] font-bold flex-shrink-0 w-10 ${critColor(p.criticidade)}`}
        title={`Criticidade: ${p.criticidade}`}>
        {p.criticidade}
      </span>

      <span className="font-mono text-xs text-ink font-medium flex-1 truncate min-w-0" title={p.pipeline_name}>
        {p.pipeline_name}
      </span>

      {/* Inativo: mostra o motivo inline (truncado), para a equipe saber por que o
          fluxo está indisponível sem precisar abrir os detalhes. */}
      {!p.active && (
        <span
          className="flex items-center gap-1 text-[10px] text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded px-1.5 py-0.5 max-w-[240px] flex-shrink-0"
          title={p.motivo_inativacao
            ? `Inativo — ${p.motivo_inativacao}${p.inativado_por ? ` (por ${p.inativado_por})` : ''}${p.inativado_em ? ` em ${p.inativado_em}` : ''}`
            : 'Inativo (motivo não informado)'}>
          <PowerOff size={10} className="flex-shrink-0" />
          <span className="truncate">{p.motivo_inativacao || 'inativo'}</span>
        </span>
      )}

      {/* Sempre visível: abre os jobs deste pipeline em nova aba (preserva o filtro daqui) */}
      <Button variant="secondary" size="sm"
        title={`Ver jobs de ${p.pipeline_name} em nova aba`}
        aria-label={`Ver jobs de ${p.pipeline_name} em nova aba`}
        onClick={() => window.open(`/jobs?pipeline=${encodeURIComponent(p.pipeline_name)}`, '_blank', 'noopener,noreferrer')}
        className="flex-shrink-0 text-blue-400 hover:text-blue-300 border-blue-800/40">
        <Boxes size={12} /> Jobs
      </Button>

      <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity border-l border-edge/40 pl-2 ml-1">
        <Button variant="ghost" size="sm" title="Visualizar" aria-label={`Visualizar ${p.pipeline_name}`} onClick={onView}><Eye size={12} /></Button>
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Editar" aria-label={`Editar ${p.pipeline_name}`} onClick={onEdit}><Edit size={12} /></Button>
        </span>
        <Button variant="ghost" size="sm" title="Lineage" aria-label={`Ver lineage de ${p.pipeline_name}`} onClick={onLineage}><GitBranch size={12} /></Button>
        <Button variant="ghost" size="sm" title="Histórico" aria-label={`Ver histórico de ${p.pipeline_name}`} onClick={onAudit}><History size={12} /></Button>
        <span className={isViewer || !p.active ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Inativar" aria-label={`Inativar ${p.pipeline_name}`} onClick={onInactivate}
            className="text-amber-500/60 hover:text-amber-400"><PowerOff size={12} /></Button>
        </span>
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm"
            title={p.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'}
            aria-label={p.dag_criada ? `Regenerar DAG de ${p.pipeline_name}` : `Gerar DAG para ${p.pipeline_name}`}
            onClick={onGenDag}
            className={p.dag_criada ? 'text-blue-400/70 hover:text-blue-300' : 'text-dim hover:text-ink'}>
            <Settings size={12} />
          </Button>
        </span>
        <span className={isViewer || !p.dag_criada ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Executar agora" aria-label={`Executar ${p.pipeline_name} agora`} onClick={onExec}
            className="text-green-500/60 hover:text-green-400"><Play size={12} /></Button>
        </span>
      </div>
    </div>
  )
}
