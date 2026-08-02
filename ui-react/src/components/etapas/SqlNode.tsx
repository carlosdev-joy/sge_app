// Nó SQL do React Flow. Mesmo visual do EtapaNode/NotificacaoNode (tile de ícone
// + nome embaixo), com identidade própria (acento violet + ícone de tabela —
// Table2, não Database: Database já serve o DataStage e desambiguar os "bancos"
// pelo glifo poupa o operador de depender só da cor). Roda
// uma query que retorna 1 valor; tipicamente liga numa Decisão a jusante, que lê
// esse valor (condição `valor_sql`). Um target handle (entrada, à esquerda) e um
// source handle (saída, à direita) — na altura do tile do ícone.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Table2 } from 'lucide-react'

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
// 14px de alvo (padrão de precisão que a Decisão já adota).
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile do ícone tem ~32px de altura no topo; handles no seu centro vertical.
const HANDLE_Y = 16

function SqlNodeImpl({ data, selected }: NodeProps & { data: SqlNodeData }) {
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

      {/* Tile do ícone (violet) — ícone de tabela branco; anel de seleção no tile. */}
      <div
        className={[
          'relative flex h-8 w-8 items-center justify-center rounded-xl bg-violet-500 text-white shadow-sm transition-shadow',
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
        <Table2 size={16} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar.
          w-[128px] > invólucro (w-12): transborda centrado (flex items-center). */}
      <p
        className="mt-1.5 w-[128px] line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: resumo curto da consulta/banco (label). */}
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

export const SqlNode = memo(SqlNodeImpl)
