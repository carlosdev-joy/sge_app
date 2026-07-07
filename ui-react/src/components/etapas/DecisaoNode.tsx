// Nó de decisão (roteador). Mesmo visual dos demais nós (tile de ícone + nome
// embaixo), com acento índigo e ícone de bifurcação. BINÁRIA: entrada à
// esquerda (target) e duas saídas rotuladas — direita = "sim", baixo = "não".
// SWITCH (N-way, condition.casos): uma saída à direita POR CASO (cor da paleta,
// tooltip = nome do caso) + saída "senão" na base.
import { memo, useEffect } from 'react'
import { Handle, Position, useUpdateNodeInternals, type NodeProps } from '@xyflow/react'
import { GitBranch } from 'lucide-react'

// Um caso do SWITCH: primeiro (na ordem da lista) cujo valor_obtido <operador>
// valor casar vence; `ramo` são os jobs de destino (derivado das arestas no save).
export interface CasoSwitch {
  nome: string
  operador: string
  valor: string
  ramo: string[]
}

// Condição de decisão (espelha o ConditionEntry do PipelineFormModal). Guardamos
// o objeto inteiro no `data` para ecoar no save; `label` é um resumo curto p/ o nó.
export interface NodeCondition {
  tipo: 'contagem' | 'query' | 'linhas_job' | 'valor_sql'
  operador: string
  valor: string
  tabela?: string
  database?: string
  sql?: string
  mssql_conn_id?: string
  // Específicos do tipo 'linhas_job' (decisão por linhas processadas).
  job_name?: string
  child_job?: string
  // Específicos do tipo 'valor_sql' (lê o valor de um nó SQL a montante).
  source_job?: string
  comparacao?: 'texto' | 'data' | 'numero'
  // O que fazer se a AVALIAÇÃO falhar: 'falhar' (task falha alto — default dos
  // saves novos) | 'ramo_falso' (degrada em silêncio, binária legada) |
  // 'senao' (switch: degrada para o ramo padrão).
  on_error?: 'falhar' | 'ramo_falso' | 'senao'
  // Derivado (NÃO persiste): true quando o JSON salvo não tem on_error — a DAG
  // publicada ainda degrada em silêncio; o 'falhar' exibido só vale após
  // salvar + republicar. Alimenta o aviso no painel.
  on_error_legado?: boolean
  ramo_verdadeiro: string[]
  ramo_falso: string[]
  // SWITCH (N-way): presença de `casos` muda o modo. operador/valor do topo
  // são ignorados (cada caso tem os seus); ramos binários ficam vazios.
  casos?: CasoSwitch[]
  ramo_senao?: string[]
}

// Paleta das saídas de caso (switch) — handle e aresta usam o mesmo índice.
// 10 cores = _COND_MAX_CASOS do backend.
export const CASO_CORES = [
  '#10b981', '#0ea5e9', '#f59e0b', '#d946ef', '#f43f5e',
  '#14b8a6', '#84cc16', '#06b6d4', '#8b5cf6', '#f97316',
] as const

export const casoCor = (idx: number) => CASO_CORES[idx % CASO_CORES.length]

export interface DecisaoNodeData {
  name: string
  condition: NodeCondition
  label: string
  isNew?: boolean
  [key: string]: unknown
}

// Bolinhas dos handles, coloridas por papel: entrada índigo, saída "sim" verde,
// "não" slate. A direção fica clara pela COR; com o nó SELECIONADO, cada saída
// ganha um rótulo flutuante (fase 5 — descoberta dos handles do switch).
// 14px de alvo (era 10px — pequeno demais para arrastar com precisão).
const HANDLE_BASE = '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel'
const HANDLE_IN = `${HANDLE_BASE} !bg-indigo-400`
const HANDLE_SIM = `${HANDLE_BASE} !bg-green-500`
const HANDLE_NAO = `${HANDLE_BASE} !bg-slate-400`

// Rótulo flutuante de uma saída (visível com o nó selecionado).
const SAIDA_LABEL =
  'pointer-events-none absolute z-10 whitespace-nowrap rounded border border-edge ' +
  'bg-panel px-1.5 py-0.5 text-[10px] font-semibold shadow-sm'

