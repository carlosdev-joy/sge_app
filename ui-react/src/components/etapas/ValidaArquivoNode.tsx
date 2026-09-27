import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { FileCheck2 } from 'lucide-react'
import type { ValidaConfig } from '../../lib/validaArquivo'

// Tile de tipo: superfície fixa cyan-700 com ícone branco nos dois temas (ui-temas-cores §4).
function ValidaArquivoNodeImpl({ data, selected }: NodeProps) {
  const cfg = data.valida_arquivo as ValidaConfig
  return <div className="flex w-12 flex-col items-center">
    <Handle type="target" position={Position.Left} style={{ top: 16 }} />
    <div className={`flex h-8 w-8 items-center justify-center rounded-md bg-cyan-700 text-white ${selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : ''}`}>
      <FileCheck2 size={20} />
    </div>
    <p className="mt-1.5 w-32 break-words text-center text-xs font-semibold text-ink">{String(data.name)}</p>
    <p className="w-32 text-center text-xs text-dim">Valida Arquivo · {cfg?.entradas.length ?? 0}</p>
    <Handle type="source" position={Position.Right} style={{ top: 16 }} />
  </div>
}
export const ValidaArquivoNode = memo(ValidaArquivoNodeImpl)
