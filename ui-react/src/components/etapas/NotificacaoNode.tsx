// Nó de notificação (Teams) do React Flow. Mesmo visual do EtapaNode (tile de
// ícone + nome embaixo), com identidade própria (acento teal + ícone de sino).
// Um target handle (entrada, à esquerda) e um source handle (saída, à direita)
// — pode ser ligado por dependência NORMAL ou virar ramo de uma decisão.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { BellRing } from 'lucide-react'

// Config do nó (round-trip com /fluxo no campo `notify`). Guardamos o objeto
// inteiro no `data` para ecoar no save; `label` é um resumo curto p/ o card.
export interface NotificacaoNodeData {
  name: string
  notify: { grupo_id: number | null; template_id: number | null; mensagem: string }
  label: string
  isNew?: boolean
  [k: string]: unknown
}

// Bolinha discreta dos handles — mesma do EtapaNode, neutra nos dois temas.
// 14px de alvo (padrão de precisão que a Decisão já adota).
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile do ícone tem 32px de altura no topo; handles no seu centro vertical (top: 16).
const HANDLE_Y = 16

function NotificacaoNodeImpl({ data, selected }: NodeProps & { data: NotificacaoNodeData }) {
  const pendente = !!(data as { pendente?: boolean }).pendente
  // Largura do invólucro = visual (tile de 32px) + 8px de folga por lado, só o
  // bastante para o handle encostar no desenho; o RÓTULO transborda de
  // propósito (w-[128px] nos <p>). Feedback de produção: com o invólucro na
  // largura do rótulo, os handles ancoravam a ~48px do tile e a aresta
  // "morria no nada" — lia como espaço desperdiçado.
  return (
    <div className="group flex w-12 flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone (teal-600: o glifo branco precisa de 3:1 sobre o chip —
          WCAG 1.4.11) — ícone de sino branco; anel de seleção no tile. */}
      <div
        className={[
          'relative flex h-8 w-8 items-center justify-center rounded-xl bg-teal-600 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          // Anel sutil no hover do tema escuro — sombra não lê sobre canvas
          // escuro; condicionado p/ não competir com os anéis de seleção/pendência.
          !selected && !pendente ? 'dark:group-hover:ring-1 dark:group-hover:ring-slate-500/60' : '',
          // Tracejado = nó recém-arrastado, ainda não salvo (sem sinal, não dava
          // pra distinguir o que já existe do que ainda é rascunho).
          data.isNew && !selected ? 'outline-dashed outline-1 outline-offset-2 outline-blue-400/70' : '',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
            : pendente ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
      >
        {pendente && (
          <span
            className="absolute -right-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Campos pendentes — selecione o nó para ver"
          />
        )}
        <BellRing size={16} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar.
          w-[128px] > invólucro (w-12): transborda centrado (flex items-center). */}
      <p
        className="mt-1.5 w-[128px] line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: resumo curto do destino/modelo (label). */}
      <p className="mt-0.5 w-[128px] line-clamp-1 text-center text-[9px] leading-tight text-dim" title={data.label}>
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

export const NotificacaoNode = memo(NotificacaoNodeImpl)
