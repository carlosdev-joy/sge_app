import {
  estadoDaCorrida, estiloDiaAtipico, ESTILO_NAO_ABRIU,
} from './statusExecucao'
import type { CorridaApi, CorridaEsperadaApi } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// A pílula de ESTADO do ciclo — spec docs/spec-malha-execucao.md §9.3/§9.9.
//
// Uma superfície, três canais: cor, ÍCONE e RÓTULO. A regra da casa é que cor
// nunca é canal único (`SupervisaoCard.tsx:64-65`), e aqui ela vale duas vezes:
// os três desfechos vermelhos (`falhou`, `encerrada sem terminar`, `não chegou
// a começar`) têm ícones diferentes de propósito, e os dois âmbares
// (`fora do prazo` e `sem sinal`) só se distinguem por ícone e texto.
//
// POR QUE COMPONENTE, e não JSX solto no card: a mesma pílula aparece no card
// da lista, na faixa do painel (F10) e na linha do Dashboard (F11). Três cópias
// das mesmas classes é como um estado ganha cor diferente em duas telas — e
// "em andamento · com falha" azul numa delas é o card mentindo de novo.
//
// O componente NÃO decide o texto: quem decide é `estadoDaCorrida`, a mesma
// função que o `resumoCorrida` usa para montar o card. Uma fonte, duas
// superfícies (Decisão 75/#5).
// ─────────────────────────────────────────────────────────────────────────────

export interface CorridaBadgeProps {
  corrida: CorridaApi | null
  /** F9/Decisão 58 — quando a corrida que deveria existir NÃO existe, é este
   *  estado que a pílula anuncia, e ele ganha precedência sobre a corrida
   *  anterior: o que o operador precisa saber às 8h não é que ontem foi bem, é
   *  que hoje não começou. */
  esperada?: CorridaEsperadaApi | null
  tamanho?: 'sm' | 'md'
  /** F12/Decisão 68 — `SEM_TRABALHO` em DIA ATÍPICO: a pílula sobe para âmbar.
   *
   *  O rótulo e o ícone NÃO mudam (o fato é o mesmo: não houve trabalho hoje);
   *  o que muda é a cor, e quem carrega o segundo canal — a regra da casa de
   *  que cor nunca é canal único — é a frase que o chamador escreve ao lado
   *  ("as últimas 4 terças tiveram trabalho"). Por isso este prop é `boolean`
   *  e não um estilo pronto: quem decide é o `resumoCorrida`, uma vez só, e as
   *  duas superfícies pintam igual. */
  diaAtipico?: boolean
}

const TAMANHO = {
  sm: { pill: 'px-1.5 py-px text-[11px] gap-1', icone: 11, dot: 'h-1.5 w-1.5' },
  md: { pill: 'px-2 py-0.5 text-[12px] gap-1.5', icone: 13, dot: 'h-2 w-2' },
}

export function CorridaBadge({ corrida, esperada, tamanho = 'sm',
                               diaAtipico = false }: CorridaBadgeProps) {
  // Degradação por AUSÊNCIA (Decisão 41): sem corrida e sem previsão, esta
  // pílula não tem o que dizer — e quem escreve o fallback "(membro mais
  // recente)" é o CHAMADOR, que é quem tem o dado antigo em mãos.
  const base = esperada ? ESTILO_NAO_ABRIU : (corrida ? estadoDaCorrida(corrida) : null)
  const estilo = base && diaAtipico ? estiloDiaAtipico(base) : base
  if (!estilo) return null
  const t = TAMANHO[tamanho]
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border font-semibold ${t.pill} ${estilo.chip}`}
    >
      {/* O dot animado é semântico e escasso (Decisão 75/#13): só ABERTA. */}
      {estilo.animado && (
        <span className={`shrink-0 animate-pulse rounded-full ${t.dot} ${estilo.dot}`} />
      )}
      <estilo.Icone size={t.icone} className="shrink-0" aria-hidden="true" />
      <span className="truncate">{estilo.rotulo}</span>
    </span>
  )
}
