// Nó de decisão (roteador). Mesmo visual dos demais nós (tile de ícone + nome
// embaixo), com acento índigo e ícone de bifurcação. Três handles: entrada à
// esquerda (target) e duas saídas rotuladas — direita = "sim", baixo = "não".
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { GitBranch } from 'lucide-react'

// Condição de decisão (espelha o ConditionEntry do PipelineFormModal). Guardamos
// o objeto inteiro no `data` para ecoar no save; `label` é um resumo curto p/ o nó.
export interface NodeCondition {
  tipo: 'contagem' | 'query' | 'linhas_job'
  operador: string
  valor: string
  tabela?: string
  database?: string
  sql?: string
  mssql_conn_id?: string
  // Específicos do tipo 'linhas_job' (decisão por linhas processadas).
  job_name?: string
  child_job?: string
  ramo_verdadeiro: string[]
  ramo_falso: string[]
}

export interface DecisaoNodeData {
  name: string
  condition: NodeCondition
  label: string
  isNew?: boolean
  [key: string]: unknown
}

const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-indigo-500'

// Tile do ícone tem 44px de altura no topo: o "sim" (direita) fica no centro
// vertical do tile; o "nao" sai pela base do tile (logo abaixo dos 44px).
const HANDLE_Y = 16
const TILE_H = 32

function DecisaoNodeImpl({ data, selected }: NodeProps & { data: DecisaoNodeData }) {
  return (
    <div className="group relative flex w-[128px] flex-col items-center">
      {/* Entrada (esquerda) — na altura do tile do ícone */}
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone (índigo) — ícone de bifurcação branco; anel no tile. */}
      <div
        className={[
          'relative flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
      >
        <GitBranch size={16} strokeWidth={2} />

        {/* Saída "sim" (direita) — centro vertical do tile */}
        <Handle
          id="sim"
          type="source"
          position={Position.Right}
          className={HANDLE_CLS}
          style={{ right: -5, top: '50%' }}
        />
        {/* Saída "não" (baixo) — base do tile */}
        <Handle
          id="nao"
          type="source"
          position={Position.Bottom}
          className={HANDLE_CLS}
          style={{ bottom: -5, left: '50%' }}
        />
      </div>

      {/* Rótulos dos ramos junto ao tile (sim à direita, não embaixo). */}
      <span
        className="pointer-events-none absolute right-[-26px] rounded bg-green-50 px-1 py-0.5 text-[9px] font-bold text-green-700 dark:bg-green-900/40 dark:text-green-300"
        style={{ top: HANDLE_Y - 8 }}
      >
        sim
      </span>
      <span
        className="pointer-events-none absolute left-1/2 -translate-x-1/2 rounded bg-slate-100 px-1 py-0.5 text-[9px] font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300"
        style={{ top: TILE_H + 4 }}
      >
        não
      </span>

      {/* Nome embaixo — até 2 linhas, sem truncar (deslocado p/ não colidir
          com o rótulo "não", que sai da base do tile). */}
      <p
        className="mt-4 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: tipo + resumo da condição (label). */}
      <p className="mt-0.5 line-clamp-1 text-center text-[9px] leading-tight text-dim" title={data.label}>
        Decisão · {data.label}
      </p>
    </div>
  )
}

export const DecisaoNode = memo(DecisaoNodeImpl)
