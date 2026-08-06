import type { CSSProperties } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Barra de progresso SEGMENTADA e acessível — spec docs/spec-malha-execucao.md
// §9.9 (Decisão 71) e §9.11 (Decisão 75).
//
// POR QUE ELA EXISTE, e por que agora:
//   • havia QUATRO barras ad-hoc no produto (CopiaProgressoModal, Dashboard,
//     PlanosAjuste, Admin) e NENHUMA delas tem `role="progressbar"`,
//     `aria-valuenow` ou `aria-label` — para quem usa leitor de tela as quatro
//     simplesmente não existem: o leitor anuncia uma `div` vazia;
//   • nenhuma delas é segmentada, e a camada de corrida da malha precisa de
//     uma barra com três tratamentos ao mesmo tempo (feito · rodando · não
//     roda hoje) sobre um denominador que NÃO encolhe (Decisão 52).
//
// O QUE ELA DELIBERADAMENTE NÃO TEM (Decisão 71 — modo sem chamador é código
// que nasce sem teste):
//   • modo INDETERMINADO — quem precisa dele hoje é só o CopiaProgressoModal,
//     que fica onde está;
//   • modo `total === 0` — na camada de corrida a barra só é renderizada com
//     `membros_total > 0`; `SEM_TRABALHO` não desenha barra nenhuma (Decisão
//     57). Há uma GUARDA aritmética contra divisão por zero mais abaixo, mas
//     guarda contra NaN não é modo: ela não muda o que a tela diz.
// ─────────────────────────────────────────────────────────────────────────────

export interface SegmentoProgresso {
  /** 'ok' | 'vivo' | 'dispensado' — chave de React e prefixo do texto acessível. */
  chave: string
  valor: number
  /** Classe Tailwind de preenchimento; par claro+escuro obrigatório (docs/ui-temas-cores.md). */
  cor: string
  /** pt-BR — alimenta o `title` do segmento E o texto que o leitor de tela lê. */
  rotulo: string
  /** Só o segmento "vivo" anima (Decisão 75: `animate-pulse` semântico e escasso). */
  animado?: boolean
  /** Trilho hachurado neutro — hachura significa UMA coisa: "não roda hoje" (§9.15/16). */
  hachurado?: boolean
}

export interface ProgressProps {
  /** Renderizados na ORDEM do array — o componente nunca reordena (§9.2). */
  segmentos: SegmentoProgresso[]
  /** Denominador. Na corrida é sempre `membros_total` do snapshot (Decisão 52). */
  total: number
  /**
   * O número que a barra ANUNCIA (`aria-valuenow`) — o mesmo `x` do `x de y`
   * escrito ao lado. É prop EXPLÍCITA, e não a soma dos segmentos, porque a
   * soma diria "7 de 7" numa corrida com 4 prontos, 2 rodando e 1 dispensado:
   * o leitor de tela contaria uma história que a tela não conta.
   */
  valorAtual: number
  /** Nome acessível, em pt-BR. Obrigatório (Decisão 75). */
  ariaLabel: string
  /**
   * Texto do VALOR (`aria-valuetext`). Sem ele o leitor de tela converte
   * valuenow/valuemax em PERCENTUAL por conta própria — e "4 de 7" viraria
   * "57%", que é exatamente o percentual de contagem que a Decisão 56 proíbe
   * em toda superfície. O default é montado a partir dos rótulos, e nunca
   * produz "%".
   */
  valorTexto?: string
  /** xs = card (h-1.5) · sm = painel (h-2.5). */
  altura?: 'xs' | 'sm'
  /** Largura/margem do trilho quando o chamador precisa limitá-lo. */
  className?: string
}

const ALTURA: Record<'xs' | 'sm', string> = { xs: 'h-1.5', sm: 'h-2.5' }

// Hachura do trilho "não roda hoje". Vai em `style` porque o Tailwind não
// gera gradiente repetido; o slate translúcido foi escolhido por LEGIBILIDADE
// nos dois temas — sobre `bg-edge` claro e escuro ele continua sendo textura,
// nunca uma quinta cor (§9.15/14: nada de `bg-{hue}-900/20` como base).
const HACHURA: CSSProperties = {
  backgroundImage:
    'repeating-linear-gradient(135deg, rgb(148 163 184 / 0.55) 0 3px, transparent 3px 6px)',
}

/**
 * Barra segmentada com `role="progressbar"`.
 *
 * A barra responde UMA coisa: quanto já ficou pronto (Decisão 54). O que
 * travou não entra nela — vira chip vermelho ao lado, no chamador.
 */
export function Progress({
  segmentos,
  total,
  valorAtual,
  ariaLabel,
  valorTexto,
  altura = 'xs',
  className = '',
}: ProgressProps) {
  // Guarda contra NaN: `total <= 0` não é um modo com texto próprio, é uma
  // divisão que não pode acontecer. Sem denominador, o trilho fica vazio.
  const pctDe = (v: number) => (total > 0 ? Math.max(0, Math.min(100, (v / total) * 100)) : 0)

  // O `x de y` vem PRIMEIRO, como na tela: ele é o número primário (Decisão
  // 56), e o detalhe por segmento vem depois. Nenhuma das duas metades pode
  // produzir "%".
  const texto =
    valorTexto ??
    `${valorAtual} de ${total} — ${segmentos.map((s) => `${s.valor} ${s.rotulo}`).join(', ')}`

  return (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={valorAtual}
      aria-valuetext={texto}
      className={`flex ${ALTURA[altura]} w-full overflow-hidden rounded-full bg-edge/60 ${className}`.trim()}
    >
      {segmentos.map((s) => (
        <div
          key={s.chave}
          // aria-hidden: o segmento é pedaço de desenho. Quem fala pelo
          // conjunto é o `aria-valuetext` acima — sem isto o leitor recitaria
          // fragmentos soltos dentro de um progressbar.
          aria-hidden="true"
          title={`${s.valor} ${s.rotulo}`}
          style={{ width: `${pctDe(s.valor)}%`, ...(s.hachurado ? HACHURA : null) }}
          className={`${ALTURA[altura]} transition-all duration-500 ${s.hachurado ? 'bg-edge' : s.cor} ${s.animado ? 'animate-pulse' : ''}`.trim()}
        />
      ))}
    </div>
  )
}
