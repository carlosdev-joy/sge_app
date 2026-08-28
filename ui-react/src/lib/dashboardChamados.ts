// Cálculos do painel de chamados — os blocos e as contagens dos gráficos.
//
// A aritmética de PRAZO mora em `prazoChamados`: ela serve também ao kanban
// da Fila, e uma segunda cópia faria o mesmo chamado aparecer "vencido" numa
// aba e "no prazo" na outra.
//
// ⚠️ POR QUE ESTAS FUNÇÕES EXISTEM, E NÃO INLINE NO JSX
// Prazo é aritmética de data, e aritmética de data erra em silêncio: o cartão
// mostra "faltam 2 dias" para quem já venceu ontem e ninguém desconfia de um
// número plausível. Fora do componente, cada caso vira um teste.
//
// As formas são as da casa (`components/chamados/graficos`): barras
// horizontais para magnitude, com o valor em texto ao lado. A cor não carrega
// significado sozinha em lugar nenhum daqui.
//
// ⚠️ O QUE **NÃO** MORA AQUI
// Os grupos do painel (backlog, andamento, pendentes, vencidas…) vêm PRONTOS
// de `GET /chamados/dashboard`, com rótulo, cor, total e a lista. O painel que
// roda em produção recalcula tudo no cliente a partir de `GET /chamados` — e é
// dessa duplicação que nasce o painel discordando da fila ao lado. Uma regra
// só, no banco, já validada contra a tela (57 = 57 = 57 no dev).

import { dataDoPrazo, diasAteOPrazo } from './prazoChamados'

export interface ChamadoDoPainel {
  sys_id: string
  numero: string
  titulo: string | null
  atribuido_a: string | null
  estado_kanban: string
  prazo: string | null
  aberto_em: string | null
  url: string | null
  sla_vencido: boolean | null
  /** Quem pediu. Substituiu `tipo_demanda`, que repetia o título. */
  demandante: string | null
  atribuido_a_email: string | null
  // As duas datas do fim. No ServiceNow "Resolvido" ainda não é "Encerrado":
  // `encerrado_em` (closed_at) costuma vir vazio em chamado resolvido, e
  // `atualizado_em` é a última mudança — que, para um resolvido, é a
  // resolução, salvo comentário posterior.
  encerrado_em: string | null
  atualizado_em: string | null
}

export interface DataDoFim {
  data: string
  /** true = é `encerrado_em`; false = é a última atualização. */
  exata: boolean
}

/**
 * Quando o chamado saiu da fila, e o quanto disso é afirmação.
 *
 * Devolve também SE a data é a de encerramento ou a última atualização, porque
 * a tela precisa dizer qual está mostrando: chamar "atualizado em" de
 * "resolvido em" afirma uma data que pode não ser — bastou um comentário
 * depois da resolução para ela estar errada. E devolver `null` em vez do
 * fallback deixaria a coluna vazia justamente no cartão que existe para ser
 * conferido (dos 21 resolvidos no dev, ZERO tinham `encerrado_em`).
 */
export function dataDoFim(c: Pick<ChamadoDoPainel, 'encerrado_em' | 'atualizado_em'>): DataDoFim | null {
  const exata = dataDoPrazo(c.encerrado_em)
  if (exata) return { data: exata, exata: true }
  const aproximada = dataDoPrazo(c.atualizado_em)
  if (aproximada) return { data: aproximada, exata: false }
  return null
}

export interface BlocoDoPainel {
  label: string
  cor: string
  total: number
  chamados: ChamadoDoPainel[]
}

/** Um item de `BarrasHorizontais` — o formato da casa para magnitude. */
export interface ContagemRotulada {
  rotulo: string
  valor: number
}

/** Backlog por responsável: quem tem dono × quem ainda espera alguém pegar. */
export function contaPorResponsavel(lista: ChamadoDoPainel[]): ContagemRotulada[] {
  // `'   '` é sem responsável. Contá-lo como dono esconderia o backlog órfão,
  // que é justamente o que este gráfico existe para mostrar.
  const com = lista.filter(c => (c.atribuido_a || '').trim()).length
  return [
    { rotulo: 'com responsável', valor: com },
    { rotulo: 'sem responsável', valor: lista.length - com },
  ]
}

/**
 * Em andamento por prazo: dentro, sem prazo e fora.
 *
 * "Sem prazo" é categoria PRÓPRIA. Somada a "dentro do prazo", faria o gráfico
 * dizer que está tudo sob controle — quando na verdade ninguém combinou data.
 */
export function contaPorPrazo(lista: ChamadoDoPainel[],
                              hoje: Date = new Date()): ContagemRotulada[] {
  let dentro = 0, fora = 0, sem = 0
  for (const c of lista) {
    const dias = diasAteOPrazo(c.prazo, hoje)
    if (dias === null) sem++
    else if (dias > 0) fora++
    else dentro++
  }
  return [
    { rotulo: 'dentro do prazo', valor: dentro },
    { rotulo: 'sem prazo', valor: sem },
    { rotulo: 'fora do prazo', valor: fora },
  ]
}

/** Os blocos que a resposta traz, na ordem em que a tela os mostra. */
export const ORDEM_FILA = ['backlog', 'andamento', 'pendentes', 'resolvidas'] as const
export const ORDEM_PRAZO = ['vencem_hoje', 'vencem_semana', 'vencidas'] as const

/** Extrai um bloco da resposta, tolerando ausência. */
export function bloco(resposta: Record<string, unknown> | undefined,
                      chave: string): BlocoDoPainel | null {
  const b = resposta?.[chave]
  if (!b || typeof b !== 'object') return null
  const obj = b as Partial<BlocoDoPainel>
  if (typeof obj.total !== 'number') return null
  return {
    label: obj.label || chave,
    cor: obj.cor || 'neutral',
    total: obj.total,
    chamados: Array.isArray(obj.chamados) ? obj.chamados : [],
  }
}
