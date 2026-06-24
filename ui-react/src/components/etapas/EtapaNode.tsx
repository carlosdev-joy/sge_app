// Node card custom do React Flow para uma etapa do pipeline (mockup).
// Visual estilo designer de workflow: chip de ícone colorido por tipo, nome em
// destaque, subtítulo mono com o comando/path e rodapé com badge do tipo + ordem.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { TYPE_META, type EtapaType } from './types'
import type { JobParam } from './JobTypeFields'

export interface EtapaNodeData {
  name: string
  type: EtapaType
  // Comando CRU (nullable) ecoado para o save. Na exibição usamos `command || '—'`.
  command: string | null
  order: number
  // Campos por tipo (round-trip com /fluxo) — lidos do GET e reenviados no save.
  // Editados ao vivo pelo painel lateral via JobTypeFields.
  ssh_conn_id?: string | null
  verbose_log?: boolean
  mssql_conn_id?: string | null
  mssql_database?: string | null
  params?: JobParam[]
  // Marca nós criados localmente (ainda não salvos) — nome/comando editáveis.
  isNew?: boolean
  [key: string]: unknown
}

// Bolinha discreta dos handles — neutra e coerente nos dois temas.
const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

function EtapaNodeImpl({ data, selected }: NodeProps & { data: EtapaNodeData }) {
  const meta = TYPE_META[data.type]
  const Icon = meta.icon

  return (
    <div
      className={[
        'group w-[148px] rounded-lg border bg-panel shadow-sm transition-shadow',
        'hover:shadow-md',
        selected
          ? 'border-blue-500 ring-2 ring-blue-500'
          : 'border-edge',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Left} className={HANDLE_CLS} />

      {/* Cabeçalho: chip de ícone + nome */}
      <div className="flex items-center gap-1.5 px-2 pt-1.5">
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded ${meta.chip}`}
        >
          <Icon size={12} strokeWidth={2.2} />
        </span>
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink">
          {data.name}
        </span>
      </div>

      {/* Subtítulo: comando / path em mono (fallback só na exibição) */}
      <div className="px-2 pb-1.5 pt-0.5">
        <p className="truncate font-mono text-[10px] text-dim" title={data.command || '—'}>
          {data.command || '—'}
        </p>
      </div>

      {/* Rodapé: badge do tipo + ordem */}
      <div className="flex items-center justify-between border-t border-edge px-2 py-1">
        <span
          className={`rounded px-1 py-0.5 text-[9px] font-semibold ${meta.badge}`}
        >
          {meta.label}
        </span>
        <span className="font-mono text-[9px] text-dim">#{data.order}</span>
      </div>

      <Handle type="source" position={Position.Right} className={HANDLE_CLS} />
    </div>
  )
}

export const EtapaNode = memo(EtapaNodeImpl)
