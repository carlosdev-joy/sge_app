// Os filtros e a ORDEM da fila do kanban — quem entra, quem some, quem vem
// primeiro.
//
// Fora da página porque é AQUI que mora a decisão, e dentro de
// `pages/Chamados.tsx` ela era inalcançável para teste (a página importa
// react-query). Filtro errado não quebra a tela: ele mostra menos, e "menos"
// é indistinguível de "é isso que existe" — o operador conclui que a fila
// esvaziou.

import { emCurso } from './prazoChamados'

/** O que os filtros precisam saber de um chamado. */
export interface ChamadoFiltravel {
  numero: string
  tipo: string
  titulo: string | null
  estado_origem: string | null
  atribuido_a: string | null
  prioridade: string | null
  categoria_diaadia: string
}

// Valores-sentinela. Precisam ser diferentes de "todos" (string vazia) e de
// qualquer valor real do banco: "sem responsável" é rótulo de tela, e o banco
// guarda NULL — um seletor que mandasse o rótulo não acharia ninguém.
export const SEM_ATRIBUICAO = '__sem_atribuicao__'
export const SEM_MARCACAO = '__sem_marcacao__'

// As duas categorias que a equipe marca nas work notes (`chamado_derivacoes`).
// Lista FECHADA: a derivação só produz estes dois valores, e um seletor
// alimentado pelo que o banco tem mostraria erro de digitação como se fosse
// opção legítima.
export const CATEGORIAS = [
  { valor: 'dia a dia', rotulo: 'Dia a dia' },
  { valor: 'iniciativa', rotulo: 'Iniciativa' },
] as const

export interface FiltrosKanban {
  busca: string
  tipo: string
  responsavel: string
  prioridade: string
  categoria: string
}

export const SEM_FILTRO: FiltrosKanban = {
  busca: '', tipo: '', responsavel: '', prioridade: '', categoria: '',
}

export function algumFiltroAtivo(f: FiltrosKanban): boolean {
  return !!(f.busca || f.tipo || f.responsavel || f.prioridade || f.categoria)
}

/**
 * Busca por texto: número, título, responsável e estado de origem.
 *
 * Por trecho e sem distinguir caixa — "RITM00" precisa achar, e é assim que se
 * procura na prática.
 */
export function casaBusca(c: ChamadoFiltravel, termo: string): boolean {
  const t = (termo || '').trim().toLowerCase()
  if (!t) return true
  return [c.numero, c.titulo, c.atribuido_a, c.estado_origem]
    .some(campo => (campo || '').toLowerCase().includes(t))
}

/**
 * Os tipos que o seletor oferece.
 *
 * ⚠️ Saem dos CARDS e SEM `task`. A tarefa não é um item da fila — ela é uma
 * linha dentro do card do pedido —, então "Tarefa" no seletor ofereceria um
 * recorte que a tela não representa.
 *
 * Consequência assumida: uma task ÓRFÃ (sem pai) vira card e deixa de ser
 * alcançável por este filtro. Ela continua na fila, no "todos" e na busca —
 * some do seletor, não da tela.
 */
export function tiposDisponiveis(cards: ChamadoFiltravel[]): string[] {
  return [...new Set(cards.map(c => c.tipo))]
    .filter(t => !!t && t !== 'task')
    .sort()
}

/**
 * Este card entra na fila filtrada?
 *
 * Dois grupos de regra, e a diferença entre eles é o que impede um resultado
 * absurdo:
 *
 *   - **linha** (busca, responsável, prioridade) casa contra o card OU
 *     qualquer tarefa dentro dele: o número da SCTASK está na tela, e o
 *     responsável que só aparece numa tarefa precisa ser filtrável;
 *   - **card** (tipo, categoria, sem atribuição) fala do card e só dele. O
 *     tipo de uma filha é sempre `task`, e a categoria mostrada no badge é a
 *     do card — casar pela filha produziria um card filtrado como
 *     "iniciativa" sem badge nenhum, e "sem atribuição" traria pedidos
 *     atribuídos que têm uma tarefa sem dono.
 */
export function casaFiltros(
  card: ChamadoFiltravel, filhas: ChamadoFiltravel[], f: FiltrosKanban,
): boolean {
  if (f.tipo && card.tipo !== f.tipo) return false

  if (f.categoria) {
    const marcada = (card.categoria_diaadia || '').trim()
    if (f.categoria === SEM_MARCACAO) {
      if (marcada) return false
    } else if (marcada !== f.categoria) {
      return false
    }
  }

  if (f.responsavel === SEM_ATRIBUICAO && (card.atribuido_a || '').trim()) {
    return false
  }

  const casaLinha = (c: ChamadoFiltravel) =>
    (!f.responsavel || f.responsavel === SEM_ATRIBUICAO
      || c.atribuido_a === f.responsavel)
    && (!f.prioridade || c.prioridade === f.prioridade)
    && casaBusca(c, f.busca)

  return casaLinha(card) || filhas.some(casaLinha)
}


// ── A ordem dentro da coluna ────────────────────────────────────────────────

/** O mínimo para decidir a ordem e o destaque. */
export interface ChamadoOrdenavel {
  tipo: string
  estado_kanban: string
}

/**
 * Este card recebe destaque de incidente?
 *
 * Incidente é interrupção: alguma coisa que funcionava parou. Ele compete por
 * atenção com pedidos de trabalho planejado, e no meio deles some.
 *
 * ⚠️ O destaque acaba quando o chamado termina. Alarme sobre trabalho FEITO
 * não pede ação nenhuma — e é o que ensina a ignorar os outros, inclusive os
 * que pedem. Mesma razão pela qual o rodapé cala idade e prazo no resolvido.
 */
export function destacaIncidente(c: ChamadoOrdenavel): boolean {
  return (c.tipo || '').trim() === 'incident' && emCurso(c.estado_kanban)
}

/**
 * A ordem dos cards dentro de uma coluna: incidentes em curso primeiro.
 *
 * Quem abre o kanban lê de cima para baixo e para quando acha o que procura —
 * um incidente na décima posição de uma coluna que rola é um incidente que
 * ninguém viu.
 *
 * A ordenação é ESTÁVEL (garantido pelo `sort` desde o ES2019): dentro de cada
 * grupo, a ordem que veio do servidor é preservada. Sem isso, dois cards
 * "iguais" trocariam de lugar entre renderizações e a fila dançaria sob o olho
 * de quem está lendo.
 *
 * Não recebe o nome da coluna de propósito: cada card carrega o próprio
 * `estado_kanban`, e conferir por card faz a regra continuar certa mesmo que
 * um dia a coluna passe a misturar estados.
 */
export function ordenarColuna<T extends ChamadoOrdenavel>(cards: T[]): T[] {
  return [...cards].sort(
    (a, b) => Number(destacaIncidente(b)) - Number(destacaIncidente(a)))
}
