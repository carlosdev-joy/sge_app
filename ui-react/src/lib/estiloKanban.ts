// A aparência do quadro: a superfície do card e o tom de cada raia.
//
// Fora do componente porque aqui houve um DEFEITO de token, e defeito de token
// não aparece em teste de comportamento — a tela renderiza, os dados estão
// certos, e o card simplesmente não se distingue do fundo.

/** As colunas do kanban e o ponto colorido de cada raia. */
export const TOM_COLUNA: Record<string, string> = {
  novo: 'bg-blue-500',
  andamento: 'bg-amber-500',
  aguardando: 'bg-violet-500',
  resolvido: 'bg-emerald-500',
  outros: 'bg-slate-400',
}

/** O tom de uma coluna, com queda para o neutro. */
export function tomDaColuna(coluna: string): string {
  return TOM_COLUNA[coluna] ?? 'bg-slate-400'
}

/**
 * As classes do card do kanban.
 *
 * ⚠️ `bg-panel`, NUNCA `bg-canvas`.
 *
 * O card vinha pintado com `bg-canvas` — que é o token do **fundo da página**
 * (`--canvas`), não o de superfície. O resultado é literal: o cartão tinha
 * exatamente a mesma cor do que estava atrás dele, e o que separava um card do
 * outro era uma borda de 1px. Daí a leitura de "quadrados jogados" — eram
 * contornos, não superfícies.
 *
 * `--panel` é o token de superfície da casa (branco no tema claro), o mesmo que
 * `Painel`, o `Dashboard` e os modais usam. A distinção é invisível em código
 * (as duas classes existem, as duas compilam) e óbvia na tela.
 */
export function classeDoCard(urgente: boolean): string {
  return [
    'group relative rounded-lg bg-panel p-3 pl-3.5 flex flex-col gap-2',
    'border shadow-sm transition-shadow hover:shadow-md',
    urgente ? 'border-red-200 dark:border-red-900/70' : 'border-edge',
  ].join(' ')
}

/**
 * A raia onde os cards ficam.
 *
 * REBAIXADA — mais escura que a superfície do card, não mais clara. É o que faz
 * o card parecer estar SOBRE a raia; uma raia clara sob card claro voltaria a
 * depender só das bordas, que é o problema que esta mudança corrige.
 */
export const CLASSE_RAIA =
  'flex flex-col min-w-0 rounded-xl border border-edge bg-black/[0.03] dark:bg-black/25'

// ── Quais raias aparecem, e em que grade ───────────────────────────────────

/**
 * A coluna que recolhe o que não se encaixou.
 *
 * Ela existe porque o mapa de estados do ServiceNow é FECHADO: um estado que o
 * mapa não conhece cai aqui em vez de sumir da fila. É uma coluna de anomalia,
 * não uma etapa do trabalho.
 */
export const COLUNA_ANOMALIA = 'outros'

/**
 * As raias que o quadro desenha.
 *
 * "Outros" só aparece quando tem card. As outras quatro são ETAPAS — a fila
 * passa por elas, e uma coluna "Em andamento" vazia é informação (ninguém
 * pegou nada). "Outros" vazia não informa nada: ela é a ausência de anomalia,
 * que é o estado normal. Mantida sempre visível, ela cobrava um quinto da
 * largura da tela para dizer "nenhum" o tempo todo.
 *
 * ⚠️ A conta é sobre o que está VISÍVEL (já filtrado), e não sobre a fila
 * inteira: uma raia vazia por causa do filtro do usuário é uma raia sem nada
 * para mostrar — mesma situação. O usuário sabe que filtrou; foi ele quem o fez.
 */
export function raiasVisiveis(
  colunas: string[], quantosEm: (coluna: string) => number,
): string[] {
  return colunas.filter(
    col => col !== COLUNA_ANOMALIA || quantosEm(col) > 0)
}

// As grades possíveis, ESCRITAS POR EXTENSO. O Tailwind varre o fonte à
// procura das classes que usa: `xl:grid-cols-${n}` seria montado só em tempo
// de execução, não estaria no CSS gerado, e a grade simplesmente não
// aconteceria — sem erro nenhum, com o quadro virando uma coluna só.
const GRADE: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4',
  5: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-5',
  6: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-6',
}

/** A grade para N raias. Fora da faixa conhecida, cai na de 5. */
export function classeDaGrade(quantas: number): string {
  return `grid gap-3 ${GRADE[quantas] ?? GRADE[5]}`
}