function DecisaoNodeImpl({ id, data, selected }: NodeProps & { data: DecisaoNodeData }) {
  const casos = data.condition?.casos
  const isSwitch = Array.isArray(casos)
  // Handles mudam com os casos (quantidade/nome) — o React Flow precisa
  // remedir o nó para reancorar as arestas.
  const updateNodeInternals = useUpdateNodeInternals()
  const handleKey = isSwitch ? casos.map((c) => c.nome).join('|') : 'bin'
  useEffect(() => {
    updateNodeInternals(id)
  }, [id, handleKey, updateNodeInternals])

  // Tile cresce com o nº de casos para os handles (14px) não se sobreporem.
  const tileH = isSwitch ? Math.max(32, casos.length * 20 + 8) : 32

  return (
    <div className="group relative flex w-[128px] flex-col items-center">
      {/* Entrada (esquerda) — centro vertical do tile (que cresce no switch) */}
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_IN}
        style={{ top: tileH / 2 }}
      />

      {/* Tile do ícone (índigo) — ícone de bifurcação branco; anel no tile. */}
      <div
        className={[
          'relative flex w-8 items-center justify-center rounded-xl bg-indigo-500 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
            : (data as { pendente?: boolean }).pendente ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
        style={{ height: tileH }}
      >
        {!!(data as { pendente?: boolean }).pendente && (
          <span
            className="absolute -left-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Campos pendentes — selecione o nó para ver"
          />
        )}
        <GitBranch size={16} strokeWidth={2} />

        {isSwitch ? (
          <>
            {/* SWITCH: uma saída à direita por caso, na ordem de avaliação. */}
            {casos.map((c, i) => (
              <Handle
                key={`caso:${c.nome}`}
                id={`caso:${c.nome}`}
                type="source"
                position={Position.Right}
                className={HANDLE_BASE}
                title={c.nome || `caso ${i + 1}`}
                style={{
                  right: -6,
                  top: `${((i + 1) * 100) / (casos.length + 1)}%`,
                  background: casoCor(i),
                }}
              />
            ))}
            {/* Rótulos das saídas — visíveis com o nó selecionado (descoberta:
                casar cor de handle com caso deixava daltônicos sem canal). */}
            {selected && casos.map((c, i) => (
              <span
                key={`lbl:${c.nome}`}
                className={SAIDA_LABEL}
                style={{
                  left: 'calc(100% + 10px)',
                  top: `${((i + 1) * 100) / (casos.length + 1)}%`,
                  transform: 'translateY(-50%)',
                  color: casoCor(i),
                }}
              >
                {c.nome || `caso ${i + 1}`}
              </span>
            ))}
            {/* Saída "senão" (baixo) — ramo padrão */}
            <Handle
              id="senao"
              type="source"
              position={Position.Bottom}
              className={HANDLE_NAO}
              title="senão (nenhum caso casou)"
              style={{ bottom: -6, left: '50%' }}
            />
            {selected && (
              /* na lateral, alinhado à borda de baixo — embaixo colidiria com o nome */
              <span
                className={`${SAIDA_LABEL} text-slate-500 dark:text-slate-300`}
                style={{ top: 'calc(100% + 8px)', left: 'calc(100% + 10px)', transform: 'translateY(-50%)' }}
              >
                ↓ senão
              </span>
            )}
          </>
        ) : (
          <>
            {/* Saída "sim" (direita) — centro vertical do tile */}
            <Handle
              id="sim"
              type="source"
              position={Position.Right}
              className={HANDLE_SIM}
              style={{ right: -6, top: '50%' }}
            />
            {/* Saída "não" (baixo) — base do tile */}
            <Handle
              id="nao"
              type="source"
              position={Position.Bottom}
              className={HANDLE_NAO}
              style={{ bottom: -6, left: '50%' }}
            />
            {selected && (
              <>
                <span
                  className={`${SAIDA_LABEL} text-green-600 dark:text-green-400`}
                  style={{ left: 'calc(100% + 10px)', top: '50%', transform: 'translateY(-50%)' }}
                >
                  sim
                </span>
                <span
                  className={`${SAIDA_LABEL} text-slate-500 dark:text-slate-300`}
                  style={{ top: 'calc(100% + 8px)', left: 'calc(100% + 10px)', transform: 'translateY(-50%)' }}
                >
                  ↓ não
                </span>
              </>
            )}
          </>
        )}
      </div>

      {/* Nome embaixo — sem rótulos sim/não sobre o nó (a aresta já mostra a
          pílula sim/não; os handles coloridos indicam a direção). */}
      <p
        className="mt-2 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
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
