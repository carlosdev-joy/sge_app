// Nó de E-mail do React Flow (spec docs/spec-notificacao-email.md, F2). Mesmo
// desenho do nó de notificação Teams — é o mesmo papel, por outro canal — com
// identidade própria: ícone de envelope sobre o mesmo acento teal da família
// "avisar alguém". Um target handle (entrada) e um source handle (saída): pode
// ser ligado por dependência normal ou virar ramo de uma decisão.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Mail } from 'lucide-react'
import { LinhaExecucaoNo } from './LinhaExecucaoNo'
import type { ExecNoEtapa } from './execucaoEtapas'
import type { EmailNoConfig } from './fluxoTypes'

// Config do nó (round-trip com /fluxo no campo `email`). Guardamos o objeto
// inteiro no `data` para ecoar no save; `label` é um resumo curto p/ o card.
export interface EmailNodeData {
  name: string
  email: EmailNoConfig
  label: string
  // Modo Execução: camada de status/horários desta etapa na data exibida.
  exec?: ExecNoEtapa | null
  isNew?: boolean
  [k: string]: unknown
}

const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

const HANDLE_Y = 16

function EmailNodeImpl({ data, selected }: NodeProps & { data: EmailNodeData }) {
  const pendente = !!(data as { pendente?: boolean }).pendente
  const exec = data.exec ?? null
  return (
    <div className="group flex w-12 flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone (teal-600: o glifo branco precisa de 3:1 sobre o chip —
          WCAG 1.4.11); anel de seleção no tile. */}
      <div
        className={[
          'relative flex h-8 w-8 items-center justify-center rounded-xl bg-teal-600 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          !selected && !pendente ? 'dark:group-hover:ring-1 dark:group-hover:ring-slate-500/60' : '',
          data.isNew && !selected ? 'outline-dashed outline-1 outline-offset-2 outline-blue-400/70' : '',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
            : pendente ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-canvas' : '',
          exec?.anel ?? '',
        ].join(' ')}
      >
        {pendente && (
          <span
            className="absolute -right-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Campos pendentes — selecione o nó para ver"
          />
        )}
        <Mail size={16} strokeWidth={2} />
      </div>

      <p
        className="mt-1.5 w-[128px] line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {exec ? <LinhaExecucaoNo exec={exec} /> : (
        <p className="mt-0.5 w-[128px] line-clamp-1 text-center text-[9px] leading-tight text-dim" title={data.label}>
          {data.label}
        </p>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />
    </div>
  )
}

export const EmailNode = memo(EmailNodeImpl)
