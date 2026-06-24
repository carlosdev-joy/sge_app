// Nó de decisão (roteador) em formato de losango. O quadro gira 45° e o conteúdo
// é contra-rotacionado para ficar legível. Dois source handles rotulados:
// direita = "sim", baixo = "não". Cor índigo/slate p/ destacar dos cards de etapa.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { GitBranch } from 'lucide-react'

export interface DecisaoNodeData {
  name: string
  condition: string
  [key: string]: unknown
}

const SIZE = 132 // lado do quadrado base (o losango é a diagonal)

const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-indigo-500'

function DecisaoNodeImpl({ data, selected }: NodeProps & { data: DecisaoNodeData }) {
  return (
    <div
      className="relative"
      style={{ width: SIZE, height: SIZE }}
    >
      {/* Losango: quadrado rotacionado 45° */}
      <div
        className={[
          'absolute inset-0 rotate-45 rounded-xl border shadow-sm transition-shadow',
          'bg-indigo-50 border-indigo-300',
          'dark:bg-indigo-900/30 dark:border-indigo-700',
          selected ? 'ring-2 ring-blue-500' : '',
          'hover:shadow-md',
        ].join(' ')}
      />

      {/* Conteúdo contra-rotacionado, centralizado */}
      <div className="absolute inset-0 flex flex-col items-center justify-center px-5 text-center">
        <GitBranch
          size={15}
          strokeWidth={2.2}
          className="mb-1 text-indigo-600 dark:text-indigo-300"
        />
        <span className="text-[11px] font-semibold leading-tight text-indigo-800 dark:text-indigo-200">
          {data.name}
        </span>
        <span className="mt-0.5 text-[10px] leading-tight text-indigo-600/90 dark:text-indigo-300/90">
          {data.condition}
        </span>
      </div>

      {/* Entrada (esquerda) */}
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ left: -5, top: '50%' }}
      />

      {/* Saída "sim" (direita) */}
      <Handle
        id="sim"
        type="source"
        position={Position.Right}
        className={HANDLE_CLS}
        style={{ right: -5, top: '50%' }}
      />
      <span className="pointer-events-none absolute right-[-30px] top-1/2 -translate-y-1/2 rounded bg-green-50 px-1 py-0.5 text-[9px] font-bold text-green-700 dark:bg-green-900/40 dark:text-green-300">
        sim
      </span>

      {/* Saída "não" (baixo) */}
      <Handle
        id="nao"
        type="source"
        position={Position.Bottom}
        className={HANDLE_CLS}
        style={{ bottom: -5, left: '50%' }}
      />
      <span className="pointer-events-none absolute bottom-[-22px] left-1/2 -translate-x-1/2 rounded bg-slate-100 px-1 py-0.5 text-[9px] font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300">
        não
      </span>
    </div>
  )
}

export const DecisaoNode = memo(DecisaoNodeImpl)
