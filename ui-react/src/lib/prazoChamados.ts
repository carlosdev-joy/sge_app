// Prazo e datas dos chamados — a aritmética que erra em silêncio.
//
// Vive fora das telas porque o erro aqui é sempre PLAUSÍVEL: o card mostra
// "faltam 2 dias" para quem venceu ontem, e ninguém desconfia de um número
// bem-formado. Fora do componente, cada caso vira um teste.
//
// Serve a DUAS telas — o kanban da Fila e o painel do Dashboard. Morava em
// `dashboardChamados` e saiu de lá quando o card do kanban passou a mostrar o
// prazo: duas cópias da mesma conta divergem no primeiro ajuste, e aí o mesmo
// chamado fica "vencido" numa aba e "no prazo" na outra.

/** Meia-noite local — o dia é a unidade, não o instante. */
function meiaNoite(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/**
 * Dias entre hoje e o prazo. Positivo = atrasado, 0 = vence hoje.
 *
 * Compara DIAS, não milissegundos: um prazo às 09:00 de hoje não está
 * "atrasado" às 14:00 — vence hoje, e é isso que o operador precisa ler.
 * `null` quando não há prazo ou a data não é interpretável: inventar 0 aqui
 * pintaria de laranja tudo que não tem prazo.
 */
export function diasAteOPrazo(prazo: string | null | undefined,
                              hoje: Date = new Date()): number | null {
  if (!prazo) return null
  const d = new Date(prazo.length <= 10 ? `${prazo}T00:00:00` : prazo)
  if (Number.isNaN(d.getTime())) return null
  const MS_DIA = 86_400_000
  return Math.round((meiaNoite(hoje).getTime() - meiaNoite(d).getTime()) / MS_DIA)
}

/**
 * A data do prazo em dd/mm/aaaa. `null` quando não há prazo ou não dá para ler.
 *
 * Formatada aqui, e não com `toLocaleDateString`, por dois motivos: o resultado
 * do `toLocale` muda com a máquina de quem abre a tela — e uma tela que mostra
 * 08/28/2026 para um e 28/08/2026 para outro não serve para conferir prazo —
 * e porque a API manda "2026-08-28 11:43:30", que o `new Date` de alguns
 * navegadores lê como UTC e devolve o DIA ANTERIOR à noite.
 *
 * Por isso a leitura é textual: os dez primeiros caracteres são a data, e é
 * só o que interessa. Hora de vencimento não muda o dia em que vence.
 */
export function dataDoPrazo(prazo: string | null | undefined): string | null {
  if (!prazo) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(prazo.trim())
  if (!m) return null
  return `${m[3]}/${m[2]}/${m[1]}`
}


export interface RotuloPrazo {
  texto: string
  tom: 'atrasado' | 'hoje' | 'no prazo'
}

/**
 * O prazo em palavras. `null` = sem prazo, e a tela cala em vez de inventar.
 *
 * O texto carrega o significado: cor sozinha não informa quem não distingue
 * cores, nem sobrevive a uma impressão em preto e branco.
 */
export function rotuloDoPrazo(prazo: string | null | undefined,
                              hoje: Date = new Date()): RotuloPrazo | null {
  const dias = diasAteOPrazo(prazo, hoje)
  if (dias === null) return null
  if (dias > 0) return { texto: `${dias}d de atraso`, tom: 'atrasado' }
  if (dias === 0) return { texto: 'vence hoje', tom: 'hoje' }
  return { texto: `faltam ${Math.abs(dias)}d`, tom: 'no prazo' }
}

/**
 * Chamado finalizado não mostra prazo nem idade.
 *
 * "Vencido há 40 dias" num chamado resolvido é ruído que ensina a ignorar o
 * aviso — e o aviso existe para o que ainda dá para fazer algo.
 */
export function mostraPrazo(estadoKanban: string): boolean {
  return emCurso(estadoKanban)
}

/** As colunas em que o chamado JÁ TERMINOU. */
export const ESTADOS_TERMINAIS = ['resolvido', 'encerrado'] as const

/**
 * O chamado ainda está em curso?
 *
 * ⚠️ Fonte ÚNICA da pergunta "isto ainda espera alguma coisa?". Ela decide
 * coisas diferentes em lugares diferentes — se o card mostra prazo e idade, se
 * o incidente sobe para o topo da coluna, se ele fica destacado — e uma
 * segunda lista de estados terminais à mão significaria um lugar parando de
 * alertar enquanto o outro continua, sem nada na tela denunciando.
 */
export function emCurso(estadoKanban: string): boolean {
  return !ESTADOS_TERMINAIS.includes(
    (estadoKanban || '').trim() as typeof ESTADOS_TERMINAIS[number])
}
