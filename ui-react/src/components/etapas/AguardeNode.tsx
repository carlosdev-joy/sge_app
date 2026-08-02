// Nó Aguarde do React Flow — o ponto de encontro entre pernas paralelas.
//
// Diferente dos demais nós (tile de ícone quadrado), este é desenhado como uma
// BARRA VERTICAL: numa esteira que corre da esquerda para a direita, a barra de
// sincronização é perpendicular ao fluxo — é assim que BPMN/UML desenham uma
// junção, e é o que faz o operador ler "aqui as pernas se encontram" sem
// precisar abrir o painel.
//
// Um target handle (entrada, à esquerda) e um source handle (saída, à direita),
// na altura do meio da barra. Várias arestas podem chegar no mesmo target — é
// justamente o ponto do nó.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'

// Config do nó (round-trip com /fluxo no campo `aguarde`).
export interface AguardeNodeData {
  name: string
  aguarde: {
    politica: 'todas_sucesso' | 'todas_terminarem'
  }
  label: string
  isNew?: boolean
  [k: string]: unknown
}

// Bolinha discreta dos handles — mesma do EtapaNode, neutra nos dois temas.
const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// A barra tem 40px de altura; handles no seu centro vertical.
const BAR_H = 40
const HANDLE_Y = BAR_H / 2

function AguardeNodeImpl({ data, selected }: NodeProps & { data: AguardeNodeData }) {
  const esperaTudo = data.aguarde?.politica === 'todas_terminarem'
  return (
    <div className="group flex w-[128px] flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Barra de sincronização (âmbar) — perpendicular ao fluxo. */}
      <div className="flex items-center justify-center" style={{ height: BAR_H }}>
        <div
          className={[
            'h-full w-2.5 rounded-full bg-amber-500 shadow-sm transition-shadow',
            'group-hover:shadow-md',
            selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : '',
          ].join(' ')}
        />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar. */}
      <p
        className="mt-1.5 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Política — muda o comportamento em caso de falha, então fica VISÍVEL
          no card em vez de escondida no painel. */}
      <p
        className={[
          'mt-0.5 line-clamp-1 text-center text-[9px] leading-tight',
          esperaTudo ? 'font-semibold text-amber-600 dark:text-amber-400' : 'text-dim',
        ].join(' ')}
        title={esperaTudo
          ? 'Libera quando todas terminarem, mesmo com falha'
          : 'Só libera se todas as etapas derem certo'}
      >
        {esperaTudo ? 'mesmo com falha' : 'todas com sucesso'}
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

export const AguardeNode = memo(AguardeNodeImpl)
