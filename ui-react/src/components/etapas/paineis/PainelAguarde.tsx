// ── Painel de um nó AGUARDE (ponto de encontro entre pernas paralelas) ───────
// O nó não tem configuração de execução: o que ele faz é inteiramente decidido
// pela POLÍTICA. Por isso o painel é essencialmente uma escolha entre duas
// opções, escritas em linguagem de operador e com a consequência explícita.
import type { Node } from '@xyflow/react'
import { GitMerge, Trash2, Link2 } from 'lucide-react'
import { Button } from '../../ui/Button'
import type { AguardeNodeData } from '../AguardeNode'
import { defaultAguarde, type AguardeConfig } from '../fluxoTypes'
import { NomeField } from './shared'

export interface PainelAguardeProps {
  node: Node
  // Quantas etapas estão ligadas na entrada do nó (arestas que chegam nele).
  entradas: number
  // Nomes das pontas soltas do fluxo (nós sem saída) que a ação "prender"
  // ligaria neste Aguarde. Vazio = não há nada solto para prender.
  pontasSoltas: string[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchAguarde: (nodeId: string, patch: Partial<AguardeConfig>) => void
  onPrenderPontasSoltas: (nodeId: string) => void
  onDelete: (id: string) => void
}

const OPCOES: { valor: AguardeConfig['politica']; titulo: string; ajuda: string }[] = [
  {
    valor: 'todas_sucesso',
    titulo: 'Só seguir se todas derem certo',
    ajuda: 'Se qualquer etapa ligada aqui falhar, o que vem depois não roda.',
  },
  {
    valor: 'todas_terminarem',
    titulo: 'Seguir assim que todas terminarem, mesmo com falha',
    ajuda: 'Use quando o passo seguinte é limpeza — apagar arquivos que as duas pernas usaram, por exemplo.',
  },
]

export function PainelAguarde({
  node, entradas, pontasSoltas, onRename, onPatchAguarde, onPrenderPontasSoltas, onDelete,
}: PainelAguardeProps) {
  const d = node.data as AguardeNodeData
  const isNew = !!d.isNew
  const cfg = d.aguarde ?? defaultAguarde()
  const esperaTudo = cfg.politica === 'todas_terminarem'

  return (
    <div className="flex flex-1 flex-col">
      {/* Cabeçalho do painel — o Excluir mora no topo direito (mesmo padrão
          nos painéis irmãos). */}
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-amber-500 text-white">
          <GitMerge size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">Aguarde (ponto de encontro)</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir aguarde
        </Button>
      </div>

      <div className="grid flex-1 gap-5 overflow-y-auto px-4 py-4 lg:grid-cols-2">
        {/* ── Coluna esquerda: identidade + o que ele está esperando ───────── */}
        <div className="flex flex-col gap-4">
          <NomeField
            id={node.id}
            name={d.name}
            isNew={isNew}
            placeholder="Ex.: Encontro_Cargas"
            onRename={onRename}
          />

          <div className="rounded-lg border border-edge bg-canvas/50 p-3">
            <p className="text-xs font-semibold text-ink">O que este nó faz</p>
            <p className="mt-1 text-[11px] leading-relaxed text-dim">
              Segura o fluxo até que <strong className="text-ink">todas</strong> as etapas
              ligadas a ele terminem. Só então o que vem depois começa.
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-dim">
              Ele espera <strong className="text-ink">apenas as etapas conectadas</strong> na
              entrada — o que não estiver ligado aqui não é esperado.
            </p>
          </div>

          {/* Contagem de entradas: é a única coisa que pode deixar o nó inútil
              sem que isso apareça no canvas. */}
          <div
            className={[
              'rounded-lg border p-3',
              entradas === 0
                ? 'border-red-300 bg-red-50 dark:border-red-900/60 dark:bg-red-950/30'
                : entradas === 1
                  ? 'border-amber-300 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30'
                  : 'border-edge bg-canvas/50',
            ].join(' ')}
          >
            <p className="text-xs font-semibold text-ink">
              {entradas === 0
                ? 'Nenhuma etapa ligada'
                : entradas === 1
                  ? '1 etapa ligada'
                  : `${entradas} etapas ligadas`}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-dim">
              {entradas === 0
                ? 'Sem entrada, ele não tem o que esperar — e o fluxo não salva.'
                : entradas === 1
                  ? 'Um ponto de encontro com uma perna só não junta nada. Ligue as outras.'
                  : 'Todas serão esperadas antes de liberar o que vem depois.'}
            </p>
            {pontasSoltas.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => onPrenderPontasSoltas(node.id)}
                title={`Liga aqui: ${pontasSoltas.join(', ')}`}
              >
                <Link2 size={13} />
                Prender {pontasSoltas.length === 1 ? 'a ponta solta' : `as ${pontasSoltas.length} pontas soltas`}
              </Button>
            )}
          </div>
        </div>

        {/* ── Coluna direita: a política ───────────────────────────────────── */}
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold text-ink">Quando uma das etapas falhar</p>

          {OPCOES.map(opt => {
            const ativa = cfg.politica === opt.valor
            return (
              <label
                key={opt.valor}
                className={[
                  'flex cursor-pointer gap-2.5 rounded-lg border p-3 transition-colors',
                  ativa
                    ? 'border-amber-400 bg-amber-50 dark:border-amber-600 dark:bg-amber-950/30'
                    : 'border-edge hover:border-dim/40',
                ].join(' ')}
              >
                <input
                  type="radio"
                  name={`politica-${node.id}`}
                  className="mt-0.5 shrink-0 accent-amber-500"
                  checked={ativa}
                  onChange={() => onPatchAguarde(node.id, { politica: opt.valor })}
                />
                <span className="min-w-0">
                  <span className="block text-xs font-semibold text-ink">{opt.titulo}</span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-dim">{opt.ajuda}</span>
                </span>
              </label>
            )
          })}

          {/* Aviso PERMANENTE na opção tolerante. Sem ele, "seguir mesmo com
              falha" é facilmente lido como "fazer o pipeline passar" — e é o
              contrário: a falha continua valendo. */}
          {esperaTudo && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/40">
              <p className="text-[11px] font-semibold text-amber-800 dark:text-amber-300">
                Isto não esconde a falha
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-amber-800/90 dark:text-amber-300/90">
                A etapa que falhou continua marcada como falha e o pipeline
                termina em erro. O que muda é só que o passo seguinte a este nó
                roda mesmo assim.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
