// Node custom do React Flow para um PIPELINE membro da malha (F8, spec §4b).
// Card compacto na linguagem da tela Malha: dot ativo/inativo + nome + CritBadge
// + agendamento ('on_demand' já chega traduzido como 'sob demanda' pelo editor).
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { CritBadge } from './CritBadge'

export interface MalhaPipelineNodeData {
  name: string
  active: boolean
  criticidade: string | null
  // Texto de agendamento pronto para exibição (schedule_type traduzido).
  schedule: string | null
  [key: string]: unknown
}

// Mesma bolinha de handle do EtapaNode — neutra e coerente nos dois temas.
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

function MalhaPipelineNodeImpl({ data, selected }: NodeProps & { data: MalhaPipelineNodeData }) {
  // Largura do invólucro = a do PRÓPRIO card (lição da PR #238): os handles
  // ancoram encostados no visual — nada de invólucro maior com aresta "morrendo
  // no nada". O nome pode quebrar em até 2 linhas DENTRO do card (title mostra
  // o nome completo).
  return (
    <div
      className={[
        'w-48 rounded-lg border bg-panel px-3 py-2 shadow-sm transition-shadow',
        selected
          ? 'border-edge ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
          : 'border-edge hover:shadow-md hover:border-[#1A5FA8]/40',
        data.active ? '' : 'opacity-60',
      ].join(' ')}
      title={data.name}
    >
      <Handle type="target" position={Position.Left} className={HANDLE_CLS} />
      <div className="flex items-start gap-1.5">
        <span
          className={`mt-1 h-2 w-2 shrink-0 rounded-full ${data.active ? 'bg-green-400' : 'bg-slate-400'}`}
          title={data.active ? 'Ativo' : 'Inativo'}
        />
        <span className="min-w-0 flex-1 break-words font-mono text-[11px] font-semibold leading-tight text-ink line-clamp-2">
          {data.name}
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {data.criticidade && <CritBadge crit={data.criticidade} />}
        {data.schedule && <span className="text-[10px] text-dim">📅 {data.schedule}</span>}
        {!data.active && <span className="text-[10px] text-dim">○ inativo</span>}
      </div>
      <Handle type="source" position={Position.Right} className={HANDLE_CLS} />
    </div>
  )
}

export const MalhaPipelineNode = memo(MalhaPipelineNodeImpl)
