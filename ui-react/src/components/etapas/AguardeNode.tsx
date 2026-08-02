// Nó Aguarde do React Flow — o ponto de encontro entre pernas paralelas.
//
// Diferente dos demais nós (tile de ícone quadrado), este é desenhado como uma
// BARRA VERTICAL: numa esteira que corre da esquerda para a direita, a barra de
// sincronização é perpendicular ao fluxo — é assim que BPMN/UML desenham uma
// junção, e é o que faz o operador ler "aqui as pernas se encontram" sem
// precisar abrir o painel.
//
// Sobre a barra vai um MEDALHÃO com a ampulheta: a barra pura foi lida em
// produção como "ícone faltando", e a ampulheta é o símbolo que adere ao NOME
// do nó ("Aguarde") sem insinuar espera por horário — Clock/Timer insinuariam,
// e a spec descartou espera por tempo de propósito. O mesmo Hourglass aparece
// na paleta e no painel, para o nó não mudar de cara entre o arrasto e o canvas.
//
// Um target handle (entrada, à esquerda) e um source handle (saída, à direita),
// na altura do meio da barra. Várias arestas podem chegar no mesmo target — é
// justamente o ponto do nó.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Hourglass } from 'lucide-react'

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
// 14px de alvo (padrão de precisão que a Decisão já adota).
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// A barra tem 32px de altura (como o tile dos irmãos); handles no seu centro
// vertical (top: 16) — mesma altura dos nós vizinhos, sem degrau nas arestas.
const BAR_H = 32
const HANDLE_Y = BAR_H / 2

function AguardeNodeImpl({ data, selected }: NodeProps & { data: AguardeNodeData }) {
  const esperaTudo = data.aguarde?.politica === 'todas_terminarem'
  const pendente = !!(data as { pendente?: boolean }).pendente
  // Largura do invólucro = visual (medalhão/barra em w-8) + 8px de folga por
  // lado, só o bastante para o handle encostar no desenho; o RÓTULO transborda
  // de propósito (w-[128px] nos <p>). Feedback de produção: com o invólucro na
  // largura do rótulo, os handles ancoravam a ~48px do desenho e a aresta
  // "morria no nada" — lia como espaço desperdiçado.
  return (
    <div className="group flex w-12 flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Barra de sincronização (âmbar) — perpendicular ao fluxo — com o
          medalhão da ampulheta centrado nela. O medalhão tem borda na cor do
          painel para se destacar da barra nos dois temas.
          O invólucro tem a LARGURA do medalhão (w-8, como o tile dos irmãos) e
          é nele que moram o anel de seleção e o ponto de pendência: na barra
          (10px de largura), o medalhão cortava o anel em dois tocos. */}
      <div
        className={[
          'relative flex w-8 items-center justify-center rounded-full',
          // Anel sutil no hover do tema escuro — sombra não lê sobre canvas escuro.
          !selected ? 'dark:group-hover:ring-1 dark:group-hover:ring-slate-500/60' : '',
          // Tracejado = nó recém-arrastado, ainda não salvo (como nos irmãos).
          data.isNew && !selected ? 'outline-dashed outline-1 outline-offset-2 outline-blue-400/70' : '',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
        style={{ height: BAR_H }}
      >
        {/* Ponto de pendência que TODOS os irmãos têm — SÓ o ponto, sem o anel
            âmbar dos demais: âmbar sobre a barra âmbar não lê. */}
        {pendente && (
          <span
            className="absolute -right-1.5 -top-1.5 z-10 h-2.5 w-2.5 rounded-full border-2 border-panel bg-amber-400"
            title="Há pendências nesta etapa — veja o painel"
          />
        )}
        {/* amber-600 (não 500): o glifo branco precisa de 3:1 — WCAG 1.4.11. */}
        <div className="h-full w-2.5 rounded-full bg-amber-600 shadow-sm transition-shadow group-hover:shadow-md" />
        {/* Medalhão h-7/ícone 15 — antes h-6/13, o menor glifo do canvas;
            agora iguala o chip do painel. */}
        <div
          className={[
            'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
            'flex h-7 w-7 items-center justify-center rounded-full',
            'border-2 border-panel bg-amber-600 text-white shadow-sm',
          ].join(' ')}
        >
          <Hourglass size={15} strokeWidth={2.4} />
        </div>
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar.
          w-[128px] > invólucro (w-12): transborda centrado (flex items-center). */}
      <p
        className="mt-1.5 w-[128px] line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Política — muda o comportamento em caso de falha, então fica VISÍVEL
          no card em vez de escondida no painel. */}
      <p
        className={[
          'mt-0.5 w-[128px] line-clamp-1 text-center text-[9px] leading-tight',
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
