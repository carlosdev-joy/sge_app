// Nó SQL do React Flow. Mesmo visual do EtapaNode/NotificacaoNode (tile de ícone
// + nome embaixo), com identidade própria (acento violet + ícone de banco). Roda
// uma query que retorna 1 valor; tipicamente liga numa Decisão a jusante, que lê
// esse valor (condição `valor_sql`). Um target handle (entrada, à esquerda) e um
// source handle (saída, à direita) — na altura do tile do ícone.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Database } from 'lucide-react'

// Config do nó (round-trip com /fluxo no campo `sql`). Guardamos o objeto inteiro
// no `data` para ecoar no save; `label` é um resumo curto p/ o card.
// on_error: 'falhar' (task falha alto — default dos saves novos) | 'nulo'
// (publica None em silêncio, comportamento legado).
export interface SqlNodeData {
  name: string
  sql: {
    sql: string
    mssql_conn_id: string | null
    database: string | null
    on_error: 'falhar' | 'nulo'
    // Derivado (não persiste): JSON salvo sem on_error — ver FluxoEditor.
    on_error_legado?: boolean
  }
  label: string
  isNew?: boolean
  [k: string]: unknown
}

// Bolinha discreta dos handles — mesma do EtapaNode, neutra nos dois temas.
const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile do ícone tem ~32px de altura no topo; handles no seu centro vertical.
const HANDLE_Y = 16

function SqlNodeImpl({ data, selected }: NodeProps & { data: SqlNodeData }) {
  return (
    <div className="group flex w-[128px] flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone (violet) — ícone de banco branco; anel de seleção no tile. */}
      <div
        className={[
          'relative flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
            : (data as { pendente?: boolean }).pendente ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
      >
        {!!(data as { pendente?: boolean }).pendente && (
          <span
            className="absolute -right-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Campos pendentes — selecione o nó para ver"
          />
        )}
        <Database size={16} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar. */}
      <p
        className="mt-1.5 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: resumo curto da consulta/banco (label). */}
      <p className="mt-0.5 line-clamp-1 text-center text-[9px] leading-tight text-dim" title={data.label}>
        {data.label}
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

export const SqlNode = memo(SqlNodeImpl)
