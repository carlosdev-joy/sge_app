// Node custom do React Flow para uma etapa do pipeline.
// Visual estilo IBM Cloud Pak / DataStage Designer: tile de ícone colorido por
// tipo + nome embaixo (até 2 linhas, sem truncar) + tipo/ordem em linha discreta.
// Os handles ficam na altura do tile do ícone (topo), não no meio do label.
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

// Tile do ícone tem ~44px de altura no topo; os handles ficam no seu centro
// vertical (top: 22) para as arestas conectarem no ícone, não no label.
const HANDLE_Y = 22

function EtapaNodeImpl({ data, selected }: NodeProps & { data: EtapaNodeData }) {
  const meta = TYPE_META[data.type]
  const Icon = meta.icon

  return (
    <div className="group flex w-[128px] flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone — quadrado colorido por tipo, ícone branco centralizado.
          Anel de seleção aqui (não no container todo). */}
      <div
        className={[
          'flex h-11 w-11 items-center justify-center rounded-xl shadow-sm transition-shadow',
          meta.chip,
          'group-hover:shadow-md',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
      >
        <Icon size={22} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar em 1; quebra palavras longas. */}
      <p
        className="mt-1.5 line-clamp-2 break-words text-center text-xs font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: tipo do componente + ordem (discreto). */}
      <p className="mt-0.5 text-center text-[10px] leading-tight text-dim">
        {meta.label} <span className="font-mono">#{data.order}</span>
      </p>

      <Handle
        type="source"
        position={Position.Right}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />
    </div>
  )
}

export const EtapaNode = memo(EtapaNodeImpl)
