// Node custom do React Flow para uma etapa do pipeline.
// Visual estilo IBM Cloud Pak / DataStage Designer: tile de ícone colorido por
// tipo + nome embaixo (até 2 linhas, sem truncar) + tipo/ordem em linha discreta.
// Os handles ficam na altura do tile do ícone (topo), não no meio do label.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Database } from 'lucide-react'
import { TYPE_META, type TypeMeta, type EtapaType } from './types'
import type { JobParam, PythonDraft } from './JobTypeFields'

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
  // Nó python v2 — draft local do modo de execução (todos os campos; o save
  // envia só o modo ativo). Ausente/modo 'modulo' = legado (python: null).
  python?: PythonDraft
  // Subtítulo derivado (calculado no FluxoEditor — etapaSublabel): para python
  // indica o modo ("script @ ssh" / "código @ ssh" / "módulo (worker)").
  sublabel?: string
  // Marca nós criados localmente (ainda não salvos) — nome/comando editáveis.
  isNew?: boolean
  [key: string]: unknown
}

// Bolinha discreta dos handles — neutra e coerente nos dois temas.
// 14px de alvo (padrão de precisão que a Decisão já adota).
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile do ícone tem 32px de altura no topo; os handles ficam no seu centro
// vertical (top: 16) para as arestas conectarem no ícone, não no label.
const HANDLE_Y = 16

// Fallback p/ tipo fora do TYPE_META (API nova/registro antigo): um tipo
// desconhecido não pode derrubar o canvas inteiro — degrada p/ chip slate
// neutro com o próprio nome do tipo como rótulo.
const META_FALLBACK: TypeMeta = {
  label: '',
  icon: Database,
  chip: 'bg-slate-500 text-white',
  badge: 'bg-slate-50 text-slate-700 border border-slate-200 dark:bg-slate-900/30 dark:text-slate-300 dark:border-slate-800',
  dot: 'bg-slate-500',
  hex: '#64748b',
}

function EtapaNodeImpl({ data, selected }: NodeProps & { data: EtapaNodeData }) {
  const meta = TYPE_META[data.type] ?? { ...META_FALLBACK, label: data.type }
  const Icon = meta.icon
  const pendente = !!(data as { pendente?: boolean }).pendente

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
          'relative flex h-8 w-8 items-center justify-center rounded-xl shadow-sm transition-shadow',
          meta.chip,
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
        {/* Ponto âmbar = validação com pendência (derivado no editor) */}
        {pendente && (
          <span
            className="absolute -right-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Campos pendentes — selecione o nó para ver"
          />
        )}
        <Icon size={16} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar em 1; quebra palavras longas. */}
      <p
        className="mt-1.5 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: subtítulo (quando derivado — ex.: modo do nó python)
          ou o label do tipo + ordem (discreto). */}
      <p className="mt-0.5 text-center text-[9px] leading-tight text-dim">
        {data.sublabel ?? meta.label} <span className="font-mono">#{data.order}</span>
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
